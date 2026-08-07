"""M176–M183 — Paper validation, walk-forward, stress, portfolio, recovery."""
from __future__ import annotations

from decimal import Decimal

import pytest

from saathi.platform.tg import (
    LIVE_TRADING_AUTHORIZED,
    LIVE_ORDER_CAPABLE,
    BROKER_CREDENTIAL_SUPPORT,
    DataClassification,
    AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA,
    classify_dataset,
    is_authoritative,
    incomplete_result,
    PortfolioRiskAnalyzer,
    PortfolioState,
    ReconciliationVerdict,
    RobustnessVerdict,
    run_recovery_suite,
    TradingGuardianService,
)
from saathi.platform.tg.data_contract import DataContractError, assert_authoritative_allowed
from saathi.platform.tg.evaluation import (
    StrategyEvaluator,
    EligibilityContext,
    FORBIDDEN_VERDICTS,
    StrategyEvaluationVerdict,
)
from saathi.platform.tg.domain import PerformanceMetrics
from saathi.platform.tg.service import reset_tg_service_for_tests


# ── M177 data classification ─────────────────────────────────────────────────
def test_authoritative_requires_non_fixture_policy():
    assert AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA is True
    assert classify_dataset("TRENDING") == DataClassification.SYNTHETIC_VALIDATION
    assert classify_dataset("TRENDING", is_test_context=True) == DataClassification.FIXTURE_TEST_ONLY
    assert classify_dataset("LOCAL_equities_2020") == DataClassification.HISTORICAL_LOCAL_DATASET
    assert classify_dataset("AUTH_spx_daily") == DataClassification.HISTORICAL_AUTHENTICATED
    assert classify_dataset("unknown_xyz") == DataClassification.INCOMPLETE
    assert not is_authoritative(DataClassification.FIXTURE_TEST_ONLY)
    assert not is_authoritative(DataClassification.SYNTHETIC_VALIDATION)
    with pytest.raises(DataContractError) as ei:
        assert_authoritative_allowed(DataClassification.FIXTURE_TEST_ONLY)
    assert ei.value.code == "AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA"


def test_failed_mapping_fails_closed_no_fixture_metrics():
    svc = TradingGuardianService()
    out = svc.run_backtest(strategy_slug="trend_following", dataset="DOES_NOT_EXIST_XYZ")
    assert out["status"] in ("INCOMPLETE", "REJECTED")
    assert out.get("metrics") is None
    assert out.get("fixture_metrics_used") is False
    assert out.get("authoritative") is False
    assert "COMPLETE_WITH_FIXTURE" not in str(out.get("status", ""))


def test_synthetic_fixture_labeled_not_authoritative():
    svc = TradingGuardianService()
    out = svc.run_backtest(strategy_slug="trend_following", dataset="TRENDING", n=30)
    assert out.get("data_classification") in (
        DataClassification.SYNTHETIC_VALIDATION.value,
        DataClassification.FIXTURE_TEST_ONLY.value,
    )
    assert out.get("authoritative") is False
    assert out.get("fixture_metrics_used") is False
    if out.get("metrics") is not None:
        assert "provenance" in out
        assert out["provenance"]["dataset_fingerprint"]
        assert out["provenance"]["bar_count"] > 0


def test_dataset_fingerprint_stable():
    from saathi.platform.tg.data_contract import fingerprint_payload
    a = fingerprint_payload({"a": 1, "b": 2})
    b = fingerprint_payload({"b": 2, "a": 1})
    assert a == b


def test_incomplete_result_never_invents_metrics():
    r = incomplete_result(reason="test", dataset_id="X")
    assert r["metrics"] is None
    assert r["fixture_metrics_used"] is False
    assert r["evaluation_verdict"] == "INSUFFICIENT_EVIDENCE"


