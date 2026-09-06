"""PERFORMANCE-ATTRIBUTION-V2 — deterministic attribution over canonical records.

Attribution is a DERIVED VIEW. It explains what the books already say; it never
becomes a second source of truth, and it never turns an estimate into a fact.

The line these tests defend hardest is the one between what happened
(ACCOUNTING), what a frozen rule says would have happened (COUNTERFACTUAL), and
what merely co-occurred (OBSERVATIONAL).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from saathi.platform.research.store import ResearchStore
from saathi.platform.tg.attribution_source import (
    counterfactuals_from_session,
    records_from_session,
)
from saathi.platform.tg.attribution_v2 import (
    CALCULATION_VERSION,
    COUNTERFACTUAL_METHOD_VERSION,
    AttributionRecord,
    AttributionStatus,
    CounterfactualOutcome,
    CounterfactualRecord,
    DecisionLayerRecord,
    EvidenceClass,
    cost_decomposition,
    decision_layer_attribution,
    guardian_counterfactual,
    performance_attribution_report,
    reconciles,
    report_id,
    turnover,
)
from saathi.platform.tg.shadow_session import (
    ShadowEventKind, ShadowMode, ShadowSessionStore,
)

X = Decimal


def rec(**kw):
    base = dict(strategy_id="mr", symbol="BTCUSDT", venue="BINANCE", asset_class="CRYPTO",
                gross_pnl=X("1000"), cost=X("90"), fee=X("60"), spread_cost=X("20"),
                slippage_cost=X("10"), notional=X("60000"))
    base.update(kw)
    return AttributionRecord(**base)


# ── cost decomposition ──────────────────────────────────────────────────────

def test_costs_split_into_fee_spread_and_slippage():
    d = cost_decomposition([rec(), rec(fee=X("30"), spread_cost=X("10"), slippage_cost=X("5"), cost=X("45"))])
    assert d["status"] == AttributionStatus.OK.value
    assert d["evidence"] == EvidenceClass.ACCOUNTING.value
    assert d["fee_drag"] == X("90")
    assert d["spread_drag"] == X("30")
    assert d["slippage_drag"] == X("15")
    assert d["total_cost"] == X("135")


def test_a_partial_breakdown_is_refused_not_half_reported():
    """Attributing unreported costs to whichever component happens to exist is
    worse than saying the split is unavailable."""
    d = cost_decomposition([rec(), rec(fee=None, spread_cost=None, slippage_cost=None)])
    assert d["status"] == AttributionStatus.DATA_INSUFFICIENT.value
    assert d["total_cost"] == X("180")          # the total is still honest
    assert "fee_drag" not in d


def test_components_that_do_not_sum_to_the_total_fail_closed():
    bad = rec(fee=X("60"), spread_cost=X("20"), slippage_cost=X("10"), cost=X("999"))
    d = cost_decomposition([bad])
    assert d["status"] == AttributionStatus.RECONCILIATION_REQUIRED.value


def test_blocked_records_contribute_no_cost():
    d = cost_decomposition([rec(), rec(guardian_blocked=True, fee=X("999"), cost=X("999"))])
    assert d["fee_drag"] == X("60"), "a blocked proposal paid nothing"


# ── turnover ────────────────────────────────────────────────────────────────

def test_turnover_names_its_convention():
    t = turnover([rec()], average_portfolio_value=X("100000"))
    assert t["convention"] == "ONE_WAY", "gross, one-way and round-trip differ by 2x"
    assert t["turnover_ratio"] == X("0.6")
    assert t["evidence"] == EvidenceClass.ACCOUNTING.value


def test_turnover_without_a_portfolio_value_is_unavailable_not_zero():
    t = turnover([rec()])
    assert t["status"] == AttributionStatus.DATA_INSUFFICIENT.value
    assert t["traded_notional"] == X("60000")
    assert "turnover_ratio" not in t
    for bad in (X("0"), X("-1")):
        assert turnover([rec()], average_portfolio_value=bad)["status"] \
            == AttributionStatus.DATA_INSUFFICIENT.value


# ── decision-layer attribution ──────────────────────────────────────────────

def test_each_layer_reports_the_exposure_it_removed():
    layers = [DecisionLayerRecord(
        "mr", "BTCUSDT", requested_weight=X("0.20"),
        constructed_weight=X("0.08"), risk_adjusted_weight=X("0.05"),
        construction_reason_codes=("POSITION_CAP", "CRYPTO_SLEEVE_CAP"),
        risk_reason_codes=("DRAWDOWN_REDUCTION",),
    )]
    d = decision_layer_attribution(layers)
    assert d["requested_exposure"] == X("0.20")
    assert d["constructed_exposure"] == X("0.08")
    assert d["final_exposure"] == X("0.05")
    assert d["construction"]["removed_exposure"] == X("-0.12")
    assert d["risk"]["removed_exposure"] == X("-0.03")
    assert d["construction"]["reason_codes"]["POSITION_CAP"] == 1
    assert d["risk"]["reason_codes"]["DRAWDOWN_REDUCTION"] == 1


def test_a_guardian_block_yields_zero_final_exposure_not_the_proposal():
    layers = [DecisionLayerRecord("mr", "BTCUSDT", X("0.20"), constructed_weight=X("0.08"),
                                  risk_adjusted_weight=X("0.05"), guardian_outcome="BLOCKED_GUARDIAN",
                                  guardian_reason_codes=("VENUE_DISABLED",))]
    d = decision_layer_attribution(layers)
    assert d["final_exposure"] == X("0")
    assert d["guardian"]["blocked"] == 1
    assert d["guardian"]["blocked_exposure"] == X("0.05")


def test_a_zero_allocation_is_a_legitimate_construction_outcome():
    layers = [DecisionLayerRecord("mr", "BTCUSDT", X("0.20"), constructed_weight=X("0"),
                                  construction_reason_codes=("ZERO_ALLOCATION",))]
    d = decision_layer_attribution(layers)
    assert d["construction"]["removed_exposure"] == X("-0.20")
    assert d["final_exposure"] == X("0")


def test_decision_layers_are_never_reported_as_returns():
    """A removed weight is an exposure fact, not a realized gain."""
    d = decision_layer_attribution([DecisionLayerRecord("mr", "BTCUSDT", X("0.20"),
                                                        constructed_weight=X("0.08"))])
    assert d["evidence"] == EvidenceClass.ACCOUNTING.value
    blob = str(d).lower()
    assert "return" not in blob or "not returns" in blob
    assert "not returns" in d["note"]


def test_no_decision_records_is_insufficient_not_an_empty_success():
    assert decision_layer_attribution([])["status"] == AttributionStatus.DATA_INSUFFICIENT.value


# ── Guardian counterfactual ─────────────────────────────────────────────────

@pytest.mark.parametrize("forward,expected", [
    (X("58000"), CounterfactualOutcome.AVOIDED_LOSS.value),
    (X("62000"), CounterfactualOutcome.MISSED_GAIN.value),
    (X("60000"), CounterfactualOutcome.NEUTRAL.value),
    (None, CounterfactualOutcome.INSUFFICIENT_DATA.value),
])
def test_blocked_trades_are_classified_in_both_directions(forward, expected):
    c = CounterfactualRecord("mr", "BTCUSDT", "GUARDIAN", X("60000"), X("1"), forward_price=forward)
    assert c.classify() == expected


def test_the_counterfactual_is_labelled_an_estimate_with_a_frozen_method():
    g = guardian_counterfactual([
        CounterfactualRecord("mr", "BTCUSDT", "GUARDIAN", X("60000"), X("1"), forward_price=X("58000")),
        CounterfactualRecord("mr", "BTCUSDT", "GUARDIAN", X("60000"), X("1"), forward_price=X("62000")),
        CounterfactualRecord("mr", "BTCUSDT", "GUARDIAN", X("60000"), X("1")),
    ])
    assert g["evidence"] == EvidenceClass.COUNTERFACTUAL.value
    assert g["method_version"] == COUNTERFACTUAL_METHOD_VERSION
    assert g["measured"] == 2 and g["unmeasured"] == 1
    assert g["net_forward_pnl_of_blocked"] == X("0")   # -2000 + 2000
    assert g["authorizes_execution"] is False
    assert "never added to it" in g["note"]


def test_a_counterfactual_never_enters_realized_pnl():
    records = [rec(gross_pnl=X("100"), cost=X("0"), fee=X("0"), spread_cost=X("0"), slippage_cost=X("0"))]
    cfs = [CounterfactualRecord("mr", "BTCUSDT", "GUARDIAN", X("60000"), X("1"), forward_price=X("90000"))]
    r = performance_attribution_report(records, counterfactuals=cfs)
    assert r["accounting"]["totals"]["net_pnl"] == X("100"), "a huge counterfactual must not move realized PnL"
    assert r["guardian_counterfactual"]["net_forward_pnl_of_blocked"] == X("30000")


# ── reconciliation ──────────────────────────────────────────────────────────

def test_every_dimension_reconciles_to_net():
    r = performance_attribution_report([
        rec(symbol="BTCUSDT", gross_pnl=X("1000")),
        rec(symbol="ETHUSDT", gross_pnl=X("-400"), cost=X("45"), fee=X("30"),
            spread_cost=X("10"), slippage_cost=X("5")),
    ])
    acc = r["accounting"]
    assert acc["reconciles"] is True
    assert acc["totals"]["net_pnl"] == X("1000") - X("90") + X("-400") - X("45")


def test_gross_minus_costs_equals_net():
    r = performance_attribution_report([rec()])
    t = r["accounting"]["totals"]
    assert t["gross_pnl"] - t["cost_drag"] == t["net_pnl"]
    assert r["costs"]["total_cost"] == t["cost_drag"], "no double counting between blocks"


# ── strategy provenance ─────────────────────────────────────────────────────

def test_ambiguous_strategy_provenance_is_declared_not_guessed():
    r = performance_attribution_report([rec(strategy_ambiguous=True)])
    assert r["by_strategy"]["status"] == AttributionStatus.AMBIGUOUS_PROVENANCE.value
    assert r["by_strategy"]["ambiguous_records"] == 1


def test_clean_provenance_attributes_by_strategy():
    r = performance_attribution_report([rec(strategy_id="mr"), rec(strategy_id="trend", gross_pnl=X("500"))])
    assert r["by_strategy"]["status"] == AttributionStatus.OK.value
    assert set(r["by_strategy"]["contributions"]) == {"mr", "trend"}


# ── benchmark ───────────────────────────────────────────────────────────────

def test_benchmark_is_versioned_and_all_or_nothing():
    full = performance_attribution_report([rec(benchmark_pnl=X("800"))],
                                          benchmark_version="BTC_BUY_AND_HOLD@1")
    assert full["benchmark"]["status"] == AttributionStatus.OK.value
    assert full["benchmark"]["version"] == "BTC_BUY_AND_HOLD@1"
    assert full["benchmark"]["excess_vs_benchmark"] == X("910") - X("800")

    partial = performance_attribution_report([rec(benchmark_pnl=X("800")), rec(benchmark_pnl=None)])
    assert partial["benchmark"]["status"] == AttributionStatus.DATA_INSUFFICIENT.value
    assert partial["benchmark"]["excess_vs_benchmark"] is None


# ── idempotency / restart reproducibility ───────────────────────────────────

def test_the_same_inputs_produce_the_same_report_id():
    a = performance_attribution_report([rec()], benchmark_version="B@1")
    b = performance_attribution_report([rec()], benchmark_version="B@1")
    assert a["report_id"] == b["report_id"]
    assert a["calculation_version"] == CALCULATION_VERSION


def test_a_changed_input_changes_the_report_id():
    a = performance_attribution_report([rec()])
    b = performance_attribution_report([rec(gross_pnl=X("1001"))])
    assert a["report_id"] != b["report_id"]


# ── numeric contract (FINANCIAL-NUMERIC-1) ──────────────────────────────────

def test_attribution_inherits_the_fail_closed_numeric_contract():
    from saathi.platform.tg.attribution_v2 import _dec
    from saathi.platform.trading_models import InvalidFinancialValue

    for hostile in ("NaN", "Infinity", "abc", True, object(), float("nan")):
        with pytest.raises(InvalidFinancialValue):
            _dec(hostile)
    assert _dec("1.25") == X("1.25")


def test_a_non_finite_portfolio_value_cannot_produce_a_turnover_ratio():
    for hostile in ("NaN", "Infinity"):
        with pytest.raises(Exception):
            turnover([rec()], average_portfolio_value=hostile)


# ── authority ───────────────────────────────────────────────────────────────

def test_attribution_holds_no_execution_authority():
    import saathi.platform.tg.attribution_v2 as mod
    import saathi.platform.tg.attribution_source as src

    for m in (mod, src):
        text = open(m.__file__).read()
        for banned in ("submit", "execute(", "place_order", "reserve_for_buy",
                       "ccxt", "binance.com", "requests.post"):
            assert banned not in text, f"{m.__name__} must not reach execution: {banned}"
    r = performance_attribution_report([rec()])
    assert r["authorizes_execution"] is False
    assert r["guardian_counterfactual"]["authorizes_execution"] is False


# ── over canonical shadow records ───────────────────────────────────────────

@pytest.fixture()
def session(tmp_path):
    store = ShadowSessionStore(research_store=ResearchStore(db_path=tmp_path / "attr.sqlite3"))
    sid = store.open_session(
        mode=ShadowMode.REPLAY, market="CRYPTO", strategy_version="mr@1.0.0",
        policy_versions={"guardian": "v2"}, feed_ref="replay:btc",
        opening_cash="250000", started_at="2026-09-01T00:00:00Z",
        benchmark="BTC_BUY_AND_HOLD",
    )
    return store, sid


def _fill(store, sid, seq, side, qty, px, fee="60"):
    store.append_event(sid, seq, ShadowEventKind.HYPOTHETICAL_FILL,
                       {"symbol": "BTCUSDT", "side": side, "qty": qty, "px": px})
    store.record_fill(sid, seq, symbol="BTCUSDT", side=side, quantity=qty,
                      reference_price=px, fill_price=px, fee=fee,
                      spread_cost="20", slippage_cost="10")


def test_a_round_trip_attributes_its_realized_pnl(session):
    store, sid = session
    _fill(store, sid, 1, "BUY", "1", "60000")
    _fill(store, sid, 2, "SELL", "1", "61000", fee="61")
    records = records_from_session(store, sid)
    assert len(records) == 1
    r = records[0]
    assert r.gross_pnl == X("1000"), "sold 1000 higher than bought"
    assert r.fee == X("121")
    assert r.cost == X("121") + X("40") + X("20")
    assert r.net_pnl == r.gross_pnl - r.cost


def test_an_open_position_without_a_mark_claims_no_unrealized_gain(session):
    store, sid = session
    _fill(store, sid, 1, "BUY", "1", "60000")
    unmarked = records_from_session(store, sid)[0]
    marked = records_from_session(store, sid, mark_prices={"BTCUSDT": "61000"})[0]
    # Unmarked: only the cash that actually left. Marking it at cost would assert
    # the position is flat, which nobody observed.
    assert unmarked.gross_pnl == X("-60000")
    assert marked.gross_pnl == X("1000")


def test_blocked_proposals_become_counterfactual_records(session):
    store, sid = session
    store.append_event(sid, 1, ShadowEventKind.GUARDIAN, {"outcome": "BLOCKED"})
    store.record_blocked(sid, 1, symbol="BTCUSDT", side="BUY", quantity="1",
                         reference_price="60000", blocked_by="GUARDIAN",
                         reason_codes=["DRAWDOWN_LIMIT"])
    store.observe_counterfactual(sid, 1, "58000")
    cfs = counterfactuals_from_session(store, sid)
    assert len(cfs) == 1
    assert cfs[0].classify() == CounterfactualOutcome.AVOIDED_LOSS.value
    assert cfs[0].reason_codes == ("DRAWDOWN_LIMIT",)


def test_attribution_recomputes_identically_after_a_restart(session, tmp_path):
    store, sid = session
    _fill(store, sid, 1, "BUY", "1", "60000")
    _fill(store, sid, 2, "SELL", "1", "61000", fee="61")
    before = performance_attribution_report(
        records_from_session(store, sid), benchmark_version="BTC_BUY_AND_HOLD@1")
    store.close()

    # A brand-new process, reading only the persisted canonical events.
    reopened = ShadowSessionStore(research_store=ResearchStore(db_path=tmp_path / "attr.sqlite3"))
    after = performance_attribution_report(
        records_from_session(reopened, sid), benchmark_version="BTC_BUY_AND_HOLD@1")

    assert after["report_id"] == before["report_id"], "attribution must be reproducible"
    assert after["accounting"]["totals"] == before["accounting"]["totals"]


def test_attribution_mutates_nothing_it_reads(session):
    store, sid = session
    _fill(store, sid, 1, "BUY", "1", "60000")
    before = store.derive_portfolio(sid)
    performance_attribution_report(records_from_session(store, sid),
                                   counterfactuals=counterfactuals_from_session(store, sid))
    after = store.derive_portfolio(sid)
    assert after.cash == before.cash
    assert after.positions == before.positions
    assert after.fills == before.fills


def test_an_unknown_session_is_refused_not_reported_as_empty(session):
    store, _ = session
    with pytest.raises(ValueError):
        records_from_session(store, "shadow-nope")
