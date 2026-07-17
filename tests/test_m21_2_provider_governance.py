"""M21.2 — Provider availability, cost, failover, circuit-breaker governance."""
from __future__ import annotations

import ast
import inspect
import os
import time
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest import mock

import pytest

from saathi.inference.availability import (
    AvailabilityState,
    evaluate_availability,
    most_severe_state,
)
from saathi.inference.bypass_guard import scan_repository
from saathi.inference.caller_policy import get_caller_policy, is_governed_callable
from saathi.inference.circuit_breaker import (
    CircuitConfig,
    CircuitState,
    ProviderCircuitBreakerRegistry,
    get_circuit_registry,
)
from saathi.inference.contract import privacy_safe_telemetry, validate_contract
from saathi.inference.cost_policy import (
    CostStatus,
    PricingMetadata,
    estimate_cost,
    enforce_cost_policy,
    validate_pricing,
)
from saathi.inference.failure_taxonomy import (
    FailureType,
    classify_exception,
    get_failure_spec,
    redact_error_message,
    taxonomy_snapshot,
)
from saathi.inference.provider_decision import (
    decide_failover,
    decide_providers,
    decide_retry,
    match_capabilities,
    privacy_safe_decision_telemetry,
    record_provider_outcome,
)
from saathi.inference.provider_descriptor import (
    assert_unique_provider_ids,
    descriptor_from_policy,
    get_descriptor,
    list_descriptors,
    validate_descriptor,
)
from saathi.inference.provider_policy import PROVIDER_POLICIES, get_provider_policy
from saathi.inference.request import InferenceRequest, Sensitivity
from saathi.inference.residual_paths import ResidualDisposition, get_residual_control


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def fresh_circuits():
    reg = ProviderCircuitBreakerRegistry(
        config=CircuitConfig(failure_threshold=3, cooldown_seconds=10.0),
        clock=lambda: 1000.0,
    )
    return reg


def _req(**kwargs) -> InferenceRequest:
    base = dict(
        prompt="hello world",
        caller_component="test_m21",
        max_output_tokens=64,
        timeout_seconds=15.0,
        local_only=True,
        max_retries=0,
        fallback_policy="none",
    )
    base.update(kwargs)
    return InferenceRequest(**base)


# ── Provider metadata ─────────────────────────────────────────────────────


def test_local_descriptor_valid():
    d = get_descriptor("ollama")
    assert d is not None
    assert d.local_or_cloud == "local"
    assert d.pricing.zero_marginal is True
    assert validate_descriptor(d) == []


def test_cloud_descriptor_valid():
    d = get_descriptor("anthropic")
    assert d is not None
    assert d.local_or_cloud == "cloud"
    assert d.production_supported is False
    assert validate_descriptor(d) == []


def test_missing_provider_id_denied():
    pol = get_provider_policy("ollama")
    d = descriptor_from_policy(pol)
    bad = replace(d, provider_id="")
    assert "missing_provider_id" in validate_descriptor(bad)


def test_duplicate_provider_ids_denied():
    assert_unique_provider_ids()  # does not raise
    ids = [p.family_id for p in PROVIDER_POLICIES]
    assert len(ids) == len(set(ids))


def test_unknown_provider_class_denied():
    d = get_descriptor("ollama")
    bad = replace(d, provider_class="spaceship")
    assert "unknown_provider_class" in validate_descriptor(bad)


def test_invalid_capability_declaration():
    d = get_descriptor("ollama")
    bad = replace(d, supported_capabilities=())
    assert "invalid_capability_declaration" in validate_descriptor(bad)


def test_invalid_token_limits():
    d = get_descriptor("ollama")
    assert "invalid_max_context_tokens" in validate_descriptor(replace(d, max_context_tokens=0))
    assert "invalid_max_output_tokens" in validate_descriptor(replace(d, max_output_tokens=0))


def test_invalid_timeout():
    d = get_descriptor("ollama")
    assert "invalid_timeout" in validate_descriptor(replace(d, default_timeout_seconds=-1))


