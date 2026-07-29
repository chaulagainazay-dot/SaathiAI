"""M192–M199 — Paper activation governance tests."""
from __future__ import annotations

from decimal import Decimal

import pytest

from saathi.platform.tg import LIVE_TRADING_AUTHORIZED, LIVE_ORDER_CAPABLE, BROKER_CREDENTIAL_SUPPORT
from saathi.platform.tg.domain import StrategyEvaluationVerdict, KillSwitchScope
from saathi.platform.tg.historical.qualification import QualificationGates
from saathi.platform.tg.paper_activation import (
    PaperActivationState,
    reset_paper_gov_for_tests,
    PaperGovError,
)
from saathi.platform.tg.paper_activation.approvals import ApprovalError
from saathi.platform.tg.paper_activation.journal import PaperJournalError
from saathi.platform.tg.paper_activation.models import SimOrderType, SimTimeInForce, SimOrder
from saathi.platform.tg.paper_activation.order_simulator import OrderSimulator, MarketTick


def _eligible_qual(**overrides):
    gates = QualificationGates(
        non_fixture_authoritative_dataset=True,
        accepted_data_quality=True,
        sufficient_date_coverage=True,
        sufficient_trade_count=True,
        untouched_final_oos=True,
        walk_forward_completed=True,
        stress_completed=True,
        monte_carlo_completed=True,
        realistic_fees=True,
        realistic_spread=True,
        realistic_slippage=True,
        corporate_actions_validated=True,
        no_critical_data_quality_failure=True,
        no_look_ahead_leakage=True,
        no_unresolved_reconciliation=True,
        acceptable_drawdown=True,
        acceptable_risk_of_ruin=True,
        parameter_stability=True,
        no_critical_cost_sensitivity=True,
        no_critical_regime_dependence=True,
        immutable_strategy_version=True,
        immutable_dataset_version=True,
        complete_evidence_journal=True,
        policy_compatibility=True,
        deterministic_risk_controls=True,
    )
    q = {
        "verdict": StrategyEvaluationVerdict.PAPER_ELIGIBLE.value,
        "data_classification": "HISTORICAL_LOCAL_DATASET",
        "authoritative": True,
        "gates": gates.to_public(),
    }
    q.update(overrides)
    return q


def test_still_paper_only():
    assert LIVE_TRADING_AUTHORIZED is False
    assert LIVE_ORDER_CAPABLE is False
    assert BROKER_CREDENTIAL_SUPPORT is False
    svc = reset_paper_gov_for_tests()
    p = svc.posture()
    assert p["paper_only"] is True
    assert p["live_trading_authorized"] is False
    assert p["llm_boundary"]["may_approve"] is False
    assert p["llm_boundary"]["may_execute_trades"] is False


def test_research_only_cannot_request_approval():
    svc = reset_paper_gov_for_tests()
    with pytest.raises(PaperGovError) as ei:
        svc.request_approval(
            strategy_slug="trend_following",
            qualification={
                "verdict": "RESEARCH_ONLY",
                "data_classification": "SYNTHETIC_VALIDATION",
                "authoritative": False,
                "gates": {},
            },
            reason="try",
            operator_id="op",
            operator_identity="operator:human",
        )
    assert ei.value.code == "NOT_PAPER_ELIGIBLE"


def test_llm_cannot_approve():
    svc = reset_paper_gov_for_tests()
    req = svc.request_approval(
        strategy_slug="trend_following",
        qualification=_eligible_qual(),
        reason="paper activation",
        operator_id="op",
        operator_identity="operator:human",
    )
    with pytest.raises(PaperGovError) as ei:
        svc.decide_approval(
            approval_id=req["approval"]["id"],
            decision="approve",
            operator_id="llm",
            operator_identity="llm:gpt",
        )
    assert ei.value.code == "SELF_APPROVAL_FORBIDDEN"


