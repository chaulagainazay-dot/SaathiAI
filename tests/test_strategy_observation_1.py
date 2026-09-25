"""STRATEGY-OBSERVATION-1 — the shadow → attribution → monitoring pipeline.

Every test here drives the REAL chain: a real ShadowSessionStore on a real
sqlite file, the real attribution bridge, the real attribution report and the
real monitor. Nothing is stubbed, because the thing under test IS the wiring —
a test double in the middle would assert only that the double was shaped the way
the test expected.
"""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from saathi.platform.research.store import ResearchStore
from saathi.platform.tg.shadow_session import (
    ShadowEventKind,
    ShadowMode,
    ShadowSessionStore,
)
from saathi.platform.tg.strategy_monitor import (
    QualificationEnvelope,
    StrategyHealth,
    evaluate_strategy_health,
)
from saathi.platform.tg.strategy_observation import (
    AdapterStatus,
    observation_from_shadow,
    resolve_cutoff_seq,
)

ADAPTER_SRC = Path("saathi/platform/tg/strategy_observation.py")


def _store(db):
    return ShadowSessionStore(research_store=ResearchStore(db_path=db))


def _open(store, **kw):
    params = dict(
        mode=ShadowMode.REPLAY,
        market="CRYPTO",
        strategy_version="btc-mean-reversion@frozen-1",
        policy_versions={"guardian": "v2", "construction": "v2", "risk": "v2"},
        feed_ref="replay:btc-2026-08",
        opening_cash="250000",
        started_at="2026-09-01T00:00:00Z",
        benchmark="BTC_BUY_AND_HOLD",
    )
    params.update(kw)
    return store.open_session(**params)


def _round_trips(store, sid, n, *, start_seq=1, day0=1, entry="100", exit_="101",
                 qty="10", fee="1", split=True):
    """n complete buy→sell round trips, each with the event reconcile() requires.

    Fills without their HYPOTHETICAL_FILL event are exactly what reconcile()
    treats as orphans, so a helper that skipped them would make every test here
    fail for the wrong reason.
    """
    seq = start_seq
    for i in range(n):
        day = day0 + i
        for side, px in (("BUY", entry), ("SELL", exit_)):
            stamp = f"2026-09-{day:02d}T0{0 if side == 'BUY' else 1}:00:00Z"
            store.append_event(sid, seq, ShadowEventKind.SIGNAL, {"i": i, "side": side},
                               observed_at=stamp)
            seq += 1
            store.append_event(sid, seq, ShadowEventKind.HYPOTHETICAL_FILL,
                               {"i": i, "side": side}, observed_at=stamp)
            store.record_fill(
                sid, seq, symbol="BTCUSDT", side=side, quantity=qty,
                reference_price=px, fill_price=px, fee=fee,
                spread_cost="0.5" if split else 0,
                slippage_cost="0.5" if split else 0,
            )
            seq += 1
    return seq


def _envelope(**kw):
    params = dict(
        strategy_id="btc-mean-reversion@frozen-1",
        strategy_version="frozen-1",
        qualification_sha="a" * 16,
        benchmark_version="BTC_BUY_AND_HOLD",
        qualified_max_drawdown=Decimal("0.15"),
        assumed_cost_drag=Decimal("100"),
        qualified_turnover=Decimal("2.0"),
        qualified_regimes=("TREND", "CHOP"),
    )
    params.update(kw)
    return QualificationEnvelope(**params)


@pytest.fixture()
def store(tmp_path):
    s = _store(tmp_path / "shadow.sqlite3")
    yield s
    s.close()


# ── 1. healthy end-to-end run ───────────────────────────────────────────────
def test_healthy_session_flows_to_a_health_verdict_without_manual_reshaping(store):
    sid = _open(store)
    _round_trips(store, sid, 25)

    result = observation_from_shadow(
        store, sid, average_portfolio_value="250000",
        benchmark_return="0.001", current_regime="TREND",
        regimes_seen=("TREND",),
    )
    # The adapter's output goes STRAIGHT into the monitor. If this needed any
    # field renaming or repacking, the convergence this milestone exists for
    # would not have happened.
    verdict = evaluate_strategy_health(_envelope(), result.observation)

    assert result.observation.closed_trades == 25
    assert result.observation.mode == "REPLAY"
    assert verdict.health in {StrategyHealth.NORMAL.value, StrategyHealth.WATCH.value,
                              StrategyHealth.INSUFFICIENT_EVIDENCE.value}
    assert verdict.authorizes_execution is False


