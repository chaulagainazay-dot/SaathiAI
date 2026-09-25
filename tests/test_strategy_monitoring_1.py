"""STRATEGY-MONITORING-1 — deterministic strategy health and degradation.

The rules these tests defend, in order of how badly getting them wrong would hurt:

  1. Monitoring never becomes authority. It classifies; it cannot size, retune,
     promote, suspend, submit or approve.
  2. Bad data is never charged to the strategy.
  3. A strategy is not NORMAL because we have not watched it long enough to
     notice anything wrong.
  4. Thresholds are frozen and versioned before evaluation — a monitor that can
     move its own goalposts is not measuring anything.
"""
from __future__ import annotations

from decimal import Decimal as X

import pytest

from saathi.platform.tg.paper_activation.ops.models import HealthClass
from saathi.platform.tg.strategy_monitor import (
    CALCULATION_VERSION, HEALTH_CLASS_OF, MONITOR_POLICY_VERSION,
    Dimension, MonitorPolicy, Observation, QualificationEnvelope, Reason,
    StrategyHealth, evaluate_benchmark, evaluate_cost, evaluate_data_quality,
    evaluate_drawdown, evaluate_observation, evaluate_regime,
    evaluate_reconciliation, evaluate_signals, evaluate_strategy_health,
    evaluate_turnover, monitoring_events,
)

POLICY = MonitorPolicy()
WEEK = 7 * 24 * 3600


def env(**kw):
    base = dict(
        strategy_id="crypto_spot_mean_reversion", strategy_version="1.0.0",
        qualification_sha="45a115c9", benchmark_version="BTC_BUY_AND_HOLD@1",
        qualified_max_drawdown=X("0.25"), assumed_cost_drag=X("100"),
        qualified_turnover=X("0.5"), qualified_regimes=("RANGE", "LOW_VOL"),
        expected_trades_per_week=X("3"),
    )
    base.update(kw)
    return QualificationEnvelope(**base)


def obs(**kw):
    """A healthy, sufficiently-observed baseline. Tests perturb one thing."""
    base = dict(
        mode="SHADOW", window_start="2026-09-01T00:00:00Z", window_end="2026-09-15T00:00:00Z",
        observed_seconds=2 * WEEK, closed_trades=30, signals=12,
        max_drawdown=X("0.05"), net_return=X("0.03"), benchmark_return=X("0.02"),
        cost_drag=X("90"), cost_detail_available=True, turnover_ratio=X("0.6"),
        regimes_seen=("RANGE",), current_regime="RANGE", reconciliation_ok=True,
        attribution_report_id="rep-1",
    )
    base.update(kw)
    return Observation(**base)


def health(**kw):
    return evaluate_strategy_health(env(), obs(**kw), policy=POLICY).health


# ── authority ───────────────────────────────────────────────────────────────

def test_monitoring_holds_no_execution_or_tuning_authority():
    """Scanned over the AST, not the raw text.

    A raw grep matches this module's own docstring — the sentence listing what it
    cannot do. Checking called NAMES and imports instead tests the code rather
    than the prose describing it.
    """
    import ast

    import saathi.platform.tg.strategy_monitor as mod

    tree = ast.parse(open(mod.__file__).read())
    called, attrs, imported = set(), set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                called.add(f.id)
            elif isinstance(f, ast.Attribute):
                attrs.add(f.attr)
        if isinstance(n, ast.Import):
            imported |= {a.name for a in n.names}
        if isinstance(n, ast.ImportFrom) and n.module:
            imported.add(n.module)

    banned = {"submit", "execute", "place_order", "reserve_for_buy", "approve",
              "set_parameter", "retune", "post", "request", "connect"}
    assert not (called | attrs) & banned, f"monitoring calls {(called | attrs) & banned}"
    for m in imported:
        assert not any(k in m.lower() for k in
                       ("broker", "venue", "ccxt", "binance", "exchange", "execution",
                        "gateway", "http", "socket")), f"monitoring imports {m}"

    v = evaluate_strategy_health(env(), obs())
    assert v.authorizes_execution is False
    assert v.mutates_parameters is False
    assert v.to_public()["authorizes_execution"] is False
    assert v.to_public()["mutates_parameters"] is False
    for e in monitoring_events(v):
        assert e["authorizes_execution"] is False


