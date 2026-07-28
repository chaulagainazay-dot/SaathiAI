"""M62.8 — operator workspace backend concerns.

Locks the concurrency fix (shared SQLite connection serialized so FastAPI's
threadpool can fan out reads without sqlite3.InterfaceError) and covers the
reconciliation read surface + account halt_reason exposed for the UI.
"""
from __future__ import annotations

import threading
from decimal import Decimal

import pytest

from saathi.platform.context import PlatformExecutionContext
from saathi.platform.trading_models import D, DataQuality, MarketState
from saathi.platform.paper_trading import (
    PaperTradingService, PaperStore, MarketEvent, ReconciliationEngine, ZERO_FEE, ZERO_SLIP,
)
from saathi.platform.safety import SafetyService


def _ctx(role="owner", org="o1"):
    return PlatformExecutionContext(user_id="u1", role=role, org_id=org, workspace_id="w1", run_id="r1")


def _ev(symbol="AAPL", bid="99.98", ask="100.02"):
    return MarketEvent(symbol=symbol, ts=1000.0, bid=D(bid), ask=D(ask), last=D("100.00"),
                       liquidity=D("1000000"), quality=DataQuality.VALID, market_state=MarketState.OPEN, ref="fx")


def _seed(tmp_path):
    ps = PaperStore(db_path=tmp_path / "p.db")
    svc = PaperTradingService(ps, fee_model=ZERO_FEE, slippage_model=ZERO_SLIP)
    sf = SafetyService(ps).bind_paper_service(svc)
    svc.bind_safety(sf)
    ctx = _ctx()
    a = svc.create_account(ctx, name="A", starting_cash="100000")
    i = svc.create_intent(ctx, account_id=a["id"], symbol="AAPL", side="BUY", order_type="MARKET", quantity="10")
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev())
    sf.provision_account_defaults(ctx, a["id"])
    sf.run_sweep(ctx, account_ids=[a["id"]])
    return ps, svc, sf, ctx, a


def test_concurrent_reads_no_interface_error(tmp_path):
    ps, svc, sf, ctx, a = _seed(tmp_path)
    recon = ReconciliationEngine(ps)
    errors = []

    def hammer():
        try:
            for _ in range(30):
                svc.list_accounts(ctx)
                svc.list_orders(ctx, account_id=a["id"])
                svc.list_positions(ctx, a["id"])
                sf.list_states(ctx)
                sf.list_trips(ctx)
                sf.list_alerts(ctx)
                sf.list_sweeps(ctx)
                recon.list_runs(ctx)
        except Exception as e:  # pragma: no cover - failure path
            errors.append(repr(e))

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [], f"concurrent reads raised: {errors[:3]}"


def test_reconciliation_read_surface(tmp_path):
    ps, svc, sf, ctx, a = _seed(tmp_path)
    recon = ReconciliationEngine(ps)
    rep = recon.reconcile_account(ctx, a["id"])
    runs = recon.list_runs(ctx, account_id=a["id"])
    assert any(r["run_id"] == rep.run_id for r in runs)
    got = recon.get_run(ctx, rep.run_id)
    assert got["run_id"] == rep.run_id
    assert "findings" in got


def test_account_detail_exposes_halt_reason(tmp_path):
    ps, svc, sf, ctx, a = _seed(tmp_path)
    sf.manual_trip(ctx, scope="PAPER_ACCOUNT", scope_ref=a["id"], reason="kill")
    detail = svc.get_account(ctx, a["id"])
    assert detail["status"] == "HALTED"
    assert "halt_reason" in detail and detail["halt_reason"]
    assert detail["mark_source"] == "replay/fixture"


def test_tenant_isolation_reads(tmp_path):
    ps, svc, sf, ctx, a = _seed(tmp_path)
    other = _ctx(org="o2")
    assert svc.list_accounts(other) == []
    assert sf.list_states(other) == []