# ── 2. insufficient observation ─────────────────────────────────────────────
def test_too_few_closed_trades_is_insufficient_evidence_not_a_performance_verdict(store):
    sid = _open(store)
    _round_trips(store, sid, 2)

    result = observation_from_shadow(store, sid, average_portfolio_value="250000")
    verdict = evaluate_strategy_health(_envelope(), result.observation)

    assert result.observation.closed_trades == 2
    assert verdict.health == StrategyHealth.INSUFFICIENT_EVIDENCE.value


# ── 3. drawdown ─────────────────────────────────────────────────────────────
def test_large_drawdown_reaches_the_monitor_from_a_supplied_equity_path(store):
    sid = _open(store)
    _round_trips(store, sid, 25)

    result = observation_from_shadow(
        store, sid, average_portfolio_value="250000",
        equity_path=["250000", "260000", "190000", "200000"],
        current_regime="TREND", regimes_seen=("TREND",),
    )
    verdict = evaluate_strategy_health(_envelope(), result.observation)

    assert result.observation.max_drawdown is not None
    assert result.observation.max_drawdown > Decimal("0.25")
    assert verdict.health == StrategyHealth.DEGRADED.value


# ── 4. benchmark underperformance ───────────────────────────────────────────
def test_benchmark_underperformance_is_visible_to_the_monitor(store):
    sid = _open(store)
    # A losing run: bought high, sold low, 25 times.
    _round_trips(store, sid, 25, entry="100", exit_="96")

    result = observation_from_shadow(
        store, sid, average_portfolio_value="250000",
        benchmark_return="0.20", current_regime="TREND", regimes_seen=("TREND",),
    )
    verdict = evaluate_strategy_health(_envelope(), result.observation)

    assert result.observation.net_return < 0
    assert result.observation.benchmark_return == Decimal("0.20")
    assert verdict.health in {StrategyHealth.WATCH.value, StrategyHealth.DEGRADED.value}


# ── 5. cost breach ──────────────────────────────────────────────────────────
def test_realized_cost_far_above_the_qualified_assumption_is_flagged(store):
    sid = _open(store)
    _round_trips(store, sid, 25, fee="50")

    result = observation_from_shadow(
        store, sid, average_portfolio_value="250000",
        current_regime="TREND", regimes_seen=("TREND",),
    )
    # Envelope assumed 100; realized is 50 fee + 1 of spread/slippage per fill
    # across 50 fills — an unmissable overrun.
    verdict = evaluate_strategy_health(_envelope(assumed_cost_drag=Decimal("100")),
                                       result.observation)

    assert result.observation.cost_drag > Decimal("2000")
    assert result.observation.cost_detail_available is True
    assert verdict.health in {StrategyHealth.WATCH.value, StrategyHealth.DEGRADED.value}


# ── 6. regime mismatch ──────────────────────────────────────────────────────
def test_a_regime_outside_the_qualified_set_is_reported_not_absorbed(store):
    sid = _open(store)
    _round_trips(store, sid, 25)

    result = observation_from_shadow(
        store, sid, average_portfolio_value="250000",
        current_regime="CRISIS", regimes_seen=("CRISIS",),
    )
    verdict = evaluate_strategy_health(_envelope(), result.observation)

    assert result.observation.current_regime == "CRISIS"
    assert verdict.health != StrategyHealth.NORMAL.value


# ── 7. stale data ───────────────────────────────────────────────────────────
def test_stale_data_blocks_interpretation_rather_than_scoring_the_strategy(store):
    sid = _open(store)
    _round_trips(store, sid, 25)

    result = observation_from_shadow(
        store, sid, average_portfolio_value="250000", data_stale=True,
    )
    verdict = evaluate_strategy_health(_envelope(), result.observation)

    assert result.status == AdapterStatus.DATA_QUALITY_BLOCKED.value
    # A DATA problem must never be recorded as a STRATEGY failure.
    assert verdict.health == StrategyHealth.DATA_QUALITY_BLOCKED.value
    assert verdict.health != StrategyHealth.DEGRADED.value


