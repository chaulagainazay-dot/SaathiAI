"""M248–M255 Institutional Investment Intelligence tests.

PAPER ONLY. No brokers. No API keys. No live trading.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.platform.tg.intelligence.models import (
    API_KEYS_ACCEPTED,
    BROKER_CONNECTIVITY_AUTHORIZED,
    LIVE_TRADING_AUTHORIZED,
    ORDER_SUBMISSION_AUTHORIZED,
    STRATEGY_CATEGORIES,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.intelligence.service import (
    InstitutionalIntelligenceService,
    reset_intelligence_for_tests,
)


@pytest.fixture()
def svc(tmp_path: Path):
    db = tmp_path / "ii_test.db"
    return reset_intelligence_for_tests(db_path=db)


def test_authority_locks_false():
    assert LIVE_TRADING_AUTHORIZED is False
    assert BROKER_CONNECTIVITY_AUTHORIZED is False
    assert API_KEYS_ACCEPTED is False
    assert ORDER_SUBMISSION_AUTHORIZED is False


def test_m248_strategy_registry(svc: InstitutionalIntelligenceService):
    s = svc.list_strategies()
    assert s["count"] >= 11
    assert s["paper_only"] is True
    cats = {x["category"] for x in s["strategies"]}
    for c in STRATEGY_CATEGORIES:
        assert c in cats
    one = svc.get_strategy("tf_dual_ma")
    assert one["ok"] is True
    st = one["strategy"]
    for key in (
        "id", "category", "description", "supported_markets", "supported_assets",
        "required_indicators", "entry_conditions", "exit_conditions",
        "stop_loss_logic", "take_profit_logic", "sizing_model",
        "expected_holding_period", "risk_profile", "confidence_model",
        "required_confirmations", "limitations",
    ):
        assert key in st


def test_m248_deterministic_strategy_run(svc: InstitutionalIntelligenceService):
    a = svc.strategy_run("tf_dual_ma")
    b = svc.strategy_run("tf_dual_ma")
    assert a["ok"] is True and b["ok"] is True
    assert a["signal"]["action"] == b["signal"]["action"]
    assert a["signal"]["confidence"] == b["signal"]["confidence"]
    assert a["LIVE_TRADING_AUTHORIZED"] is False


def test_m249_portfolio_calculations(svc: InstitutionalIntelligenceService):
    p = svc.portfolio_overview()
    assert p["paper_only"] is True
    assert "allocation" in p
    assert "diversification" in p
    assert "concentration" in p
    assert "sector_exposure" in p
    assert "geographic_exposure" in p
    assert "asset_class_exposure" in p
    assert "cash_utilisation" in p
    assert "unrealised_pnl" in p
    assert "realised_pnl" in p
    assert "portfolio_beta" in p
    assert "volatility_annualized" in p
    assert "sharpe_ratio" in p
    assert "sortino_ratio" in p
    assert "maximum_drawdown" in p
    assert "correlation" in p
    assert "var" in p
    assert "expected_shortfall_95" in p["var"]
    r = svc.portfolio_risk()
    assert "risk_summary" in r
    report = svc.portfolio_report()
    assert "overview" in report and "risk" in report


def test_m250_backtest_deterministic(svc: InstitutionalIntelligenceService):
    a = svc.backtest("tf_dual_ma", seed=42)
    b = svc.backtest("tf_dual_ma", seed=42)
    assert a["ok"] is True
    assert a["evidence_hash"] == b["evidence_hash"]
    assert "equity_curve" in a
    assert "drawdown_curve" in a
    assert "monthly_returns" in a
    assert "yearly_returns" in a
    assert "win_rate" in a
    assert "expectancy" in a
    assert "profit_factor" in a
    assert "benchmark" in a
    assert "performance_attribution" in a
    assert a["costs"]["commission_bps"] > 0
    cmp_ = svc.backtest_compare(["tf_dual_ma", "mr_bollinger_reversion"], seed=1)
    assert len(cmp_["ranking"]) == 2


def test_m251_walk_forward_no_test_opt(svc: InstitutionalIntelligenceService):
    wf = svc.run_walk_forward("tf_dual_ma", seed=42, n_folds=3)
    assert wf["ok"] is True
    assert wf["invariants"]["optimized_on_evaluation_set"] is False
    assert wf["invariants"]["selected_before_test"] is True
    assert "overfitting" in wf
    assert "robustness_score" in wf
    assert "confidence_score" in wf
    for fold in wf["folds"]:
        assert fold["optimized_on_test"] is False
        assert fold["selected_before_test"] is True


def test_m252_monte_carlo_repeatable(svc: InstitutionalIntelligenceService):
    a = svc.run_monte_carlo(n_simulations=100, seed=7, horizon=40)
    b = svc.run_monte_carlo(n_simulations=100, seed=7, horizon=40)
    assert a["ok"] is True
    assert a["evidence_hash"] == b["evidence_hash"]
    assert a["probability_of_ruin"] == b["probability_of_ruin"]
    assert "sequence_risk" in a
    assert "confidence_intervals" in a
    assert "worst_case_scenarios" in a
    assert "recovery_analysis" in a
    assert a["repeatable"] is True


def test_m253_explanation_generation(svc: InstitutionalIntelligenceService):
    ex = svc.explain("SPY", strategy_id="tf_dual_ma")
    for key in (
        "why", "why_now", "supporting_evidence", "conflicting_evidence",
        "assumptions", "risks", "confidence", "historical_behaviour",
        "comparable_situations", "expected_upside", "expected_downside",
        "invalidation_conditions",
    ):
        assert key in ex
    assert ex["investor_readable"] is True
    assert ex["paper_only"] is True
    assert ex["not_financial_advice"] is True


def test_m254_committee_consensus(svc: InstitutionalIntelligenceService):
    rev = svc.committee_review(
        "SPY",
        context={"trend": "up", "regime": "risk_on", "valuation": "fair"},
    )
    assert rev["final_recommendation"]
    assert len(rev["opinions"]) == 6
    roles = {o["role"] for o in rev["opinions"]}
    assert "macro_analyst" in roles
    assert "technical_analyst" in roles
    assert "fundamental_analyst" in roles
    assert "quant_analyst" in roles
    assert "risk_manager" in roles
    assert "portfolio_manager" in roles
    assert "voting_summary" in rev
    assert "agreements" in rev
    assert "disagreements" in rev
    assert "dissenting_opinions" in rev
    assert "explanation" in rev
    assert rev["paper_only"] is True


def test_m255_command_center_dashboard(svc: InstitutionalIntelligenceService):
    d = svc.dashboard()
    sections = d["sections"]
    for key in (
        "strategy_library", "portfolio_overview", "risk_dashboard",
        "performance_dashboard", "backtests", "monte_carlo", "walk_forward",
        "investment_committee", "explainable_recommendations",
        "historical_decisions", "confidence_trends", "watchlists",
        "alerts", "decision_timeline",
    ):
        assert key in sections
    assert d["broker_controls"] is False
    assert d["credential_controls"] is False
    assert d["connection_controls"] is False
    assert d["ui_route"] == "/trading/intelligence"


def test_boundary_refusals(svc: InstitutionalIntelligenceService):
    assert svc.refuse_broker()["ok"] is False
    assert svc.refuse_credentials("x")["ok"] is False
    assert svc.refuse_order()["ok"] is False
    sec = svc.security_scan()
    assert sec["ok"] is True
    assert sec["live_trading"] is False


def test_certify_verdict(svc: InstitutionalIntelligenceService):
    c = svc.certify()
    assert c["verdict"] == TERMINAL_VERDICT
    assert c["hard_gates_pass"] is True
    assert c["LIVE_TRADING_AUTHORIZED"] is False
    assert c["BROKER_CONNECTIVITY_AUTHORIZED"] is False
    assert "PAPER ONLY" in c["statements"]
    assert "NO BROKER CONNECTIVITY" in c["statements"]
    assert "NO API KEYS" in c["statements"]
    assert "NO LIVE MARKET ACCESS" in c["statements"]
    assert "NO ORDER EXECUTION" in c["statements"]
    assert "NO LIVE TRADING" in c["statements"]


def test_cli_intelligence_commands():
    from saathi.platform.tg.cli import main
    # smoke a few aliases
    assert main(["strategy-list"]) == 0
    assert main(["portfolio-risk"]) == 0
    assert main(["paper-gov", "ii-strategy-list"]) == 0


def test_api_routes_registered():
    from saathi.platform import api as platform_api
    paths = {getattr(r, "path", None) for r in platform_api.router.routes}
    prefix = "/api/v1/platform"
    expected = [
        "/tg/intelligence/posture",
        "/tg/intelligence/strategies",
        "/tg/intelligence/portfolio",
        "/tg/intelligence/risk",
        "/tg/intelligence/backtests",
        "/tg/intelligence/simulations/monte-carlo",
        "/tg/intelligence/simulations/walk-forward",
        "/tg/intelligence/committee",
        "/tg/intelligence/explanations",
        "/tg/intelligence/dashboard",
        "/tg/intelligence/certify",
    ]
    for p in expected:
        full = prefix + p
        assert full in paths or p in paths, f"missing route {p}"
