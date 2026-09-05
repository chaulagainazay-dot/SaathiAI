"""FM-I6.2-MG-FIX — combined macOS memory gate injected-probe tests.

No live Ollama inference. All metrics injected.
"""
from __future__ import annotations

import time

import pytest

from saathi.agent_runtime.harness.audit import HarnessAuditLog
from saathi.agent_runtime.harness.errors import HarnessError, HarnessErrorCode
from saathi.agent_runtime.harness.local_model import LocalModelHarness
from saathi.agent_runtime.harness.local_model_memory_gate import (
    ABSOLUTE_RECLAIMABLE_MIB_FLOOR,
    COMPRESSOR_HARD_FRACTION,
    COMPRESSOR_SOFT_FRACTION,
    DARWIN_FREE_PERCENT_MIN,
    DEFAULT_PINNED_BUDGET,
    HYSTERESIS_MIB,
    MEMORY_GATE_POLICY_VERSION,
    PINNED_ESTIMATED_PEAK_MIB,
    PINNED_REQUIRED_HEADROOM_MIB,
    PINNED_SAFETY_FACTOR,
    CombinedMacOSMemoryGate,
    LocalModelMemoryBudget,
    MemoryGateReason,
    build_sample_from_raw,
    evaluate_memory_samples,
    make_sample,
)
from saathi.agent_runtime.harness.local_model_types import (
    LocalModelConfig,
    MemorySnapshot,
    PINNED_MODEL,
    PINNED_MODEL_DIGEST,
    PRODUCTION_CERTIFIED,
    RuntimeInventory,
    ModelInventoryEntry,
)
from saathi.agent_runtime.harness.local_model_transport import MockOllamaTransport, MockScript
from saathi.agent_runtime.harness.types import (
    HarnessBudget,
    HarnessSessionStartRequest,
)


def _healthy(**kwargs):
    """Healthy 8 GiB host with enough reclaimable for pinned budget + margin."""
    base = dict(
        physical_memory_bytes=8 * 1024 ** 3,
        darwin_free_percent=55.0,
        free_mib=200.0,
        inactive_mib=4500.0,
        speculative_mib=50.0,
        compressor_mib=400.0,  # ~4.9% of 8 GiB
        swap_used_mib=0.0,
        swapins=0,
        sampled_at=1_000_000.0,
        probe_valid=True,
    )
    base.update(kwargs)
    return make_sample(**base)


def _pair(s1_kw=None, s2_kw=None, delta_t: float = 2.5):
    s1 = _healthy(**(s1_kw or {}))
    s2k = dict(s1_kw or {})
    s2k.update(s2_kw or {})
    s2k.setdefault("sampled_at", s1.sampled_at + delta_t)
    s2 = _healthy(**s2k)
    return s1, s2


def _eval(s1, s2, **kwargs):
    return evaluate_memory_samples(
        s1,
        s2,
        budget=DEFAULT_PINNED_BUDGET,
        now=s2.sampled_at + 0.1,
        **kwargs,
    )


# ── Threshold consistency ───────────────────────────────────────────────────


def test_pinned_budget_matches_approved_decision():
    b = DEFAULT_PINNED_BUDGET
    assert b.model_name == PINNED_MODEL
    assert b.model_digest == PINNED_MODEL_DIGEST
    assert b.estimated_peak_mib == PINNED_ESTIMATED_PEAK_MIB
    assert b.safety_factor == PINNED_SAFETY_FACTOR
    assert b.peak_is_estimate is True
    assert abs(b.required_headroom_mib - PINNED_REQUIRED_HEADROOM_MIB) < 1.0
    assert b.required_headroom_mib >= ABSOLUTE_RECLAIMABLE_MIB_FLOOR
    assert abs(b.required_headroom_mib - (2681.0 * 1.5)) < 0.1
    assert PRODUCTION_CERTIFIED is False


# ── Core allow / deny ───────────────────────────────────────────────────────


def test_t01_normal_metrics_sufficient_headroom_allows():
    s1, s2 = _pair()
    d = _eval(s1, s2)
    assert d.allowed is True
    assert d.health_state == "MODEL_READY"
    assert d.denial_reasons == ()
    assert d.policy_version == MEMORY_GATE_POLICY_VERSION