# ── 8. reconciliation ───────────────────────────────────────────────────────
def test_an_orphan_fill_surfaces_as_reconciliation_required_end_to_end(store):
    sid = _open(store)
    _round_trips(store, sid, 5)
    # A fill with no HYPOTHETICAL_FILL event behind it: history that does not
    # explain itself.
    store.record_fill(sid, 9001, symbol="ETHUSDT", side="BUY", quantity="1",
                      reference_price="10", fill_price="10", fee="0")

    result = observation_from_shadow(store, sid, average_portfolio_value="250000")
    verdict = evaluate_strategy_health(_envelope(), result.observation)

    assert result.status == AdapterStatus.RECONCILIATION_REQUIRED.value
    assert result.observation.reconciliation_ok is False
    assert verdict.health == StrategyHealth.DATA_QUALITY_BLOCKED.value


# ── 9. ambiguous provenance ─────────────────────────────────────────────────
def test_a_session_with_no_strategy_version_is_ambiguous_not_silently_named(store):
    sid = _open(store, strategy_version="")
    _round_trips(store, sid, 3)

    result = observation_from_shadow(store, sid, average_portfolio_value="250000")

    assert result.status == AdapterStatus.AMBIGUOUS_PROVENANCE.value
    assert result.detail is not None


# ── 10. zero trades ─────────────────────────────────────────────────────────
def test_a_session_with_no_fills_reports_insufficient_source_data_not_zero_return(store):
    sid = _open(store)
    store.append_event(sid, 1, ShadowEventKind.OBSERVATION, {"tick": 1},
                       observed_at="2026-09-01T00:00:00Z")

    result = observation_from_shadow(store, sid, average_portfolio_value="250000")

    assert result.status == AdapterStatus.INSUFFICIENT_SOURCE_DATA.value
    assert result.observation.closed_trades == 0
    # THE CENTRAL HONESTY CLAIM: no trades means no return was measured. A 0.0
    # here would read as "the strategy broke even", which nobody observed.
    assert result.observation.net_return is None
    assert "net_return" in result.unavailable_fields


# ── 11. missing benchmark ───────────────────────────────────────────────────
def test_an_unavailable_benchmark_stays_none_and_never_becomes_zero(store):
    sid = _open(store)
    _round_trips(store, sid, 25)

    result = observation_from_shadow(store, sid, average_portfolio_value="250000")

    assert result.observation.benchmark_return is None
    assert result.observation.benchmark_return != Decimal("0")
    assert "benchmark_return" in result.unavailable_fields
    # And the monitor must not score underperformance against a phantom zero.
    verdict = evaluate_strategy_health(_envelope(), result.observation)
    assert verdict.health != StrategyHealth.DEGRADED.value


# ── 12. cost detail ─────────────────────────────────────────────────────────
def test_a_shadow_session_always_yields_a_complete_cost_split(store):
    """The PARTIAL-cost branch is NOT reachable from this source, and that is a
    property worth pinning rather than a scenario worth faking.

    `shadow_fills` stores fee, spread_cost and slippage_cost as non-null columns
    and the bridge coerces each to a number, so every record arrives with a full
    breakdown that sums exactly to its total. Zeros are a real split, not a
    missing one. The adapter's partial handling stays as a defence for a future
    source that reports less — see the companion test below, which proves the
    contract it depends on.
    """
    sid = _open(store)
    _round_trips(store, sid, 5, fee="2", split=False)

    result = observation_from_shadow(store, sid, average_portfolio_value="250000")

    assert result.observation.cost_drag == Decimal("20")
    assert result.observation.cost_detail_available is True
    assert "cost_detail" not in result.unavailable_fields
    assert result.status == AdapterStatus.PARTIAL.value  # drawdown/benchmark absent


def test_attribution_reports_a_total_cost_even_when_the_split_is_unavailable():
    """The contract the adapter's partial branch rests on.

    Exercised against the real attribution function, so if `cost_decomposition`
    ever stopped returning `total_cost` on the DATA_INSUFFICIENT path, the
    adapter would start reporting an unknown drag — and this test would fail
    first.
    """
    from saathi.platform.tg.attribution_v2 import (
        AttributionRecord,
        AttributionStatus,
        cost_decomposition,
    )

    rec = AttributionRecord(
        strategy_id="s", symbol="BTCUSDT", venue="X", asset_class="CRYPTO",
        gross_pnl=Decimal("100"), cost=Decimal("7"), fee=None,
        spread_cost=None, slippage_cost=None, notional=Decimal("1000"),
    )
    out = cost_decomposition([rec])

    assert out["status"] == AttributionStatus.DATA_INSUFFICIENT.value
    assert out["total_cost"] == Decimal("7")
    assert "fee_drag" not in out


