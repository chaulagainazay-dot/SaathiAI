"""M62.6 — durable reconciliation, drift detection, recovery, and controlled
repair planning.

Proves: recompute-from-immutable-events, seven reconciliation dimensions, drift
severity classification, CRITICAL drift halts the affected account (fail-closed),
repair plans are generated but NEVER executed automatically, deterministic
recovery, immutable reports, tenant isolation, RBAC, and fail-closed behaviour
under injected corruption (position/cash/ledger/reservation/fill/order + duplicate
recovery + interrupted transactions + replay-ordering determinism).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.trading_models import D, DataQuality, MarketState
from saathi.platform.paper_trading import (
    PaperTradingService, PaperStore, MarketEvent, ReconciliationEngine,
    ZERO_FEE, ZERO_SLIP, DriftSeverity, RepairPlanStatus, AccountStatus,
)


# ── helpers ───────────────────────────────────────────────────────────────────
def _ctx(role="operator", org="o1", user="u1", ws="w1"):
    return PlatformExecutionContext(user_id=user, role=role, org_id=org, workspace_id=ws, run_id="r1")


def _svc(tmp_path, **kw):
    return PaperTradingService(PaperStore(db_path=tmp_path / "paper.db"),
                               fee_model=ZERO_FEE, slippage_model=ZERO_SLIP, **kw)


def _ev(*, symbol="TRENDING", liquidity="1000000", ref="fx"):
    return MarketEvent(symbol=symbol, ts=1000.0, bid=D("99.98"), ask=D("100.02"), last=D("100.00"),
                       liquidity=D(liquidity), quality=DataQuality.VALID, market_state=MarketState.OPEN, ref=ref)


def _acct(svc, ctx, cash="100000"):
    return svc.create_account(ctx, name="a", starting_cash=cash)


def _buy_and_fill(svc, ctx, a, *, qty="10", ref="c"):
    i = svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="BUY", order_type="MARKET", quantity=qty)
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev(ref=ref))
    return r["order"]["id"]


def _open_buy(svc, ctx, a, *, qty="10"):
    """Submit a BUY (reserves cash) but do NOT fill — leaves an OPEN order."""
    i = svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="BUY", order_type="MARKET", quantity=qty)
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    return r["order"]["id"]


def _codes(rep):
    return {f.code for f in rep.findings}


def _corrupt(svc, sql, params):
    svc.store._conn.execute(sql, params)
    svc.store._conn.commit()


# ══════════════════════════════ HAPPY PATH ══════════════════════════════════
def test_clean_account_reconciles(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _buy_and_fill(svc, ctx, a)
    eng = ReconciliationEngine(svc.store)
    rep = eng.reconcile_account(ctx, a["id"])
    assert rep.severity_max == DriftSeverity.INFO
    assert rep.is_clean() and not rep.halted
    assert rep.expected_state["cash"] == rep.persisted_state["cash"] == "98999.80"
    assert rep.repair_plan_ids == []


def test_recompute_matches_persisted(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _buy_and_fill(svc, ctx, a)
    eng = ReconciliationEngine(svc.store)
    exp = eng.recompute_expected(ctx.org_id, a["id"])
    persisted = svc.get_account(ctx, a["id"])
    assert exp["cash"] == persisted["current_cash"]
    assert exp["positions"]["TRENDING"]["quantity"] == "10"


def test_reconcile_all_multiple_accounts(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx()
    a1 = _acct(svc, ctx); a2 = _acct(svc, ctx)
    _buy_and_fill(svc, ctx, a1)
    reps = ReconciliationEngine(svc.store).reconcile_all(ctx)
    assert len(reps) == 2 and all(r.is_clean() for r in reps)


# ══════════════════════════ DRIFT CLASSIFICATION ════════════════════════════
def test_position_corruption_is_critical_and_halts(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _buy_and_fill(svc, ctx, a)
    _corrupt(svc, "UPDATE paper_positions SET quantity='999' WHERE account_id=?", (a["id"],))
    eng = ReconciliationEngine(svc.store)
    rep = eng.reconcile_account(ctx, a["id"])
    assert rep.severity_max == DriftSeverity.CRITICAL
    assert "position_mismatch" in _codes(rep)
    assert rep.halted
    assert svc.get_account(ctx, a["id"])["status"] == "HALTED"
    assert rep.repair_plan_ids  # a plan was proposed


def test_cash_corruption_is_critical(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _buy_and_fill(svc, ctx, a)
    _corrupt(svc, "UPDATE paper_accounts SET current_cash='50000' WHERE id=?", (a["id"],))
    rep = ReconciliationEngine(svc.store).reconcile_account(ctx, a["id"])
    assert rep.severity_max == DriftSeverity.CRITICAL
    assert "cash_mismatch" in _codes(rep)
    assert rep.halted


def test_ledger_corruption_is_error(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _buy_and_fill(svc, ctx, a)
    # delete the buy ledger row → cash still matches immutable fills (no CRITICAL)
    # but the ledger projection no longer reconciles → ERROR
    _corrupt(svc, "DELETE FROM paper_ledger WHERE account_id=? AND kind='buy'", (a["id"],))
    rep = ReconciliationEngine(svc.store).reconcile_account(ctx, a["id"])
    assert "cash_mismatch" not in _codes(rep)          # fills still agree with cash
    assert {"ledger_cash_mismatch", "ledger_fill_count_mismatch"} & _codes(rep)
    assert rep.severity_max == DriftSeverity.ERROR      # ledger-derived mismatch only
    assert not rep.halted                               # ERROR does not halt


def test_order_fill_mismatch_is_error(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    oid = _buy_and_fill(svc, ctx, a)
    _corrupt(svc, "UPDATE paper_orders SET filled_quantity='3' WHERE id=?", (oid,))
    rep = ReconciliationEngine(svc.store).reconcile_account(ctx, a["id"])
    assert "order_fill_mismatch" in _codes(rep)
    assert rep.severity_max in (DriftSeverity.ERROR, DriftSeverity.CRITICAL)


def test_reservation_corruption_error(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _open_buy(svc, ctx, a)  # reserved_cash > 0, order OPEN
    _corrupt(svc, "UPDATE paper_accounts SET reserved_cash='1.23' WHERE id=?", (a["id"],))
    rep = ReconciliationEngine(svc.store).reconcile_account(ctx, a["id"])
    assert "reserved_mismatch" in _codes(rep)


def test_reserved_exceeds_cash_is_critical(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _corrupt(svc, "UPDATE paper_accounts SET reserved_cash='999999' WHERE id=?", (a["id"],))
    rep = ReconciliationEngine(svc.store).reconcile_account(ctx, a["id"])
    assert rep.severity_max == DriftSeverity.CRITICAL
    assert {"reserved_exceeds_cash", "negative_available_cash"} & _codes(rep)
    assert rep.halted


def test_corrupted_fill_detected_and_halts(tmp_path):
    """A tampered immutable fill row makes the account no longer reconcile → CRITICAL."""
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    oid = _buy_and_fill(svc, ctx, a)
    _corrupt(svc, "UPDATE paper_fills SET gross_amount='1' WHERE paper_order_id=?", (oid,))
    rep = ReconciliationEngine(svc.store).reconcile_account(ctx, a["id"])
    assert rep.severity_max == DriftSeverity.CRITICAL
    assert rep.halted


# ══════════════════════════ RECOVERY / DETERMINISM ══════════════════════════
def test_replay_recompute_is_deterministic(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _buy_and_fill(svc, ctx, a, ref="c1")
    eng = ReconciliationEngine(svc.store)
    e1 = eng.recompute_expected(ctx.org_id, a["id"])
    e2 = eng.recompute_expected(ctx.org_id, a["id"])
    assert e1 == e2


def test_recovery_after_restart_is_clean(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _buy_and_fill(svc, ctx, a)
    # simulate restart: new store on same DB
    svc2 = PaperTradingService(PaperStore(db_path=tmp_path / "paper.db"),
                               fee_model=ZERO_FEE, slippage_model=ZERO_SLIP)
    out = ReconciliationEngine(svc2.store).recover_account(ctx, a["id"])
    assert out["deterministic"] and not out["silent_repair"]
    assert out["reconciliation"]["clean"]


def test_duplicate_recovery_no_double_count(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    i = svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="BUY", order_type="MARKET", quantity="10")
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev(ref="dup"))
    svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev(ref="dup"))  # idempotent
    eng = ReconciliationEngine(svc.store)
    r1 = eng.recover_account(ctx, a["id"])
    r2 = eng.recover_account(ctx, a["id"])
    assert r1["expected_state"] == r2["expected_state"]
    assert r1["reconciliation"]["clean"] and r2["reconciliation"]["clean"]


def test_interrupted_transaction_leaves_no_partial_state(tmp_path):
    """A failed approval consume rolls back fully → account still reconciles clean."""
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    i = svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="BUY", order_type="MARKET", quantity="50")
    with pytest.raises(PlatformContextError):
        svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev(), approval_id="")  # >= threshold, no approval
    rep = ReconciliationEngine(svc.store).reconcile_account(ctx, a["id"])
    assert rep.is_clean()


# ══════════════════════════ IMMUTABLE REPORTS ═══════════════════════════════
def test_reports_are_immutable_and_persisted(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _buy_and_fill(svc, ctx, a)
    eng = ReconciliationEngine(svc.store)
    r1 = eng.reconcile_account(ctx, a["id"])
    fetched = eng.get_run(ctx, r1.run_id)
    assert fetched["report_hash"] == r1.report_hash
    r2 = eng.reconcile_account(ctx, a["id"])
    assert r2.run_id != r1.run_id                        # new immutable run
    assert eng.get_run(ctx, r1.run_id)["report_hash"] == r1.report_hash  # old unchanged
    runs = eng.list_runs(ctx, account_id=a["id"])
    assert len(runs) == 2


# ══════════════════════════ REPAIR PLANNING (never executes) ════════════════
def test_repair_plan_generated_but_never_executed(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _buy_and_fill(svc, ctx, a)
    _corrupt(svc, "UPDATE paper_positions SET quantity='999' WHERE account_id=?", (a["id"],))
    eng = ReconciliationEngine(svc.store)
    rep = eng.reconcile_account(ctx, a["id"])
    plans = eng.list_repair_plans(ctx, account_id=a["id"])
    assert plans and all(p["executes_automatically"] is False for p in plans)
    assert all(p["status"] == "PROPOSED" for p in plans)
    # the corruption is NOT repaired by reconciliation
    assert svc.store.get_position(ctx.org_id, a["id"], "TRENDING").quantity == Decimal("999")
    # the engine has no execute-repair method
    assert not hasattr(eng, "execute_repair") and not hasattr(eng, "apply_repair")


def test_repair_plan_ack_then_authorize(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); owner = _ctx(role="owner"); a = _acct(svc, ctx)
    _buy_and_fill(svc, ctx, a)
    _corrupt(svc, "UPDATE paper_accounts SET current_cash='1' WHERE id=?", (a["id"],))
    eng = ReconciliationEngine(svc.store)
    rep = eng.reconcile_account(ctx, a["id"])
    pid = rep.repair_plan_ids[0]
    acked = eng.acknowledge_repair_plan(owner, pid)
    assert acked["status"] == "ACKNOWLEDGED"
    authed = eng.authorize_repair_plan(owner, pid)
    assert authed["status"] == "AUTHORIZED"
    assert authed["executes_automatically"] is False
    # authorization did NOT change the (still-corrupt) financial state
    assert svc.store.get_account(ctx.org_id, a["id"]).current_cash == Decimal("1")


def test_authorize_requires_prior_acknowledge(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); owner = _ctx(role="owner"); a = _acct(svc, ctx)
    _buy_and_fill(svc, ctx, a)
    _corrupt(svc, "UPDATE paper_accounts SET current_cash='1' WHERE id=?", (a["id"],))
    eng = ReconciliationEngine(svc.store)
    rep = eng.reconcile_account(ctx, a["id"])
    with pytest.raises(PlatformContextError):
        eng.authorize_repair_plan(owner, rep.repair_plan_ids[0])  # not acknowledged yet


# ══════════════════════════ SAFETY INTEGRATION ══════════════════════════════
def test_critical_halt_blocks_new_orders(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _corrupt(svc, "UPDATE paper_accounts SET reserved_cash='999999' WHERE id=?", (a["id"],))
    rep = ReconciliationEngine(svc.store).reconcile_account(ctx, a["id"])  # halts
    assert rep.halted and svc.get_account(ctx, a["id"])["status"] == "HALTED"
    i = svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="BUY", order_type="MARKET", quantity="1")
    # halted account → service refuses to submit (fail-closed)
    with pytest.raises(PlatformContextError) as e:
        svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    assert "ACTIVE" in str(e.value) or "HALT" in str(e.value).upper()


# ══════════════════════════ TENANT ISOLATION / RBAC ═════════════════════════
def test_cross_tenant_reconcile_rejected(tmp_path):
    svc = _svc(tmp_path); a_ctx = _ctx(org="orgA"); b_ctx = _ctx(org="orgB")
    a = _acct(svc, a_ctx); _buy_and_fill(svc, a_ctx, a)
    eng = ReconciliationEngine(svc.store)
    with pytest.raises(PlatformContextError):
        eng.reconcile_account(b_ctx, a["id"])
    with pytest.raises(PlatformContextError):
        eng.recompute_expected("orgB", a["id"])


def test_viewer_cannot_run_but_can_read(tmp_path):
    svc = _svc(tmp_path); op = _ctx(role="operator"); viewer = _ctx(role="viewer"); a = _acct(svc, op)
    _buy_and_fill(svc, op, a)
    eng = ReconciliationEngine(svc.store)
    with pytest.raises(PlatformContextError):
        eng.reconcile_account(viewer, a["id"])
    rep = eng.reconcile_account(op, a["id"])
    assert eng.list_runs(viewer, account_id=a["id"])          # viewer read ok
    assert eng.get_run(viewer, rep.run_id)


def test_operator_cannot_authorize_repair(tmp_path):
    svc = _svc(tmp_path); op = _ctx(role="operator"); a = _acct(svc, op)
    _buy_and_fill(svc, op, a)
    _corrupt(svc, "UPDATE paper_accounts SET current_cash='1' WHERE id=?", (a["id"],))
    eng = ReconciliationEngine(svc.store)
    rep = eng.reconcile_account(op, a["id"])
    with pytest.raises(PlatformContextError):
        eng.acknowledge_repair_plan(op, rep.repair_plan_ids[0])   # operator lacks REPAIR_PLAN_ACKNOWLEDGE