def test_invalid_price():
    p = PricingMetadata(input_cost_per_million="-1", known=True)
    assert any("negative" in e for e in validate_pricing(p))
    p2 = PricingMetadata(input_cost_per_million="not-a-number", known=True)
    assert any("malformed" in e for e in validate_pricing(p2))


def test_invalid_currency():
    p = PricingMetadata(currency="XYZ", input_cost_per_million="1", known=True)
    assert any("unsupported_currency" in e for e in validate_pricing(p))


def test_fake_provider_production_denied():
    req = _req()
    dec = decide_providers(req, production_context=True, master_inference_enabled=True)
    fake = next(c for c in dec.candidates if c.provider_id == "fake")
    assert fake.eligible is False
    assert fake.availability.state in {
        AvailabilityState.FAKE,
        AvailabilityState.DISABLED,
        AvailabilityState.TEST_ONLY,
    }


def test_uncertified_cloud_not_selected_production():
    req = _req(local_only=False, cloud_allowed=True, cloud_fallback_permitted=True)
    dec = decide_providers(
        req, production_context=True, allow_cloud_fallback=True, master_inference_enabled=True
    )
    if dec.ok:
        d = get_descriptor(dec.selected_provider_id)
        assert d is not None
        assert d.local_or_cloud != "cloud" or d.production_supported


# ── Availability ──────────────────────────────────────────────────────────


def test_enabled_healthy_available():
    dec = evaluate_availability(
        "ollama",
        policy_enabled=True,
        configured=True,
        credential_required=False,
        credential_present=None,
        production_supported=True,
        production_context=False,
        provider_class="local",
        killed=False,
        circuit_open=False,
        health_probe=lambda _: {"reachable": True, "healthy": True, "reason": "ok", "tier": "injected"},
    )
    assert dec.state is AvailabilityState.AVAILABLE


def test_disabled_provider():
    dec = evaluate_availability(
        "x",
        policy_enabled=False,
        configured=True,
        credential_required=False,
        credential_present=True,
        production_supported=True,
        production_context=False,
        provider_class="local",
        killed=False,
        circuit_open=False,
    )
    assert dec.state is AvailabilityState.DISABLED


def test_global_kill(monkeypatch):
    monkeypatch.setenv("SAATHI_INFERENCE_KILL_ALL", "1")
    req = _req()
    d = decide_providers(req, master_inference_enabled=True)
    assert d.ok is False
    assert d.reason_code == "kill_switch_active"


def test_provider_kill(monkeypatch):
    monkeypatch.delenv("SAATHI_INFERENCE_KILL_ALL", raising=False)
    monkeypatch.setenv("SAATHI_PROVIDER_KILL_OLLAMA", "1")
    dec = evaluate_availability(
        "ollama",
        policy_enabled=True,
        configured=True,
        credential_required=False,
        credential_present=None,
        production_supported=True,
        production_context=False,
        provider_class="local",
        killed=True,
        circuit_open=False,
    )
    assert dec.state is AvailabilityState.KILLED


def test_missing_credential_misconfigured():
    dec = evaluate_availability(
        "anthropic",
        policy_enabled=True,
        configured=True,
        credential_required=True,
        credential_present=False,
        production_supported=False,
        production_context=False,
        provider_class="cloud",
        killed=False,
        circuit_open=False,
    )
    assert dec.state is AvailabilityState.MISCONFIGURED


def test_missing_runtime_unavailable():
    dec = evaluate_availability(
        "ollama",
        policy_enabled=True,
        configured=True,
        credential_required=False,
        credential_present=None,
        production_supported=True,
        production_context=False,
        provider_class="local",
        killed=False,
        circuit_open=False,
        health_probe=lambda _: {
            "reachable": False,
            "healthy": False,
            "reason": "down",
            "tier": "injected",
        },
    )
    assert dec.state is AvailabilityState.UNAVAILABLE