# ── 13. restart reproducibility ─────────────────────────────────────────────
def test_the_same_session_reread_after_a_restart_yields_an_identical_report(tmp_path):
    db = tmp_path / "shadow.sqlite3"
    first = _store(db)
    sid = _open(first)
    _round_trips(first, sid, 25)
    before = observation_from_shadow(first, sid, average_portfolio_value="250000",
                                     benchmark_return="0.01")
    first.close()

    # New process, new connection, same durable state.
    second = _store(db)
    after = observation_from_shadow(second, sid, average_portfolio_value="250000",
                                    benchmark_return="0.01")
    second.close()

    assert before.observation == after.observation
    # The report id is a content hash: equal ids prove the whole attribution
    # body reproduced, not merely the handful of fields asserted above.
    assert before.attribution_report_id == after.attribution_report_id
    assert before.status == after.status


# ── 14. future events excluded ──────────────────────────────────────────────
def test_a_point_in_time_read_excludes_everything_after_the_cutoff(store):
    sid = _open(store)
    end = _round_trips(store, sid, 5, day0=1)
    _round_trips(store, sid, 5, start_seq=end, day0=20)

    cutoff = resolve_cutoff_seq(store, sid, as_of="2026-09-10T00:00:00Z")
    early = observation_from_shadow(store, sid, as_of="2026-09-10T00:00:00Z",
                                    average_portfolio_value="250000")
    full = observation_from_shadow(store, sid, average_portfolio_value="250000")

    assert cutoff is not None
    assert early.observation.closed_trades == 5
    assert full.observation.closed_trades == 10
    # Later fills must not reach the earlier window's costs either.
    assert early.observation.cost_drag < full.observation.cost_drag
    assert early.observation.window_end == "2026-09-10T00:00:00Z"


def test_a_cutoff_before_any_recorded_event_observes_nothing(store):
    sid = _open(store)
    _round_trips(store, sid, 5)

    result = observation_from_shadow(store, sid, as_of="2026-08-01T00:00:00Z",
                                     average_portfolio_value="250000")

    # Failing closed: nothing was known then, so nothing is reported. The
    # opposite default — treating "no qualifying event" as "no bound" — would
    # return the ENTIRE session for a cutoff predating it.
    assert result.observation.closed_trades == 0
    assert result.status == AdapterStatus.INSUFFICIENT_SOURCE_DATA.value


# ── mode integrity ──────────────────────────────────────────────────────────
def test_mode_is_carried_through_verbatim_and_never_defaulted(store):
    replay = _open(store, mode=ShadowMode.REPLAY)
    live = _open(store, mode=ShadowMode.LIVE_PUBLIC)
    _round_trips(store, replay, 2)
    _round_trips(store, live, 2)

    assert observation_from_shadow(store, replay).observation.mode == "REPLAY"
    assert observation_from_shadow(store, live).observation.mode == "LIVE_PUBLIC"


def test_a_session_whose_mode_cannot_be_read_is_refused_not_labelled_shadow(store):
    sid = _open(store)
    store.connection.execute("UPDATE shadow_sessions SET mode='' WHERE session_id=?", (sid,))
    store.connection.commit()

    with pytest.raises(ValueError, match="no mode"):
        observation_from_shadow(store, sid)


def test_a_cutoff_cannot_be_given_two_ways_at_once(store):
    sid = _open(store)
    with pytest.raises(ValueError, match="not both"):
        observation_from_shadow(store, sid, as_of="2026-09-02T00:00:00Z", max_seq=3)


