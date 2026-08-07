"""M62.4 — deterministic strategy versioning + bias-resistant backtesting.

Unit + persistence + integration + adversarial + HTTP. Proves immutable versions,
structural look-ahead prevention, deterministic result hashing, non-overlapping
splits, transaction costs + slippage, reconciling portfolio accounting, validated
metrics, walk-forward, stress, sensitivity, the broken-strategy matrix, read-only
research references, the simulation-only Guardian veto, and that NO execution
authority is added.
"""
from __future__ import annotations

import copy
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.service import reset_platform_for_tests
from saathi.platform.market_data.fixtures import build_bars, dataset_hash
from saathi.platform.market_data.models import Timeframe
from saathi.platform.strategy import (
    StrategyService, StrategyStore, run_backtest, valid_momentum, valid_mean_reversion,
    valid_buy_and_hold, validate_strategy, is_runnable, evaluate_backtest, SufficiencyPolicy,
    compute_feature, compute_metrics, PortfolioAccountant, simulate_fill, target_quantity,
    SizingError, make_chronological_splits, check_splits, build_folds, Fold, aggregate_folds,
    strategy_hash, ZERO_COST, REALISTIC_COST, STRESSED_COST, BacktestContext, LookAheadViolation,
    SimulatedOrder, SimOrderStatus, can_strategy_transition, StrategyStatus, evaluate_signals,
)
from saathi.platform.strategy.models import FeatureSpec, FeatureKind, SizingRule, SizingMethod, D
from saathi.platform.strategy.fixtures import BROKEN_MATRIX, strategy_fixture_manifest
from saathi.platform.strategy import stress as stress_mod


def _ctx(role="owner", org="o1"):
    return PlatformExecutionContext(user_id="u1", role=role, org_id=org, workspace_id="w1")


def _svc(tmp_path):
    return StrategyService(StrategyStore(db_path=tmp_path / "strat.db"))


# ── unit: features ────────────────────────────────────────────────────────────
def _bars(name="TRENDING", n=30):
    return build_bars(name, Timeframe.D1, n)


def test_feature_sma_hand_calculated():
    bars = _bars("FLAT", 12)
    spec = FeatureSpec("sma", FeatureKind.SMA, lookback=3)
    w = bars[:3]
    expected = (w[0].close + w[1].close + w[2].close) / Decimal(3)
    assert compute_feature(spec, w) == expected


def test_feature_return_hand_calculated():
    bars = _bars("TRENDING", 12)
    spec = FeatureSpec("ret", FeatureKind.RETURN, lookback=1)
    w = bars[:2]
    expected = (w[1].close - w[0].close) / w[0].close
    assert compute_feature(spec, w) == expected


def test_feature_not_ready_returns_none():
    spec = FeatureSpec("sma", FeatureKind.SMA, lookback=10)
    assert compute_feature(spec, _bars("FLAT", 12)[:3]) is None  # warm-up not full


def test_feature_rolling_high_low_and_momentum():
    bars = _bars("HIGH_VOLATILITY", 20)
    w = bars[:5]
    assert compute_feature(FeatureSpec("hi", FeatureKind.ROLLING_HIGH, lookback=5, source="high"), w) == max(b.high for b in w)
    assert compute_feature(FeatureSpec("lo", FeatureKind.ROLLING_LOW, lookback=5, source="low"), w) == min(b.low for b in w)
    mom = compute_feature(FeatureSpec("m", FeatureKind.MOMENTUM, lookback=4), w)
    assert mom == w[-1].close - w[0].close


# ── unit: no-future-data access ───────────────────────────────────────────────
def test_context_refuses_future_bar():
    ctx = BacktestContext(_bars("FLAT", 10))
    ctx._set_cursor(3)
    with pytest.raises(LookAheadViolation):
        ctx.bar_at(1)
    # past + present are fine and recorded
    ctx.window(3)
    assert ctx.max_accessed_epoch <= ctx.decision_epoch


def test_future_peek_records_violation_epoch():
    ctx = BacktestContext(_bars("FLAT", 10))
    ctx._set_cursor(3)
    ctx.future_peek(2)
    assert ctx.max_accessed_epoch > ctx.decision_epoch  # instrumentation catches it