def test_a_degraded_verdict_still_changes_nothing():
    """DEGRADED is a statement, not an instruction. Nothing in the result can be
    read as a new parameter, size or status."""
    v = evaluate_strategy_health(env(), obs(max_drawdown=X("0.40")))
    assert v.health == StrategyHealth.DEGRADED.value
    public = v.to_public()
    for forbidden in ("position_size", "parameters", "new_status", "suspend",
                      "promote", "demote", "allocation"):
        assert forbidden not in public


# ── observation sufficiency dominates ───────────────────────────────────────

@pytest.mark.parametrize("trades,expected", [
    (0, StrategyHealth.INSUFFICIENT_EVIDENCE.value),
    (1, StrategyHealth.INSUFFICIENT_EVIDENCE.value),
    (POLICY.min_closed_trades - 1, StrategyHealth.INSUFFICIENT_EVIDENCE.value),
    (POLICY.min_closed_trades, StrategyHealth.NORMAL.value),
    (POLICY.min_closed_trades + 10, StrategyHealth.NORMAL.value),
])
def test_premature_normal_is_impossible(trades, expected):
    assert health(closed_trades=trades) == expected


def test_a_short_window_is_insufficient_however_good_the_numbers():
    assert health(observed_seconds=3600, net_return=X("0.50")) \
        == StrategyHealth.INSUFFICIENT_EVIDENCE.value


def test_insufficient_evidence_never_hides_a_real_degradation():
    """Not having watched long enough must not mask a breach that is already
    unambiguous — a 40% drawdown is 40% whether or not we have 20 trades."""
    v = evaluate_strategy_health(env(), obs(closed_trades=2, max_drawdown=X("0.40")))
    assert v.health == StrategyHealth.DEGRADED.value
    assert Reason.DRAWDOWN_DEGRADED.value in v.reasons


def test_insufficient_evidence_is_a_warning_not_a_strategy_failure():
    v = evaluate_strategy_health(env(), obs(closed_trades=1))
    assert v.health_class == HealthClass.WARNING.value
    assert v.health != StrategyHealth.DEGRADED.value


# ── drawdown bands + hysteresis ─────────────────────────────────────────────

@pytest.mark.parametrize("dd,expected", [
    (X("0.05"), StrategyHealth.NORMAL.value),
    (X("0.0999"), StrategyHealth.NORMAL.value),
    (X("0.10"), StrategyHealth.WATCH.value),            # exact watch threshold
    (X("0.15"), StrategyHealth.WATCH.value),
    (X("0.20"), StrategyHealth.DEGRADED.value),         # exact degraded threshold
    (X("0.35"), StrategyHealth.DEGRADED.value),
])
def test_drawdown_bands_including_exact_thresholds(dd, expected):
    assert evaluate_drawdown(obs(max_drawdown=dd), POLICY).health == expected


def test_recovery_requires_clearing_the_band_not_merely_touching_it():
    """Without hysteresis a value parked on the threshold flaps forever."""
    # Just under watch, but inside the hysteresis margin, having been WATCH.
    still = evaluate_drawdown(obs(max_drawdown=X("0.09")), POLICY,
                              previous=StrategyHealth.WATCH.value)
    assert still.health == StrategyHealth.WATCH.value

    # Clearly clear of it: recovery is recognised.
    recovered = evaluate_drawdown(obs(max_drawdown=X("0.02")), POLICY,
                                  previous=StrategyHealth.WATCH.value)
    assert recovered.health == StrategyHealth.NORMAL.value
    assert Reason.RECOVERY_OBSERVED.value in recovered.reasons