# ── structural invariants ───────────────────────────────────────────────────
def test_the_adapter_reads_no_clock():
    """NO_FUTURE_DATA_LEAKAGE has a structural half: no ambient time source.

    Checked by parsing the module rather than grepping, so this test cannot be
    satisfied by a comment and cannot be broken by one either.
    """
    tree = ast.parse(ADAPTER_SRC.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not ({"datetime", "time", "calendar"} & imported), imported

    called = {
        n.func.attr for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert not ({"now", "utcnow", "today", "time", "monotonic"} & called), called


def test_the_adapter_holds_no_execution_authority():
    tree = ast.parse(ADAPTER_SRC.read_text())
    called = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute):
                called.add(n.func.attr)
            elif isinstance(n.func, ast.Name):
                called.add(n.func.id)
    forbidden = {"submit", "place", "execute", "send_order", "cancel", "promote",
                 "record_fill", "append_event", "record_blocked", "set_status", "commit"}
    assert not (forbidden & called), forbidden & called


def test_the_adapter_defines_no_second_observation_type():
    """The brief's one hard structural rule: do not fork the Observation DTO."""
    tree = ast.parse(ADAPTER_SRC.read_text())
    classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    assert "Observation" not in classes

    # Compared by ORIGIN, not identity: another suite legitimately reloads
    # strategy_monitor to prove restart determinism, which rebinds the class
    # object without forking the type. Origin still catches the thing this test
    # exists to catch — an Observation defined anywhere but the monitor.
    from saathi.platform.tg import strategy_observation
    assert strategy_observation.Observation.__module__ == \
        "saathi.platform.tg.strategy_monitor"
    assert strategy_observation.Observation.__qualname__ == "Observation"


def test_the_result_never_claims_execution_authority(store):
    sid = _open(store)
    _round_trips(store, sid, 3)
    assert observation_from_shadow(store, sid).authorizes_execution is False


def test_repeated_reads_of_a_broken_session_converge_rather_than_accumulate(store):
    """The adapter's one side effect must not compound.

    `reconcile` flips a broken session's status as it fails closed, so the adapter
    is not strictly read-only. It recomputes from history, so a second read must
    reach the identical verdict — otherwise a monitoring loop calling this on a
    schedule would drift.
    """
    sid = _open(store)
    _round_trips(store, sid, 5)
    store.record_fill(sid, 9001, symbol="ETHUSDT", side="BUY", quantity="1",
                      reference_price="10", fill_price="10", fee="0")

    first = observation_from_shadow(store, sid, average_portfolio_value="250000")
    second = observation_from_shadow(store, sid, average_portfolio_value="250000")

    assert first.observation == second.observation
    assert first.status == second.status == AdapterStatus.RECONCILIATION_REQUIRED.value


def test_the_attribution_period_matches_the_observation_window(store):
    sid = _open(store)
    end = _round_trips(store, sid, 5, day0=1)
    _round_trips(store, sid, 5, start_seq=end, day0=20)

    bounded = observation_from_shadow(store, sid, max_seq=20,
                                      average_portfolio_value="250000")
    # A sequence-bounded read carries no `as_of`, so the window must come from
    # the events actually inside it — not be left open.
    assert bounded.observation.window_end is not None
    assert bounded.observation.window_end < "2026-09-20T00:00:00Z"


def test_a_book_that_cannot_be_rebuilt_returns_a_status_not_an_exception(store):
    """An underivable book must not crash a monitoring caller.

    `reconcile` catches the derivation failure, but every layer downstream —
    `records_from_session` among them — derives the same portfolio and would
    raise. The adapter has to stop at the reconciliation verdict.
    """
    from saathi.platform.tg.shadow_session import ShadowReconciliationError

    sid = _open(store)
    _round_trips(store, sid, 1)
    # Sell more than was ever held: history that does not add up.
    store.append_event(sid, 500, ShadowEventKind.HYPOTHETICAL_FILL, {"oversell": True},
                       observed_at="2026-09-02T00:00:00Z")
    store.record_fill(sid, 500, symbol="BTCUSDT", side="SELL", quantity="9999",
                      reference_price="100", fill_price="100", fee="1")

    with pytest.raises(ShadowReconciliationError):
        store.derive_portfolio(sid)  # the raw layer still fails loudly

    result = observation_from_shadow(store, sid, average_portfolio_value="250000")

    assert result.status == AdapterStatus.RECONCILIATION_REQUIRED.value
    assert result.observation.reconciliation_ok is False
    assert result.observation.net_return is None
    assert result.detail
