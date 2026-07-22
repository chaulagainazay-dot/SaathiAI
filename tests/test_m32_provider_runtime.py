"""M32 — Provider runtime: bounded execution, timeouts, retry, idempotency,
health/quarantine, shadow/simulation, eligibility, runtime integration, invariants.

Deterministic; simulator only; no network/credentials/accounts.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.connectors.providers.adapters.echo_provider import EchoProviderAdapter
from saathi.connectors.providers.config import ProviderConfig, RetryPolicy, TimeoutPolicy
from saathi.connectors.providers.eligibility import (
    ProviderEligibilityDecision,
    resolve_execution_eligibility,
)
from saathi.connectors.providers.health import (
    ProviderHealthTracker,
    compute_readiness,
)
from saathi.connectors.providers.models import (
    ExecutionMode,
    ProviderErrorCode,
    ProviderExecutionContext,
    ProviderHealthState,
    ProviderSideEffectClass,
    ProviderStatus,
)
from saathi.connectors.providers.quarantine import ProviderQuarantineStore
from saathi.connectors.providers.registry import ProviderRegistry
from saathi.connectors.providers.runtime import ProviderExecutionRuntime
from saathi.connectors.providers.verification import (
    ProviderVerificationStore,
    verify_provider,
)
from saathi.connectors.testing.provider_simulator import (
    SIMULATOR_VERSION,
    ProviderSimulator,
    SimulatorShutdown,
)

SIMV = SIMULATOR_VERSION
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def registry():
    return ProviderRegistry()


@pytest.fixture()
def identity(registry):
    return registry.resolve("saathi.echo.v1")


@pytest.fixture()
def config(identity):
    return ProviderConfig(
        provider_id=identity.provider_id,
        environment="test",
        allowed_operations=tuple(identity.capabilities),
        side_effect_class=identity.side_effect_class,
        data_classification=identity.data_classification,
    )


def _ctx(identity, scenario="success", mode=ExecutionMode.SIMULATION.value, op="echo", key="", payload=None):
    return ProviderExecutionContext(
        connector_id=identity.connector_id, provider_id=identity.provider_id,
        operation=op, request_id="r", idempotency_key=key,
        payload=payload if payload is not None else {"m": 1},
        mode=mode, safe_metadata={"scenario": scenario},
    )


def _adapter(identity, config, simulator=None):
    a = EchoProviderAdapter(identity=identity, simulator=simulator or ProviderSimulator())
    a.prepare(config)
    return a


# ── Bounded execution & timeouts (45-52) ─────────────────────────────────────
def test_success_execution(identity, config):
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, config), _ctx(identity, "success"), config)
    assert res.status == ProviderStatus.SUCCESS.value and res.ok


def test_timeout_produces_canonical_error(identity, config):
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, config), _ctx(identity, "timeout"), config)
    assert res.status == ProviderStatus.TIMEOUT.value and res.error_code == ProviderErrorCode.TIMEOUT.value


def test_total_deadline_prevents_late_retry(identity):
    # tiny deadline; server_error retry backoff must exceed it → no unbounded waiting
    cfg = ProviderConfig(provider_id=identity.provider_id, allowed_operations=identity.capabilities,
                         side_effect_class=identity.side_effect_class,
                         timeout_policy=TimeoutPolicy(total_deadline=0.001),
                         retry_policy=RetryPolicy(max_retries=3, backoff_base_seconds=1.0))
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, cfg), _ctx(identity, "server_error"), cfg)
    assert res.attempts == 1  # retry blocked by deadline


def test_cancellation_stops_execution(identity, config):
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, config), _ctx(identity, "cancellation"), config)
    assert res.status == ProviderStatus.CANCELLED.value and res.error_code == ProviderErrorCode.CANCELLED.value


def test_shutdown_during_execution_fails_safely(identity, config):
    sim = ProviderSimulator()
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, config, sim), _ctx(identity, "shutdown"), config)
    assert res.status == ProviderStatus.ERROR.value
    # simulator now shut down; a subsequent call still fails safely (no corruption)
    res2 = rt.execute(_adapter(identity, config, sim), _ctx(identity, "success"), config)
    assert res2.status == ProviderStatus.ERROR.value


def test_no_unbounded_retry(identity):
    cfg = ProviderConfig(provider_id=identity.provider_id, allowed_operations=identity.capabilities,
                         side_effect_class=identity.side_effect_class,
                         retry_policy=RetryPolicy(max_retries=2))
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, cfg), _ctx(identity, "server_error"), cfg)
    assert res.attempts <= 3


# ── Retry integration (53-62) ────────────────────────────────────────────────
def test_idempotent_transient_retries(identity):
    cfg = ProviderConfig(provider_id=identity.provider_id, allowed_operations=identity.capabilities,
                         side_effect_class=identity.side_effect_class, retry_policy=RetryPolicy(max_retries=2))
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, cfg), _ctx(identity, "server_error"), cfg)
    assert res.attempts == 3


def test_non_idempotent_does_not_retry(identity):
    cfg = ProviderConfig(provider_id=identity.provider_id, allowed_operations=identity.capabilities,
                         side_effect_class=identity.side_effect_class, retry_policy=RetryPolicy(max_retries=3))
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, cfg), _ctx(identity, "server_error"), cfg, idempotent=False)
    assert res.attempts == 1


def test_auth_failure_does_not_retry(identity):
    cfg = ProviderConfig(provider_id=identity.provider_id, allowed_operations=identity.capabilities,
                         side_effect_class=identity.side_effect_class, retry_policy=RetryPolicy(max_retries=3))
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, cfg), _ctx(identity, "auth_failure"), cfg)
    assert res.attempts == 1 and res.error_code == ProviderErrorCode.AUTHENTICATION_FAILED.value


def test_scope_failure_does_not_retry(identity):
    cfg = ProviderConfig(provider_id=identity.provider_id, allowed_operations=identity.capabilities,
                         side_effect_class=identity.side_effect_class, retry_policy=RetryPolicy(max_retries=3))
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, cfg), _ctx(identity, "scope_failure"), cfg)
    assert res.attempts == 1


def test_revoked_credential_blocks_retry(identity):
    cfg = ProviderConfig(provider_id=identity.provider_id, allowed_operations=identity.capabilities,
                         side_effect_class=identity.side_effect_class, retry_policy=RetryPolicy(max_retries=3))
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, cfg), _ctx(identity, "server_error"), cfg, credential_eligible=False)
    assert res.attempts == 1


def test_quarantined_provider_blocks_call(identity, config):
    q = ProviderQuarantineStore()
    q.quarantine(identity.provider_id, reason="operator_action")
    rt = ProviderExecutionRuntime(quarantine=q)
    res = rt.execute(_adapter(identity, config), _ctx(identity, "success"), config)
    assert res.status == ProviderStatus.DENIED.value


# ── Idempotency integration (63-71) ──────────────────────────────────────────
def test_duplicate_request_reuses_no_new_side_effect(identity, config):
    rt = ProviderExecutionRuntime()
    a = _adapter(identity, config)
    r1 = rt.execute(a, _ctx(identity, "success", key="idem-1"), config)
    r2 = rt.execute(a, _ctx(identity, "success", key="idem-1"), config)
    assert r1.ok
    assert "idempotent_replay" in r2.limitations


def test_changed_request_conflicts(identity, config):
    rt = ProviderExecutionRuntime()
    a = _adapter(identity, config)
    rt.execute(a, _ctx(identity, "success", key="idem-2", payload={"m": 1}), config)
    r2 = rt.execute(a, _ctx(identity, "success", key="idem-2", payload={"m": 999}), config)
    assert r2.status == ProviderStatus.DENIED.value and r2.error_code == ProviderErrorCode.CONFLICT.value


# ── Rate limits integration (72-79) ──────────────────────────────────────────
def test_rate_limited_classified(identity, config):
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, config), _ctx(identity, "rate_limited"), config)
    assert res.status == ProviderStatus.RATE_LIMITED.value
    assert res.rate_limit and res.rate_limit["retry_after"] is not None


def test_rate_limited_provider_becomes_degraded(identity, config):
    h = ProviderHealthTracker()
    rt = ProviderExecutionRuntime(health=h)
    rt.execute(_adapter(identity, config), _ctx(identity, "rate_limited"), config)
    assert h.get(identity.provider_id).state == ProviderHealthState.RATE_LIMITED.value


# ── Health & readiness (80-88) ───────────────────────────────────────────────
def test_healthy_simulator_reports_healthy(identity, config):
    h = ProviderHealthTracker()
    rt = ProviderExecutionRuntime(health=h)
    rt.execute(_adapter(identity, config), _ctx(identity, "success"), config)
    assert h.get(identity.provider_id).state == ProviderHealthState.HEALTHY.value


def test_timeout_degrades_health(identity, config):
    h = ProviderHealthTracker()
    rt = ProviderExecutionRuntime(health=h)
    rt.execute(_adapter(identity, config), _ctx(identity, "timeout"), config)
    assert h.get(identity.provider_id).state == ProviderHealthState.DEGRADED.value


def test_repeated_malformed_quarantines(identity, config):
    h = ProviderHealthTracker()
    q = ProviderQuarantineStore()
    rt = ProviderExecutionRuntime(health=h, quarantine=q)
    for _ in range(3):
        rt.execute(_adapter(identity, config), _ctx(identity, "malformed_json"), config)
    assert q.is_quarantined(identity.provider_id)


def test_provider_health_distinct_from_connector_and_account():
    r = compute_readiness(
        provider_id="p", config_enabled=True, connector_certified=True, provider_verified=True,
        provider_health=ProviderHealthState.HEALTHY, account_ready=False,
    )
    assert not r.ready and r.reason == "account_not_ready"
    assert r.layers["provider_health"] == "HEALTHY"  # provider health stayed healthy independently


def test_certified_connector_with_disabled_provider_blocked():
    r = compute_readiness(
        provider_id="p", config_enabled=False, connector_certified=True, provider_verified=True,
        provider_health=ProviderHealthState.HEALTHY,
    )
    assert not r.ready and r.reason == "provider_disabled"


def test_provider_health_alone_does_not_authorize():
    r = compute_readiness(
        provider_id="p", config_enabled=True, connector_certified=False, provider_verified=True,
        provider_health=ProviderHealthState.HEALTHY,
    )
    assert not r.ready and r.reason == "connector_not_certified"


# ── Shadow & simulation (89-98) ──────────────────────────────────────────────
def test_dry_run_performs_no_provider_call(identity, config):
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, config), _ctx(identity, "success", mode=ExecutionMode.DRY_RUN.value), config)
    assert res.status == ProviderStatus.DRY_RUN.value and res.normalized_data.get("validated")


def test_simulation_uses_local_provider(identity, config):
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, config), _ctx(identity, "success", mode=ExecutionMode.SIMULATION.value), config)
    assert res.mode == ExecutionMode.SIMULATION.value and res.ok


def test_shadow_result_non_authoritative(identity, config):
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, config), _ctx(identity, "success", mode=ExecutionMode.SHADOW.value), config)
    assert res.mode == ExecutionMode.SHADOW.value and res.authoritative is False


@pytest.mark.parametrize("mode", [ExecutionMode.CANARY.value, ExecutionMode.ACTIVE.value])
def test_canary_and_active_rejected(identity, config, mode):
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, config), _ctx(identity, "success", mode=mode), config)
    assert res.status == ProviderStatus.DENIED.value and "mode_prohibited" in res.safe_message


def test_shadow_cannot_activate_rollout(identity, config):
    a = _adapter(identity, config)
    assert a.can_activate_rollout() is False


# ── Eligibility composition (129-140 subset) ─────────────────────────────────
def _vstore(tmp):
    return ProviderVerificationStore(path=tmp / "v.json", persist=True, clock=lambda: 1.0)


def test_full_eligibility_requires_all_layers(identity, config, tmp_path):
    vs = _vstore(tmp_path)
    verify_provider(identity.provider_id, identity=identity, config=config, simulator_version=SIMV, store=vs)
    ok = resolve_execution_eligibility(identity=identity, config=config, mode=ExecutionMode.SHADOW.value,
                                       verification_store=vs, simulator_version=SIMV)
    assert ok.allowed and ok.reason == "eligible_shadow_only"


def test_production_certification_required(identity, config, tmp_path):
    vs = _vstore(tmp_path)
    verify_provider(identity.provider_id, identity=identity, config=config, simulator_version=SIMV, store=vs)
    d = resolve_execution_eligibility(identity=identity, config=config, mode=ExecutionMode.SHADOW.value,
                                      production_certified=False, verification_store=vs, simulator_version=SIMV)
    assert not d.allowed and d.reason == "production_not_certified"


def test_connector_certification_required(identity, config, tmp_path):
    vs = _vstore(tmp_path)
    verify_provider(identity.provider_id, identity=identity, config=config, simulator_version=SIMV, store=vs)
    d = resolve_execution_eligibility(identity=identity, config=config, mode=ExecutionMode.SHADOW.value,
                                      connector_certified=False, verification_store=vs, simulator_version=SIMV)
    assert not d.allowed and d.reason == "connector_not_certified"


def test_provider_verification_required(identity, config, tmp_path):
    vs = _vstore(tmp_path)  # not verified
    d = resolve_execution_eligibility(identity=identity, config=config, mode=ExecutionMode.SHADOW.value,
                                      verification_store=vs, simulator_version=SIMV)
    assert not d.allowed and d.reason.startswith("verification:")


def test_approval_required(identity, config, tmp_path):
    vs = _vstore(tmp_path)
    verify_provider(identity.provider_id, identity=identity, config=config, simulator_version=SIMV, store=vs)
    d = resolve_execution_eligibility(identity=identity, config=config, mode=ExecutionMode.SHADOW.value,
                                      approval_valid=False, verification_store=vs, simulator_version=SIMV)
    assert not d.allowed and d.reason == "approval_invalid"


def test_caller_cannot_bypass_eligibility(identity, config, tmp_path):
    vs = _vstore(tmp_path)
    verify_provider(identity.provider_id, identity=identity, config=config, simulator_version=SIMV, store=vs)
    d = resolve_execution_eligibility(identity=identity, config=config, mode=ExecutionMode.SHADOW.value,
                                      verification_store=vs, simulator_version=SIMV,
                                      caller_metadata={"force_verified": True})
    assert not d.allowed and d.reason == "caller_override_rejected"


def test_eligibility_read_does_not_mutate_verification_store(identity, config, tmp_path):
    vs = _vstore(tmp_path)
    verify_provider(identity.provider_id, identity=identity, config=config, simulator_version=SIMV, store=vs)
    # drift the read; store must remain verified (M31 correction preserved)
    resolve_execution_eligibility(identity=identity, config=config, mode=ExecutionMode.SHADOW.value,
                                  verification_store=vs, simulator_version="DRIFTED")
    assert vs.get(identity.provider_id).state == "SIMULATION_VERIFIED"


def test_canary_active_ineligible(identity, config, tmp_path):
    vs = _vstore(tmp_path)
    verify_provider(identity.provider_id, identity=identity, config=config, simulator_version=SIMV, store=vs)
    for mode in (ExecutionMode.CANARY.value, ExecutionMode.ACTIVE.value):
        d = resolve_execution_eligibility(identity=identity, config=config, mode=mode,
                                          verification_store=vs, simulator_version=SIMV)
        assert not d.allowed and "mode_prohibited" in d.reason


# ── Failure injection (117-128 subset) ───────────────────────────────────────
def test_connection_failure_fails_closed(identity, config):
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, config), _ctx(identity, "connection_failure"), config)
    assert res.status == ProviderStatus.ERROR.value and res.error_code == ProviderErrorCode.CONNECTION_FAILED.value


def test_500_and_429_classify(identity, config):
    rt = ProviderExecutionRuntime()
    r500 = rt.execute(_adapter(identity, config), _ctx(identity, "server_error"), config)
    r429 = rt.execute(_adapter(identity, config), _ctx(identity, "rate_limited"), config)
    assert r500.error_code == ProviderErrorCode.PROVIDER_UNAVAILABLE.value
    assert r429.error_code == ProviderErrorCode.RATE_LIMITED.value


def test_partial_not_false_success(identity, config):
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, config), _ctx(identity, "partial_success"), config)
    assert res.status == ProviderStatus.PARTIAL.value and not res.ok


def test_oversized_response_fails_closed(identity, config):
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, config), _ctx(identity, "oversized"), config)
    assert res.status == ProviderStatus.ERROR.value and res.error_code == ProviderErrorCode.MALFORMED_RESPONSE.value


def test_forbidden_headers_stripped_from_result(identity, config):
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, config), _ctx(identity, "forbidden_headers"), config)
    blob = json.dumps(res.to_dict()).lower()
    assert "set-cookie" not in blob and "bearer" not in blob and "synthetic-token" not in blob


# ── Repository invariants (141-158) ──────────────────────────────────────────
def test_no_raw_response_escapes_boundary(identity, config):
    rt = ProviderExecutionRuntime()
    res = rt.execute(_adapter(identity, config), _ctx(identity, "success"), config)
    # normalized_data only; no raw transport object
    assert isinstance(res.normalized_data, dict)


def test_trading_guardian_unengaged_in_stores(tmp_path, identity, config):
    vs = _vstore(tmp_path)
    verify_provider(identity.provider_id, identity=identity, config=config, simulator_version=SIMV, store=vs)
    data = json.loads((tmp_path / "v.json").read_text())
    assert data["trading_guardian"] == "UNCHANGED / UNENGAGED"


def test_side_effect_ceiling_read_only(identity):
    assert identity.side_effect_class in (
        ProviderSideEffectClass.READ_ONLY.value, ProviderSideEffectClass.NONE.value,
    )