def test_oscillation_across_the_threshold_is_damped():
    seq = [X("0.11"), X("0.09"), X("0.11"), X("0.09")]
    previous = StrategyHealth.NORMAL.value
    states = []
    for dd in seq:
        previous = evaluate_drawdown(obs(max_drawdown=dd), POLICY, previous).health
        states.append(previous)
    # Enters WATCH once and stays; it does not flap back on a 1-point improvement.
    assert states == [StrategyHealth.WATCH.value] * 4


def test_a_missing_drawdown_is_unknown_not_zero():
    d = evaluate_drawdown(obs(max_drawdown=None), POLICY)
    assert d.health == StrategyHealth.INSUFFICIENT_EVIDENCE.value
    assert d.observed is None


# ── performance is not one number ───────────────────────────────────────────

@pytest.mark.parametrize("net,bench,expected", [
    (X("0.10"), X("0.02"), StrategyHealth.NORMAL.value),   # up absolute, up relative
    (X("0.10"), X("0.30"), StrategyHealth.WATCH.value),    # up absolute, DOWN relative
    (X("-0.05"), X("-0.30"), StrategyHealth.NORMAL.value),  # down absolute, UP relative
    (X("-0.20"), X("0.05"), StrategyHealth.WATCH.value),   # down absolute, down relative
    (X("0.00"), X("0.00"), StrategyHealth.NORMAL.value),   # flat
])
def test_absolute_and_relative_performance_are_judged_separately(net, bench, expected):
    assert evaluate_benchmark(obs(net_return=net, benchmark_return=bench), POLICY).health == expected


def test_a_losing_strategy_that_beat_a_worse_benchmark_is_not_degraded():
    """Down 5% while the benchmark fell 30% is not a failure of the strategy."""
    assert health(net_return=X("-0.05"), benchmark_return=X("-0.30")) == StrategyHealth.NORMAL.value


def test_relative_performance_needs_enough_trades_to_mean_anything():
    d = evaluate_benchmark(obs(closed_trades=3, net_return=X("-0.5"), benchmark_return=X("0.5")), POLICY)
    assert d.health == StrategyHealth.INSUFFICIENT_EVIDENCE.value


def test_a_missing_benchmark_is_unavailable_not_underperformance():
    d = evaluate_benchmark(obs(benchmark_return=None), POLICY)
    assert d.health == StrategyHealth.INSUFFICIENT_EVIDENCE.value
    assert Reason.BENCHMARK_UNAVAILABLE.value in d.reasons


# ── costs ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("actual,expected", [
    (X("90"), StrategyHealth.NORMAL.value),      # within assumption
    (X("140"), StrategyHealth.NORMAL.value),     # above, below the 1.5x breach
    (X("150"), StrategyHealth.WATCH.value),      # exactly the breach ratio
    (X("400"), StrategyHealth.WATCH.value),      # materially above
])
def test_cost_overrun_against_the_qualified_assumption(actual, expected):
    assert evaluate_cost(obs(cost_drag=actual), env(), POLICY).health == expected


def test_missing_cost_detail_is_not_silently_zero():
    d = evaluate_cost(obs(cost_drag=None), env(), POLICY)
    assert d.health == StrategyHealth.INSUFFICIENT_EVIDENCE.value
    assert Reason.COST_DETAIL_UNAVAILABLE.value in d.reasons
    assert d.observed is None


def test_a_partial_cost_breakdown_is_flagged_even_when_within_budget():
    d = evaluate_cost(obs(cost_drag=X("90"), cost_detail_available=False), env(), POLICY)
    assert d.health == StrategyHealth.NORMAL.value
    assert Reason.COST_DETAIL_UNAVAILABLE.value in d.reasons


def test_a_non_positive_cost_assumption_cannot_produce_a_ratio():
    assert evaluate_cost(obs(), env(assumed_cost_drag=X("0")), POLICY).health \
        == StrategyHealth.INSUFFICIENT_EVIDENCE.value