def test_t02_pure_free_below_1_percent_but_healthy_allows():
    # free_mib=50 on 8 GiB ≈ 0.6% pure free — must not deny by pure free.
    s1, s2 = _pair(s1_kw={"free_mib": 50.0, "inactive_mib": 4600.0})
    d = _eval(s1, s2)
    assert d.allowed is True
    assert s1.pure_free_mib < 0.01 * 8192


def test_t03_darwin_free_below_20_denies():
    s1, s2 = _pair(s1_kw={"darwin_free_percent": 19.0}, s2_kw={"darwin_free_percent": 19.0})
    d = _eval(s1, s2)
    assert d.allowed is False
    assert MemoryGateReason.DARWIN_FREE_PERCENT_LOW in d.denial_reasons


def test_t04_reclaimable_below_2048_denies():
    s1, s2 = _pair(
        s1_kw={"free_mib": 100.0, "inactive_mib": 500.0, "speculative_mib": 10.0},
        s2_kw={"free_mib": 100.0, "inactive_mib": 500.0, "speculative_mib": 10.0},
    )
    assert s1.reclaimable_mib < ABSOLUTE_RECLAIMABLE_MIB_FLOOR
    d = _eval(s1, s2)
    assert d.allowed is False
    assert MemoryGateReason.ABSOLUTE_RECLAIMABLE_LOW in d.denial_reasons


def test_t05_reclaimable_above_2048_below_4022_denies():
    # ~2500 MiB reclaimable
    s1, s2 = _pair(
        s1_kw={"free_mib": 100.0, "inactive_mib": 2300.0, "speculative_mib": 100.0},
        s2_kw={"free_mib": 100.0, "inactive_mib": 2300.0, "speculative_mib": 100.0},
    )
    assert s1.reclaimable_mib > 2048
    assert s1.reclaimable_mib < PINNED_REQUIRED_HEADROOM_MIB
    d = _eval(s1, s2)
    assert d.allowed is False
    assert MemoryGateReason.MODEL_HEADROOM_LOW in d.denial_reasons


def test_t06_exactly_required_headroom_edge():
    # Exactly required — require >= so equal should allow (strict edge).
    need = DEFAULT_PINNED_BUDGET.required_headroom_mib
    s1, s2 = _pair(
        s1_kw={"free_mib": 0.0, "inactive_mib": need, "speculative_mib": 0.0},
        s2_kw={"free_mib": 0.0, "inactive_mib": need, "speculative_mib": 0.0},
    )
    d = _eval(s1, s2)
    assert abs(s1.reclaimable_mib - need) < 1.0
    assert d.allowed is True


def test_t07_hysteresis_after_prior_denial():
    need = DEFAULT_PINNED_BUDGET.required_headroom_mib
    # At required without hysteresis buffer → deny when prior_denial
    s1, s2 = _pair(
        s1_kw={"free_mib": 0.0, "inactive_mib": need, "speculative_mib": 0.0},
        s2_kw={"free_mib": 0.0, "inactive_mib": need, "speculative_mib": 0.0},
    )
    d = _eval(s1, s2, prior_denial=True)
    assert d.allowed is False
    assert MemoryGateReason.HYSTERESIS_NOT_SATISFIED in d.denial_reasons or (
        MemoryGateReason.MODEL_HEADROOM_LOW in d.denial_reasons
    )
    # With hysteresis buffer → allow
    s1b, s2b = _pair(
        s1_kw={"free_mib": 0.0, "inactive_mib": need + HYSTERESIS_MIB, "speculative_mib": 0.0},
        s2_kw={"free_mib": 0.0, "inactive_mib": need + HYSTERESIS_MIB, "speculative_mib": 0.0},
    )
    d2 = _eval(s1b, s2b, prior_denial=True)
    assert d2.allowed is True


def test_t08_swap_over_512_denies():
    s1, s2 = _pair(s1_kw={"swap_used_mib": 600.0}, s2_kw={"swap_used_mib": 600.0})
    d = _eval(s1, s2)
    assert d.allowed is False
    assert MemoryGateReason.SWAP_LIMIT_EXCEEDED in d.denial_reasons


def test_t09_swap_rising_across_samples_denies():
    s1, s2 = _pair(
        s1_kw={"swap_used_mib": 100.0, "swapins": 10},
        s2_kw={"swap_used_mib": 150.0, "swapins": 12},
    )
    d = _eval(s1, s2)
    assert d.allowed is False
    assert MemoryGateReason.SWAP_RISING in d.denial_reasons


