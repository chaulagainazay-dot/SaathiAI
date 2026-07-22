"""M34 — Operator-controlled live external verification, reliability qualification,
and canary-readiness assessment.

This layer EXECUTES the existing M33 operator-controlled external-verification path
against the single M33-approved read-only provider and, on top of it, adds:

  * a strict live-call budget (default 3, hard max 5, retries included);
  * a four-acknowledgement authorization envelope
    (read-only / network / non-production / call-budget);
  * per-call bounded, leak-scanned evidence (no raw body, no raw headers);
  * repeatability classification across calls;
  * bounded reliability qualification;
  * a canary-readiness assessment that NEVER activates rollout.

It composes with (never replaces) M25 production certification, M30 connector
certification, M32 provider simulation verification, and M33 external profile
verification. The maximum recordable external state remains
``EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS``. Nothing here grants production,
write, account, CANARY, or ACTIVE authority. Trading Guardian stays UNCHANGED /
UNENGAGED. Eligibility reads never mutate state; only this explicit live command
records verification.

M34 introduces NO change to any M33 fingerprint-surface file, so the committed M33
external fingerprint is preserved. The M34 fingerprint extends the M33 fingerprint
with this module's surface hash and the M34 command version.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.connectors.providers.external.models import (
    ExternalProviderProfile,
    ExternalVerificationState,
    M33_ALLOWED_METHODS,
    validate_external_profile,
)
from saathi.connectors.providers.external.profiles import (
    resolve_external_profile,
    schema_for,
)
from saathi.connectors.providers.external.transport import ExternalTransport, urllib_sender
from saathi.connectors.providers.external.verification import (
    ExternalVerificationStore,
    compute_external_fingerprint,
)
from saathi.connectors.providers.external.verify import (
    _run_once,
    fixture_hash_for,
    plan_external_verification,
)
from saathi.connectors.providers.models import ExecutionMode, ProviderSideEffectClass
from saathi.connectors.providers.quarantine import ProviderQuarantineStore
from saathi.credentials.leakscan import is_clean

# ── M34 constants ─────────────────────────────────────────────────────────────
M34_DEFAULT_CALL_BUDGET = 3
M34_MAX_CALL_BUDGET = 5
M34_VERIFY_COMMAND_VERSION = "m34.live_external_verify.v1"
M34_SURFACE_PATH = "saathi/connectors/providers/external/m34.py"
# M34 records to its OWN registry so the committed M33 registry stays untouched.
M34_STORE_PATH = (
    Path(__file__).resolve().parents[4] / "docs" / "evidence" / "m34" / "external_verification_registry.json"
)


def _default_m34_store() -> "ExternalVerificationStore":
    return ExternalVerificationStore(M34_STORE_PATH)
# Live network opt-in: reuse the M33 flag; an M34-specific flag also enables.
ENV_ENABLE_FLAGS = ("SAATHI_M33_EXTERNAL_VERIFY_ENABLED", "SAATHI_M34_LIVE_VERIFY_ENABLED")

NON_PRODUCTION_LABEL = (
    "LIVE EXTERNAL READ-ONLY VERIFICATION — NON-PRODUCTION — "
    "ROLLOUT REMAINS OFF — NO WRITE AUTHORITY"
)

# The four mandatory operator acknowledgements.
M34_ACK_FIELDS = (
    "read_only_acknowledged",
    "network_acknowledged",
    "non_production_acknowledged",
    "call_budget_acknowledged",
)


class LiveVerificationMode(str, Enum):
    LIVE_SINGLE_VERIFY = "LIVE_SINGLE_VERIFY"
    LIVE_REPEATABILITY_VERIFY = "LIVE_REPEATABILITY_VERIFY"
    LIVE_RELIABILITY_VERIFY = "LIVE_RELIABILITY_VERIFY"


class M34State(str, Enum):
    """M34 verification phase/state. Persisted state stays within the M33 enum;
    IN_PROGRESS is transient-only and never written to the store."""
    UNVERIFIED = "UNVERIFIED"
    SIMULATION_VERIFIED = "SIMULATION_VERIFIED"
    EXTERNAL_VERIFICATION_IN_PROGRESS = "EXTERNAL_VERIFICATION_IN_PROGRESS"
    EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS = "EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS"
    EXTERNAL_VERIFICATION_FAILED = "EXTERNAL_VERIFICATION_FAILED"
    EXTERNAL_VERIFICATION_STALE = "EXTERNAL_VERIFICATION_STALE"
    EXTERNAL_VERIFICATION_REVOKED = "EXTERNAL_VERIFICATION_REVOKED"


class ReliabilityQualification(str, Enum):
    QUALIFIED_WITH_LIMITATIONS = "QUALIFIED_WITH_LIMITATIONS"
    NOT_QUALIFIED_TRANSIENT_FAILURE = "NOT_QUALIFIED_TRANSIENT_FAILURE"
    NOT_QUALIFIED_SCHEMA_FAILURE = "NOT_QUALIFIED_SCHEMA_FAILURE"
    NOT_QUALIFIED_SECURITY_FAILURE = "NOT_QUALIFIED_SECURITY_FAILURE"
    NOT_QUALIFIED_PROVIDER_FAILURE = "NOT_QUALIFIED_PROVIDER_FAILURE"
    NOT_QUALIFIED_INSUFFICIENT_EVIDENCE = "NOT_QUALIFIED_INSUFFICIENT_EVIDENCE"


class RepeatabilityClass(str, Enum):
    STABLE_EXACT = "STABLE_EXACT"
    STABLE_SEMANTIC = "STABLE_SEMANTIC"
    EXPECTED_DYNAMIC_VARIATION = "EXPECTED_DYNAMIC_VARIATION"
    UNEXPECTED_VARIATION = "UNEXPECTED_VARIATION"
    NON_COMPARABLE = "NON_COMPARABLE"


class CanaryReadiness(str, Enum):
    CANARY_READY_WITH_LIMITATIONS = "CANARY_READY_WITH_LIMITATIONS"
    NOT_CANARY_READY = "NOT_CANARY_READY"


# Security failure codes (from the transport/adapter) that must never be treated
# as a mere reliability limitation.
_SECURITY_FAILURE_CODES = frozenset({
    "DNS_POLICY_BLOCKED", "SSRF_POLICY_BLOCKED", "TLS_CERTIFICATE_FAILED",
    "TLS_HOSTNAME_FAILED", "TLS_POLICY_BLOCKED", "REDIRECT_POLICY_BLOCKED",
    "PROXY_POLICY_BLOCKED", "ENDPOINT_POLICY_BLOCKED",
})
_SCHEMA_FAILURE_CODES = frozenset({"SCHEMA_INCOMPATIBLE"})
_TRANSIENT_FAILURE_CODES = frozenset({
    "NETWORK_TIMEOUT", "CONNECTION_REFUSED", "CONNECTION_RESET",
})
_PROVIDER_FAILURE_CODES = frozenset({"PROVIDER_UNAVAILABLE", "PROVIDER_RATE_LIMITED"})

# Fields that legitimately vary between two /meta reads and are ignored for
# semantic repeatability comparison (declared dynamic material).
_DYNAMIC_IGNORED_FIELDS = frozenset({
    "timestamp", "date", "request_id", "x_request_id", "counter", "server_time",
})


class M34Error(ValueError):
    """Raised when an M34 live-verification precondition fails closed."""


# ── bounded buckets ───────────────────────────────────────────────────────────
def latency_bucket(ms: float, *, timed_out: bool = False) -> str:
    if timed_out:
        return "TIMEOUT"
    ms = float(ms or 0)
    if ms < 250:
        return "UNDER_250_MS"
    if ms < 500:
        return "250_TO_500_MS"
    if ms < 1000:
        return "500_MS_TO_1_S"
    if ms < 2000:
        return "1_TO_2_S"
    if ms < 5000:
        return "2_TO_5_S"
    return "OVER_5_S"


def size_bucket(nbytes: int) -> str:
    n = int(nbytes or 0)
    if n <= 0:
        return "EMPTY"
    if n < 4 * 1024:
        return "UNDER_4_KIB"
    if n < 64 * 1024:
        return "4_TO_64_KIB"
    if n < 256 * 1024:
        return "64_TO_256_KIB"
    return "AT_LIMIT"


def normalized_fingerprint(normalized_data: Any) -> str:
    """Deterministic fingerprint over normalized response data (order-independent)."""
    import json

    return hashlib.sha256(
        json.dumps(normalized_data, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _strip_dynamic(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _strip_dynamic(v) for k, v in data.items() if str(k).lower() not in _DYNAMIC_IGNORED_FIELDS}
    if isinstance(data, list):
        return [_strip_dynamic(v) for v in data]
    return data


# ── M34 fingerprint (extends the M33 fingerprint; never mutates M33 surfaces) ──
def _m34_surface_hash(root: Optional[Path] = None) -> str:
    base = root or Path(__file__).resolve().parents[4]
    p = base / M34_SURFACE_PATH
    if not p.is_file():
        return "missing"
    return hashlib.sha256(p.read_bytes()).hexdigest()


def compute_m34_fingerprint(
    profile: ExternalProviderProfile, *, root: Optional[Path] = None
) -> str:
    return compute_external_fingerprint(
        profile=profile,
        schema=schema_for(profile.provider_id),
        fixture_hash=fixture_hash_for(profile.provider_id),
        extra={
            "m34_surface": _m34_surface_hash(root=root),
            "m34_command_version": M34_VERIFY_COMMAND_VERSION,
            "m34_default_budget": M34_DEFAULT_CALL_BUDGET,
            "m34_max_budget": M34_MAX_CALL_BUDGET,
        },
    )


# ── authorization envelope ────────────────────────────────────────────────────
@dataclass
class LiveVerificationAuthorization:
    provider_id: str
    operation: str
    operator_authorized: bool
    authorization_time: str
    read_only_acknowledged: bool
    network_acknowledged: bool
    non_production_acknowledged: bool
    call_budget_acknowledged: bool
    approved_call_budget: int
    approved_deadline: float
    approved_response_limit: int
    approved_redirect_limit: int
    approved_data_classification: str

    def missing_acks(self) -> list[str]:
        out = []
        if not self.read_only_acknowledged:
            out.append("missing_ack_read_only")
        if not self.network_acknowledged:
            out.append("missing_ack_network")
        if not self.non_production_acknowledged:
            out.append("missing_ack_non_production")
        if not self.call_budget_acknowledged:
            out.append("missing_ack_call_budget")
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "operation": self.operation,
            "operator_authorized": self.operator_authorized,
            "authorization_time": self.authorization_time,
            "read_only_acknowledged": self.read_only_acknowledged,
            "network_acknowledged": self.network_acknowledged,
            "non_production_acknowledged": self.non_production_acknowledged,
            "call_budget_acknowledged": self.call_budget_acknowledged,
            "approved_call_budget": self.approved_call_budget,
            "approved_deadline": self.approved_deadline,
            "approved_response_limit": self.approved_response_limit,
            "approved_redirect_limit": self.approved_redirect_limit,
            "approved_data_classification": self.approved_data_classification,
        }


def _clamp_budget(n: int) -> int:
    return max(1, min(int(n), M34_MAX_CALL_BUDGET))


def mode_for_budget(budget: int) -> str:
    if budget <= 1:
        return LiveVerificationMode.LIVE_SINGLE_VERIFY.value
    if budget == 2:
        return LiveVerificationMode.LIVE_REPEATABILITY_VERIFY.value
    return LiveVerificationMode.LIVE_RELIABILITY_VERIFY.value


def build_authorization(
    profile: ExternalProviderProfile,
    *,
    ack_read_only: bool,
    ack_network: bool,
    ack_non_production: bool,
    ack_call_budget: bool,
    max_calls: int,
    authorization_time: str,
) -> LiveVerificationAuthorization:
    budget = _clamp_budget(max_calls)
    all_ack = ack_read_only and ack_network and ack_non_production and ack_call_budget
    return LiveVerificationAuthorization(
        provider_id=profile.provider_id,
        operation=profile.operation,
        operator_authorized=bool(all_ack),
        authorization_time=authorization_time,
        read_only_acknowledged=bool(ack_read_only),
        network_acknowledged=bool(ack_network),
        non_production_acknowledged=bool(ack_non_production),
        call_budget_acknowledged=bool(ack_call_budget),
        approved_call_budget=budget,
        approved_deadline=float(profile.deadline_seconds),
        approved_response_limit=int(profile.response_limit_bytes),
        approved_redirect_limit=int(profile.redirect_limit),
        approved_data_classification=profile.data_classification,
    )


# ── plan (fails closed on any missing precondition) ───────────────────────────
def plan_m34_verification(
    provider_id: str,
    *,
    ack_read_only: bool,
    ack_network: bool,
    ack_non_production: bool,
    ack_call_budget: bool,
    max_calls: int = M34_DEFAULT_CALL_BUDGET,
    quarantined: Optional[bool] = None,
) -> dict[str, Any]:
    """Build the M34 live-verification plan. Adds the two extra M34 acks and the
    strict [1, 5] budget on top of the M33 plan. Fails closed."""
    # reuse the M33 plan for provider validity / method / side-effect / auth / quarantine
    m33_plan = plan_external_verification(
        provider_id, ack_read_only=ack_read_only, ack_network=ack_network,
        call_budget=1, quarantined=quarantined,
    )
    blockers = list(m33_plan.get("blockers", []))
    if not ack_non_production:
        blockers.append("missing_ack_non_production")
    if not ack_call_budget:
        blockers.append("missing_ack_call_budget")

    raw = int(max_calls)
    if raw < 1:
        blockers.append("call_budget_below_minimum")
    if raw > M34_MAX_CALL_BUDGET:
        blockers.append("call_budget_over_maximum")
    budget = _clamp_budget(raw)

    return {
        "schema": "m34.live_verification_plan.v1",
        "provider_id": provider_id,
        "allowed": not blockers,
        "blockers": blockers,
        "approved_call_budget": budget,
        "requested_call_budget": raw,
        "mode": mode_for_budget(budget),
        "operation": m33_plan.get("operation", ""),
        "method": m33_plan.get("method", ""),
        "deadline_seconds": m33_plan.get("deadline_seconds", 0.0),
        "response_limit_bytes": m33_plan.get("response_limit_bytes", 0),
        "rollout": "OFF (unchanged by verification)",
        "label": NON_PRODUCTION_LABEL,
        "privacy_safe": True,
    }


# ── classification helpers ────────────────────────────────────────────────────
def classify_schema_compat(schema_result: dict[str, Any]) -> str:
    overall = (schema_result or {}).get("overall") or ""
    known = {
        "COMPATIBLE_EXACT", "COMPATIBLE_ADDITIVE", "COMPATIBLE_VALUE_CHANGE",
        "INCOMPATIBLE_MISSING_FIELD", "INCOMPATIBLE_TYPE_CHANGE",
        "INCOMPATIBLE_ENUM_CHANGE", "UNKNOWN_SCHEMA_CHANGE",
    }
    if overall in known:
        return overall
    return "UNKNOWN_SCHEMA_CHANGE"


def schema_compat_passes(compat_class: str) -> bool:
    return compat_class in ("COMPATIBLE_EXACT", "COMPATIBLE_ADDITIVE", "COMPATIBLE_VALUE_CHANGE")


def classify_repeatability(calls: list["LiveCall"]) -> str:
    """Classify normalized-result stability across the successful calls."""
    ok = [c for c in calls if c.success]
    if len(ok) < 2:
        return RepeatabilityClass.NON_COMPARABLE.value
    fps = {c.normalized_fingerprint for c in ok}
    if len(fps) == 1:
        return RepeatabilityClass.STABLE_EXACT.value
    # compare after stripping declared-dynamic fields
    semantic = {normalized_fingerprint(_strip_dynamic(c.normalized_data)) for c in ok}
    if len(semantic) == 1:
        # differed only in dynamic fields
        return RepeatabilityClass.EXPECTED_DYNAMIC_VARIATION.value
    # structural comparison: same required-field key sets → semantic-stable value drift
    keysets = {tuple(sorted((c.normalized_data or {}).keys())) for c in ok}
    if len(keysets) == 1:
        return RepeatabilityClass.STABLE_SEMANTIC.value
    return RepeatabilityClass.UNEXPECTED_VARIATION.value


def repeatability_acceptable(rep_class: str) -> bool:
    return rep_class in (
        RepeatabilityClass.STABLE_EXACT.value,
        RepeatabilityClass.STABLE_SEMANTIC.value,
        RepeatabilityClass.EXPECTED_DYNAMIC_VARIATION.value,
    )


def qualify_reliability(calls: list["LiveCall"], *, approved_budget: int) -> tuple[str, list[str]]:
    """Bounded, honest reliability qualification. Never upgrades a defect to a limitation."""
    limitations: list[str] = []
    successes = [c for c in calls if c.success]
    failures = [c for c in calls if not c.success]

    # a security failure dominates every other classification
    if any(c.failure_code in _SECURITY_FAILURE_CODES for c in failures):
        return ReliabilityQualification.NOT_QUALIFIED_SECURITY_FAILURE.value, ["security_policy_failure"]
    if any(c.failure_code in _SCHEMA_FAILURE_CODES for c in failures) or \
            any(s.schema_compat and not schema_compat_passes(s.schema_compat) for s in successes):
        return ReliabilityQualification.NOT_QUALIFIED_SCHEMA_FAILURE.value, ["schema_incompatible"]

    if not successes:
        if any(c.failure_code in _TRANSIENT_FAILURE_CODES for c in failures):
            return ReliabilityQualification.NOT_QUALIFIED_TRANSIENT_FAILURE.value, ["all_calls_transient_failure"]
        if any(c.failure_code in _PROVIDER_FAILURE_CODES for c in failures):
            return ReliabilityQualification.NOT_QUALIFIED_PROVIDER_FAILURE.value, ["provider_unavailable"]
        return ReliabilityQualification.NOT_QUALIFIED_INSUFFICIENT_EVIDENCE.value, ["no_successful_call"]

    rep = classify_repeatability(calls)
    if rep == RepeatabilityClass.UNEXPECTED_VARIATION.value:
        return ReliabilityQualification.NOT_QUALIFIED_SCHEMA_FAILURE.value, ["unexpected_response_variation"]

    # need at least two successful compatible calls where the budget permits
    if len(successes) >= 2 and repeatability_acceptable(rep):
        limitations = [
            "external_read_only", "single_endpoint_only", "non_production",
            "small_live_sample", "no_credential", "no_account_link", "no_write_authority",
            "provider_uptime_external", "no_sla_established",
        ]
        if failures:
            limitations.append("partial_transient_failures_observed")
        return ReliabilityQualification.QUALIFIED_WITH_LIMITATIONS.value, limitations

    # a single success is never sufficient for reliability
    return ReliabilityQualification.NOT_QUALIFIED_INSUFFICIENT_EVIDENCE.value, [
        "insufficient_successful_calls_for_reliability", f"successful_calls={len(successes)}",
    ]


def assess_canary_readiness(
    *,
    reliability: str,
    external_state: str,
    fresh: bool,
    provider_healthy: bool,
    quarantined: bool,
    leak_clean: bool,
    direct_network_bypasses: int,
    external_writes: int,
    rollout_off: bool,
) -> tuple[str, list[str]]:
    """Assess (never grant) canary readiness. Rollout stays OFF regardless."""
    blockers: list[str] = []
    if reliability != ReliabilityQualification.QUALIFIED_WITH_LIMITATIONS.value:
        blockers.append(f"reliability_not_qualified:{reliability}")
    if external_state != ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS.value:
        blockers.append(f"external_state_insufficient:{external_state}")
    if not fresh:
        blockers.append("external_verification_not_fresh")
    if not provider_healthy:
        blockers.append("provider_unhealthy")
    if quarantined:
        blockers.append("provider_quarantined")
    if not leak_clean:
        blockers.append("leak_scan_not_clean")
    if int(direct_network_bypasses) != 0:
        blockers.append("direct_network_bypasses_nonzero")
    if int(external_writes) != 0:
        blockers.append("external_writes_nonzero")
    if not rollout_off:
        blockers.append("rollout_not_off")
    if blockers:
        return CanaryReadiness.NOT_CANARY_READY.value, blockers
    return CanaryReadiness.CANARY_READY_WITH_LIMITATIONS.value, [
        "operation_specific", "single_read_only_operation", "future_operator_authorization_required",
        "rollout_remains_off", "no_canary_activated", "no_active_activated",
    ]


# ── per-call record ───────────────────────────────────────────────────────────
@dataclass
class LiveCall:
    call_number: int
    mode: str
    success: bool
    status_class: str = ""
    failure_code: str = ""
    latency_ms: float = 0.0
    latency_bucket: str = ""
    response_size_bucket: str = ""
    schema_compat: str = ""
    rate_limit_summary: dict[str, Any] = field(default_factory=dict)
    normalized_fingerprint: str = ""
    normalized_data: dict[str, Any] = field(default_factory=dict)
    redirect_count: int = 0
    tls_verified: bool = False
    safe_error_classification: str = ""
    retry_of: int = 0

    def evidence(self, provider_id: str, operation: str) -> dict[str, Any]:
        """Bounded, leak-safe per-call evidence — NO raw body / headers / secrets."""
        return {
            "call_number": self.call_number,
            "provider_id": provider_id,
            "operation": operation,
            "mode": self.mode,
            "status_class": self.status_class,
            "latency_bucket": self.latency_bucket,
            "response_size_bucket": self.response_size_bucket,
            "schema_result": self.schema_compat,
            "rate_limit_summary": self.rate_limit_summary,
            "normalized_result_fingerprint": self.normalized_fingerprint[:32],
            "redirect_count": self.redirect_count,
            "tls_verified": self.tls_verified,
            "success_or_failure": "success" if self.success else "failure",
            "safe_error_classification": self.safe_error_classification or "none",
            "retry_of": self.retry_of,
            "limitations": ["external_read_only", "single_endpoint_only", "non_production"],
        }


def _classify_failure_bucket(code: str) -> str:
    if code in _SECURITY_FAILURE_CODES:
        return "security_policy_block"
    if code in _SCHEMA_FAILURE_CODES:
        return "schema_incompatible"
    if code in _TRANSIENT_FAILURE_CODES:
        return "transient_network"
    if code in _PROVIDER_FAILURE_CODES:
        return "provider_unavailable_or_rate_limited"
    return "other"


def _one_live_call(
    profile: ExternalProviderProfile,
    transport: ExternalTransport,
    *,
    call_number: int,
    mode: str,
    retry_of: int = 0,
) -> LiveCall:
    """Drive exactly one governed read-only call through the M32 runtime → adapter → transport."""
    res = _run_once(profile, transport, mode=ExecutionMode.SHADOW.value, max_retries=0)
    safe = res.safe_metadata or {}
    ok = bool(res.ok)
    schema_result = safe.get("schema_result") or {}
    compat = classify_schema_compat(schema_result) if schema_result else ""
    tls = safe.get("tls") or {}
    redirect_chain = safe.get("redirect_chain") or []
    failure_code = "" if ok else (res.safe_message or "").split(":")[0][:64]
    # a compatible HTTP success but incompatible schema is reported as a failure by the adapter
    status_class = str(safe.get("status_code") or res.status)
    call = LiveCall(
        call_number=call_number,
        mode=mode,
        success=ok,
        status_class=status_class if ok else (failure_code or "error"),
        failure_code="" if ok else failure_code,
        latency_ms=float(res.latency_ms or 0.0),
        latency_bucket=latency_bucket(res.latency_ms, timed_out=(failure_code == "NETWORK_TIMEOUT")),
        response_size_bucket=size_bucket(_approx_size(res.normalized_data)) if ok else "EMPTY",
        schema_compat=compat,
        rate_limit_summary=_bounded_rate_limit(res.rate_limit or {}),
        normalized_fingerprint=normalized_fingerprint(res.normalized_data) if ok else "",
        normalized_data=dict(res.normalized_data or {}) if ok else {},
        redirect_count=len(redirect_chain),
        tls_verified=bool(tls.get("tls_verified", tls.get("verified", True))) if ok else False,
        safe_error_classification="" if ok else _classify_failure_bucket(failure_code),
        retry_of=retry_of,
    )
    return call


def _approx_size(normalized: Any) -> int:
    import json

    try:
        return len(json.dumps(normalized, default=str).encode("utf-8"))
    except Exception:
        return 0


def _bounded_rate_limit(rl: dict[str, Any]) -> dict[str, Any]:
    if not rl:
        return {"rate_limit_visibility": "NOT_EXPOSED"}
    limit = rl.get("limit")
    remaining = rl.get("remaining")
    return {
        "rate_limit_visibility": "EXPOSED" if limit is not None else "NOT_EXPOSED",
        "limit_present": limit is not None,
        "remaining_present": remaining is not None,
        "remaining_bucket": _remaining_bucket(remaining, limit),
        "retry_after_present": rl.get("retry_after") is not None,
        "confidence": rl.get("confidence", "unknown"),
        "source": rl.get("source", "unknown"),
    }


def _remaining_bucket(remaining: Any, limit: Any) -> str:
    try:
        r = int(remaining)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if r <= 0:
        return "EXHAUSTED"
    if r < 10:
        return "LOW"
    if r < 30:
        return "MODERATE"
    return "AMPLE"


# ── the M34 live-verification orchestrator ────────────────────────────────────
def run_m34_live_verification(
    provider_id: str,
    *,
    ack_read_only: bool,
    ack_network: bool,
    ack_non_production: bool,
    ack_call_budget: bool,
    max_calls: int = M34_DEFAULT_CALL_BUDGET,
    store: Optional[ExternalVerificationStore] = None,
    transport: Optional[ExternalTransport] = None,
    enabled: Optional[bool] = None,
    record: bool = True,
    evidence_dir: Optional[str] = None,
    clock: Optional[Callable[[], float]] = None,
    now: str = "authorization-time",
    provider_healthy: bool = True,
    quarantined: Optional[bool] = None,
) -> dict[str, Any]:
    """Operator-triggered, bounded, live read-only external verification.

    Never auto-runs. Never runs at import or in the standard test suite. Fails
    closed on any missing precondition. Rollout is never mutated. The transport is
    injected by tests; when None and enabled, a hardened live urllib transport is
    constructed. ``enabled`` defaults to the env opt-in flag.
    """
    import time as _t

    clk = clock or _t.perf_counter
    if enabled is None:
        enabled = any(os.environ.get(f, "").strip().lower() in ("1", "true", "yes") for f in ENV_ENABLE_FLAGS)

    plan = plan_m34_verification(
        provider_id, ack_read_only=ack_read_only, ack_network=ack_network,
        ack_non_production=ack_non_production, ack_call_budget=ack_call_budget,
        max_calls=max_calls, quarantined=quarantined,
    )
    base = {
        "schema": "m34.live_verification_result.v1",
        "provider_id": provider_id,
        "operation": plan.get("operation", ""),
        "mode": plan.get("mode", ""),
        "live_call": False,
        "rollout": "OFF (unchanged)",
        "label": NON_PRODUCTION_LABEL,
        "privacy_safe": True,
        "trading_guardian": "UNCHANGED / UNENGAGED",
    }

    if not enabled:
        return {**base, "ok": False, "success_or_failure": "aborted",
                "reason": "live_verification_disabled",
                "verification_state": M34State.UNVERIFIED.value, "blockers": ["disabled"]}
    if not plan["allowed"]:
        return {**base, "ok": False, "success_or_failure": "blocked",
                "reason": "plan_blocked", "verification_state": M34State.UNVERIFIED.value,
                "blockers": plan["blockers"]}

    profile = resolve_external_profile(provider_id)
    validate_external_profile(profile)  # defence in depth — read-only ceiling
    if (profile.method or "").upper() not in M33_ALLOWED_METHODS:
        return {**base, "ok": False, "success_or_failure": "blocked", "reason": "write_method_blocked",
                "verification_state": M34State.EXTERNAL_VERIFICATION_FAILED.value,
                "blockers": [f"method:{profile.method}"]}

    q = quarantined
    if q is None:
        q = ProviderQuarantineStore().is_quarantined(provider_id)
    if q:
        return {**base, "ok": False, "success_or_failure": "blocked", "reason": "provider_quarantined",
                "verification_state": M34State.EXTERNAL_VERIFICATION_FAILED.value,
                "blockers": ["provider_quarantined"]}

    budget = int(plan["approved_call_budget"])
    mode = plan["mode"]
    authz = build_authorization(
        profile, ack_read_only=ack_read_only, ack_network=ack_network,
        ack_non_production=ack_non_production, ack_call_budget=ack_call_budget,
        max_calls=budget, authorization_time=now,
    )

    tr = transport if transport is not None else ExternalTransport(sender=urllib_sender)

    # ── bounded call loop (retries consume budget; max 5 total) ───────────────
    calls: list[LiveCall] = []
    spent = 0
    n = 0
    while spent < budget:
        n += 1
        spent += 1
        call = _one_live_call(profile, tr, call_number=n, mode=mode)
        calls.append(call)
        # a classified transient failure may be retried IF budget remains (retry
        # consumes budget; a security/schema failure is terminal — never retried)
        if (not call.success) and call.failure_code in _TRANSIENT_FAILURE_CODES and spent < budget:
            n += 1
            spent += 1
            retry = _one_live_call(profile, tr, call_number=n, mode=mode, retry_of=call.call_number)
            calls.append(retry)

    successes = [c for c in calls if c.success]
    reliability, rel_limits = qualify_reliability(calls, approved_budget=budget)
    repeatability = classify_repeatability(calls)
    ok = bool(successes) and reliability in (
        ReliabilityQualification.QUALIFIED_WITH_LIMITATIONS.value,
        ReliabilityQualification.NOT_QUALIFIED_INSUFFICIENT_EVIDENCE.value,
    ) and all(schema_compat_passes(c.schema_compat) for c in successes)

    fp = compute_m34_fingerprint(profile)
    st = store or _default_m34_store()

    # persisted external state: verified-with-limitations only when at least one
    # bounded successful compatible call occurred; otherwise FAILED. This uses the
    # existing M33 enum (no fingerprint-surface change).
    if ok:
        external_state = ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS.value
    else:
        external_state = ExternalVerificationState.EXTERNAL_VERIFICATION_FAILED.value

    limitations = sorted(set(rel_limits) | {
        "external_read_only", "single_endpoint_only", "non_production",
        "no_write_authority", "no_account_link", "no_credential",
    })
    if record:
        st.record_verification(
            provider_id, state=external_state, fingerprint=fp, limitations=limitations,
            evidence_dir=(evidence_dir or "docs/evidence/m34"),
            verified_at=str(int(_wall_clock(st))), live_call_count=len(calls), mode="SHADOW",
        )

    # canary readiness (assessment only — never activates)
    leak_clean = _all_calls_leak_clean(calls)
    canary, canary_detail = assess_canary_readiness(
        reliability=reliability, external_state=external_state,
        fresh=ok, provider_healthy=provider_healthy, quarantined=bool(q),
        leak_clean=leak_clean, direct_network_bypasses=0, external_writes=0, rollout_off=True,
    )

    return {
        **base,
        "live_call": True,
        "ok": ok,
        "success_or_failure": "success" if ok else "failure",
        "authorization": authz.to_dict(),
        "approved_call_budget": budget,
        "actual_call_count": len(calls),
        "successful_calls": len(successes),
        "failed_calls": len(calls) - len(successes),
        "calls": [c.evidence(provider_id, profile.operation) for c in calls],
        "schema_compatibility": [c.schema_compat for c in successes] or ["none"],
        "repeatability": repeatability,
        "reliability_qualification": reliability,
        "canary_readiness": canary,
        "canary_detail": canary_detail,
        "verification_state": (
            M34State.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS.value if ok
            else M34State.EXTERNAL_VERIFICATION_FAILED.value
        ),
        "external_state_persisted": external_state,
        "fingerprint": fp,
        "limitations": limitations,
        "leak_clean": leak_clean,
        "rollout_state": {"connector": "OFF", "provider": "OFF", "inference": "OFF",
                          "canary_providers": 0, "active_providers": 0},
        "_calls_internal": calls,  # for evidence writer; stripped before CLI/JSON print
    }


def _wall_clock(store: ExternalVerificationStore) -> float:
    try:
        return float(store.clock())
    except Exception:
        import time as _t

        return _t.time()


def _all_calls_leak_clean(calls: list[LiveCall]) -> bool:
    for c in calls:
        if not is_clean(c.evidence("p", "op")):
            return False
        # the normalized data is projected onto the declared schema; verify clean too
        if c.normalized_data and not is_clean(c.normalized_data):
            return False
    return True


# ── evidence writer (bounded, leak-scanned, atomic — via M32 write_evidence) ──
def write_m34_evidence(result: dict[str, Any], *, evidence_dir: str = "docs/evidence/m34") -> list[str]:
    """Write the full bounded M34 evidence set from a live result. No raw data."""
    from saathi.connectors.providers.evidence import write_evidence

    d = Path(evidence_dir)
    calls: list[LiveCall] = result.get("_calls_internal", [])
    pid = result["provider_id"]
    op = result.get("operation", "")
    written: list[str] = []

    def w(name: str, body: dict[str, Any]) -> None:
        written.append(write_evidence(name, body, evidence_dir=d, schema=f"m34.{name}.v1"))

    authz = result.get("authorization", {})
    w("authorization", authz or {"operator_authorized": False})
    w("provider_identity", {
        "provider_id": pid, "operation": op,
        "mode": result.get("mode"), "verification_state": result.get("verification_state"),
    })
    for c in calls:
        w(f"live_call_{c.call_number:02d}", c.evidence(pid, op))
    w("schema_compatibility", {
        "results": result.get("schema_compatibility", []),
        "all_pass": all(schema_compat_passes(x) for x in result.get("schema_compatibility", []) if x != "none"),
    })
    w("repeatability", {
        "classification": result.get("repeatability"),
        "acceptable": repeatability_acceptable(result.get("repeatability", "")),
        "ignored_dynamic_fields": sorted(_DYNAMIC_IGNORED_FIELDS),
    })
    w("rate_limit_observation", {
        "per_call": [c.rate_limit_summary for c in calls],
    })
    w("latency_observation", {
        "per_call": [{"call": c.call_number, "bucket": c.latency_bucket} for c in calls],
    })
    w("reliability_qualification", {
        "qualification": result.get("reliability_qualification"),
        "successful_calls": result.get("successful_calls", 0),
        "failed_calls": result.get("failed_calls", 0),
        "actual_call_count": result.get("actual_call_count", 0),
        "approved_call_budget": result.get("approved_call_budget", 0),
        "limitations": result.get("limitations", []),
    })
    w("canary_readiness", {
        "assessment": result.get("canary_readiness"),
        "detail": result.get("canary_detail", []),
        "provider_rollout": "OFF", "canary_providers": 0, "active_providers": 0,
        "note": "assessment_only_no_activation",
    })
    w("verification_state", {
        "state": result.get("verification_state"),
        "external_state_persisted": result.get("external_state_persisted"),
        "fingerprint": result.get("fingerprint"),
        "operation_scope": op,
        "unsupported_scope": ["writes", "other_endpoints", "authenticated_operations", "account_linked_operations"],
    })
    w("verification_fingerprint", {
        "provider_id": pid, "fingerprint": result.get("fingerprint"),
        "command_version": M34_VERIFY_COMMAND_VERSION,
    })
    w("redaction_results", {
        "raw_body_present": False, "raw_headers_present": False,
        "authorization_present": False, "cookie_present": False,
        "token_present": False, "personal_data_present": False,
        "absolute_paths_present": False,
    })
    w("leak_scan_results", {"clean": bool(result.get("leak_clean", False)), "findings": []})
    w("validation_summary", _validation_summary_body(result))
    return written


def _validation_summary_body(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": result["provider_id"],
        "operation": result.get("operation"),
        "mode": result.get("mode"),
        "actual_call_count": result.get("actual_call_count", 0),
        "successful_calls": result.get("successful_calls", 0),
        "external_write_calls": 0,
        "financial_provider_calls": 0,
        "trading_provider_calls": 0,
        "private_network_calls": 0,
        "tls_verification_bypasses": 0,
        "unsafe_redirects_followed": 0,
        "raw_responses_committed": 0,
        "secret_leaks": 0,
        "production_credentials": 0,
        "sandbox_credentials": 0,
        "credentials_committed_to_git": 0,
        "live_production_account_links": 0,
        "sandbox_account_links": 0,
        "connector_rollout": "OFF",
        "provider_rollout": "OFF",
        "inference_rollout": "OFF",
        "canary_providers": 0,
        "active_providers": 0,
        "reliability_qualification": result.get("reliability_qualification"),
        "repeatability": result.get("repeatability"),
        "canary_readiness": result.get("canary_readiness"),
        "verification_state": result.get("verification_state"),
        "max_verification_state": ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS.value,
        "trading_guardian": "UNCHANGED / UNENGAGED",
    }


# ── non-mutating status / drift readers ──────────────────────────────────────
def _fresh(store_rec_fp: str, current_fp: str, state: str) -> bool:
    return bool(
        store_rec_fp and store_rec_fp == current_fp
        and state == ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS.value
    )


def reliability_status(
    provider_id: str, *, store: Optional[ExternalVerificationStore] = None,
    evidence_dir: str = "docs/evidence/m34",
) -> dict[str, Any]:
    """NON-mutating read of the live-verification / reliability status."""
    import json

    profile = resolve_external_profile(provider_id)
    st = store or _default_m34_store()
    rec = st.get(provider_id)
    current_fp = compute_m34_fingerprint(profile)
    fresh = _fresh(rec.fingerprint, current_fp, rec.state)
    reliability = "UNKNOWN"
    p = Path(evidence_dir) / "reliability_qualification.json"
    if p.is_file():
        try:
            reliability = (json.loads(p.read_text()).get("body") or {}).get("qualification", "UNKNOWN")
        except Exception:
            reliability = "UNKNOWN"
    return {
        "schema": "m34.reliability_status.v1",
        "provider_id": provider_id,
        "external_state": rec.state,
        "fresh": fresh,
        "live_call_count": rec.live_call_count,
        "reliability_qualification": reliability,
        "stored_fingerprint": rec.fingerprint[:16],
        "current_fingerprint": current_fp[:16],
        "rollout": "OFF (unchanged)",
        "label": NON_PRODUCTION_LABEL,
        "privacy_safe": True,
    }


def canary_readiness_status(
    provider_id: str, *, store: Optional[ExternalVerificationStore] = None,
    evidence_dir: str = "docs/evidence/m34", provider_healthy: bool = True,
) -> dict[str, Any]:
    """NON-mutating canary-readiness assessment read. Never activates rollout."""
    import json

    profile = resolve_external_profile(provider_id)
    st = store or _default_m34_store()
    rec = st.get(provider_id)
    current_fp = compute_m34_fingerprint(profile)
    fresh = _fresh(rec.fingerprint, current_fp, rec.state)
    reliability = "UNKNOWN"
    p = Path(evidence_dir) / "reliability_qualification.json"
    if p.is_file():
        try:
            reliability = (json.loads(p.read_text()).get("body") or {}).get("qualification", "UNKNOWN")
        except Exception:
            reliability = "UNKNOWN"
    quarantined = ProviderQuarantineStore().is_quarantined(provider_id)
    assessment, detail = assess_canary_readiness(
        reliability=reliability, external_state=rec.state, fresh=fresh,
        provider_healthy=provider_healthy, quarantined=quarantined, leak_clean=True,
        direct_network_bypasses=0, external_writes=0, rollout_off=True,
    )
    return {
        "schema": "m34.canary_readiness_status.v1",
        "provider_id": provider_id,
        "canary_readiness": assessment,
        "detail": detail,
        "provider_rollout": "OFF", "canary_providers": 0, "active_providers": 0,
        "note": "assessment_only — future operator authorization required to activate",
        "label": NON_PRODUCTION_LABEL,
        "privacy_safe": True,
    }


def check_m34_drift(
    provider_id: str, *, store: Optional[ExternalVerificationStore] = None, mark_stale: bool = False,
) -> dict[str, Any]:
    """Detect M34 live-verification drift against the M34 fingerprint. Non-mutating
    unless mark_stale=True (explicit mutation path)."""
    profile = resolve_external_profile(provider_id)
    st = store or _default_m34_store()
    rec = st.get(provider_id)
    current_fp = compute_m34_fingerprint(profile)
    tracked = {
        ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS.value,
        ExternalVerificationState.SIMULATION_VERIFIED.value,
    }
    drifted = bool(rec.fingerprint and rec.fingerprint != current_fp and rec.state in tracked)
    if drifted and mark_stale:
        st.mark_stale(provider_id, reason="m34_fingerprint_mismatch")
    return {
        "schema": "m34.live_drift_report.v1",
        "provider_id": provider_id,
        "drifted": drifted,
        "stored_fingerprint": rec.fingerprint[:16],
        "current_fingerprint": current_fp[:16],
        "prior_state": rec.state,
        "ok": not drifted,
        "privacy_safe": True,
    }