# ── turnover / signals ──────────────────────────────────────────────────────

def test_turnover_inflation_is_watched_against_the_qualified_envelope():
    assert evaluate_turnover(obs(turnover_ratio=X("1.2")), env(), POLICY).health \
        == StrategyHealth.WATCH.value
    assert evaluate_turnover(obs(turnover_ratio=X("0.6")), env(), POLICY).health \
        == StrategyHealth.NORMAL.value


def test_turnover_without_a_qualified_reference_is_unavailable():
    assert evaluate_turnover(obs(), env(qualified_turnover=None), POLICY).health \
        == StrategyHealth.INSUFFICIENT_EVIDENCE.value


def test_sparse_signals_mean_keep_watching_not_failure():
    d = evaluate_signals(obs(signals=1, observed_seconds=2 * WEEK), env(), POLICY)
    assert d.health == StrategyHealth.INSUFFICIENT_EVIDENCE.value
    assert Reason.SIGNAL_SPARSE.value in d.reasons


# ── regime ──────────────────────────────────────────────────────────────────

def test_regime_compatibility_is_observational():
    assert evaluate_regime(obs(current_regime="RANGE"), env()).health == StrategyHealth.NORMAL.value
    mismatch = evaluate_regime(obs(current_regime="HIGH_VOL_TREND"), env())
    assert mismatch.health == StrategyHealth.WATCH.value
    assert Reason.REGIME_MISMATCH.value in mismatch.reasons
    # A mismatch is a WATCH, never a DEGRADED verdict on skill.
    assert mismatch.health != StrategyHealth.DEGRADED.value


def test_an_unknown_regime_is_unknown_not_a_mismatch():
    """The regime engine fails closed to UNKNOWN. Treating that as
    incompatibility would manufacture a verdict from our own missing data."""
    for unknown in (None, "UNKNOWN"):
        d = evaluate_regime(obs(current_regime=unknown), env())
        assert d.health == StrategyHealth.INSUFFICIENT_EVIDENCE.value
        assert Reason.REGIME_UNKNOWN.value in d.reasons


def test_a_strategy_with_no_declared_regime_cannot_be_judged_on_regime():
    assert evaluate_regime(obs(), env(qualified_regimes=())).health \
        == StrategyHealth.INSUFFICIENT_EVIDENCE.value


# ── data quality is never the strategy's fault ──────────────────────────────

@pytest.mark.parametrize("kw", [
    {"data_stale": True}, {"data_gap": True}, {"reconciliation_ok": False},
])
def test_bad_data_blocks_interpretation_rather_than_blaming_the_strategy(kw):
    v = evaluate_strategy_health(env(), obs(**kw))
    assert v.health == StrategyHealth.DATA_QUALITY_BLOCKED.value
    assert v.health != StrategyHealth.DEGRADED.value


def test_a_blocked_observation_makes_no_performance_claim():
    """Excellent numbers on untrustworthy data are still untrustworthy."""
    v = evaluate_strategy_health(env(), obs(data_stale=True, net_return=X("0.90")))
    assert v.health == StrategyHealth.DATA_QUALITY_BLOCKED.value
    assert Reason.BENCHMARK_UNDERPERFORMANCE.value not in v.reasons


def test_failed_reconciliation_can_never_read_as_normal():
    assert health(reconciliation_ok=False) != StrategyHealth.NORMAL.value


# ── policy freezing ─────────────────────────────────────────────────────────

def test_the_policy_is_versioned_and_fingerprinted():
    v = evaluate_strategy_health(env(), obs(), policy=POLICY)
    assert v.policy_version == MONITOR_POLICY_VERSION
    assert v.calculation_version == CALCULATION_VERSION
    assert v.policy_fingerprint == POLICY.fingerprint()


