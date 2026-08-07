"""M288–M295 Institutional Paper Trading Simulation tests.

VIRTUAL EXCHANGE ONLY. No broker. No real orders. No live trading.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.platform.tg.paper_simulation.errors import PaperSimError
from saathi.platform.tg.paper_simulation.models import (
    BROKER_CONNECTIVITY_AUTHORIZED,
    LIVE_TRADING_AUTHORIZED,
    ORDER_EXECUTION_AUTHORIZED,
    REAL_EXCHANGE_AUTHORIZED,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.paper_simulation.service import (
    PaperSimulationService,
    reset_paper_simulation_for_tests,
)


@pytest.fixture()
def svc(tmp_path: Path):
    return reset_paper_simulation_for_tests(db_path=tmp_path / "ps_test.db")


def test_authority_locks():
    assert LIVE_TRADING_AUTHORIZED is False
    assert BROKER_CONNECTIVITY_AUTHORIZED is False
    assert ORDER_EXECUTION_AUTHORIZED is False
    assert REAL_EXCHANGE_AUTHORIZED is False


def test_market_and_limit_orders(svc: PaperSimulationService):
    pf = svc.create_portfolio("t1", initial_cash=50_000)
    pid = pf["portfolio_id"]
    mkt = svc.submit_order(pid, "SPY", "BUY", "MARKET", 5)
    assert mkt["match"]["filled"] is True
    assert mkt["simulated"] is True
    tick = svc.exchange.latest_tick("AAPL")
    lim_px = float(tick["bid"]) - 1.0
    lim = svc.submit_order(pid, "AAPL", "BUY", "LIMIT", 2, limit_price=lim_px, tif="GTC")
    assert lim["order"]["status"] in ("ACCEPTED", "PARTIALLY_FILLED", "FILLED")
    svc.publish_tick("AAPL", lim_px - 0.1, lim_px, lim_px, volume=1_000_000)
    orders = svc.list_orders(pid)
    assert orders["count"] >= 2
    fills = svc.list_fills(pid)
    assert fills["count"] >= 1


def test_session_closed_blocks_market(svc: PaperSimulationService):
    pf = svc.create_portfolio("t2", initial_cash=10_000)
    svc.exchange.set_session("MSFT", "CLOSED")
    with pytest.raises(PaperSimError) as ei:
        svc.submit_order(pf["portfolio_id"], "MSFT", "BUY", "MARKET", 1)
    assert ei.value.code == "SESSION_NOT_OPEN"
    svc.exchange.set_session("MSFT", "OPEN")


def test_kill_switch_blocks_orders(svc: PaperSimulationService):
    pf = svc.create_portfolio("t3", initial_cash=10_000)
    pid = pf["portfolio_id"]
    ks = svc.activate_kill_switch("test", scope="PORTFOLIO", scope_ref=pid, actor="operator")
    with pytest.raises(PaperSimError) as ei:
        svc.submit_order(pid, "SPY", "BUY", "MARKET", 1)
    assert ei.value.code == "KILL_SWITCH_ACTIVE"
    svc.deactivate_kill_switch(ks["kill_switch_id"], actor="operator")
    ok = svc.submit_order(pid, "SPY", "BUY", "MARKET", 1)
    assert ok["ok"]


def test_llm_cannot_activate_kill_switch(svc: PaperSimulationService):
    with pytest.raises(PaperSimError) as ei:
        svc.activate_kill_switch("nope", actor="llm")
    assert ei.value.code == "KILL_SWITCH_AUTHORITY"


def test_order_book_and_cash_ledger(svc: PaperSimulationService):
    book = svc.order_book("SPY")
    assert book["bids"] and book["asks"]
    assert book["simulated"] is True
    pf = svc.create_portfolio("t4", initial_cash=20_000)
    svc.submit_order(pf["portfolio_id"], "SPY", "BUY", "MARKET", 2)
    cash = svc.cash_ledger(pf["portfolio_id"])
    assert cash["count"] >= 2


def test_corporate_action_dividend(svc: PaperSimulationService):
    pf = svc.create_portfolio("t5", initial_cash=50_000)
    pid = pf["portfolio_id"]
    svc.submit_order(pid, "SPY", "BUY", "MARKET", 10)
    before = svc.get_portfolio(pid)["metrics"]["cash"]
    ca = svc.register_corporate_action(symbol="SPY", action_type="DIVIDEND", ex_date="2026-01-01", amount=1.0)
    svc.apply_corporate_action(ca["ca_id"], pid)
    after = svc.get_portfolio(pid)["metrics"]["cash"]
    assert after > before


def test_cancel_order(svc: PaperSimulationService):
    pf = svc.create_portfolio("t6", initial_cash=20_000)
    tick = svc.exchange.latest_tick("AAPL")
    lim = svc.submit_order(pf["portfolio_id"], "AAPL", "BUY", "LIMIT", 1, limit_price=float(tick["bid"]) - 50, tif="GTC")
    oid = lim["order"]["order_id"]
    c = svc.cancel_order(oid)
    assert c["status"] == "CANCELLED"


def test_refusals_and_certify(svc: PaperSimulationService):
    assert svc.refuse_broker()["refused"] is True
    assert svc.refuse_credentials("k")["refused"] is True
    assert svc.refuse_real_order()["refused"] is True
    assert svc.refuse_canary()["refused"] is True
    assert svc.refuse_live()["refused"] is True
    cert = svc.certify()
    assert cert["ok"] is True
    assert cert["verdict"] == TERMINAL_VERDICT


def test_bootstrap_pipeline(svc: PaperSimulationService):
    pipe = svc.bootstrap_demo_pipeline()
    assert pipe["ok"] is True
    assert pipe["market_fill"] is True
    assert pipe["fill_count"] >= 1