def test_unknown_health_not_available_in_production():
    dec = evaluate_availability(
        "ollama",
        policy_enabled=True,
        configured=True,
        credential_required=False,
        credential_present=None,
        production_supported=True,
        production_context=True,
        provider_class="local",
        killed=False,
        circuit_open=False,
        health_probe=lambda _: {
            "reachable": None,
            "healthy": None,
            "reason": "none",
            "tier": "none",
        },
    )
    assert dec.state is AvailabilityState.UNKNOWN
    assert dec.state is not AvailabilityState.AVAILABLE


def test_degraded_distinguishable():
    dec = evaluate_availability(
        "ollama",
        policy_enabled=True,
        configured=True,
        credential_required=False,
        credential_present=None,
        production_supported=True,
        production_context=False,
        provider_class="local",
        killed=False,
        circuit_open=False,
        degraded=True,
        health_probe=lambda _: {
            "reachable": True,
            "healthy": True,
            "reason": "ok",
            "tier": "injected",
        },
    )
    assert dec.state is AvailabilityState.DEGRADED


def test_circuit_open_state():
    dec = evaluate_availability(
        "ollama",
        policy_enabled=True,
        configured=True,
        credential_required=False,
        credential_present=None,
        production_supported=True,
        production_context=False,
        provider_class="local",
        killed=False,
        circuit_open=True,
    )
    assert dec.state is AvailabilityState.CIRCUIT_OPEN


def test_availability_precedence():
    assert most_severe_state(
        AvailabilityState.AVAILABLE, AvailabilityState.KILLED
    ) is AvailabilityState.KILLED
    assert most_severe_state(
        AvailabilityState.DISABLED, AvailabilityState.UNAVAILABLE
    ) is AvailabilityState.DISABLED


# ── Capability matching ───────────────────────────────────────────────────


def test_streaming_mismatch():
    d = get_descriptor("fake")
    req = _req(streaming_requested=True)
    m = match_capabilities(d, req)
    assert m.ok is False
    assert m.reason_code == "streaming_mismatch"


def test_tool_use_mismatch():
    d = get_descriptor("ollama")
    req = _req(tool_use_permitted=True)
    m = match_capabilities(d, req)
    assert m.ok is False
    assert m.reason_code == "tool_use_mismatch"


def test_structured_output_mismatch():
    d = get_descriptor("ollama")
    req = _req(structured_output_schema="MySchema")
    m = match_capabilities(d, req)
    assert m.ok is False


def test_output_limit_mismatch():
    d = get_descriptor("ollama")
    req = _req(max_output_tokens=d.max_output_tokens + 1)
    m = match_capabilities(d, req)
    assert m.ok is False
    assert m.reason_code == "output_limit_mismatch"


def test_privacy_mismatch_cloud_sensitive():
    d = get_descriptor("anthropic")
    req = _req(sensitivity=Sensitivity.SENSITIVE, local_only=False)
    m = match_capabilities(d, req)
    assert m.ok is False


def test_local_only_blocks_cloud():
    d = get_descriptor("openai")
    req = _req(local_only=True)
    m = match_capabilities(d, req)
    assert m.ok is False
    assert m.reason_code == "local_only_cloud"


def test_provider_override_denied():
    d = get_descriptor("ollama")
    req = _req(metadata={"force_provider": "anthropic"})
    m = match_capabilities(d, req)
    assert m.ok is False
    assert m.reason_code == "caller_provider_override_denied"


def test_capability_ok_local():
    d = get_descriptor("ollama")
    req = _req()
    assert match_capabilities(d, req).ok is True


# ── Cost ──────────────────────────────────────────────────────────────────


def test_known_cost_deterministic():
    p = PricingMetadata(
        currency="USD",
        input_cost_per_million="1.00",
        output_cost_per_million="2.00",
        request_fixed_cost="0",
        known=True,
        cost_confidence="known",
        cost_source="test",
        cost_updated_at=time.time(),
    )
    a = estimate_cost(p, input_tokens=1_000_000, output_tokens_ceiling=1_000_000)
    b = estimate_cost(p, input_tokens=1_000_000, output_tokens_ceiling=1_000_000)
    assert a.estimated_total == b.estimated_total
    assert Decimal(a.estimated_total) == Decimal("3.00")