def test_t10_compressor_49_percent_not_denied_by_compressor():
    # 49% of 8 GiB
    mib = 0.49 * 8192
    s1, s2 = _pair(s1_kw={"compressor_mib": mib}, s2_kw={"compressor_mib": mib})
    d = _eval(s1, s2)
    assert MemoryGateReason.COMPRESSOR_SOFT_LIMIT not in d.denial_reasons
    assert MemoryGateReason.COMPRESSOR_HARD_LIMIT not in d.denial_reasons
    assert d.allowed is True


def test_t11_compressor_50_percent_soft_denial():
    mib = COMPRESSOR_SOFT_FRACTION * 8192
    s1, s2 = _pair(s1_kw={"compressor_mib": mib}, s2_kw={"compressor_mib": mib})
    d = _eval(s1, s2)
    assert d.allowed is False
    assert MemoryGateReason.COMPRESSOR_SOFT_LIMIT in d.denial_reasons


def test_t12_compressor_70_percent_hard_denial():
    # Slightly above 70% to avoid float edge under int conversion.
    mib = COMPRESSOR_HARD_FRACTION * 8192 + 50
    s1, s2 = _pair(s1_kw={"compressor_mib": mib}, s2_kw={"compressor_mib": mib})
    d = _eval(s1, s2)
    assert d.allowed is False
    assert MemoryGateReason.COMPRESSOR_HARD_LIMIT in d.denial_reasons


def test_t13_no_model_loaded_ok():
    s1, s2 = _pair()
    d = _eval(s1, s2, loaded_models=())
    assert d.allowed is True


def test_t14_correct_pinned_model_loaded_ok():
    s1, s2 = _pair()
    d = _eval(s1, s2, loaded_models=(PINNED_MODEL,))
    assert d.allowed is True


def test_t15_wrong_model_loaded_denies():
    s1, s2 = _pair()
    d = _eval(s1, s2, loaded_models=("qwen3:8b",))
    assert d.allowed is False
    assert MemoryGateReason.WRONG_MODEL_LOADED in d.denial_reasons


def test_t16_multiple_models_loaded_denies():
    s1, s2 = _pair()
    d = _eval(s1, s2, loaded_models=(PINNED_MODEL, "qwen3:4b"))
    assert d.allowed is False
    assert MemoryGateReason.MULTIPLE_MODELS_LOADED in d.denial_reasons


def test_t17_active_local_session_denies():
    s1, s2 = _pair()
    d = _eval(s1, s2, active_local_sessions=1)
    assert d.allowed is False
    assert MemoryGateReason.CONCURRENCY_LIMIT in d.denial_reasons


def test_t18_probe_invalid_denies():
    s1 = make_sample(probe_valid=False, probe_errors=("boom",), sampled_at=1e6)
    s2 = make_sample(probe_valid=False, probe_errors=("boom",), sampled_at=1e6 + 2)
    d = _eval(s1, s2)
    assert d.allowed is False
    assert MemoryGateReason.PROBE_FAILED in d.denial_reasons


def test_t19_stale_sample_denies():
    s1 = _healthy(sampled_at=100.0)
    s2 = _healthy(sampled_at=102.0)
    d = evaluate_memory_samples(s1, s2, now=10_000.0)
    assert d.allowed is False
    assert MemoryGateReason.SAMPLE_STALE in d.denial_reasons


def test_t20_negative_impossible_metric_denies():
    s1 = make_sample(free_mib=-10.0, sampled_at=1e6)
    # free_bytes becomes negative from int(-10 * mib)
    s1 = make_sample(sampled_at=1e6)
    # Force invalid via replace
    from dataclasses import replace

    s1 = replace(s1, free_bytes=-1)
    s2 = replace(_healthy(sampled_at=1e6 + 2), free_bytes=-1)
    d = _eval(s1, s2)
    assert d.allowed is False
    assert MemoryGateReason.INVALID_METRICS in d.denial_reasons


def test_t21_physical_ram_mismatch_denies():
    s1 = _healthy(physical_memory_bytes=8 * 1024 ** 3, sampled_at=1e6)
    s2 = _healthy(physical_memory_bytes=16 * 1024 ** 3, sampled_at=1e6 + 2)
    d = _eval(s1, s2)
    assert d.allowed is False
    assert MemoryGateReason.PHYSICAL_RAM_MISMATCH in d.denial_reasons


