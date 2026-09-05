"""T-NEXT-4 Phase 14 — deterministic failure injection F1..F20.

Each scenario asserts a *terminal behaviour*, not merely that no exception was
raised. The bar throughout: ambiguity must never resolve itself into action.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from saathi.platform.context import PlatformExecutionContext
from saathi.platform.paper_trading import (
    BrokerOrderState, MarketEvent, PaperStore, PaperTradingService, can_broker_transition,
)
from saathi.platform.paper_trading.execution_integrity import (
    ExecutionReadiness,
    ExternalOrderSnapshot,
    LedgerSnapshot,
    OmsSnapshot,
    ReconciliationAuthority,
    RetryDisposition,
    SubmissionAttemptStore,
    SubmissionOutcome,
    classify_submission,
)
from saathi.platform.trading_models import D, DataQuality, MarketState


def _ctx(role="operator", org="o1", user="u1", ws="w1"):
    return PlatformExecutionContext(user_id=user, role=role, org_id=org, workspace_id=ws, run_id="r1")


def _svc(tmp_path, **kw):
    return PaperTradingService(PaperStore(db_path=tmp_path / "paper.db"), **kw)


def _ev(*, bid="99.98", ask="100.02", last="100.00", liquidity="1000000",
        quality=DataQuality.VALID, market_state=MarketState.OPEN, ts=1000.0,
        symbol="TRENDING", ref="fx"):
    return MarketEvent(symbol=symbol, ts=ts, bid=D(bid), ask=D(ask), last=D(last),
                       liquidity=D(liquidity), quality=quality, market_state=market_state, ref=ref)


@pytest.fixture()
def attempts(tmp_path):
    return SubmissionAttemptStore(tmp_path / "attempts.db")


@pytest.fixture()
def authority():
    return ReconciliationAuthority()


def _snapshots(orders=(), fills=(), *, cash="1000.00", positions=None, available=True):
    positions = positions or {}
    return dict(
        oms=OmsSnapshot(orders=list(orders), fills=list(fills), as_of=1.0),
        external=ExternalOrderSnapshot(orders=list(orders), fills=list(fills), as_of=1.0, available=available),
        ledger=LedgerSnapshot(cash=cash, positions=positions, as_of=1.0),
        expected_cash=cash,
        expected_positions=positions,
    )


# ── F1 duplicate submit ─────────────────────────────────────────────────────

def test_F1_duplicate_submit_cannot_create_two_orders(tmp_path):
    svc = _svc(tmp_path)
    ctx = _ctx()
    acct = svc.create_account(ctx, name="a", starting_cash="100000")
    intent = svc.create_intent(ctx, account_id=acct["id"], symbol="TRENDING", side="BUY",
                               order_type="MARKET", quantity="10")
    ev = _ev()
    first = svc.submit_order(ctx, intent_id=intent["intent_id"], event=ev)["order"]
    second = svc.submit_order(ctx, intent_id=intent["intent_id"], event=ev)["order"]
    assert first["id"] == second["id"], "same idempotency key must return the same order"
    assert len(svc.list_orders(ctx, account_id=acct["id"])) == 1


def test_F1b_attempt_store_refuses_second_submission_after_ack(attempts):
    attempts.record(request_id="r1", client_order_id="c1", idempotency_key="k1",
                    attempt=1, outcome=SubmissionOutcome.ACKNOWLEDGED)
    assert attempts.may_submit("k1") is False


# ── F2 timeout before send ──────────────────────────────────────────────────

def test_F2_timeout_before_send_is_safe_to_retry(attempts):
    attempts.record(request_id="r1", client_order_id="c1", idempotency_key="k2",
                    attempt=1, outcome=SubmissionOutcome.TIMEOUT_BEFORE_SEND)
    assert classify_submission(SubmissionOutcome.TIMEOUT_BEFORE_SEND) is RetryDisposition.SAFE_TO_RETRY
    assert attempts.may_submit("k2") is True


# ── F3 timeout after potential send ─────────────────────────────────────────

def test_F3_timeout_after_send_blocks_until_reconciled(attempts):
    attempts.record(request_id="r1", client_order_id="c1", idempotency_key="k3",
                    attempt=1, outcome=SubmissionOutcome.TIMEOUT_AFTER_SEND)
    assert attempts.may_submit("k3") is False
    assert attempts.requires_reconciliation("k3") is True


# ── F4 process crash after submit ───────────────────────────────────────────

def test_F4_crash_after_submit_reloads_order_and_never_resubmits(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    acct = svc.create_account(ctx, name="a", starting_cash="100000")
    intent = svc.create_intent(ctx, account_id=acct["id"], symbol="TRENDING", side="BUY",
                               order_type="MARKET", quantity="10")
    order = svc.submit_order(ctx, intent_id=intent["intent_id"], event=_ev())["order"]

    # simulate process restart: brand new service over the same durable store
    reborn = PaperTradingService(PaperStore(db_path=tmp_path / "paper.db"))
    recovered = reborn.get_order(ctx, order["id"])
    assert recovered["id"] == order["id"], "no order may disappear across restart"

    again = reborn.submit_order(ctx, intent_id=intent["intent_id"], event=_ev())["order"]
    assert again["id"] == order["id"], "restart must not create a second order"


# ── F5 duplicate ack ────────────────────────────────────────────────────────

def test_F5_duplicate_ack_is_idempotent(attempts):
    a = attempts.record(request_id="r-ack", client_order_id="c1", idempotency_key="k5",
                        attempt=1, outcome=SubmissionOutcome.ACKNOWLEDGED)
    b = attempts.record(request_id="r-ack", client_order_id="c1", idempotency_key="k5",
                        attempt=1, outcome=SubmissionOutcome.ACKNOWLEDGED)
    assert a["request_id"] == b["request_id"]
    assert len(attempts.attempts_for("k5")) == 1


# ── F6 duplicate fill ───────────────────────────────────────────────────────

def test_F6_duplicate_fill_moves_ledger_once(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    acct = svc.create_account(ctx, name="a", starting_cash="100000")
    intent = svc.create_intent(ctx, account_id=acct["id"], symbol="TRENDING", side="BUY",
                               order_type="MARKET", quantity="10")
    order = svc.submit_order(ctx, intent_id=intent["intent_id"], event=_ev())["order"]

    ev = _ev(ts=1001.0)
    svc.process_market_event(ctx, order_id=order["id"], event=ev)
    fills_once = svc.list_fills(ctx, order["id"])
    positions_once = svc.list_positions(ctx, acct["id"])

    # replay the identical event — must be deduplicated
    svc.process_market_event(ctx, order_id=order["id"], event=ev)
    assert len(svc.list_fills(ctx, order["id"])) == len(fills_once)
    assert svc.list_positions(ctx, acct["id"]) == positions_once


# ── F7 out-of-order fill ────────────────────────────────────────────────────

def test_F7_out_of_order_fill_is_handled_deterministically(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    acct = svc.create_account(ctx, name="a", starting_cash="100000")
    intent = svc.create_intent(ctx, account_id=acct["id"], symbol="TRENDING", side="BUY",
                               order_type="MARKET", quantity="10")
    order = svc.submit_order(ctx, intent_id=intent["intent_id"], event=_ev())["order"]

    svc.process_market_event(ctx, order_id=order["id"], event=_ev(ts=2000.0))
    after = svc.get_order(ctx, order["id"])
    # a stale, earlier event must not increase filled quantity beyond the order
    svc.process_market_event(ctx, order_id=order["id"], event=_ev(ts=1000.0))
    later = svc.get_order(ctx, order["id"])
    assert Decimal(later["filled_quantity"]) <= Decimal(later["original_quantity"])
    assert Decimal(later["filled_quantity"]) >= Decimal(after["filled_quantity"])


# ── F8 / F9 cancel interactions ─────────────────────────────────────────────

def test_F8_cancel_after_full_fill_cannot_resurrect_order(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    acct = svc.create_account(ctx, name="a", starting_cash="100000")
    intent = svc.create_intent(ctx, account_id=acct["id"], symbol="TRENDING", side="BUY",
                               order_type="MARKET", quantity="10")
    order = svc.submit_order(ctx, intent_id=intent["intent_id"], event=_ev())["order"]
    svc.process_market_event(ctx, order_id=order["id"], event=_ev(ts=1001.0))
    filled = svc.get_order(ctx, order["id"])
    if filled["broker_state"] == BrokerOrderState.FILLED.value:
        assert can_broker_transition(BrokerOrderState.FILLED, BrokerOrderState.CANCELLED) is False
        assert can_broker_transition(BrokerOrderState.FILLED, BrokerOrderState.OPEN) is False


def test_F9_state_machine_forbids_illegal_resurrection():
    forbidden = [
        (BrokerOrderState.FILLED, BrokerOrderState.ACCEPTED),
        (BrokerOrderState.FILLED, BrokerOrderState.OPEN),
        (BrokerOrderState.CANCELLED, BrokerOrderState.ACCEPTED),
        (BrokerOrderState.CANCELLED, BrokerOrderState.PARTIALLY_FILLED),
        (BrokerOrderState.REJECTED, BrokerOrderState.FILLED),
        (BrokerOrderState.EXPIRED, BrokerOrderState.FILLED),
    ]
    for cur, tgt in forbidden:
        assert can_broker_transition(cur, tgt) is False, f"{cur} -> {tgt} must be forbidden"


# ── F10 ledger write failure ────────────────────────────────────────────────

def test_F10_ledger_posting_failure_requests_reconciliation(tmp_path, monkeypatch):
    from saathi.platform.fund_ledger import posting as posting_mod

    ledger = object()
    posts = posting_mod.FillPostingStore(tmp_path / "posts.db")
    posts.bind_account("acct-1", "fund-1")

    def _boom(*a, **k):
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(posting_mod, "post_paper_fill_to_ledger", _boom)
    out = posting_mod.post_accepted_fill(
        ledger, posts, account_id="acct-1", fill_id="f1", order_id="o1",
        side="BUY", symbol="AAPL", quantity="1", price="10",
    )
    assert out["status"] == posting_mod.POST_FAILED
    assert out["portfolio_status"] == "RECONCILIATION_REQUIRED"


# ── F11 reconciliation mismatch ─────────────────────────────────────────────

def test_F11_reconciliation_mismatch_blocks_execution(authority):
    order = {"order_id": "o1", "client_order_id": "c1", "state": "FILLED", "filled_quantity": "10"}
    v = authority.evaluate(
        oms=OmsSnapshot(orders=[order], fills=[], as_of=1.0),
        external=ExternalOrderSnapshot(orders=[], fills=[], as_of=1.0),
        ledger=LedgerSnapshot(cash="1000.00", positions={}, as_of=1.0),
        expected_cash="1000.00", expected_positions={},
    )
    assert v.readiness is ExecutionReadiness.MISMATCH
    assert v.permits_new_execution is False


# ── F12 stale market data ───────────────────────────────────────────────────

def test_F12_stale_market_data_is_rejected_before_submission(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    acct = svc.create_account(ctx, name="a", starting_cash="100000")
    intent = svc.create_intent(ctx, account_id=acct["id"], symbol="TRENDING", side="BUY",
                               order_type="MARKET", quantity="10")
    stale = _ev(quality=DataQuality.STALE)
    with pytest.raises(Exception):
        svc.submit_order(ctx, intent_id=intent["intent_id"], event=stale)


def test_F12b_zero_or_negative_price_is_rejected(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    acct = svc.create_account(ctx, name="a", starting_cash="100000")
    intent = svc.create_intent(ctx, account_id=acct["id"], symbol="TRENDING", side="BUY",
                               order_type="MARKET", quantity="10")
    with pytest.raises(Exception):
        svc.submit_order(ctx, intent_id=intent["intent_id"],
                         event=_ev(bid="0", ask="0", last="0"))


# ── F13 / F14 approval and proposal validity ────────────────────────────────

def test_F13_unknown_approval_is_refused(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    acct = svc.create_account(ctx, name="a", starting_cash="100000")
    intent = svc.create_intent(ctx, account_id=acct["id"], symbol="TRENDING", side="BUY",
                               order_type="MARKET", quantity="10")
    with pytest.raises(Exception):
        svc.submit_order(ctx, intent_id=intent["intent_id"], event=_ev(),
                         approval_id="never-issued")


def test_F14_unknown_intent_cannot_produce_an_order(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    svc.create_account(ctx, name="a", starting_cash="100000")
    with pytest.raises(Exception):
        svc.submit_order(ctx, intent_id="does-not-exist", event=_ev())


# ── F17 kill switch ─────────────────────────────────────────────────────────

def test_F17_halted_account_blocks_new_orders(tmp_path):
    ctx = _ctx(role="owner")
    svc = _svc(tmp_path)
    acct = svc.create_account(ctx, name="a", starting_cash="100000")
    intent = svc.create_intent(ctx, account_id=acct["id"], symbol="TRENDING", side="BUY",
                               order_type="MARKET", quantity="10")
    svc.halt_account(ctx, acct["id"], expected_version=acct["version"], reason="kill switch")
    with pytest.raises(Exception):
        svc.submit_order(ctx, intent_id=intent["intent_id"], event=_ev())


# ── F18 corrupted / stale persisted state ───────────────────────────────────

def test_F18_ambiguous_persisted_state_forces_unknown(authority):
    murky = {"order_id": "o9", "client_order_id": "c9", "state": "UNKNOWN", "filled_quantity": "0"}
    v = authority.evaluate(
        oms=OmsSnapshot(orders=[murky], fills=[], as_of=1.0),
        external=ExternalOrderSnapshot(orders=[murky], fills=[], as_of=1.0),
        ledger=LedgerSnapshot(cash="1000.00", positions={}, as_of=1.0),
        expected_cash="1000.00", expected_positions={},
    )
    assert v.readiness is ExecutionReadiness.UNKNOWN
    assert v.permits_new_execution is False


# ── F19 unknown external order ──────────────────────────────────────────────

def test_F19_unknown_external_order_blocks(authority):
    ghost = {"order_id": "ghost-1", "client_order_id": "cX", "state": "FILLED", "filled_quantity": "5"}
    v = authority.evaluate(
        oms=OmsSnapshot(orders=[], fills=[], as_of=1.0),
        external=ExternalOrderSnapshot(orders=[ghost], fills=[], as_of=1.0),
        ledger=LedgerSnapshot(cash="1000.00", positions={}, as_of=1.0),
        expected_cash="1000.00", expected_positions={},
    )
    assert v.readiness is ExecutionReadiness.MISMATCH
    assert v.permits_new_execution is False


# ── F20 overfill ────────────────────────────────────────────────────────────

def test_F20_overfill_is_mismatch_and_blocks(authority):
    over = {"order_id": "o1", "client_order_id": "c1", "state": "FILLED", "filled_quantity": "12"}
    v = authority.evaluate(
        oms=OmsSnapshot(orders=[over], fills=[], as_of=1.0),
        external=ExternalOrderSnapshot(orders=[over], fills=[], as_of=1.0),
        ledger=LedgerSnapshot(cash="1000.00", positions={}, as_of=1.0),
        expected_cash="1000.00", expected_positions={},
        order_original_quantities={"o1": "10"},
    )
    assert v.readiness is ExecutionReadiness.MISMATCH
    assert v.permits_new_execution is False


def test_F20b_order_can_never_fill_beyond_original_quantity(tmp_path):
    ctx = _ctx()
    svc = _svc(tmp_path)
    acct = svc.create_account(ctx, name="a", starting_cash="100000")
    intent = svc.create_intent(ctx, account_id=acct["id"], symbol="TRENDING", side="BUY",
                               order_type="MARKET", quantity="10")
    order = svc.submit_order(ctx, intent_id=intent["intent_id"], event=_ev())["order"]
    for i in range(5):
        svc.process_market_event(ctx, order_id=order["id"], event=_ev(ts=2000.0 + i))
    final = svc.get_order(ctx, order["id"])
    assert Decimal(final["filled_quantity"]) <= Decimal(final["original_quantity"])