def test_zero_marginal_local():
    d = get_descriptor("ollama")
    est = estimate_cost(d.pricing, input_tokens=500, output_tokens_ceiling=100)
    assert est.status is CostStatus.ZERO_MARGINAL
    assert est.estimated_total == "0"


def test_unknown_paid_blocks_fallback():
    p = PricingMetadata(known=False, cost_confidence="unknown")
    est = estimate_cost(p, input_tokens=100, output_tokens_ceiling=50)
    v = enforce_cost_policy(est, paid_provider=True, cloud_fallback=True)
    assert v.allowed is False
    assert v.reason_code == "unknown_pricing"


def test_stale_pricing_blocks_cloud():
    p = PricingMetadata(
        currency="USD",
        input_cost_per_million="1",
        output_cost_per_million="1",
        known=True,
        cost_confidence="stale",
        cost_source="external",
        cost_updated_at=1.0,
    )
    est = estimate_cost(p, input_tokens=100, output_tokens_ceiling=50, now=time.time())
    v = enforce_cost_policy(est, paid_provider=True, cloud_fallback=True)
    assert v.allowed is False
    assert v.reason_code == "stale_pricing"


def test_request_ceiling_enforced():
    p = PricingMetadata(
        currency="USD",
        input_cost_per_million="1000",
        output_cost_per_million="1000",
        known=True,
        cost_confidence="known",
        cost_source="test",
        cost_updated_at=time.time(),
    )
    est = estimate_cost(p, input_tokens=1_000_000, output_tokens_ceiling=1_000_000)
    v = enforce_cost_policy(est, request_ceiling="0.50", paid_provider=True)
    assert v.allowed is False
    assert "ceiling" in v.reason_code


def test_caller_ceiling_enforced():
    p = PricingMetadata(
        currency="USD",
        input_cost_per_million="10",
        output_cost_per_million="10",
        known=True,
        cost_confidence="known",
        cost_source="test",
        cost_updated_at=time.time(),
    )
    est = estimate_cost(p, input_tokens=1_000_000, output_tokens_ceiling=0)
    v = enforce_cost_policy(est, caller_ceiling="1", paid_provider=True)
    assert v.allowed is False


def test_cost_uses_decimal_not_float_enforcement():
    p = PricingMetadata(
        currency="USD",
        input_cost_per_million="0.1",
        output_cost_per_million="0.2",
        known=True,
        cost_confidence="known",
        cost_source="test",
        cost_updated_at=time.time(),
    )
    est = estimate_cost(p, input_tokens=3, output_tokens_ceiling=7)
    assert isinstance(Decimal(est.estimated_total), Decimal)
    # string representation — no binary float in enforcement path
    assert est.estimated_total == str(Decimal(est.estimated_total))


def test_malformed_price_fails_closed():
    p = PricingMetadata(input_cost_per_million="??", known=True)
    est = estimate_cost(p, input_tokens=10, output_tokens_ceiling=10)
    v = enforce_cost_policy(est, paid_provider=True)
    assert v.allowed is False


def test_currency_mismatch_fails_closed():
    est = estimate_cost(
        PricingMetadata(
            currency="EUR",
            input_cost_per_million="1",
            output_cost_per_million="1",
            known=True,
            cost_confidence="known",
            cost_source="test",
            cost_updated_at=time.time(),
        ),
        input_tokens=1,
        output_tokens_ceiling=1,
    )
    # invalid currency becomes unknown/invalid path
    v = enforce_cost_policy(est, paid_provider=True)
    assert v.allowed is False


def test_retry_cost_within_ceiling():
    p = PricingMetadata(
        currency="USD",
        input_cost_per_million="1",
        output_cost_per_million="1",
        known=True,
        cost_confidence="known",
        cost_source="test",
        cost_updated_at=time.time(),
    )
    est = estimate_cost(p, input_tokens=1000, output_tokens_ceiling=1000)
    v = enforce_cost_policy(est, request_ceiling="10", paid_provider=True)
    assert v.allowed is True
    # decide_retry respects cost_remaining_ok
    r = decide_retry(FailureType.PROVIDER_TIMEOUT, attempt=0, max_retries=1, cost_remaining_ok=False)
    assert r.allow is False
    assert r.reason_code == "cost_ceiling"