# ── unit: signals ─────────────────────────────────────────────────────────────
def test_signal_skips_unwarmed_feature():
    from saathi.platform.strategy.models import SignalRule, Comparator, SignalAction
    rules = [SignalRule("f", Comparator.GT, "0", SignalAction.ENTER_LONG)]
    action, _ = evaluate_signals(rules, {"f": None}, {})
    assert action is None


# ── unit: sizing / leverage ───────────────────────────────────────────────────
def test_sizing_equity_fraction():
    rule = SizingRule(SizingMethod.EQUITY_FRACTION, Decimal("0.5"), Decimal("1"))
    qty = target_quantity(rule, equity=Decimal("100000"), price=Decimal("100"),
                          quantity_precision=0, risk_max_fraction=Decimal("1"))
    assert qty == Decimal("500")


def test_sizing_rejects_leverage():
    rule = SizingRule(SizingMethod.EQUITY_FRACTION, Decimal("2"), Decimal("1"))
    with pytest.raises(SizingError):
        target_quantity(rule, equity=Decimal("100000"), price=Decimal("100"),
                        quantity_precision=0, risk_max_fraction=Decimal("1"))


def test_sizing_rejects_cap_over_one():
    rule = SizingRule(SizingMethod.EQUITY_FRACTION, Decimal("0.5"), Decimal("3"))
    with pytest.raises(SizingError):
        target_quantity(rule, equity=Decimal("100000"), price=Decimal("100"),
                        quantity_precision=0, risk_max_fraction=Decimal("3"))


# ── unit: fee + slippage models ───────────────────────────────────────────────
def test_fee_model_minimum_applies():
    from saathi.platform.strategy.execution_model import compute_fees
    fee = compute_fees(REALISTIC_COST, Decimal("1"), Decimal("100"))
    assert fee == Decimal("1.00")  # min_fee floor


def test_slippage_is_adverse():
    from saathi.platform.strategy.execution_model import apply_slippage
    bar = _bars("FLAT", 5)[0]
    buy, _ = apply_slippage(REALISTIC_COST, "BUY", Decimal("100"), bar)
    sell, _ = apply_slippage(REALISTIC_COST, "SELL", Decimal("100"), bar)
    assert buy > Decimal("100") and sell < Decimal("100")


def test_limit_order_not_reached_rejected():
    bars = _bars("FLAT", 5)
    order = simulate_fill(seq=1, side="BUY", order_type="LIMIT", quantity=Decimal("10"),
                          decision_bar=bars[0], fill_bar=bars[1], cost=ZERO_COST, limit_price=Decimal("1"))
    assert order.status == SimOrderStatus.REJECTED


# ── unit: accounting invariants ───────────────────────────────────────────────
def test_accounting_reconciles():
    acct = PortfolioAccountant(starting_cash=Decimal("100000"), instruments=["X"])
    bars = _bars("TRENDING", 5)
    buy = simulate_fill(seq=1, side="BUY", order_type="MARKET", quantity=Decimal("100"),
                        decision_bar=bars[0], fill_bar=bars[1], cost=REALISTIC_COST)
    acct.apply(buy)
    marks = {"X": bars[1].close}
    assert acct.check_invariants(marks) == []
    sell = simulate_fill(seq=2, side="SELL", order_type="MARKET", quantity=Decimal("100"),
                         decision_bar=bars[2], fill_bar=bars[3], cost=REALISTIC_COST)
    acct.apply(sell)
    assert acct.check_invariants({"X": bars[3].close}) == []


def test_accounting_long_only_no_oversell():
    acct = PortfolioAccountant(starting_cash=Decimal("100000"), instruments=["X"])
    bars = _bars("FLAT", 4)
    acct.apply(simulate_fill(seq=1, side="BUY", order_type="MARKET", quantity=Decimal("10"),
                             decision_bar=bars[0], fill_bar=bars[1], cost=ZERO_COST))
    acct.apply(simulate_fill(seq=2, side="SELL", order_type="MARKET", quantity=Decimal("999"),
                             decision_bar=bars[1], fill_bar=bars[2], cost=ZERO_COST))
    assert acct.positions["X"].quantity == Decimal("0")   # clamped, never negative


