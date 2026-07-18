"""M33 — External verification runner (offline deterministic + optional live).

Offline verification is fixture-backed, requires no network, and records a
fixture-backed ``SIMULATION_VERIFIED`` external state. Live verification is
operator-triggered ONLY (explicit acks + strict call budget + deadline + response
limit), never runs at import time, never runs in the standard test suite, never
activates rollout, and never grants write authority. A failure never becomes a
false success. The maximum recordable live state is
``EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS``.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Callable, Optional

from saathi.connectors.providers.config import ProviderConfig, RetryPolicy, TimeoutPolicy
from saathi.connectors.providers.external.adapters.github_meta import GithubMetaAdapter
from saathi.connectors.providers.external.fixtures import fixture_body_bytes, fixture_path
from saathi.connectors.providers.external.models import (
    ExternalProviderProfile,
    ExternalVerificationState,
    M33_ALLOWED_METHODS,
    M33_DEFAULT_CALL_BUDGET,
    M33_MAX_CALL_BUDGET,
    validate_external_profile,
)
from saathi.connectors.providers.external.profiles import (
    GITHUB_META_SCHEMA,
    resolve_external_profile,
    schema_for,
)
from saathi.connectors.providers.external.testkit import fixture_sender, make_transport
from saathi.connectors.providers.external.transport import ExternalTransport, urllib_sender
from saathi.connectors.providers.external.verification import (
    ExternalVerificationStore,
    compute_external_fingerprint,
)
from saathi.connectors.providers.models import (
    ExecutionMode,
    ProviderExecutionContext,
    ProviderSideEffectClass,
)
from saathi.connectors.providers.quarantine import ProviderQuarantineStore
from saathi.connectors.providers.runtime import ProviderExecutionRuntime

NON_PRODUCTION_LABEL = "EXTERNAL READ-ONLY SHADOW VERIFICATION — NOT PRODUCTION AUTHORITY"
# Live verification is disabled by default; the operator opts in explicitly.
ENV_ENABLE_FLAG = "SAATHI_M33_EXTERNAL_VERIFY_ENABLED"


def fixture_hash_for(provider_id: str, name: str = "get_meta.success") -> str:
    p = fixture_path(provider_id, name)
    if not p.is_file():
        return "missing"
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _external_config(profile: ExternalProviderProfile, *, max_retries: int = 0) -> ProviderConfig:
    return ProviderConfig(
        provider_id=profile.provider_id,
        environment=profile.environment,
        endpoint_reference=profile.endpoint_reference,
        timeout_policy=TimeoutPolicy(total_deadline=float(profile.deadline_seconds)),
        retry_policy=RetryPolicy(max_retries=max_retries),
        auth_profile=profile.auth_profile,
        response_size_limit=int(profile.response_limit_bytes),
        allowed_operations=tuple(profile.operation_set),
        data_classification=profile.data_classification,
        side_effect_class=profile.side_effect_class,
    )


def offline_transport(provider_id: str) -> ExternalTransport:
    """Fixture-backed transport — deterministic, no network."""
    body = fixture_body_bytes(provider_id)
    headers = {
        "content-type": "application/json",
        "x-ratelimit-limit": "60",
        "x-ratelimit-remaining": "59",
        "x-github-request-id": "OFFLINE-DETERMINISTIC",
    }
    return make_transport(sender=fixture_sender(body_bytes=body, headers=headers))


def _run_once(
    profile: ExternalProviderProfile,
    transport: ExternalTransport,
    *,
    mode: str = ExecutionMode.SHADOW.value,
    max_retries: int = 0,
) -> Any:
    """Drive one governed call through the M32 runtime → external adapter → transport."""
    adapter = GithubMetaAdapter(profile=profile, schema=schema_for(profile.provider_id), transport=transport)
    config = _external_config(profile, max_retries=max_retries)
    adapter.prepare(config)
    runtime = ProviderExecutionRuntime()
    ctx = ProviderExecutionContext(
        connector_id=profile.connector_id,
        provider_id=profile.provider_id,
        operation=profile.operation,
        request_id="external-verify",
        payload={},
        mode=mode,
    )
    return runtime.execute(adapter, ctx, config)


def run_offline_verification(
    provider_id: str = "github_meta",
    *,
    store: Optional[ExternalVerificationStore] = None,
    record: bool = True,
    evidence_dir: str = "docs/evidence/m33",
) -> dict[str, Any]:
    """Fixture-backed offline verification. Records SIMULATION_VERIFIED external state."""
    profile = resolve_external_profile(provider_id)
    res = _run_once(profile, offline_transport(provider_id))
    fp = compute_external_fingerprint(
        profile=profile, schema=schema_for(provider_id), fixture_hash=fixture_hash_for(provider_id),
    )
    st = store or ExternalVerificationStore()
    ok = bool(res.ok)
    if record:
        state = (
            ExternalVerificationState.SIMULATION_VERIFIED.value if ok
            else ExternalVerificationState.EXTERNAL_VERIFICATION_FAILED.value
        )
        st.record_verification(
            provider_id, state=state, fingerprint=fp,
            limitations=["offline_fixture_backed", "no_live_call", "single_endpoint_only"],
            evidence_dir=evidence_dir, verified_at=str(int(st.clock())), live_call_count=0, mode="OFFLINE",
        )
    return {
        "provider_id": provider_id,
        "ok": ok,
        "status": res.status,
        "fingerprint": fp,
        "schema_result": (res.safe_metadata or {}).get("schema_result", {}),
        "mode": "OFFLINE",
        "label": NON_PRODUCTION_LABEL,
        "live_call": False,
    }


def plan_external_verification(
    provider_id: str,
    *,
    ack_read_only: bool,
    ack_network: bool,
    call_budget: int = M33_DEFAULT_CALL_BUDGET,
    quarantined: Optional[bool] = None,
) -> dict[str, Any]:
    """Build a live-verification plan. Fails closed on any missing precondition."""
    blockers: list[str] = []
    if not ack_read_only:
        blockers.append("missing_ack_read_only")
    if not ack_network:
        blockers.append("missing_ack_network")

    profile: Optional[ExternalProviderProfile] = None
    try:
        profile = resolve_external_profile(provider_id)
        validate_external_profile(profile)
    except Exception as e:
        blockers.append(f"provider_invalid:{type(e).__name__}")

    if profile is not None:
        if (profile.method or "").upper() not in M33_ALLOWED_METHODS:
            blockers.append(f"write_method_blocked:{profile.method}")
        if profile.side_effect_class not in (
            ProviderSideEffectClass.NONE.value, ProviderSideEffectClass.READ_ONLY.value,
        ):
            blockers.append("side_effect_blocked")
        if (profile.auth_profile or "none").lower() not in ("none", "public", "sandbox_none"):
            blockers.append("unapproved_credential_blocked")

    q = quarantined
    if q is None and profile is not None:
        q = ProviderQuarantineStore().is_quarantined(provider_id)
    if q:
        blockers.append("provider_quarantined")

    budget = max(1, min(int(call_budget), M33_MAX_CALL_BUDGET))
    return {
        "schema": "m33.external_verification_plan.v1",
        "provider_id": provider_id,
        "allowed": not blockers,
        "blockers": blockers,
        "call_budget": budget,
        "mode": "SHADOW",
        "operation": profile.operation if profile else "",
        "method": profile.method if profile else "",
        "deadline_seconds": profile.deadline_seconds if profile else 0.0,
        "response_limit_bytes": profile.response_limit_bytes if profile else 0,
        "rollout": "OFF (unchanged by verification)",
        "label": NON_PRODUCTION_LABEL,
        "privacy_safe": True,
    }


def run_live_verification(
    provider_id: str,
    *,
    ack_read_only: bool,
    ack_network: bool,
    call_budget: int = M33_DEFAULT_CALL_BUDGET,
    store: Optional[ExternalVerificationStore] = None,
    transport: Optional[ExternalTransport] = None,
    enabled: Optional[bool] = None,
    record: bool = True,
) -> dict[str, Any]:
    """Operator-triggered bounded live verification. Never auto-runs; fails closed.

    ``transport`` is injected by tests; when None, a hardened live urllib transport
    is constructed. ``enabled`` defaults to the env opt-in flag (disabled → aborted).
    """
    if enabled is None:
        enabled = os.environ.get(ENV_ENABLE_FLAG, "").strip().lower() in ("1", "true", "yes")

    plan = plan_external_verification(
        provider_id, ack_read_only=ack_read_only, ack_network=ack_network, call_budget=call_budget,
    )
    base = {
        "schema": "m33.external_verification_result.v1",
        "provider_id": provider_id,
        "mode": "SHADOW",
        "operation": plan.get("operation", ""),
        "live_call": False,
        "label": NON_PRODUCTION_LABEL,
        "privacy_safe": True,
    }

    if not enabled:
        return {**base, "ok": False, "success_or_failure": "aborted", "reason": "external_verification_disabled",
                "verification_state": ExternalVerificationState.UNVERIFIED.value, "blockers": ["disabled"]}
    if not plan["allowed"]:
        return {**base, "ok": False, "success_or_failure": "blocked", "reason": "plan_blocked",
                "verification_state": ExternalVerificationState.UNVERIFIED.value, "blockers": plan["blockers"]}

    profile = resolve_external_profile(provider_id)
    tr = transport if transport is not None else ExternalTransport(sender=urllib_sender)
    res = _run_once(profile, tr, mode=ExecutionMode.SHADOW.value, max_retries=0)
    fp = compute_external_fingerprint(
        profile=profile, schema=schema_for(provider_id), fixture_hash=fixture_hash_for(provider_id),
    )
    st = store or ExternalVerificationStore()
    ok = bool(res.ok)
    schema_result = (res.safe_metadata or {}).get("schema_result", {})
    state = (
        ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS.value if ok
        else ExternalVerificationState.EXTERNAL_VERIFICATION_FAILED.value
    )
    if record:
        st.record_verification(
            provider_id, state=state, fingerprint=fp,
            limitations=[
                "external_read_only", "single_endpoint_only", "non_production",
                "no_write_authority", "no_account_link", "no_credential",
            ],
            evidence_dir="docs/evidence/m33", verified_at=str(int(st.clock())),
            live_call_count=1, mode="SHADOW",
        )
    return {
        **base,
        "live_call": True,
        "ok": ok,
        "success_or_failure": "success" if ok else "failure",
        "status": res.status,
        "status_class": (res.safe_metadata or {}).get("status_code", res.status),
        "latency_bucket": _latency_bucket(res.latency_ms),
        "response_size_bucket": _size_bucket((res.safe_metadata or {}).get("status_code")),
        "schema_result": schema_result,
        "rate_limit_summary": res.rate_limit or {},
        "verification_state": state,
        "limitations": res.limitations,
        "call_budget": plan["call_budget"],
    }


def _latency_bucket(ms: float) -> str:
    ms = float(ms or 0)
    if ms < 100:
        return "<100ms"
    if ms < 500:
        return "100-500ms"
    if ms < 2000:
        return "500-2000ms"
    return ">2000ms"


def _size_bucket(_: Any) -> str:
    return "small(<64KiB)"