# ── Failure taxonomy ──────────────────────────────────────────────────────


def test_timeout_retryable():
    s = get_failure_spec(FailureType.PROVIDER_TIMEOUT)
    assert s.retryable is True
    assert s.failure_class.value == "soft"


def test_privacy_hard():
    s = get_failure_spec(FailureType.PRIVACY_DENIED)
    assert s.failure_class.value == "hard"
    assert s.failover_eligible is False


def test_security_hard():
    s = get_failure_spec(FailureType.AUTHORIZATION_DENIED)
    assert s.failover_eligible is False


def test_kill_hard():
    s = get_failure_spec(FailureType.KILL_SWITCH_ACTIVE)
    assert s.retryable is False
    assert s.failover_eligible is False


def test_auth_failure_not_soft_fallback():
    s = get_failure_spec(FailureType.AUTHENTICATION_FAILED)
    assert s.failover_eligible is False
    assert s.retryable is False
    assert s.circuit_impact is True


def test_rate_limit_deterministic():
    s = get_failure_spec(FailureType.RATE_LIMITED)
    assert s.retryable is True
    assert s.circuit_impact is True


def test_model_not_found():
    s = get_failure_spec(FailureType.MODEL_NOT_FOUND)
    assert s.same_provider_retry is False


def test_context_limit_no_blind_failover():
    s = get_failure_spec(FailureType.CONTEXT_LIMIT_EXCEEDED)
    assert s.failover_eligible is False


def test_unknown_provider_conservative():
    s = get_failure_spec(FailureType.UNKNOWN_PROVIDER_ERROR)
    assert s.failover_eligible is False
    assert s.retryable is False


def test_redacted_error():
    msg = redact_error_message("auth failed api_key=sk-abc123secret bearer xyz")
    assert "sk-abc" not in msg
    assert "REDACTED" in msg or "api_key" not in msg.lower() or "[REDACTED]" in msg


def test_classify_timeout():
    assert classify_exception(TimeoutError("timed out")) is FailureType.PROVIDER_TIMEOUT


# ── Retry ─────────────────────────────────────────────────────────────────


def test_default_retry_zero():
    r = decide_retry(FailureType.PROVIDER_TIMEOUT, attempt=0, max_retries=0)
    assert r.allow is False
    assert r.reason_code == "max_retries_zero"


def test_retryable_when_allowed():
    r = decide_retry(FailureType.PROVIDER_TIMEOUT, attempt=0, max_retries=2)
    assert r.allow is True
    assert r.delay_seconds > 0


def test_hard_never_retries():
    r = decide_retry(FailureType.PRIVACY_DENIED, attempt=0, max_retries=5)
    assert r.allow is False


def test_retry_bounded():
    r = decide_retry(FailureType.PROVIDER_TIMEOUT, attempt=2, max_retries=2)
    assert r.allow is False
    assert r.reason_code == "retry_exhausted"


def test_backoff_deterministic():
    a = decide_retry(FailureType.PROVIDER_TIMEOUT, attempt=0, max_retries=5)
    b = decide_retry(FailureType.PROVIDER_TIMEOUT, attempt=0, max_retries=5)
    assert a.delay_seconds == b.delay_seconds


# ── Failover ──────────────────────────────────────────────────────────────


def test_default_fallback_off():
    dec = decide_providers(_req(fallback_policy="none"), master_inference_enabled=True)
    assert dec.fallback_permitted is False
    assert dec.cloud_fallback_permitted is False


def test_local_to_cloud_denied_default():
    dec = decide_providers(_req(), master_inference_enabled=True)
    fo = decide_failover(
        FailureType.PROVIDER_UNREACHABLE,
        dec,
        failed_provider_id="ollama",
        request_allows_fallback=True,
        caller_allows_fallback=True,
    )
    # fallback_permitted false on decision
    assert fo.allow is False