# ── M178 walk-forward ────────────────────────────────────────────────────────
def test_walk_forward_chronological_and_untouched_test():
    svc = TradingGuardianService()
    wf = svc.run_walk_forward(strategy_slug="trend_following", dataset="TRENDING", n=50, n_folds=2)
    assert wf.get("status") == "COMPLETE"
    assert wf.get("final_test_untouched") is True
    assert wf.get("n_folds", 0) >= 1
    for fold in wf.get("folds") or []:
        assert fold.get("selected_before_test") is True
        tr, te = fold["train_range"], fold["test_range"]
        assert tr[1] <= te[0] + 1e-6 or tr[0] < te[0]


def test_walk_forward_no_trade_baseline():
    svc = TradingGuardianService()
    wf = svc.run_walk_forward(strategy_slug="no_trade", dataset="TRENDING")
    assert wf.get("status") == "COMPLETE"
    assert coerce0(wf.get("out_of_sample_expectancy")) == 0


def coerce0(v):
    return float(v or 0)


# ── M179 stress ──────────────────────────────────────────────────────────────
def test_stress_lab_produces_verdict_and_cost_cases():
    svc = TradingGuardianService()
    st = svc.run_stress(strategy_slug="trend_following", dataset="TRENDING", n=30)
    assert st.get("status") == "COMPLETE"
    assert st.get("robustness_verdict") in {v.value for v in RobustnessVerdict}
    names = {c["name"] for c in st.get("cases") or []}
    assert any("fees" in n or "cost" in n for n in names)
    assert st.get("authoritative") is False
    for c in st.get("cases") or []:
        assert "pass" in c
        assert c.get("reason_code")
        assert c.get("criticality") in ("info", "warning", "critical")


def test_stress_no_trade_control():
    st = TradingGuardianService().run_stress(strategy_slug="no_trade")
    assert st["robustness_verdict"] == "ROBUST"


# ── M180 portfolio ───────────────────────────────────────────────────────────
def test_portfolio_correlation_and_unreconciled_block():
    az = PortfolioRiskAnalyzer(max_sector_pct=Decimal("10"))
    st = PortfolioState(
        equity=Decimal("100000"),
        positions={
            "A": {"quantity": Decimal("100"), "avg_cost": Decimal("100"), "sector": "TECH"},
            "B": {"quantity": Decimal("100"), "avg_cost": Decimal("100"), "sector": "TECH"},
        },
        sector_of={"A": "TECH", "B": "TECH"},
    )
    analysis = az.analyze(st, marks={"A": Decimal("100"), "B": Decimal("100")})
    assert "SECTOR_LIMIT" in analysis["breaches"] or analysis["blocks_new_proposals"]

    st.reconciliation = ReconciliationVerdict.UNRECONCILED_BLOCKED
    ok, reason = az.may_accept_proposal(st)
    assert ok is False
    assert reason == "UNRECONCILED_BLOCKED"

    sc = az.scenario("kill_switch_partial", PortfolioState(
        open_orders=[{"id": "1", "status": "PENDING"}, {"id": "2", "status": "FILLED"}],
    ))
    assert "cancelled_1_orders" in sc["notes"]


def test_portfolio_scenarios_exist():
    az = PortfolioRiskAnalyzer()
    st = PortfolioState(positions={"X": {"quantity": Decimal("5"), "avg_cost": Decimal("10")}})
    for name in ("correlated_selloff", "gap_through_stops", "liquidity_collapse",
                 "loss_streak", "unreconciled", "conflicting_proposals"):
        out = az.scenario(name, st)
        assert out["scenario"] == name
        assert out["paper_only"] is True


# ── M181 recovery ────────────────────────────────────────────────────────────
def test_recovery_suite_pass():
    report = run_recovery_suite()
    assert report["paper_only"] is True
    assert report["live_authorized"] is False
    assert report["passed"] == report["total"]
    scenarios = {r["scenario"] for r in report["results"]}
    assert "self_approval_llm" in scenarios
    assert "kill_switch_persistent" in scenarios
    assert "unreconciled_blocks" in scenarios
    assert "no_live_capability" in scenarios
    for r in report["results"]:
        assert r["live_capability"] is False
        assert r["pass"] is True


