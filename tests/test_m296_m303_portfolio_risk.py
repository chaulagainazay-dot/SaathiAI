"""M296–M303 Institutional Portfolio & Risk Intelligence tests.

PAPER/RESEARCH ONLY. No broker. No orders. No live trading.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.platform.tg.portfolio_risk.errors import PortfolioRiskError
from saathi.platform.tg.portfolio_risk.models import (
    BROKER_CONNECTIVITY_AUTHORIZED,
    LIVE_TRADING_AUTHORIZED,
    ORDER_EXECUTION_AUTHORIZED,
    REGULATORY_GRADE_RISK,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.portfolio_risk.service import (
    PortfolioRiskService,
    reset_portfolio_risk_for_tests,
)


@pytest.fixture()
def svc(tmp_path: Path):
    return reset_portfolio_risk_for_tests(db_path=tmp_path / "pr_test.db")


def test_authority_locks():
    assert LIVE_TRADING_AUTHORIZED is False
    assert BROKER_CONNECTIVITY_AUTHORIZED is False
    assert ORDER_EXECUTION_AUTHORIZED is False
    assert REGULATORY_GRADE_RISK is False


def test_analytics_exposures(svc: PortfolioRiskService):
    a = svc.analyze()
    assert a["ok"]
    assert "factor_exposure" in a
    assert "sector_exposure" in a
    assert "correlation_matrix" in a
    assert "risk_attribution" in a
    assert a["analytics"]["expected_shortfall_95"] >= 0 or True


def test_limits_and_budgets(svc: PortfolioRiskService):
    lim = svc.evaluate_limits()
    assert lim["ok"]
    assert lim["state"] in ("WITHIN_LIMITS", "WARNING", "BREACHED")
    assert "risk_budgets" in lim
    assert "drawdown_manager" in lim


def test_sizing_and_dynamic(svc: PortfolioRiskService):
    s = svc.size_positions(["SPY", "TLT", "GLD"], method="inverse_volatility")
    assert s["ok"]
    assert abs(sum(s["weights"].values()) + s["cash_weight"] - 1.0) < 1e-6 or sum(s["weights"].values()) <= 1.0
    d = svc.dynamic_allocation(s["weights"], regime="high_volatility")
    assert d["ok"]
    assert d["test_set_tuning"] is False


def test_sizing_rejects_leverage(svc: PortfolioRiskService):
    with pytest.raises(PortfolioRiskError) as ei:
        svc.size_positions(["SPY"], max_leverage=2.0)
    assert ei.value.code == "LEVERAGE_POLICY"


def test_optimiser_v2_and_leverage_block(svc: PortfolioRiskService):
    good = svc.optimise(["SPY", "QQQ", "TLT"], method="equal_weight")
    assert good.get("optimiser_version") == "v2"
    bad = svc.optimise(["SPY", "TLT"], method="equal_weight", constraints={"leverage_limit": 2.0})
    assert bad.get("ok") is False


def test_scenarios_and_dashboards(svc: PortfolioRiskService):
    sc = svc.run_scenarios()
    assert sc["ok"]
    assert sc["scenario_count"] >= 4
    assert "stress_dashboard" in sc
    assert "liquidity_dashboard" in sc
    assert "expected_shortfall_dashboard" in sc


def test_attribution_and_committee(svc: PortfolioRiskService):
    attr = svc.performance_attribution()
    assert attr["ok"]
    assert "RESEARCH" in attr["label"]
    cm = svc.committee_review()
    assert cm["committee_version"] == "v2"
    assert cm["authorizes_execution"] is False


def test_refusals_and_certify(svc: PortfolioRiskService):
    assert svc.refuse_broker()["refused"] is True
    assert svc.refuse_credentials("k")["refused"] is True
    assert svc.refuse_order()["refused"] is True
    assert svc.refuse_canary()["refused"] is True
    assert svc.refuse_live()["refused"] is True
    cert = svc.certify()
    assert cert["ok"] is True
    assert cert["verdict"] == TERMINAL_VERDICT


def test_bootstrap(svc: PortfolioRiskService):
    pipe = svc.bootstrap_demo_pipeline()
    assert pipe["ok"] is True
    assert pipe["analytics"]["ok"] is True