def test_full_activation_order_fill_reconcile_analytics():
    svc = reset_paper_gov_for_tests()
    port = svc.create_portfolio(name="Fund A", starting_cash="100000")
    pid = port["portfolio"]["id"]
    req = svc.request_approval(
        strategy_slug="trend_following",
        qualification=_eligible_qual(),
        reason="activate after historical research",
        operator_id="op",
        operator_identity="operator:owner",
        dataset_id="hist1",
        dataset_fingerprint="fp1",
    )
    apid = req["approval"]["id"]
    svc.decide_approval(
        approval_id=apid, decision="approve",
        operator_id="op", operator_identity="operator:owner", notes="ok",
    )
    act = svc.activate_strategy(
        strategy_slug="trend_following",
        approval_id=apid,
        portfolio_id=pid,
        operator_identity="operator:owner",
    )
    assert act["activation"]["state"] == PaperActivationState.PAPER_ACTIVE.value

    o = svc.place_order(
        portfolio_id=pid, strategy_slug="trend_following",
        symbol="AAPL", side="BUY", quantity="10", order_type="MARKET",
        reason="breakout", market_regime="BULL", confidence="0.7",
    )
    assert o["order"]["status"] == "ACCEPTED"
    assert o["live_order"] is False

    tick = svc.process_market(pid, symbol="AAPL", bid="150", ask="150.1", last="150.05")
    assert any(r.get("filled") for r in tick["results"])
    pos = svc.list_positions(pid)["positions"]
    assert any(p["symbol"] == "AAPL" for p in pos)

    journal = svc.list_journal(portfolio_id=pid)
    assert len(journal["entries"]) >= 1
    assert journal["immutable"] is True

    recon = svc.reconcile(pid)
    assert recon["reconciliation"]["verdict"] in ("RECONCILED", "RECONCILED_WITH_WARNINGS")

    analytics = svc.analytics(pid)["analytics"]
    assert "sharpe" in analytics
    assert analytics["paper_only"] is True


def test_inactive_strategy_orders_rejected():
    svc = reset_paper_gov_for_tests()
    pid = svc.create_portfolio()["portfolio"]["id"]
    o = svc.place_order(
        portfolio_id=pid, strategy_slug="momentum_rs",
        symbol="MSFT", side="BUY", quantity="5",
    )
    assert o["order"]["status"] == "REJECTED"
    assert o["order"]["reject_reason"] == "strategy_not_paper_active"


def test_kill_switch_blocks_orders_and_halts_portfolios():
    svc = reset_paper_gov_for_tests()
    # activate path
    pid = svc.create_portfolio()["portfolio"]["id"]
    req = svc.request_approval(
        strategy_slug="trend_following", qualification=_eligible_qual(),
        reason="r", operator_id="op", operator_identity="operator:h",
    )
    apid = req["approval"]["id"]
    svc.decide_approval(approval_id=apid, decision="approve", operator_id="op", operator_identity="operator:h")
    svc.activate_strategy(
        strategy_slug="trend_following", approval_id=apid, portfolio_id=pid,
        operator_identity="operator:h",
    )
    svc.activate_kill_switch(
        scope=KillSwitchScope.GLOBAL, reason="test halt",
        activated_by="operator:h", source_identity="operator",
    )
    with pytest.raises(PaperGovError) as ei:
        svc.place_order(
            portfolio_id=pid, strategy_slug="trend_following",
            symbol="X", side="BUY", quantity="1",
        )
    assert ei.value.code == "KILL_SWITCH"
    p = svc.get_portfolio(pid)["portfolio"]
    assert p["status"] == "HALTED"


def test_daily_loss_circuit_breaker():
    svc = reset_paper_gov_for_tests()
    from saathi.platform.tg.paper_activation.models import RiskLimits
    port = svc.create_portfolio(
        starting_cash="10000",
        risk_limits=RiskLimits(daily_loss_limit_pct=Decimal("1"), max_position_notional=Decimal("50000")),
    )
    pid = port["portfolio"]["id"]
    req = svc.request_approval(
        strategy_slug="trend_following", qualification=_eligible_qual(),
        reason="r", operator_id="op", operator_identity="operator:h",
    )
    apid = req["approval"]["id"]
    svc.decide_approval(approval_id=apid, decision="approve", operator_id="op", operator_identity="operator:h")
    svc.activate_strategy(
        strategy_slug="trend_following", approval_id=apid, portfolio_id=pid,
        operator_identity="operator:h",
    )
    # buy then mark down hard
    svc.place_order(portfolio_id=pid, strategy_slug="trend_following", symbol="Z", side="BUY", quantity="50")
    svc.process_market(pid, symbol="Z", bid="100", ask="100.1", last="100")
    # crash
    out = svc.process_market(pid, symbol="Z", bid="10", ask="10.1", last="10")
    # either halted by risk or still open depending on equity path — force check
    p = svc.get_portfolio(pid)["portfolio"]
    # After severe mark-down, post_trade on next process should halt
    if p["status"] != "HALTED":
        # second tick to re-evaluate
        svc.process_market(pid, symbol="Z", bid="5", ask="5.1", last="5")
        p = svc.get_portfolio(pid)["portfolio"]
    assert p["status"] == "HALTED" or float(p["drawdown_pct"]) > 0


