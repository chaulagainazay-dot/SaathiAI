"""T-NEXT-1.1 — automatic OMS→ledger cutover, retry, recon, crash recovery."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from saathi.platform.context import PlatformExecutionContext
from saathi.platform.trading_models import D, DataQuality, MarketState
# Import modules directly to avoid paper_trading package __init__ pulling ExecutionGateway
# (Python 3.9 type-union incompatibility on some host toolchains).
from saathi.platform.paper_trading.service import PaperTradingService
from saathi.platform.paper_trading.store import PaperStore
from saathi.platform.paper_trading.broker import MarketEvent
from saathi.platform.paper_trading.models import ZERO_FEE, ZERO_SLIP
from saathi.platform.fund_ledger.posting import POST_POSTED, POST_DUPLICATE, POST_FAILED
from saathi.platform.fund_ledger.view_adapter import LedgerPortfolioViewAdapter
from saathi.platform.fund_ledger.cutover import CUTOVER_POLICY, fund_id_for_account


def _ctx(role="operator", org="o1", user="u1", ws="w1"):
    return PlatformExecutionContext(user_id=user, role=role, org_id=org, workspace_id=ws, run_id="r1")


def _svc(tmp_path, **kw):
    return PaperTradingService(
        PaperStore(db_path=tmp_path / "paper.db"),
        fee_model=ZERO_FEE,
        slippage_model=ZERO_SLIP,
        **kw,
    )


def _ev(*, bid="99.98", ask="100.00", last="100.00", liquidity="1000000", ref="fx", symbol="AAA"):
    return MarketEvent(
        symbol=symbol,
        ts=1000.0,
        bid=D(bid),
        ask=D(ask),
        last=D(last),
        liquidity=D(liquidity),
        quality=DataQuality.VALID,
        market_state=MarketState.OPEN,
        ref=ref,
    )


def _buy_fill(svc, ctx, cash="100000", qty="10", symbol="AAA"):
    acct = svc.create_account(ctx, name="a", starting_cash=cash)
    intent = svc.create_intent(
        ctx, account_id=acct["id"], symbol=symbol, side="BUY", order_type="MARKET", quantity=qty
    )
    sub = svc.submit_order(ctx, intent_id=intent["intent_id"], event=_ev(symbol=symbol))
    fr = svc.process_market_event(ctx, order_id=sub["order"]["id"], event=_ev(symbol=symbol, ref="e1"))
    return acct, sub, fr


def test_create_account_opens_fund(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    acct = svc.create_account(ctx, name="a", starting_cash="50000")
    assert acct["fund_id"] == fund_id_for_account(acct["id"])
    assert acct["books_authority"] == "canonical_fund_ledger"
    assert acct["legacy_oms_state_not_books_authority"] is True
    state = svc.ledger.get_state(acct["fund_id"])
    assert state["cash"] == "50000.00"
    assert state["nav"] == "50000.00"


def test_automatic_fill_posts_to_ledger(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    acct, sub, fr = _buy_fill(svc, ctx)
    assert fr["filled"] is True
    assert fr["ledger_post"]["status"] in (POST_POSTED, POST_DUPLICATE)
    assert fr["ledger_post"]["ledger_event_id"]
    assert fr["books_authority"] == "canonical_fund_ledger"
    books = svc.get_account(ctx, acct["id"])
    assert books["books_authority"] == "canonical_fund_ledger"
    assert books["source"] == "canonical_fund_ledger"
    assert Decimal(books["positions"][0]["quantity"]) == Decimal("10")
    assert books["portfolio_status"] == "HEALTHY"
    # cash reduced by 10 * 100 = 1000
    assert Decimal(books["cash"]) == Decimal("99000.00")


def test_duplicate_fill_event_no_double_accounting(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    acct, sub, fr = _buy_fill(svc, ctx)
    oid = sub["order"]["id"]
    cash1 = svc.get_account(ctx, acct["id"])["cash"]
    dup = svc.process_market_event(ctx, order_id=oid, event=_ev(symbol="AAA", ref="e1"))
    assert dup["filled"] is False
    cash2 = svc.get_account(ctx, acct["id"])["cash"]
    assert cash1 == cash2
    pos = svc.list_positions(ctx, acct["id"])
    assert len(pos) == 1
    assert pos[0]["quantity"] == "10.000000"


def test_partial_sell_realized_and_command_snapshot(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    acct, sub, fr = _buy_fill(svc, ctx, qty="10")
    # sell 4
    intent = svc.create_intent(
        ctx, account_id=acct["id"], symbol="AAA", side="SELL", order_type="MARKET", quantity="4"
    )
    sub2 = svc.submit_order(
        ctx, intent_id=intent["intent_id"], event=_ev(bid="110", ask="110.02", symbol="AAA")
    )
    fr2 = svc.process_market_event(
        ctx, order_id=sub2["order"]["id"], event=_ev(bid="110", ask="110.02", symbol="AAA", ref="sell1")
    )
    assert fr2["filled"] is True
    books = svc.get_account(ctx, acct["id"])
    assert Decimal(books["positions"][0]["quantity"]) == Decimal("6")
    assert Decimal(books["realized_pnl"]) > 0
    snap = svc.command_center_snapshot(ctx, acct["id"])
    assert snap["mode"] == "PAPER"
    assert snap["live_execution"] == "UNAVAILABLE"
    assert snap["source"] == "canonical_fund_ledger"
    assert snap["paper_nav"] is not None
    assert snap["portfolio_healthy"] is True


def test_ledger_post_failure_marks_recon_and_retry(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    acct = svc.create_account(ctx, name="a", starting_cash="100000")

    # force post failure by breaking fund binding mid-flight: use spy
    real_post = svc.ledger.record_fill
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated ledger outage")
        return real_post(*a, **k)

    svc.ledger.record_fill = boom  # type: ignore

    intent = svc.create_intent(
        ctx, account_id=acct["id"], symbol="AAA", side="BUY", order_type="MARKET", quantity="1"
    )
    sub = svc.submit_order(ctx, intent_id=intent["intent_id"], event=_ev())
    fr = svc.process_market_event(ctx, order_id=sub["order"]["id"], event=_ev(ref="fail1"))
    assert fr["filled"] is True
    assert fr["ledger_post"]["status"] == POST_FAILED
    recon = svc.portfolio_reconciliation_status(ctx, acct["id"])
    assert recon["portfolio_status"] == "RECONCILIATION_REQUIRED"
    assert recon["pending_ledger_posts"] >= 1

    # restore and retry
    svc.ledger.record_fill = real_post  # type: ignore
    # retry_pending uses payload — but first attempt may not have stored full payload if boom before?
    # post_accepted_fill records PENDING then FAILED with payload — good
    out = svc.retry_ledger_posts(ctx)
    assert out["retried"] >= 1
    recon2 = svc.portfolio_reconciliation_status(ctx, acct["id"])
    assert recon2["pending_ledger_posts"] == 0
    assert recon2["portfolio_status"] == "HEALTHY"
    books = svc.get_account(ctx, acct["id"])
    assert Decimal(books["positions"][0]["quantity"]) == Decimal("1")


def test_crash_recovery_new_service_instance(tmp_path):
    ctx = _ctx()
    db = tmp_path / "paper.db"
    svc1 = PaperTradingService(PaperStore(db_path=db), fee_model=ZERO_FEE, slippage_model=ZERO_SLIP)
    acct, sub, fr = _buy_fill(svc1, ctx)
    assert fr["filled"]
    # new process
    svc2 = PaperTradingService(PaperStore(db_path=db), fee_model=ZERO_FEE, slippage_model=ZERO_SLIP)
    books = svc2.get_account(ctx, acct["id"])
    assert books["books_authority"] == "canonical_fund_ledger"
    assert Decimal(books["positions"][0]["quantity"]) == Decimal("10")
    # retry is no-op / healthy
    r = svc2.retry_ledger_posts(ctx)
    assert r["pending_remaining"] == 0


def test_view_adapter_marks_legacy_flag():
    state = {
        "fund_id": "fund_x",
        "currency": "USD",
        "cash": "100.00",
        "realized_pnl": "0",
        "unrealized_pnl": "0",
        "total_pnl": "0",
        "positions_value": "0",
        "nav": "100.00",
        "paper_nav": "100.00",
        "exposure": {"gross": "0", "net": "0"},
        "positions": [],
        "open_lots": [],
        "invariants_ok": True,
        "event_count": 1,
    }
    v = LedgerPortfolioViewAdapter.from_ledger_state(state, account_id="a1", reserved_cash="10")
    assert v["legacy_oms_state_not_books_authority"] is True
    assert v["available_cash"] == "90.00"
    assert v["books_authority"] == "canonical_fund_ledger"


def test_cutover_policy_constant():
    assert CUTOVER_POLICY == "RESET_PAPER_FUND_FOR_NEW_CANONICAL_ERA"


def test_concurrent_fills_two_symbols(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    acct = svc.create_account(ctx, name="a", starting_cash="100000")
    for sym, ref in [("AAA", "a1"), ("BBB", "b1")]:
        intent = svc.create_intent(
            ctx, account_id=acct["id"], symbol=sym, side="BUY", order_type="MARKET", quantity="5"
        )
        sub = svc.submit_order(
            ctx, intent_id=intent["intent_id"], event=_ev(symbol=sym)
        )
        fr = svc.process_market_event(ctx, order_id=sub["order"]["id"], event=_ev(symbol=sym, ref=ref))
        assert fr["filled"] is True
        assert fr["ledger_post"]["status"] in (POST_POSTED, POST_DUPLICATE)
    books = svc.get_account(ctx, acct["id"])
    assert len(books["positions"]) == 2
    assert books["portfolio_status"] == "HEALTHY"
    assert books["invariants_ok"] if "invariants_ok" in books else True
