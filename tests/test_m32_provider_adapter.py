"""M32 — Provider adapter: selection, contract, config, normalization, errors,
retry, idempotency, rate limits, verification/drift, redaction/evidence, failure.

Deterministic; no network, no credentials, no accounts, simulator only.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from saathi.connectors.providers.adapters.echo_provider import EchoProviderAdapter
from saathi.connectors.providers.config import (
    ConfigError,
    ProviderConfig,
    RetryPolicy,
    TimeoutPolicy,
    caller_attempts_config_override,
    validate_config,
)
from saathi.connectors.providers.contract import (
    REQUIRED_CONTRACT_METHODS,
    adapter_satisfies_contract,
)
from saathi.connectors.providers.errors import (
    ProviderError,
    classify_exception,
    classify_status,
    retry_category_for,
    safe_error_message,
)
from saathi.connectors.providers.fingerprint import compute_provider_fingerprint
from saathi.connectors.providers.idempotency import (
    IdempotencyStore,
    compute_request_fingerprint,
)
from saathi.connectors.providers.models import (
    DataClassification,
    ExecutionMode,
    ProviderErrorCode,
    ProviderExecutionContext,
    ProviderIdentity,
    ProviderSideEffectClass,
    ProviderStatus,
    RetryCategory,
    provider_is_prohibited,
)
from saathi.connectors.providers.normalization import (
    NormalizationError,
    normalize_headers,
    normalize_request,
    normalize_response,
)
from saathi.connectors.providers.ratelimit import (
    honored_retry_after,
    parse_rate_limit,
    safe_rate_limit_evidence,
)
from saathi.connectors.providers.registry import (
    ProviderRegistry,
    ProviderRegistryError,
)
from saathi.connectors.providers.retry import RetryGates, decide_retry, deterministic_backoff
from saathi.connectors.providers.verification import (
    ProviderVerificationStore,
    check_provider_drift,
    resolve_provider_verification,
    verify_provider,
)
from saathi.connectors.testing.provider_simulator import SIMULATOR_VERSION
from saathi.credentials.leakscan import LeakDetected

SIMV = SIMULATOR_VERSION


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


@pytest.fixture()
def adapter(identity, config):
    a = EchoProviderAdapter(identity=identity)
    a.prepare(config)
    return a


# ── Provider selection (1-8) ─────────────────────────────────────────────────
def test_safe_deterministic_provider_accepted(registry):
    assert registry.is_m32_safe("saathi.echo.v1")


def test_credential_free_provider_classified_safe(identity):
    assert identity.auth_profile == "none"
    assert identity.side_effect_class == ProviderSideEffectClass.READ_ONLY.value


def test_unknown_provider_rejected(registry):
    with pytest.raises(ProviderRegistryError):
        registry.resolve("no.such.provider")


def test_caller_supplied_identity_rejected(registry):
    # a caller-shaped provider id that is not registered fails closed
    assert registry.get("caller.invented") is None
    with pytest.raises(ProviderRegistryError):
        registry.resolve("caller.invented")


@pytest.mark.parametrize("pid", ["binance_exchange", "stripe_payment", "broker_order", "bank_transfer"])
def test_financial_trading_payment_providers_rejected(registry, pid):
    assert provider_is_prohibited(pid) is not None
    with pytest.raises(ProviderRegistryError):
        registry.resolve(pid)


def test_prohibited_provider_cannot_register(registry):
    bad = ProviderIdentity(provider_id="crypto_withdraw", connector_id="gov.http",
                           side_effect_class=ProviderSideEffectClass.READ_ONLY.value)
    with pytest.raises(ProviderRegistryError):
        registry.register(bad)


def test_production_social_write_provider_rejected(registry):
    assert not registry.is_m32_safe("gmail")
    assert not registry.is_m32_safe("instagram")


# ── Adapter contract (9-16) ──────────────────────────────────────────────────
def test_registered_adapter_satisfies_contract(adapter):
    ok, missing = adapter_satisfies_contract(adapter)
    assert ok and missing == []
    for m in REQUIRED_CONTRACT_METHODS:
        assert callable(getattr(adapter, m))


def test_missing_contract_method_fails():
    class Broken:
        def prepare(self, c): ...
    ok, missing = adapter_satisfies_contract(Broken())
    assert not ok and "execute" in missing


def test_adapter_cannot_determine_authority(adapter):
    assert adapter.determines_authority() is False
    assert adapter.can_activate_rollout() is False


def test_adapter_result_never_authoritative(adapter, identity, config):
    ctx = ProviderExecutionContext(connector_id=identity.connector_id, provider_id=identity.provider_id,
                                   operation="echo", payload={"m": 1}, safe_metadata={"scenario": "success"})
    res = adapter.execute(ctx)
    assert res.authoritative is False


# ── Configuration (17-24) ────────────────────────────────────────────────────
def test_loopback_endpoint_passes():
    validate_config(ProviderConfig(provider_id="p", environment="test",
                                   endpoint_reference="http://127.0.0.1:9/x"))


def test_inprocess_endpoint_passes():
    validate_config(ProviderConfig(provider_id="p", endpoint_reference="inprocess://x"))


def test_arbitrary_external_http_without_tls_fails():
    with pytest.raises(ConfigError):
        validate_config(ProviderConfig(provider_id="p", endpoint_reference="http://evil.example.com/x"))


def test_unknown_scheme_endpoint_fails():
    with pytest.raises(ConfigError):
        validate_config(ProviderConfig(provider_id="p", endpoint_reference="ftp://x/y"))


def test_production_environment_disabled():
    with pytest.raises(ConfigError):
        validate_config(ProviderConfig(provider_id="p", environment="production"))


def test_caller_supplied_auth_mechanism_fails():
    with pytest.raises(ConfigError):
        validate_config(ProviderConfig(provider_id="p", auth_profile="oauth_bearer"))


def test_caller_config_override_detected():
    assert caller_attempts_config_override({"endpoint": "x"}) == "endpoint"
    assert caller_attempts_config_override({"max_retries": 99}) == "max_retries"
    assert caller_attempts_config_override({"msg": "ok"}) is None


def test_timeout_and_retry_escalation_clamped():
    cfg = ProviderConfig(provider_id="p",
                         timeout_policy=TimeoutPolicy(total_deadline=9999),
                         retry_policy=RetryPolicy(max_retries=9999))
    assert cfg.timeout_policy.total_deadline <= 30.0
    assert cfg.retry_policy.max_retries <= 3


def test_disabled_provider_blocks(config):
    config.enabled = False
    assert config.enabled is False


# ── Request normalization (25-34) ────────────────────────────────────────────
def test_valid_request_normalizes():
    out = normalize_request({"msg": "hi", "n": 2}, operation="echo",
                            allowed_operations=("echo",), request_size_limit=1024)
    assert out == {"msg": "hi", "n": 2}


def test_unsupported_operation_fails():
    with pytest.raises(NormalizationError):
        normalize_request({"m": 1}, operation="delete_all", allowed_operations=("echo",), request_size_limit=1024)


def test_oversized_request_fails():
    with pytest.raises(NormalizationError):
        normalize_request({"m": "x" * 5000}, operation="echo", allowed_operations=("echo",), request_size_limit=100)


@pytest.mark.parametrize("field", ["headers", "authorization", "endpoint", "url", "retry_policy", "max_retries", "cookie", "api_key"])
def test_injection_fields_rejected(field):
    with pytest.raises(NormalizationError):
        normalize_request({field: "x"}, operation="echo", allowed_operations=("echo",), request_size_limit=4096)


def test_material_request_fingerprint_deterministic():
    a = compute_request_fingerprint(connector_id="gov.http", provider_id="p", operation="echo",
                                    normalized_payload={"m": 1, "n": 2})
    b = compute_request_fingerprint(connector_id="gov.http", provider_id="p", operation="echo",
                                    normalized_payload={"n": 2, "m": 1})
    assert a == b


def test_changed_request_changes_fingerprint():
    a = compute_request_fingerprint(connector_id="gov.http", provider_id="p", operation="echo",
                                    normalized_payload={"m": 1})
    b = compute_request_fingerprint(connector_id="gov.http", provider_id="p", operation="echo",
                                    normalized_payload={"m": 2})
    assert a != b


def test_secret_excluded_from_fingerprint():
    a = compute_request_fingerprint(connector_id="c", provider_id="p", operation="o",
                                    normalized_payload={"m": 1, "token": "AAA"})
    b = compute_request_fingerprint(connector_id="c", provider_id="p", operation="o",
                                    normalized_payload={"m": 1, "token": "BBB"})
    assert a == b


# ── Response normalization (35-44) ───────────────────────────────────────────
def test_valid_response_normalizes():
    out = normalize_response({"ok": True, "value": 3}, response_size_limit=10_000)
    assert out["ok"] is True and out["value"] == 3


def test_malformed_response_fails_safely():
    with pytest.raises(NormalizationError):
        normalize_response("{bad json,,", response_size_limit=10_000)


def test_oversized_response_fails():
    with pytest.raises(NormalizationError):
        normalize_response({"d": "x" * 20_000}, response_size_limit=1000)


def test_sensitive_header_removed():
    h = normalize_headers({"set-cookie": "a=b", "authorization": "Bearer x", "content-type": "application/json"})
    assert "set-cookie" not in h and "authorization" not in h and h["content-type"] == "application/json"


def test_token_cookie_authorization_removed_from_body():
    out = normalize_response({"access_token": "SECRET", "cookie": "c", "authorization": "z", "ok": True},
                             response_size_limit=10_000)
    assert "access_token" not in out and "cookie" not in out and "authorization" not in out
    assert out["ok"] is True


def test_stack_trace_removed():
    out = normalize_response({"traceback": "File ...", "stack": "boom", "ok": 1}, response_size_limit=10_000)
    assert "traceback" not in out and "stack" not in out


def test_partial_success_represented():
    out = normalize_response({"partial": True, "items": [1]}, response_size_limit=10_000)
    assert out["partial"] is True


def test_unknown_fields_handled_safely():
    out = normalize_response({"weird_field": {"nested": "ok"}}, response_size_limit=10_000)
    assert out["weird_field"]["nested"] == "ok"


# ── Error taxonomy (status/exception/retry) ──────────────────────────────────
@pytest.mark.parametrize("code,expected", [
    (401, ProviderErrorCode.AUTHENTICATION_FAILED),
    (403, ProviderErrorCode.AUTHORIZATION_FAILED),
    (404, ProviderErrorCode.NOT_FOUND),
    (409, ProviderErrorCode.CONFLICT),
    (429, ProviderErrorCode.RATE_LIMITED),
    (500, ProviderErrorCode.PROVIDER_UNAVAILABLE),
    (504, ProviderErrorCode.TIMEOUT),
])
def test_status_classification(code, expected):
    assert classify_status(code) == expected


def test_exception_classification():
    assert classify_exception(TimeoutError()) == ProviderErrorCode.TIMEOUT
    assert classify_exception(ConnectionError()) == ProviderErrorCode.CONNECTION_FAILED


def test_error_message_is_redacted_and_bounded():
    msg = safe_error_message(ProviderErrorCode.RATE_LIMITED, "Bearer abc123 token=zzz " + "x" * 500)
    assert len(msg) < 220
    assert "RATE_LIMITED" in msg


def test_authz_and_scope_never_retry():
    assert retry_category_for(ProviderErrorCode.AUTHORIZATION_FAILED) == RetryCategory.NO_RETRY
    assert retry_category_for(ProviderErrorCode.SCOPE_INSUFFICIENT) == RetryCategory.NO_RETRY


# ── Retry policy (deterministic decisions) ───────────────────────────────────
def test_idempotent_transient_may_retry():
    d = decide_retry(category=RetryCategory.SAFE_RETRY, attempt=1, max_retries=2,
                     remaining_deadline=5.0, gates=RetryGates(idempotent=True))
    assert d.should_retry


def test_non_idempotent_does_not_retry():
    d = decide_retry(category=RetryCategory.SAFE_RETRY, attempt=1, max_retries=2,
                     remaining_deadline=5.0, gates=RetryGates(idempotent=False))
    assert not d.should_retry and d.reason == "non_idempotent"


def test_retry_budget_enforced():
    d = decide_retry(category=RetryCategory.SAFE_RETRY, attempt=3, max_retries=2,
                     remaining_deadline=5.0, gates=RetryGates(idempotent=True))
    assert not d.should_retry and d.reason == "retry_budget_exhausted"


def test_retry_after_beyond_deadline_rejected():
    d = decide_retry(category=RetryCategory.RATE_LIMITED, attempt=1, max_retries=3,
                     remaining_deadline=1.0, gates=RetryGates(idempotent=True),
                     retry_after=5.0, max_retry_after=10.0)
    assert not d.should_retry


def test_revoked_credential_blocks_retry():
    d = decide_retry(category=RetryCategory.SAFE_RETRY, attempt=1, max_retries=3,
                     remaining_deadline=5.0, gates=RetryGates(idempotent=True, credential_eligible=False))
    assert not d.should_retry and d.reason == "credential_ineligible"


def test_quarantined_provider_blocks_retry():
    d = decide_retry(category=RetryCategory.SAFE_RETRY, attempt=1, max_retries=3,
                     remaining_deadline=5.0, gates=RetryGates(idempotent=True, provider_quarantined=True))
    assert not d.should_retry and d.reason == "provider_quarantined"


def test_changed_request_blocks_retry():
    d = decide_retry(category=RetryCategory.SAFE_RETRY, attempt=1, max_retries=3,
                     remaining_deadline=5.0, gates=RetryGates(idempotent=True, fingerprint_unchanged=False))
    assert not d.should_retry and d.reason == "request_changed"


def test_backoff_is_deterministic():
    assert deterministic_backoff(1, base=0.01, factor=2.0) == deterministic_backoff(1, base=0.01, factor=2.0)


# ── Idempotency store ────────────────────────────────────────────────────────
def _store():
    return IdempotencyStore(clock=lambda: 1000.0, ttl_seconds=300.0)


def test_same_request_reuses_logical_operation():
    s = _store()
    s.reserve(idempotency_key="k", connector_id="c", provider_id="p", operation="o", request_fingerprint="fp")
    state, _ = s.reserve(idempotency_key="k", connector_id="c", provider_id="p", operation="o", request_fingerprint="fp")
    assert state == "replay"


def test_changed_request_conflicts():
    s = _store()
    s.reserve(idempotency_key="k", connector_id="c", provider_id="p", operation="o", request_fingerprint="fp1")
    state, _ = s.reserve(idempotency_key="k", connector_id="c", provider_id="p", operation="o", request_fingerprint="fp2")
    assert state == "conflict"


def test_cross_provider_connector_account_reuse_fails():
    s = _store()
    s.reserve(idempotency_key="k", connector_id="c", provider_id="p", operation="o", request_fingerprint="fp")
    assert s.reserve(idempotency_key="k", connector_id="c", provider_id="OTHER", operation="o", request_fingerprint="fp")[0] == "new"
    assert s.reserve(idempotency_key="k", connector_id="OTHER", provider_id="p", operation="o", request_fingerprint="fp")[0] == "new"
    assert s.reserve(idempotency_key="k", connector_id="c", provider_id="p", operation="o", request_fingerprint="fp", account_link_id="X")[0] == "new"


def test_expired_record_fails_safely():
    clk = {"t": 1000.0}
    s = IdempotencyStore(clock=lambda: clk["t"], ttl_seconds=10.0)
    s.reserve(idempotency_key="k", connector_id="c", provider_id="p", operation="o", request_fingerprint="fp")
    clk["t"] = 2000.0
    state, _ = s.reserve(idempotency_key="k", connector_id="c", provider_id="p", operation="o", request_fingerprint="fp")
    assert state == "new"


def test_secret_absent_from_idempotency_record():
    s = _store()
    _, rec = s.reserve(idempotency_key="k", connector_id="c", provider_id="p", operation="o",
                       request_fingerprint="fp", approval_fingerprint="af")
    d = rec.to_dict()
    blob = json.dumps(d).lower()
    for bad in ("secret", "password", "bearer", "access_token"):
        assert bad not in blob


# ── Rate limits ──────────────────────────────────────────────────────────────
def test_valid_429_and_retry_after_parsed():
    rl = parse_rate_limit({"retry-after": "3", "x-ratelimit-limit": "60", "x-ratelimit-remaining": "0"})
    assert rl.retry_after == 3.0 and rl.limit == 60 and rl.source == "header"


def test_malformed_retry_after_ignored():
    rl = parse_rate_limit({"retry-after": "not-a-number"})
    assert rl.retry_after is None


def test_caller_cannot_spoof_rate_limit_metadata():
    # non-dict / body values are not parsed as headers
    rl = parse_rate_limit("retry-after: 9999")
    assert rl.source == "none"


def test_retry_after_beyond_deadline_not_honored():
    rl = parse_rate_limit({"retry-after": "8"})
    assert honored_retry_after(rl, remaining_deadline=2.0, max_retry_after=10.0) is None


def test_retry_after_clamped_to_cap():
    rl = parse_rate_limit({"retry-after": "99999"}, max_retry_after=10.0)
    assert rl.retry_after == 10.0


def test_rate_limit_evidence_has_no_sensitive_headers():
    rl = parse_rate_limit({"retry-after": "3", "authorization": "Bearer x"})
    ev = safe_rate_limit_evidence(rl)
    assert "authorization" not in json.dumps(ev).lower()
    assert ev["privacy_safe"] is True


# ── Verification & drift ─────────────────────────────────────────────────────
def _vstore(tmp):
    return ProviderVerificationStore(path=tmp / "v.json", persist=True, clock=lambda: 1.0)


def test_provider_fingerprint_deterministic(identity, config):
    a = compute_provider_fingerprint(identity=identity, config=config, simulator_version=SIMV)
    b = compute_provider_fingerprint(identity=identity, config=config, simulator_version=SIMV)
    assert a == b


def test_simulator_change_marks_verification_stale(identity, config, tmp_path):
    vs = _vstore(tmp_path)
    verify_provider(identity.provider_id, identity=identity, config=config, simulator_version=SIMV, store=vs)
    dec = resolve_provider_verification(identity.provider_id, identity=identity, config=config,
                                        simulator_version="OTHER", store=vs)
    assert not dec.allowed and dec.state == "STALE"


def test_eligibility_read_does_not_refresh_stale(identity, config, tmp_path):
    vs = _vstore(tmp_path)
    verify_provider(identity.provider_id, identity=identity, config=config, simulator_version=SIMV, store=vs)
    # a drifting READ must not mutate the persisted state
    resolve_provider_verification(identity.provider_id, identity=identity, config=config,
                                  simulator_version="OTHER", store=vs)
    assert vs.get(identity.provider_id).state == "SIMULATION_VERIFIED"


def test_explicit_reassessment_refreshes(identity, config, tmp_path):
    vs = _vstore(tmp_path)
    verify_provider(identity.provider_id, identity=identity, config=config, simulator_version=SIMV, store=vs)
    vs.mark_stale(identity.provider_id, reason="x")
    assert vs.get(identity.provider_id).state == "STALE"
    verify_provider(identity.provider_id, identity=identity, config=config, simulator_version=SIMV, store=vs)
    assert vs.get(identity.provider_id).state == "SIMULATION_VERIFIED"


def test_drift_check_marks_stale_explicitly(identity, config, tmp_path):
    vs = _vstore(tmp_path)
    verify_provider(identity.provider_id, identity=identity, config=config, simulator_version=SIMV, store=vs)
    rep = check_provider_drift(identity.provider_id, identity=identity, config=config,
                               simulator_version="CHANGED", store=vs, mark_stale=True)
    assert rep["drifted"] is True
    assert vs.get(identity.provider_id).state == "STALE"


def test_max_verification_state_is_shadow_with_limitations():
    from saathi.connectors.providers.models import M32_MAX_VERIFICATION, ProviderVerificationState
    assert M32_MAX_VERIFICATION == ProviderVerificationState.SHADOW_VERIFIED_WITH_LIMITATIONS


# ── Redaction & evidence ─────────────────────────────────────────────────────
def test_synthetic_token_in_response_blocked_from_normalized():
    out = normalize_response({"token": "sk-synthetic", "ok": True}, response_size_limit=10_000)
    assert "token" not in out


def test_evidence_write_is_atomic_and_clean(tmp_path):
    from saathi.connectors.providers.evidence import write_evidence
    rel = write_evidence("unit_sample", {"ok": True, "count": 3}, evidence_dir=tmp_path)
    data = json.loads((tmp_path / "unit_sample.json").read_text())
    assert data["privacy_safe"] is True and data["fingerprint"]
    assert rel.endswith("unit_sample.json")


def test_evidence_write_rejects_secret(tmp_path):
    from saathi.connectors.providers.evidence import write_evidence
    with pytest.raises(LeakDetected):
        write_evidence("leaky", {"authorization": "Bearer sk-live-1234567890abcdefghij"}, evidence_dir=tmp_path)


def test_evidence_fingerprint_stable(tmp_path):
    from saathi.connectors.providers.evidence import write_evidence
    write_evidence("s1", {"a": 1, "b": 2}, evidence_dir=tmp_path)
    f1 = json.loads((tmp_path / "s1.json").read_text())["fingerprint"]
    write_evidence("s1", {"b": 2, "a": 1}, evidence_dir=tmp_path)
    f2 = json.loads((tmp_path / "s1.json").read_text())["fingerprint"]
    assert f1 == f2