# ── unit: metrics ─────────────────────────────────────────────────────────────
def test_metrics_zero_denominator_handled():
    from saathi.platform.strategy.models import EquityPoint
    curve = [EquityPoint(epoch=float(i), equity=Decimal("100000"), cash=Decimal("100000"),
                         positions_value=Decimal("0"), drawdown=Decimal("0")) for i in range(5)]
    m = compute_metrics(curve, [], starting_cash=Decimal("100000"), total_fees=Decimal("0"),
                        total_slippage_cost=Decimal("0"), turnover=Decimal("0"))
    assert m["sharpe_ratio"].status == "UNDEFINED"       # zero volatility, not inf
    assert m["sharpe_ratio"].value is None


def test_metrics_insufficient_trades_flagged():
    from saathi.platform.strategy.models import EquityPoint
    curve = [EquityPoint(epoch=float(i), equity=Decimal("100000"), cash=Decimal("100000"),
                         positions_value=Decimal("0"), drawdown=Decimal("0")) for i in range(3)]
    m = compute_metrics(curve, [], starting_cash=Decimal("100000"), total_fees=Decimal("0"),
                        total_slippage_cost=Decimal("0"), turnover=Decimal("0"))
    assert m["trade_count"].status == "INSUFFICIENT_SAMPLE"


# ── unit: dataset splitting ───────────────────────────────────────────────────
def test_splits_non_overlapping():
    epochs = [float(i) for i in range(20)]
    splits = make_chronological_splits(epochs, train=0.6, validation=0.2)
    assert check_splits(splits) == []
    kinds = [s.kind.value for s in splits]
    assert kinds == ["TRAIN", "VALIDATION", "TEST"]


def test_splits_reject_shuffled():
    with pytest.raises(ValueError):
        make_chronological_splits([5.0, 1.0, 3.0])


def test_overlap_detected():
    from saathi.platform.strategy.walk_forward import Split, SplitKind
    bad = [Split(SplitKind.TRAIN, 0, 10), Split(SplitKind.TEST, 5, 15)]
    assert check_splits(bad)


# ── unit: walk-forward folds ──────────────────────────────────────────────────
def test_walk_forward_folds_are_ordered():
    epochs = [float(i) for i in range(30)]
    folds = build_folds(epochs, n_folds=3, mode="expanding", train_min=10, test_size=5)
    for tr, va, te in folds:
        assert tr[0] <= va[0] < te[0]     # test always follows train/validation


def test_aggregate_surfaces_failures():
    folds = [Fold(0, (0, 1), (1, 2), (2, 3), {}, "h", 1, status="OK", metrics={"total_return": "0.1", "max_drawdown": "0.05"}),
             Fold(1, (0, 1), (1, 2), (2, 3), {}, "h", 1, status="FAILED")]
    agg = aggregate_folds(folds)
    assert agg["failed"] == 1 and agg["consistent"] is False


# ── unit: run-manifest hashing / determinism ──────────────────────────────────
def test_deterministic_result_hash():
    d = valid_momentum("TRENDING")
    bars = _bars("TRENDING", 30)
    r1 = run_backtest(d, bars)
    r2 = run_backtest(d, bars)
    r3 = run_backtest(d, bars)
    assert r1.result_hash == r2.result_hash == r3.result_hash
    assert r1.manifest["strategy_hash"] and r1.manifest["dataset_hash"]


def test_strategy_hash_changes_with_logic():
    d1 = valid_momentum("TRENDING")
    d2 = copy.deepcopy(d1)
    d2.warmup_bars = 999
    assert strategy_hash(d1) != strategy_hash(d2)


def test_dataset_hash_matches_market_data():
    # engine dataset hash is over a stable projection; classification must not change it
    d = valid_momentum("TRENDING")
    bars = _bars("TRENDING", 30)
    r = run_backtest(d, bars)
    r2 = run_backtest(d, bars)   # bars already classified in-place would break a naive hash
    assert r.manifest["dataset_hash"] == r2.manifest["dataset_hash"]