def test_privacy_never_failover():
    dec = decide_providers(_req(), master_inference_enabled=True)
    fo = decide_failover(
        FailureType.PRIVACY_DENIED,
        replace(dec, fallback_permitted=True) if hasattr(dec, "__dataclass_fields__") else dec,
        failed_provider_id="ollama",
        request_allows_fallback=True,
        caller_allows_fallback=True,
    )
    # Use a decision with fallback forced for taxonomy check
    from dataclasses import replace as dc_replace

    dec2 = dc_replace(dec, fallback_permitted=True)
    fo = decide_failover(
        FailureType.PRIVACY_DENIED,
        dec2,
        failed_provider_id="ollama",
        request_allows_fallback=True,
        caller_allows_fallback=True,
    )
    assert fo.allow is False


def test_cost_never_failover():
    from dataclasses import replace as dc_replace

    dec = dc_replace(
        decide_providers(_req(), master_inference_enabled=True),
        fallback_permitted=True,
    )
    fo = decide_failover(
        FailureType.COST_DENIED,
        dec,
        failed_provider_id="ollama",
        request_allows_fallback=True,
        caller_allows_fallback=True,
    )
    assert fo.allow is False


def test_kill_never_failover():
    from dataclasses import replace as dc_replace

    dec = dc_replace(
        decide_providers(_req(), master_inference_enabled=True),
        fallback_permitted=True,
    )
    fo = decide_failover(
        FailureType.KILL_SWITCH_ACTIVE,
        dec,
        failed_provider_id="ollama",
        request_allows_fallback=True,
        caller_allows_fallback=True,
    )
    assert fo.allow is False


def test_ranking_stable():
    a = decide_providers(_req(), master_inference_enabled=True)
    b = decide_providers(_req(), master_inference_enabled=True)
    assert [c.provider_id for c in a.candidates] == [c.provider_id for c in b.candidates]
    assert a.selected_provider_id == b.selected_provider_id


def test_tie_break_deterministic():
    # scores include provider_id as last key
    a = decide_providers(_req(), master_inference_enabled=True)
    assert a.candidates[0].score[-1] == a.candidates[0].provider_id


# ── Circuit breaker ───────────────────────────────────────────────────────


def test_circuit_initial_closed(fresh_circuits):
    assert fresh_circuits.state("ollama") is CircuitState.CLOSED


def test_circuit_opens_at_threshold(fresh_circuits):
    for _ in range(3):
        fresh_circuits.record_failure("ollama", reason="timeout")
    assert fresh_circuits.state("ollama") is CircuitState.OPEN


def test_open_blocks_request(fresh_circuits):
    for _ in range(3):
        fresh_circuits.record_failure("ollama")
    ok, reason = fresh_circuits.allow_request("ollama")
    assert ok is False
    assert reason == "circuit_open"


def test_cooldown_half_open():
    t = {"now": 1000.0}
    reg = ProviderCircuitBreakerRegistry(
        config=CircuitConfig(failure_threshold=2, cooldown_seconds=5.0),
        clock=lambda: t["now"],
    )
    reg.record_failure("ollama")
    reg.record_failure("ollama")
    assert reg.state("ollama") is CircuitState.OPEN
    t["now"] = 1006.0
    assert reg.state("ollama") is CircuitState.HALF_OPEN


def test_success_closes():
    t = {"now": 1000.0}
    reg = ProviderCircuitBreakerRegistry(
        config=CircuitConfig(failure_threshold=2, cooldown_seconds=5.0),
        clock=lambda: t["now"],
    )
    reg.record_failure("ollama")
    reg.record_failure("ollama")
    t["now"] = 1006.0
    assert reg.allow_request("ollama")[0] is True
    reg.record_success("ollama")
    assert reg.state("ollama") is CircuitState.CLOSED