def test_t22_first_pass_second_fail_denies():
    s1 = _healthy(darwin_free_percent=50.0, sampled_at=1e6)
    s2 = _healthy(darwin_free_percent=10.0, sampled_at=1e6 + 2)
    d = _eval(s1, s2)
    assert d.allowed is False
    assert MemoryGateReason.DARWIN_FREE_PERCENT_LOW in d.denial_reasons


def test_t23_first_fail_second_pass_denies():
    s1 = _healthy(darwin_free_percent=10.0, sampled_at=1e6)
    s2 = _healthy(darwin_free_percent=50.0, sampled_at=1e6 + 2)
    d = _eval(s1, s2)
    assert d.allowed is False
    assert MemoryGateReason.DARWIN_FREE_PERCENT_LOW in d.denial_reasons


def test_t24_both_samples_pass_allows():
    s1, s2 = _pair()
    d = _eval(s1, s2)
    assert d.allowed is True


def test_t25_retry_limit_via_gate_object():
    s1, s2 = _pair(s1_kw={"darwin_free_percent": 5.0}, s2_kw={"darwin_free_percent": 5.0})
    gate = CombinedMacOSMemoryGate(fixed_samples=(s1, s2), sleeper=lambda _s: None)
    d = gate.evaluate(retry_count=2)
    # evaluate_memory_samples still returns deny; harness enforces retry_count separately.
    assert d.allowed is False
    # Harness path:
    inv = RuntimeInventory(
        reachable=True,
        version="0.32.5",
        models=(ModelInventoryEntry(PINNED_MODEL, PINNED_MODEL_DIGEST),),
        loaded_models=(),
    )
    h = LocalModelHarness(
        transport=MockOllamaTransport(
            script=MockScript(inventory=inv),
        ),
        live_mode=False,
        config=LocalModelConfig(enforce_memory_gate=True, enforce_binding_gate=False),
        memory_gate=gate,
        audit_log=HarnessAuditLog(),
    )
    h._memory_retry_count = 2
    with h._lock:
        decision = h._run_memory_gate_unlocked(inv)
    assert decision.allowed is False
    assert decision.retry_allowed is False
    assert "retry_limit" in decision.detail


def test_t26_capability_cannot_raise_threshold():
    # Budget is frozen on the gate; no public capability path mutates floors.
    b = LocalModelMemoryBudget()
    assert b.required_headroom_mib >= 4000
    assert DARWIN_FREE_PERCENT_MIN == 20


def test_t27_harness_cannot_override_denial():
    s1, s2 = _pair(s1_kw={"darwin_free_percent": 5.0}, s2_kw={"darwin_free_percent": 5.0})
    gate = CombinedMacOSMemoryGate(fixed_samples=(s1, s2), sleeper=lambda _s: None)
    inv = RuntimeInventory(
        reachable=True,
        version="0.32.5",
        models=(ModelInventoryEntry(PINNED_MODEL, PINNED_MODEL_DIGEST),),
    )
    h = LocalModelHarness(
        transport=MockOllamaTransport(script=MockScript(inventory=inv)),
        config=LocalModelConfig(enforce_memory_gate=True, enforce_binding_gate=False),
        memory_gate=gate,
    )
    with pytest.raises(HarnessError) as ei:
        h.start_session(
            HarnessSessionStartRequest(
                session_id="s1",
                actor_id="a",
                organization_id="o",
                workspace_id="w",
                correlation_id="c1",
                budget=HarnessBudget(),
            )
        )
    assert ei.value.code == HarnessErrorCode.RESOURCE_EXHAUSTED


def test_t28_no_operator_flag_bypass_on_critical_pressure():
    # There is no public override API on CombinedMacOSMemoryGate.
    assert not hasattr(CombinedMacOSMemoryGate, "force_allow")
    assert not hasattr(CombinedMacOSMemoryGate, "bypass")


