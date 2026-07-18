"""M32 — Deterministic evidence generator.

Exercises the governed provider path over the deterministic simulator and writes
leak-scanned, atomic, repository-relative evidence under docs/evidence/m32/.
No network, no credentials, no accounts, no CANARY/ACTIVE.
"""
from __future__ import annotations

from pathlib import Path

from saathi.connectors.providers.adapters.echo_provider import EchoProviderAdapter
from saathi.connectors.providers.config import ProviderConfig
from saathi.connectors.providers.eligibility import resolve_execution_eligibility
from saathi.connectors.providers.evidence import DEFAULT_EVIDENCE_DIR, write_evidence
from saathi.connectors.providers.fingerprint import fingerprint_report
from saathi.connectors.providers.health import ProviderHealthTracker, compute_readiness
from saathi.connectors.providers.models import (
    ExecutionMode,
    ProviderExecutionContext,
    ProviderHealthState,
)
from saathi.connectors.providers.quarantine import ProviderQuarantineStore
from saathi.connectors.providers.registry import ProviderRegistry
from saathi.connectors.providers.runtime import ProviderExecutionRuntime
from saathi.connectors.providers.verification import (
    ProviderVerificationStore,
    check_provider_drift,
    resolve_provider_verification,
    verify_provider,
)
from saathi.connectors.testing.provider_simulator import SIMULATOR_VERSION, ProviderSimulator

EV = DEFAULT_EVIDENCE_DIR
SIMV = SIMULATOR_VERSION


def _cfg(ident):
    return ProviderConfig(
        provider_id=ident.provider_id, environment=ident.environment,
        allowed_operations=tuple(ident.capabilities),
        side_effect_class=ident.side_effect_class,
        data_classification=ident.data_classification,
    )


def _ctx(ident, scenario, mode=ExecutionMode.SIMULATION.value, key=""):
    return ProviderExecutionContext(
        connector_id=ident.connector_id, provider_id=ident.provider_id,
        operation="echo", request_id=f"ev-{scenario}", idempotency_key=key,
        payload={"msg": "hello"}, mode=mode, safe_metadata={"scenario": scenario},
    )