def test_moving_a_threshold_changes_the_fingerprint_and_the_verdict_id():
    """Goalposts cannot be moved invisibly."""
    loose = MonitorPolicy(drawdown_watch=X("0.90"), drawdown_degraded=X("0.95"))
    a = evaluate_strategy_health(env(), obs(max_drawdown=X("0.30")), policy=POLICY)
    b = evaluate_strategy_health(env(), obs(max_drawdown=X("0.30")), policy=loose)
    assert a.policy_fingerprint != b.policy_fingerprint
    assert a.verdict_id != b.verdict_id
    assert a.health == StrategyHealth.DEGRADED.value
    assert b.health != StrategyHealth.DEGRADED.value


# ── identity / restart reproducibility ──────────────────────────────────────

def test_the_same_window_and_policy_reproduce_the_same_verdict():
    a = evaluate_strategy_health(env(), obs(), policy=POLICY)
    b = evaluate_strategy_health(env(), obs(), policy=POLICY)
    assert a.verdict_id == b.verdict_id
    assert a.health == b.health
    assert a.reasons == b.reasons


def test_recomputing_after_a_restart_is_identical():
    """Nothing in the verdict depends on process state or a clock."""
    import importlib

    import saathi.platform.tg.strategy_monitor as mod
    before = evaluate_strategy_health(env(), obs(), policy=POLICY)
    importlib.reload(mod)
    after = mod.evaluate_strategy_health(
        mod.QualificationEnvelope(**env().__dict__),
        mod.Observation(**obs().__dict__),
        policy=mod.MonitorPolicy(),
    )
    assert after.verdict_id == before.verdict_id
    assert after.health == before.health


def test_a_different_strategy_version_is_never_aggregated_into_one_state():
    a = evaluate_strategy_health(env(strategy_version="1.0.0"), obs())
    b = evaluate_strategy_health(env(strategy_version="1.1.0"), obs())
    assert a.verdict_id != b.verdict_id


# ── PIT safety ──────────────────────────────────────────────────────────────

def test_monitoring_sees_only_what_it_is_given():
    """No lookup, no clock, no I/O — so no future price, revision or outcome can
    leak in. Proven structurally: the module imports nothing that could fetch."""
    import ast

    import saathi.platform.tg.strategy_monitor as mod

    tree = ast.parse(open(mod.__file__).read())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
    for forbidden in ("time", "datetime", "requests", "httpx", "sqlite3", "urllib"):
        assert forbidden not in mods, f"monitoring must not reach {forbidden} — PIT risk"


def test_a_later_window_does_not_change_an_earlier_verdict():
    early = evaluate_strategy_health(
        env(), obs(window_end="2026-09-15T00:00:00Z", max_drawdown=X("0.05")), policy=POLICY)
    later = evaluate_strategy_health(
        env(), obs(window_end="2026-10-15T00:00:00Z", max_drawdown=X("0.40")), policy=POLICY)
    assert early.health == StrategyHealth.NORMAL.value
    assert later.health == StrategyHealth.DEGRADED.value
    # Recomputing the earlier window still yields the earlier answer.
    again = evaluate_strategy_health(
        env(), obs(window_end="2026-09-15T00:00:00Z", max_drawdown=X("0.05")), policy=POLICY)
    assert again.verdict_id == early.verdict_id


# ── numeric contract ────────────────────────────────────────────────────────

def test_monitoring_inherits_the_fail_closed_numeric_contract():
    from saathi.platform.trading_models import InvalidFinancialValue

    for hostile in ("NaN", "Infinity", "abc", True):
        with pytest.raises(InvalidFinancialValue):
            evaluate_drawdown(obs(max_drawdown=hostile), POLICY)


# ── transitions and alert deduplication ─────────────────────────────────────