def test_failed_probe_reopens():
    t = {"now": 1000.0}
    reg = ProviderCircuitBreakerRegistry(
        config=CircuitConfig(failure_threshold=2, cooldown_seconds=5.0),
        clock=lambda: t["now"],
    )
    reg.record_failure("ollama")
    reg.record_failure("ollama")
    t["now"] = 1006.0
    reg.allow_request("ollama")
    reg.record_failure("ollama", reason="still_down")
    assert reg.state("ollama") is CircuitState.OPEN


def test_manual_reset(fresh_circuits):
    for _ in range(5):
        fresh_circuits.record_failure("ollama")
    fresh_circuits.manual_reset("ollama")
    assert fresh_circuits.state("ollama") is CircuitState.CLOSED


def test_policy_denial_no_circuit_count(fresh_circuits):
    record_provider_outcome(
        "ollama", FailureType.PRIVACY_DENIED, success=False, circuits=fresh_circuits
    )
    assert fresh_circuits.snapshot("ollama").failure_count == 0


def test_invalid_request_no_circuit(fresh_circuits):
    record_provider_outcome(
        "ollama", FailureType.INVALID_REQUEST, success=False, circuits=fresh_circuits
    )
    assert fresh_circuits.snapshot("ollama").failure_count == 0


def test_kill_precedence_over_circuit(monkeypatch, fresh_circuits):
    monkeypatch.setenv("SAATHI_INFERENCE_KILL_ALL", "1")
    # circuit closed but kill wins at decision
    d = decide_providers(_req(), master_inference_enabled=True, circuits=fresh_circuits)
    assert d.ok is False
    assert d.reason_code == "kill_switch_active"


def test_circuit_telemetry_safe(fresh_circuits):
    fresh_circuits.record_failure("ollama", reason="timeout")
    tel = fresh_circuits.drain_telemetry()
    blob = str(tel)
    assert "prompt" not in blob or "schema" in blob
    assert "api_key" not in blob


# ── cheap_ask ─────────────────────────────────────────────────────────────


def test_cheap_ask_api_compatible():
    from saathi.tools.cheap_llm import cheap_ask

    # With mocks — public API returns dict
    with mock.patch("saathi.tools.cheap_llm._provider_decision_gate", return_value=None):
        with mock.patch("saathi.tools.cheap_llm._kill_blocks", return_value=False):
            with mock.patch(
                "saathi.inference.compat.cheap_ask_adopted",
                side_effect=Exception("skip"),
            ):
                with mock.patch("saathi.llm.generate", side_effect=Exception("no llm")):
                    out = cheap_ask("hi")
    assert isinstance(out, dict)
    assert "error" in out or "reply" in out


def test_cheap_ask_proxy_blocked_in_source():
    src = Path("saathi/tools/cheap_llm.py").read_text()
    assert "httpx.post" not in src or "CHEAP_PROXY" not in src.split("def cheap_ask")[1].split("def cheap_proxy")[0]
    # body of cheap_ask must not call proxy post
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "cheap_ask":
            text = ast.get_source_segment(src, node) or ""
            assert "httpx.post" not in text
            assert "/v1/messages" not in text


def test_cheap_ask_kill_all(monkeypatch):
    monkeypatch.setenv("SAATHI_INFERENCE_KILL_ALL", "1")
    from saathi.tools.cheap_llm import cheap_ask

    out = cheap_ask("hi")
    assert "error" in out
    assert out.get("reason_code") == "kill_switch_active" or "KILL_ALL" in str(out.get("error", ""))


def test_cheap_ask_no_silent_cloud():
    from saathi.tools.cheap_llm import _provider_decision_gate

    # gate never returns a cloud selection as success
    # (returns None to continue or error dict)
    r = _provider_decision_gate("hi", "sys", 32)
    if r is not None and r.get("selected_provider_id"):
        d = get_descriptor(r["selected_provider_id"])
        if d:
            assert d.local_or_cloud != "cloud"


# ── Transitional caller ───────────────────────────────────────────────────