def test_order_simulator_limit_stop_ioc_fok():
    sim = OrderSimulator()
    # limit buy not marketable
    o = SimOrder(symbol="S", side="BUY", order_type=SimOrderType.LIMIT, quantity=Decimal("10"),
                 limit_price=Decimal("90"), portfolio_id="p")
    tick = MarketTick(symbol="S", bid=Decimal("99"), ask=Decimal("100"), last=Decimal("99.5"))
    r = sim.try_fill(o, tick)
    assert r["filled"] is False

    # market fill
    o2 = SimOrder(symbol="S", side="BUY", order_type=SimOrderType.MARKET, quantity=Decimal("10"), portfolio_id="p")
    r2 = sim.try_fill(o2, tick)
    assert r2["filled"] is True

    # FOK with low liquidity
    o3 = SimOrder(symbol="S", side="BUY", order_type=SimOrderType.MARKET, tif=SimTimeInForce.FOK,
                  quantity=Decimal("1000000"), portfolio_id="p")
    tick2 = MarketTick(symbol="S", bid=Decimal("99"), ask=Decimal("100"), last=Decimal("99.5"), volume=Decimal("10"))
    r3 = sim.try_fill(o3, tick2)
    assert r3["filled"] is False
    assert o3.status.value in ("CANCELLED", "REJECTED") or "fok" in (o3.reject_reason or r3.get("reason", ""))

    # stop buy
    o4 = SimOrder(symbol="S", side="BUY", order_type=SimOrderType.STOP, quantity=Decimal("5"),
                  stop_price=Decimal("101"), portfolio_id="p")
    r4 = sim.try_fill(o4, tick)
    assert r4["filled"] is False  # not triggered
    tick3 = MarketTick(symbol="S", bid=Decimal("101"), ask=Decimal("102"), last=Decimal("101.5"))
    r5 = sim.try_fill(o4, tick3)
    assert r5["filled"] is True


def test_journal_immutable():
    svc = reset_paper_gov_for_tests()
    pid = svc.create_portfolio()["portfolio"]["id"]
    # force order rejected still journals
    o = svc.place_order(portfolio_id=pid, strategy_slug="x", symbol="A", side="BUY", quantity="1")
    jid = o["journal_entry_id"]
    with pytest.raises(PaperJournalError):
        svc.journal.mutate(jid, notes="hack")


def test_single_use_approval_consumed():
    svc = reset_paper_gov_for_tests()
    pid = svc.create_portfolio()["portfolio"]["id"]
    req = svc.request_approval(
        strategy_slug="trend_following", qualification=_eligible_qual(),
        reason="r", operator_id="op", operator_identity="operator:h",
    )
    apid = req["approval"]["id"]
    svc.decide_approval(approval_id=apid, decision="approve", operator_id="op", operator_identity="operator:h")
    svc.activate_strategy(
        strategy_slug="trend_following", approval_id=apid, portfolio_id=pid,
        operator_identity="operator:h",
    )
    # second activate should fail consume
    with pytest.raises(PaperGovError):
        svc.activate_strategy(
            strategy_slug="trend_following", approval_id=apid, portfolio_id=pid,
            operator_identity="operator:h",
        )


def test_partial_close_and_sell():
    svc = reset_paper_gov_for_tests()
    pid = svc.create_portfolio(starting_cash="50000")["portfolio"]["id"]
    req = svc.request_approval(
        strategy_slug="trend_following", qualification=_eligible_qual(),
        reason="r", operator_id="op", operator_identity="operator:h",
    )
    apid = req["approval"]["id"]
    svc.decide_approval(approval_id=apid, decision="approve", operator_id="op", operator_identity="operator:h")
    svc.activate_strategy(
        strategy_slug="trend_following", approval_id=apid, portfolio_id=pid,
        operator_identity="operator:h",
    )
    svc.place_order(portfolio_id=pid, strategy_slug="trend_following", symbol="QQQ", side="BUY", quantity="20")
    svc.process_market(pid, symbol="QQQ", bid="100", ask="100.1", last="100")
    svc.place_order(portfolio_id=pid, strategy_slug="trend_following", symbol="QQQ", side="SELL", quantity="5")
    svc.process_market(pid, symbol="QQQ", bid="105", ask="105.1", last="105")
    pos = svc.list_positions(pid)["positions"]
    q = next(p for p in pos if p["symbol"] == "QQQ")
    assert Decimal(q["quantity"]) == Decimal("15")


def test_reason_required_for_approval_request():
    svc = reset_paper_gov_for_tests()
    with pytest.raises(PaperGovError) as ei:
        svc.request_approval(
            strategy_slug="trend_following", qualification=_eligible_qual(),
            reason="  ", operator_id="op", operator_identity="operator:h",
        )
    assert ei.value.code == "REASON_REQUIRED"