def test_a_transition_is_reported_and_a_steady_state_is_not():
    entering = evaluate_strategy_health(env(), obs(max_drawdown=X("0.15")),
                                        previous_health=StrategyHealth.NORMAL.value)
    assert entering.transitioned is True
    assert monitoring_events(entering), "entering WATCH must alert"

    steady = evaluate_strategy_health(env(), obs(max_drawdown=X("0.15")),
                                      previous_health=StrategyHealth.WATCH.value)
    assert steady.transitioned is False
    assert monitoring_events(steady) == [], "a steady state must not alert every cycle"


def test_alerts_are_idempotent_for_an_unchanged_verdict():
    v = evaluate_strategy_health(env(), obs(max_drawdown=X("0.15")),
                                 previous_health=StrategyHealth.NORMAL.value)
    a = monitoring_events(v)
    b = monitoring_events(evaluate_strategy_health(
        env(), obs(max_drawdown=X("0.15")), previous_health=StrategyHealth.NORMAL.value))
    assert [e["key"] for e in a] == [e["key"] for e in b]
    assert len({e["key"] for e in a}) == len(a), "no duplicate keys within one verdict"


def test_recovery_is_an_event_too():
    v = evaluate_strategy_health(env(), obs(max_drawdown=X("0.02")),
                                 previous_health=StrategyHealth.WATCH.value)
    assert v.health == StrategyHealth.NORMAL.value
    assert any(e["reason"] == Reason.RECOVERY_OBSERVED.value for e in monitoring_events(v))


# ── taxonomy bridge ─────────────────────────────────────────────────────────

def test_every_strategy_health_maps_onto_the_canonical_operational_taxonomy():
    for h in StrategyHealth:
        assert h in HEALTH_CLASS_OF
        assert isinstance(HEALTH_CLASS_OF[h], HealthClass)
    assert HEALTH_CLASS_OF[StrategyHealth.NORMAL] == HealthClass.HEALTHY
    assert HEALTH_CLASS_OF[StrategyHealth.DEGRADED] == HealthClass.DEGRADED


def test_every_dimension_is_reported_even_when_it_cannot_be_judged():
    v = evaluate_strategy_health(env(), Observation(mode="REPLAY"))
    reported = {d.dimension for d in v.dimensions}
    assert reported == {d.value for d in Dimension}


def test_replay_evidence_is_never_labelled_live():
    v = evaluate_strategy_health(env(), obs(mode="REPLAY"))
    assert v.mode == "REPLAY"
    assert "LIVE" not in v.mode


# ── adversarial ─────────────────────────────────────────────────────────────

def test_many_trades_with_nothing_measurable_is_not_normal():
    """Sufficiency is about EVIDENCE, not trade count.

    99 trades over a year still supports no conclusion if every metric is
    unavailable — that is a monitoring blind spot, not a healthy strategy.
    """
    v = evaluate_strategy_health(
        env(qualified_regimes=(), assumed_cost_drag=None, qualified_turnover=None,
            expected_trades_per_week=None),
        Observation(mode="SHADOW", closed_trades=99, observed_seconds=52 * WEEK,
                    regimes_seen=("RANGE",)),
    )
    assert v.health != StrategyHealth.NORMAL.value
    assert v.health == StrategyHealth.INSUFFICIENT_EVIDENCE.value


def test_the_worst_dimension_wins():
    v = evaluate_strategy_health(env(), obs(max_drawdown=X("0.30"), cost_drag=X("400")))
    assert v.health == StrategyHealth.DEGRADED.value
    assert Reason.DRAWDOWN_DEGRADED.value in v.reasons
    assert Reason.COST_ASSUMPTION_BREACH.value in v.reasons, "the milder reason is still reported"


def test_catastrophic_numbers_on_bad_data_still_blame_the_data():
    v = evaluate_strategy_health(
        env(), obs(data_stale=True, reconciliation_ok=False, max_drawdown=X("0.90")))
    assert v.health == StrategyHealth.DATA_QUALITY_BLOCKED.value
    assert Reason.DRAWDOWN_DEGRADED.value not in v.reasons