def test_unknown_caller_test_cert():
    # M21.3: transitional unknown is FORBIDDEN/disabled (no production acceptance)
    pol = get_caller_policy("unknown")
    assert pol is not None
    assert pol.certification.value in {"test", "forbidden"}
    if pol.certification.value == "forbidden":
        assert pol.enabled is False


def test_unknown_caller_production_denied(monkeypatch):
    monkeypatch.setenv("SAATHI_PRODUCTION_POSTURE", "1")
    from saathi.inference.config import InferenceSettings

    req = InferenceRequest(prompt="x", caller_component="unknown", max_output_tokens=32)
    res = validate_contract(req, InferenceSettings(), governed=True)
    assert res.ok is False
    assert any("unknown" in v.code for v in res.violations)


def test_unknown_production_decision(monkeypatch):
    d = decide_providers(_req(caller_component="unknown"), production_context=True)
    assert d.ok is False
    assert d.reason_code == "unknown_caller"


def test_unknown_caller_fail_closed_unregistered():
    from saathi.inference.config import InferenceSettings

    req = InferenceRequest(prompt="x", caller_component="totally_new_zzz", max_output_tokens=32)
    res = validate_contract(req, InferenceSettings(), governed=True)
    assert res.ok is False


# ── Static guards ─────────────────────────────────────────────────────────


def test_bypass_guard_clean():
    rep = scan_repository()
    assert rep["ok"] is True
    assert rep["blocking_count"] == 0


def test_residual_proxy_blocked():
    ctrl = get_residual_control("cheap_ask_legacy_proxy")
    assert ctrl is not None
    assert ctrl.disposition is ResidualDisposition.BLOCK


def test_approved_adapter_exists():
    assert Path("saathi/inference/adapters/ollama.py").is_file()
    assert Path("saathi/inference/provider_decision.py").is_file()


# ── Privacy / TG ──────────────────────────────────────────────────────────


def test_decision_telemetry_no_prompt():
    dec = decide_providers(_req(prompt="SECRET_PROMPT_XYZ"), master_inference_enabled=True)
    tel = privacy_safe_decision_telemetry(dec)
    blob = str(tel)
    assert "SECRET_PROMPT_XYZ" not in blob
    assert "prompt" not in tel


def test_contract_telemetry_no_prompt():
    req = _req(prompt="SECRET_PROMPT_ABC")
    tel = privacy_safe_telemetry(req)
    assert "SECRET_PROMPT_ABC" not in str(tel)


def test_trading_guardian_forbidden():
    assert is_governed_callable("trading_guardian") is False
    pol = get_caller_policy("trading_guardian")
    assert pol is None or pol.certification.value == "forbidden" or not pol.enabled


def test_no_exchange_import_in_governance():
    for mod in (
        "saathi/inference/provider_decision.py",
        "saathi/inference/provider_governance.py",
        "saathi/inference/cost_policy.py",
        "saathi/inference/circuit_breaker.py",
    ):
        src = Path(mod).read_text()
        assert "ccxt" not in src
        assert "withdrawal" not in src.lower() or "no withdrawal" in src.lower()


def test_taxonomy_snapshot_schema():
    snap = taxonomy_snapshot()
    assert snap["schema"] == "m21.2.failure_taxonomy.v1"
    assert snap["count"] >= 20


def test_governance_cli_snapshot():
    from saathi.inference.provider_governance import governance_snapshot

    snap = governance_snapshot()
    assert snap["production_certified"] is False
    assert snap["cloud_fallback_default"] is False
    assert len(snap["providers"]) >= 5


def test_decide_selects_ollama_local_first():
    dec = decide_providers(_req(), master_inference_enabled=True)
    assert dec.ok is True
    assert dec.selected_provider_id == "ollama"


def test_cloud_not_implicit():
    dec = decide_providers(_req(), master_inference_enabled=True, allow_cloud_fallback=False)
    assert dec.cloud_fallback_permitted is False
    for c in dec.candidates:
        if c.provider_id != "ollama" and get_descriptor(c.provider_id).local_or_cloud == "cloud":
            assert c.eligible is False