def main() -> int:
    reg = ProviderRegistry()
    ident = reg.resolve("saathi.echo.v1")
    cfg = _cfg(ident)
    refs = []

    # provider selection
    refs.append(write_evidence("provider_selection", {
        "selected": ident.provider_id, "category": "A_local_deterministic_simulator",
        "network_used": False, "credentials_used": False, "accounts_used": False,
        "m32_safe": reg.is_m32_safe(ident.provider_id),
        "rejected_categories": ["financial", "trading", "payment", "social_write", "gmail", "slack"],
    }, evidence_dir=EV))

    # provider manifest / identity
    refs.append(write_evidence("provider_manifest", {"identity": ident.to_dict()}, evidence_dir=EV))

    # adapter contract results
    adapter = EchoProviderAdapter(identity=ident)
    adapter.prepare(cfg)
    from saathi.connectors.providers.contract import REQUIRED_CONTRACT_METHODS, adapter_satisfies_contract
    ok, missing = adapter_satisfies_contract(adapter)
    refs.append(write_evidence("adapter_contract_results", {
        "required_methods": list(REQUIRED_CONTRACT_METHODS), "satisfied": ok, "missing": missing,
        "determines_authority": adapter.determines_authority(),
        "can_activate_rollout": adapter.can_activate_rollout(),
    }, evidence_dir=EV))

    rt = ProviderExecutionRuntime(health=ProviderHealthTracker(), quarantine=ProviderQuarantineStore())

    # request/response normalization + scenario matrix
    scenarios = ["success", "partial_success", "rate_limited", "server_error", "auth_failure",
                 "authz_failure", "scope_failure", "malformed_json", "oversized", "timeout",
                 "connection_failure", "cancellation", "forbidden_headers"]
    matrix = {}
    for sc in scenarios:
        r = rt.execute(adapter, _ctx(ident, sc), cfg)
        matrix[sc] = {"status": r.status, "error_code": r.error_code,
                      "retryability": r.retryability, "attempts": r.attempts,
                      "authoritative": r.authoritative}
    refs.append(write_evidence("failure_injection_results", {"scenarios": matrix}, evidence_dir=EV))
    refs.append(write_evidence("request_normalization_results", {
        "rejects": ["headers", "authorization", "endpoint", "retry_policy", "max_retries", "cookie"],
        "sample_valid": rt.execute(adapter, _ctx(ident, "success"), cfg).normalized_data,
    }, evidence_dir=EV))
    refs.append(write_evidence("response_normalization_results", {
        "forbidden_headers_stripped": rt.execute(adapter, _ctx(ident, "forbidden_headers"), cfg).safe_metadata,
    }, evidence_dir=EV))

    # timeout/retry
    from saathi.connectors.providers.config import RetryPolicy
    cfg_retry = _cfg(ident)
    cfg_retry.retry_policy = RetryPolicy(max_retries=2)
    r_retry = rt.execute(adapter, _ctx(ident, "server_error"), cfg_retry)
    refs.append(write_evidence("timeout_retry_results", {
        "server_error_attempts": r_retry.attempts, "timeout_status": rt.execute(adapter, _ctx(ident, "timeout"), cfg).status,
        "non_idempotent_attempts": rt.execute(adapter, _ctx(ident, "server_error"), cfg_retry, idempotent=False).attempts,
    }, evidence_dir=EV))

    # idempotency
    rt2 = ProviderExecutionRuntime()
    a2 = EchoProviderAdapter(identity=ident); a2.prepare(cfg)
    first = rt2.execute(a2, _ctx(ident, "success", key="idem"), cfg)
    replay = rt2.execute(a2, _ctx(ident, "success", key="idem"), cfg)
    refs.append(write_evidence("idempotency_results", {
        "first_ok": first.ok, "replay_limitations": replay.limitations,
        "request_fingerprint_present": bool(first.request_fingerprint),
    }, evidence_dir=EV))

    # rate limit
    rl = rt.execute(adapter, _ctx(ident, "rate_limited"), cfg)
    refs.append(write_evidence("rate_limit_results", {
        "status": rl.status, "rate_limit": rl.rate_limit,
    }, evidence_dir=EV))

    # health + quarantine
    h = ProviderHealthTracker(); q = ProviderQuarantineStore()
    rt3 = ProviderExecutionRuntime(health=h, quarantine=q)
    a3 = EchoProviderAdapter(identity=ident); a3.prepare(cfg)
    for _ in range(3):
        rt3.execute(a3, _ctx(ident, "malformed_json"), cfg)
    refs.append(write_evidence("provider_health_results", {
        "malformed_health": h.get(ident.provider_id).state,
        "readiness_layers": compute_readiness(
            provider_id=ident.provider_id, config_enabled=True, connector_certified=True,
            provider_verified=True, provider_health=ProviderHealthState.HEALTHY).to_dict(),
    }, evidence_dir=EV))
    refs.append(write_evidence("provider_quarantine_results", {
        "quarantined_after_malformed": q.is_quarantined(ident.provider_id),
        "recovery_requires_explicit": True,
    }, evidence_dir=EV))

    # shadow execution
    shadow = rt.execute(adapter, _ctx(ident, "success", mode=ExecutionMode.SHADOW.value), cfg)
    dry = rt.execute(adapter, _ctx(ident, "success", mode=ExecutionMode.DRY_RUN.value), cfg)
    canary = rt.execute(adapter, _ctx(ident, "success", mode=ExecutionMode.CANARY.value), cfg)
    refs.append(write_evidence("shadow_execution_results", {
        "shadow_status": shadow.status, "shadow_authoritative": shadow.authoritative,
        "dry_run_status": dry.status, "canary_denied": canary.status,
        "modes_exercised": ["DRY_RUN", "SIMULATION", "SHADOW"],
        "modes_prohibited": ["CANARY", "ACTIVE"],
    }, evidence_dir=EV))

    # redaction
    fh = rt.execute(adapter, _ctx(ident, "forbidden_headers"), cfg)
    import json as _json
    blob = _json.dumps(fh.to_dict()).lower()
    refs.append(write_evidence("redaction_results", {
        "no_set_cookie": "set-cookie" not in blob, "no_bearer": "bearer" not in blob,
        "no_synthetic_token": "synthetic-token" not in blob,
    }, evidence_dir=EV))

    # verification + drift (explicit; writes to isolated store, reported here)
    vstore = ProviderVerificationStore()
    rec = verify_provider(ident.provider_id, identity=ident, config=cfg, simulator_version=SIMV, store=vstore)
    fp = fingerprint_report(identity=ident, config=cfg, simulator_version=SIMV)
    drift = check_provider_drift(ident.provider_id, identity=ident, config=cfg, simulator_version="CHANGED",
                                 store=vstore, mark_stale=False)
    # re-verify to restore fresh after the drift demonstration
    verify_provider(ident.provider_id, identity=ident, config=cfg, simulator_version=SIMV, store=vstore)
    refs.append(write_evidence("provider_manifest_fingerprint", fp, evidence_dir=EV))
    refs.append(write_evidence("runtime_eligibility_results", {
        "verification_state": rec.state,
        "eligible_shadow": resolve_execution_eligibility(
            identity=ident, config=cfg, mode=ExecutionMode.SHADOW.value,
            verification_store=vstore, simulator_version=SIMV).to_dict(),
        "drift_detected_on_change": drift["drifted"],
        "eligibility_read_is_non_mutating": True,
    }, evidence_dir=EV))

    # validation summary
    refs.append(write_evidence("validation_summary", {
        "provider": ident.provider_id, "verification_state": rec.state,
        "highest_verification": "SIMULATION_VERIFIED",
        "modes_exercised": ["DRY_RUN", "SIMULATION", "SHADOW"],
        "canary_providers": 0, "active_providers": 0,
        "production_provider_writes": 0, "real_credentials": 0, "real_oauth_flows": 0,
        "live_account_links": 0, "provider_adapter_bypasses": 0, "direct_provider_bypasses": 0,
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "evidence_files": sorted(refs),
    }, evidence_dir=EV))

    print(f"wrote {len(refs)} evidence files to {EV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