# ── structural validation ─────────────────────────────────────────────────────
def test_structural_valid_strategy_runnable():
    ok, findings = is_runnable(valid_momentum("TRENDING"))
    assert ok


def test_structural_dangling_signal_rejected():
    d = valid_momentum("TRENDING")
    from saathi.platform.strategy.models import SignalRule, Comparator, SignalAction
    d.signals = [SignalRule("ghost", Comparator.GT, "nope", SignalAction.ENTER_LONG)]
    ok, findings = is_runnable(d)
    assert not ok and any(f.code == "DANGLING_SIGNAL_REF" for f in findings)


# ── statistical sufficiency outcomes ──────────────────────────────────────────
def test_evaluate_excessive_drawdown():
    from saathi.platform.strategy.metrics import Metric, MetricStatus
    m = {"number_of_observations": Metric("number_of_observations", Decimal("50"), "OK"),
         "trade_count": Metric("trade_count", Decimal("10"), "OK"),
         "max_drawdown": Metric("max_drawdown", Decimal("0.9"), "OK")}
    res = evaluate_backtest(m, oos_observations=10, trade_pnls=[Decimal("1")] * 10)
    assert res.outcome == "EXCESSIVE_DRAWDOWN" and not res.technically_valid


def test_evaluate_single_trade_dominance():
    from saathi.platform.strategy.metrics import Metric
    m = {"number_of_observations": Metric("number_of_observations", Decimal("50"), "OK"),
         "trade_count": Metric("trade_count", Decimal("10"), "OK"),
         "max_drawdown": Metric("max_drawdown", Decimal("0.1"), "OK")}
    pnls = [Decimal("100")] + [Decimal("1")] * 9
    res = evaluate_backtest(m, oos_observations=10, trade_pnls=pnls)
    assert res.outcome == "FAILED_BIAS_CHECK"


# ── integration: full pipeline ────────────────────────────────────────────────
def test_full_pipeline(tmp_path):
    svc = _svc(tmp_path)
    ctx = _ctx()
    body = valid_momentum("TRENDING").to_public()
    body["cost_tier"] = "realistic"
    s = svc.create_strategy(ctx, {**body, "instrument": "TRENDING"})
    sid = s["strategy_id"]
    run = svc.create_backtest(ctx, sid, dataset="TRENDING", n=30)
    rid = run["run_id"]
    done = svc.run_backtest(ctx, sid, rid)
    assert done["status"] == "COMPLETE" and done["completed"] == 1
    assert svc.metrics(ctx, sid, rid)["sharpe_ratio"]["value"]
    assert svc.stress(ctx, sid, rid)["_summary"]["blocked_invalid"]      # invalid regime blocked
    assert "surface" in svc.sensitivity(ctx, sid, rid)
    g = svc.store.get_result("o1", rid, "guardian")
    assert g["is_trade_approval"] is False and g["context"] == "SIMULATION_ONLY"
    m = svc.manifest(ctx, sid, rid)
    assert m["result_hash"] and m["completed"]


def test_version_immutability_and_lineage(tmp_path):
    svc = _svc(tmp_path)
    ctx = _ctx()
    s = svc.create_strategy(ctx, {**valid_momentum("TRENDING").to_public(), "instrument": "TRENDING"})
    sid = s["strategy_id"]
    v1 = svc.create_version(ctx, sid, rationale="baseline")
    v2 = svc.create_version(ctx, sid, parameters={"tweak": 1}, rationale="param change")
    assert v2["version"] == v1["version"] + 1 and v2["parent_version"] == v1["version"]
    # a completed run's manifest is frozen — re-run refused
    run = svc.create_backtest(ctx, sid, dataset="TRENDING", n=30)
    svc.run_backtest(ctx, sid, run["run_id"])
    with pytest.raises(PlatformContextError):
        svc.run_backtest(ctx, sid, run["run_id"])