# ── M183 evaluation ──────────────────────────────────────────────────────────
def test_no_forbidden_verdicts():
    for v in FORBIDDEN_VERDICTS:
        assert not hasattr(StrategyEvaluationVerdict, v)
    assert StrategyEvaluationVerdict.PAPER_ELIGIBLE.value == "PAPER_ELIGIBLE"


def test_paper_eligible_requires_authoritative_evidence():
    ev = StrategyEvaluator()
    m = PerformanceMetrics(
        number_of_trades=30, max_drawdown=Decimal("0.05"),
        profit_factor=Decimal("1.5"), total_return=Decimal("0.1"),
        estimated_fees=Decimal("1"), estimated_slippage=Decimal("1"),
    )
    # Synthetic data cannot be PAPER_ELIGIBLE
    el_syn = EligibilityContext(
        data_classification=DataClassification.SYNTHETIC_VALIDATION.value,
        trade_count=30, oos_evaluated=True, walk_forward_evaluated=True,
        walk_forward_consistent=True, costs_included=True, stress_completed=True,
        parameter_stable=True, reconciled=True, policy_risk_passed=True,
        strategy_version_immutable=True, audit_complete=True,
        max_drawdown=Decimal("0.05"),
    )
    assert ev.evaluate(m, eligibility=el_syn) == StrategyEvaluationVerdict.RESEARCH_ONLY

    el_auth = EligibilityContext(
        data_classification=DataClassification.HISTORICAL_LOCAL_DATASET.value,
        trade_count=30, oos_evaluated=True, walk_forward_evaluated=True,
        walk_forward_consistent=True, costs_included=True, stress_completed=True,
        critical_robustness_failure=False, parameter_stable=True, reconciled=True,
        policy_risk_passed=True, strategy_version_immutable=True, audit_complete=True,
        max_drawdown=Decimal("0.05"),
    )
    assert ev.evaluate(m, eligibility=el_auth) == StrategyEvaluationVerdict.PAPER_ELIGIBLE


def test_scorecard_and_compare_honest():
    svc = reset_tg_service_for_tests()
    card = svc.research_scorecard(strategy_slug="no_trade", dataset="TRENDING", n=30)
    assert card["scorecard"]["verdict"] in (
        "INSUFFICIENT_EVIDENCE", "RESEARCH_ONLY", "PAPER_APPROVAL_REQUIRED", "PAPER_ELIGIBLE", "REJECTED",
    )
    assert card["authoritative"] is False
    assert card["live_authorized"] is False
    cmp = svc.compare_strategies()
    assert "no_trade" in cmp["strategies"]
    assert cmp["live_approved"] is False
    assert "scorecards" in cmp


def test_kotegawa_still_rejects_pure_decline():
    from saathi.platform.tg.strategies.kotegawa_mean_reversion import KotegawaMeanReversion
    from saathi.platform.tg.domain import MarketBar, MarketSnapshot
    bars = []
    for i in range(15):
        px = Decimal(str(100 - i))
        bars.append(MarketBar(
            symbol="X", ts=float(i), open=px, high=px, low=px, close=px,
            volume=Decimal("300000"), timeframe="1d",
        ))
    snap = MarketSnapshot(
        symbol="X", last_price=bars[-1].close, volume=Decimal("300000"),
        avg_traded_value=Decimal("5000000"), spread=Decimal("0.01"),
        bars=bars, market_state="OPEN", data_quality="VALID", freshness_seconds=1,
    )
    sigs = KotegawaMeanReversion().evaluate(snap, params={"reversal_require_green": True})
    assert sigs == []


def test_live_still_forbidden():
    assert LIVE_TRADING_AUTHORIZED is False
    assert LIVE_ORDER_CAPABLE is False
    assert BROKER_CREDENTIAL_SUPPORT is False


def test_m166_regression_posture():
    """M166–M175 still passes core posture after M176 changes."""
    from saathi.platform.tg import list_catalog
    svc = TradingGuardianService()
    p = svc.posture()
    assert p["paper_only"] is True
    assert p["authority_mode"] == "ADVISORY"
    assert len(list_catalog()) == 4