def test_t29_reservation_released_on_denial_no_session():
    s1, s2 = _pair(s1_kw={"darwin_free_percent": 5.0}, s2_kw={"darwin_free_percent": 5.0})
    gate = CombinedMacOSMemoryGate(fixed_samples=(s1, s2), sleeper=lambda _s: None)
    inv = RuntimeInventory(
        reachable=True,
        version="0.32.5",
        models=(ModelInventoryEntry(PINNED_MODEL, PINNED_MODEL_DIGEST),),
    )
    h = LocalModelHarness(
        transport=MockOllamaTransport(script=MockScript(inventory=inv)),
        config=LocalModelConfig(enforce_memory_gate=True, enforce_binding_gate=False),
        memory_gate=gate,
    )
    with pytest.raises(HarnessError):
        h.start_session(
            HarnessSessionStartRequest(
                session_id="s1",
                actor_id="a",
                organization_id="o",
                workspace_id="w",
                correlation_id="c1",
                budget=HarnessBudget(),
            )
        )
    # No session retained after denial.
    assert h.metrics().resource_pressure_count >= 1
    with h._lock:
        assert "s1" not in h._sessions


def test_t30_no_inference_transport_on_memory_gate_tests():
    """Memory-gate-only evaluation never touches transport stream methods."""

    class BoomTransport(MockOllamaTransport):
        def stream_chat(self, *a, **k):  # type: ignore[no-untyped-def]
            raise AssertionError("stream_chat must not be called by memory gate tests")

        def chat(self, *a, **k):  # type: ignore[no-untyped-def]
            raise AssertionError("chat must not be called by memory gate tests")

    s1, s2 = _pair()
    gate = CombinedMacOSMemoryGate(fixed_samples=(s1, s2), sleeper=lambda _s: None)
    inv = RuntimeInventory(
        reachable=True,
        version="0.32.5",
        models=(ModelInventoryEntry(PINNED_MODEL, PINNED_MODEL_DIGEST),),
    )
    h = LocalModelHarness(
        transport=BoomTransport(script=MockScript(inventory=inv)),
        config=LocalModelConfig(enforce_memory_gate=True, enforce_binding_gate=False),
        memory_gate=gate,
    )
    # start_session may call inventory only — BoomTransport inherits inventory.
    h.start_session(
        HarnessSessionStartRequest(
            session_id="s1",
            actor_id="a",
            organization_id="o",
            workspace_id="w",
            correlation_id="c1",
            budget=HarnessBudget(),
        )
    )


def test_legacy_memory_snapshot_injection_still_works():
    h = LocalModelHarness(
        transport=MockOllamaTransport(),
        config=LocalModelConfig(enforce_memory_gate=True, enforce_binding_gate=False),
        memory_probe=lambda: MemorySnapshot(8 * 1024 ** 3, 5.0, 100.0, False, "low"),
    )
    with pytest.raises(HarnessError) as ei:
        h.start_session(
            HarnessSessionStartRequest(
                session_id="s1",
                actor_id="a",
                organization_id="o",
                workspace_id="w",
                correlation_id="c1",
                budget=HarnessBudget(),
            )
        )
    assert ei.value.code == HarnessErrorCode.RESOURCE_EXHAUSTED


def test_build_sample_from_raw_roundtrip():
    memsize = str(8 * 1024 ** 3)
    vm = (
        "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
        "Pages free:                       1000.\n"
        "Pages active:                     5000.\n"
        "Pages inactive:                  20000.\n"
        "Pages speculative:                 100.\n"
        "Pages wired down:                 4000.\n"
        "Pages purgeable:                   50.\n"
        "Pages occupied by compressor:     1000.\n"
        "Swapins:                            0.\n"
        "Swapouts:                           0.\n"
    )
    swap = "total = 0.00M  used = 0.00M  free = 0.00M  (encrypted)"
    pressure = "System-wide memory free percentage: 42%\n"
    s = build_sample_from_raw(
        memsize_text=memsize,
        vm_stat_text=vm,
        swap_text=swap,
        pressure_text=pressure,
        sampled_at=123.0,
    )
    assert s.probe_valid is True
    assert s.darwin_free_percent == 42.0
    assert s.reclaimable_bytes == (1000 + 20000 + 100) * 16384


def test_gate_evaluate_uses_fixed_samples_without_sleep():
    slept = []
    s1, s2 = _pair()
    gate = CombinedMacOSMemoryGate(
        fixed_samples=(s1, s2),
        sleeper=lambda sec: slept.append(sec),
    )
    d = gate.evaluate()
    assert d.allowed is True
    assert slept == []  # fixed_samples path must not sleep