# ── persistence: tenant isolation + restart ───────────────────────────────────
def test_tenant_isolation(tmp_path):
    store = StrategyStore(db_path=tmp_path / "iso.db")
    svc_a = StrategyService(store)
    a = svc_a.create_strategy(_ctx(org="orgA"), {**valid_momentum("TRENDING").to_public(), "instrument": "TRENDING"})
    # org B cannot see org A's strategy
    with pytest.raises(PlatformContextError):
        svc_a.get_strategy(_ctx(org="orgB"), a["strategy_id"])


def test_restart_recovery(tmp_path):
    db = tmp_path / "restart.db"
    ctx = _ctx()
    svc1 = StrategyService(StrategyStore(db_path=db))
    s = svc1.create_strategy(ctx, {**valid_momentum("TRENDING").to_public(), "instrument": "TRENDING"})
    run = svc1.create_backtest(ctx, s["strategy_id"], dataset="TRENDING", n=30)
    done = svc1.run_backtest(ctx, s["strategy_id"], run["run_id"])
    # reopen the DB in a fresh service
    svc2 = StrategyService(StrategyStore(db_path=db))
    reloaded = svc2.get_backtest(ctx, s["strategy_id"], run["run_id"])
    assert reloaded["result_hash"] == done["result_hash"] and reloaded["completed"] == 1


def test_optimistic_concurrency(tmp_path):
    svc = _svc(tmp_path)
    ctx = _ctx()
    s = svc.create_strategy(ctx, {**valid_momentum("TRENDING").to_public(), "instrument": "TRENDING"})
    sid = s["strategy_id"]
    body = {**valid_momentum("TRENDING").to_public(), "instrument": "TRENDING"}
    with pytest.raises(PlatformContextError):
        svc.update_strategy(ctx, sid, body, expected_version=999)   # stale


# ── adversarial: the broken-strategy matrix ───────────────────────────────────
def test_broken_matrix_structural():
    for name, spec in BROKEN_MATRIX.items():
        if spec["expected_channel"] != "structural":
            continue
        d = spec["builder"]()
        d.instrument_universe = [spec["dataset"]]
        ok, findings = is_runnable(d)
        codes = [f.code for f in findings if f.severity == "critical"]
        assert not ok and spec["expected_code"] in codes, (name, codes)


def test_broken_look_ahead_rejected():
    spec = BROKEN_MATRIX["LOOK_AHEAD_STRATEGY"]
    d = spec["builder"](); d.instrument_universe = ["TRENDING"]
    r = run_backtest(d, _bars("TRENDING", 30), probe=spec["probe"])
    assert r.status == "REJECTED" and not r.look_ahead_ok


def test_broken_invalid_price_blocked():
    d = valid_momentum("INVALID_OHLC")
    r = run_backtest(d, _bars("INVALID_OHLC", 30))
    assert r.status == "REJECTED" and "quality" in r.reason


def test_broken_duplicate_order_deduped():
    spec = BROKEN_MATRIX["DUPLICATE_ORDER_STRATEGY"]
    d = spec["builder"]()
    r = run_backtest(d, _bars("TRENDING", 30))
    buys = [f for f in r.fills if f.side == "BUY"]
    assert len(buys) == 1   # engine held==0 guard prevents duplicate entries


def test_broken_cost_sensitive_flagged():
    from saathi.platform.strategy.fixtures import _zero_cost_dependent
    cr = stress_mod.cost_resilience(_zero_cost_dependent(), _bars("MEAN_REVERTING", 30))
    assert cr["cost_sensitive"] is True


def test_out_of_order_bars_blocked():
    d = valid_momentum("OUT_OF_ORDER_BARS")
    r = run_backtest(d, _bars("OUT_OF_ORDER_BARS", 30))
    assert r.status == "REJECTED"


def test_negative_quantity_rejected():
    bars = _bars("FLAT", 5)
    order = simulate_fill(seq=1, side="BUY", order_type="MARKET", quantity=Decimal("-5"),
                          decision_bar=bars[0], fill_bar=bars[1], cost=ZERO_COST)
    assert order.status == SimOrderStatus.REJECTED


# ── research integration (read-only) ──────────────────────────────────────────
def test_research_reference_non_authoritative_when_unpublished(tmp_path):
    from saathi.platform.research import ResearchStore, ResearchService
    rstore = ResearchStore(db_path=tmp_path / "research.db")
    rsvc = ResearchService(rstore)
    ctx = _ctx()
    p = rsvc.create_project(ctx, title="T", question="q?")
    svc = StrategyService(StrategyStore(db_path=tmp_path / "strat.db"), research_store=rstore)
    s = svc.create_strategy(ctx, {**valid_momentum("TRENDING").to_public(), "instrument": "TRENDING"})
    sid = s["strategy_id"]
    cur = svc.get_strategy(ctx, sid)
    res = svc.link_research(ctx, sid, project_id=p["project_id"], expected_version=cur["version"])
    assert res["thesis_ref"]["authoritative"] is False   # no published thesis => non-authoritative


# ── guardian simulation veto (never approval) ─────────────────────────────────
def test_guardian_sim_veto_is_not_approval():
    from saathi.platform.strategy import simulate_guardian_review
    dec = simulate_guardian_review(instrument="X", intended_quantity=Decimal("100000"),
                                   reference_price=Decimal("100"), starting_cash=Decimal("100000"))
    assert dec["is_trade_approval"] is False and dec["context"] == "SIMULATION_ONLY"
    assert dec["allowed"] is False   # oversized exposure vetoed by fail-closed guardian


# ── permissions ───────────────────────────────────────────────────────────────
def test_viewer_cannot_create(tmp_path):
    svc = _svc(tmp_path)
    with pytest.raises(PlatformContextError):
        svc.create_strategy(_ctx(role="viewer"), {**valid_momentum("TRENDING").to_public(), "instrument": "TRENDING"})


def test_only_owner_can_certify(tmp_path):
    svc = _svc(tmp_path)
    owner = _ctx(role="owner")
    s = svc.create_strategy(owner, {**valid_momentum("TRENDING").to_public(), "instrument": "TRENDING"})
    with pytest.raises(PlatformContextError):
        svc.certify_strategy(_ctx(role="operator"), s["strategy_id"], expected_version=s["version"], decision="validate")


# ── HTTP contract + no trading endpoint ───────────────────────────────────────
def test_http_strategy(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_STRATEGY_DB", str(tmp_path / "http.db"))
    platform = reset_platform_for_tests(tmp_path / "plat.db")
    owner = platform.bootstrap_owner_secure(email="o@m624.local", name="O", password="OwnerPassw0rd!",
                                             org_name="Org", workspace_name="WS")
    from saathi.server import app
    client = TestClient(app)
    h = {"X-Platform-Token": owner["token"]}
    assert client.get("/api/v1/platform/strategies").status_code == 401
    body = {**valid_momentum("TRENDING").to_public(), "instrument": "TRENDING", "cost_tier": "realistic"}
    sid = client.post("/api/v1/platform/strategies", json=body, headers=h).json()["strategy"]["strategy_id"]
    bt = client.post(f"/api/v1/platform/strategies/{sid}/backtests", json={"dataset": "TRENDING", "n": 30}, headers=h)
    rid = bt.json()["backtest"]["run_id"]
    run = client.post(f"/api/v1/platform/strategies/{sid}/backtests/{rid}/run", headers=h)
    assert run.status_code == 200 and run.json()["backtest"]["status"] == "COMPLETE"
    for ep in ["metrics", "trades", "equity", "validation", "stress", "sensitivity", "manifest"]:
        assert client.get(f"/api/v1/platform/strategies/{sid}/backtests/{rid}/{ep}", headers=h).status_code == 200
    # NO order/broker endpoints under strategy
    assert client.post(f"/api/v1/platform/strategies/{sid}/order", json={}, headers=h).status_code in (404, 405)


def test_fixture_manifest_stable():
    m1 = strategy_fixture_manifest()
    m2 = strategy_fixture_manifest()
    assert m1 == m2 and m1["valid"] and m1["broken"]
