"""M62.5 — deterministic paper broker + durable order lifecycle.

Unit + persistence + integration (Runtime/Gateway/tool) + adversarial. Proves:
durable paper accounts, cash/position reservation, intent↔order separation, a
validated broker state machine, deterministic market/limit fills, partial fills,
cancellation, multi-layer idempotency, reconciling accounting, the fail-closed
Trading Guardian veto BEFORE submission, server-owned approval verification and
consumption, the ExecutionGateway/registered-tool mutation boundary, tenant
isolation, atomic rollback, restart persistence, and that NO live/leverage/short/
derivative/network capability exists.
"""
from __future__ import annotations

import time
from decimal import Decimal

import pytest

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.trading_models import (
    D, Environment, OrderSide, OrderType, DataQuality, MarketState,
)
from saathi.platform.paper_trading import (
    PaperTradingService, PaperStore, PaperBroker, MarketEvent, AccountStatus, BrokerOrderState,
    FeeModel, SlippageModel, REALISTIC_FEE, REALISTIC_SLIP, ZERO_FEE, ZERO_SLIP,
    assert_paper_safe, PaperSafetyError, can_broker_transition, can_account_transition, fixtures,
)
from saathi.platform.paper_trading.models import (
    PaperAccount, PaperPosition, PaperOrder, fill_result_hash,
)
from saathi.platform.paper_trading.broker import from_quote, from_bar
from saathi.platform.paper_trading.execution_tool import _event_from_args


def _ctx(role="operator", org="o1", user="u1", ws="w1"):
    return PlatformExecutionContext(user_id=user, role=role, org_id=org, workspace_id=ws, run_id="r1")


def _svc(tmp_path, **kw):
    return PaperTradingService(PaperStore(db_path=tmp_path / "paper.db"), **kw)


def _ev(*, bid="99.98", ask="100.02", last="100.00", liquidity="1000000", quality=DataQuality.VALID,
        market_state=MarketState.OPEN, ts=1000.0, symbol="TRENDING", ref="fx"):
    return MarketEvent(symbol=symbol, ts=ts, bid=D(bid), ask=D(ask), last=D(last), liquidity=D(liquidity),
                       quality=quality, market_state=market_state, ref=ref)


def _acct(svc, ctx, cash="100000"):
    return svc.create_account(ctx, name="a", starting_cash=cash)


def _buy(svc, ctx, acct, *, qty="10", otype="MARKET", limit=None, symbol="TRENDING", side="BUY"):
    return svc.create_intent(ctx, account_id=acct["id"], symbol=symbol, side=side, order_type=otype,
                             quantity=qty, limit_price=limit)


# ══════════════════════════════════ SAFETY ══════════════════════════════════
def test_safety_prohibited_config_fails_closed():
    for tok in ["LIVE", "PRODUCTION", "REAL_MONEY", "LEVERAGE", "MARGIN", "SHORT_SELLING", "OPTIONS",
                "FUTURES", "PERPETUALS", "DERIVATIVES", "BORROWING", "LIVE_BROKER"]:
        with pytest.raises(PaperSafetyError):
            assert_paper_safe({tok: True})


def test_safety_non_paper_environment_rejected():
    with pytest.raises(PaperSafetyError):
        assert_paper_safe(environment=Environment.LIVE)
    with pytest.raises(PaperSafetyError):
        assert_paper_safe(environment=Environment.PAPER, config={"DERIVATIVES": "DERIVATIVES"})
    assert_paper_safe(environment=Environment.PAPER)  # ok


def test_broker_refuses_prohibited_by_construction():
    b = PaperBroker(fee_model=REALISTIC_FEE, slippage_model=REALISTIC_SLIP)
    assert b.engine_version.startswith("paper-broker")


# ══════════════════════════════ MODELS / MACHINES ═══════════════════════════
def test_broker_state_machine_edges():
    assert can_broker_transition(BrokerOrderState.OPEN, BrokerOrderState.PARTIALLY_FILLED)
    assert can_broker_transition(BrokerOrderState.PARTIALLY_FILLED, BrokerOrderState.FILLED)
    assert not can_broker_transition(BrokerOrderState.FILLED, BrokerOrderState.CANCELLED)
    assert not can_broker_transition(BrokerOrderState.CANCELLED, BrokerOrderState.OPEN)
    assert not can_broker_transition(BrokerOrderState.REJECTED, BrokerOrderState.OPEN)


def test_account_state_machine():
    assert can_account_transition(AccountStatus.ACTIVE, AccountStatus.HALTED)
    assert can_account_transition(AccountStatus.HALTED, AccountStatus.ACTIVE)
    assert not can_account_transition(AccountStatus.CLOSED, AccountStatus.ACTIVE)


def test_fee_model_min_and_pct():
    f = FeeModel(pct=Decimal("0.001"), minimum=Decimal("1"))
    assert f.fee(quantity=Decimal("1"), price=Decimal("100")) == Decimal("1.00")   # min floor
    assert f.fee(quantity=Decimal("100"), price=Decimal("100")) == Decimal("10.00")  # pct


def test_slippage_adverse_direction():
    s = SlippageModel(bps=Decimal("10"), spread_aware=False)
    buy = s.adjust(side=OrderSide.BUY, reference=Decimal("100"), spread=None)
    sell = s.adjust(side=OrderSide.SELL, reference=Decimal("100"), spread=None)
    assert buy > Decimal("100") > sell


# ══════════════════════════════ FILL ENGINE (pure) ══════════════════════════
def _order(side="BUY", otype="MARKET", qty="10", limit=None):
    return PaperOrder(id="o", order_intent_id="i", paper_account_id="a", org_id="o1", symbol="TRENDING",
                      side=OrderSide(side), order_type=OrderType(otype), original_quantity=D(qty),
                      limit_price=D(limit) if limit else None, broker_state=BrokerOrderState.OPEN)


def _account():
    return PaperAccount(id="a", org_id="o1", workspace_id="w1", project_id="", name="a", base_currency="USD",
                        starting_cash=Decimal("100000"), current_cash=Decimal("100000"), status=AccountStatus.ACTIVE)


def test_market_buy_fills_at_ask_plus_slippage():
    b = PaperBroker(fee_model=ZERO_FEE, slippage_model=SlippageModel(bps=Decimal("0"), spread_aware=False))
    plan = b.compute_fill(order=_order(), account=_account(), event=_ev())
    assert plan.eligible and plan.quantity == Decimal("10") and plan.price == Decimal("100.02")


def test_limit_buy_not_crossed_no_fill():
    b = PaperBroker(fee_model=ZERO_FEE, slippage_model=ZERO_SLIP)
    plan = b.compute_fill(order=_order(otype="LIMIT", limit="100.00"), account=_account(), event=_ev(ask="100.02"))
    assert not plan.eligible and "limit not crossed" in plan.reason


def test_limit_buy_never_fills_above_limit():
    b = PaperBroker(fee_model=ZERO_FEE, slippage_model=SlippageModel(bps=Decimal("50"), spread_aware=True))
    # ask 99.90 <= limit 100 → crosses; slippage would push >100 but must clamp to limit
    plan = b.compute_fill(order=_order(otype="LIMIT", limit="100.00"), account=_account(),
                          event=_ev(bid="99.86", ask="99.90"))
    assert plan.eligible and plan.price <= Decimal("100.00")


def test_partial_fill_on_low_liquidity():
    b = PaperBroker(fee_model=ZERO_FEE, slippage_model=SlippageModel(bps=Decimal("0"), spread_aware=False,
                    max_volume_participation=Decimal("0.25")))
    plan = b.compute_fill(order=_order(qty="100"), account=_account(), event=_ev(liquidity="40"))
    assert plan.eligible and plan.quantity == Decimal("10")  # floor(40*0.25)


def test_invalid_quality_blocks_fill():
    b = PaperBroker(fee_model=ZERO_FEE, slippage_model=ZERO_SLIP)
    plan = b.compute_fill(order=_order(), account=_account(), event=_ev(quality=DataQuality.STALE))
    assert not plan.eligible and "quality" in plan.reason


def test_market_closed_blocks_fill():
    b = PaperBroker(fee_model=ZERO_FEE, slippage_model=ZERO_SLIP)
    plan = b.compute_fill(order=_order(), account=_account(), event=_ev(market_state=MarketState.CLOSED))
    assert not plan.eligible and "not open" in plan.reason


def test_fill_determinism_identical_inputs_identical_hash():
    b = PaperBroker(fee_model=REALISTIC_FEE, slippage_model=REALISTIC_SLIP, seed=7)
    p1 = b.compute_fill(order=_order(), account=_account(), event=_ev())
    p2 = b.compute_fill(order=_order(), account=_account(), event=_ev())
    assert p1.result_hash == p2.result_hash and p1.result_hash


# ══════════════════════════════ SERVICE FLOW ════════════════════════════════
def test_account_creation_and_positive_cash(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx)
    assert a["status"] == "ACTIVE" and a["environment"] == "PAPER" and a["available_cash"] == "100000.00"
    with pytest.raises(PlatformContextError):
        svc.create_account(ctx, name="bad", starting_cash="0")


def test_market_buy_reserves_then_fills(tmp_path):
    svc = _svc(tmp_path, fee_model=ZERO_FEE, slippage_model=ZERO_SLIP); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a, qty="10")
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    assert r["order"]["broker_state"] == "OPEN"
    after = svc.get_account(ctx, a["id"])
    assert D(after["reserved_cash"]) > 0 and D(after["available_cash"]) < Decimal("100000")
    fr = svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev())
    assert fr["filled"] and fr["order"]["broker_state"] == "FILLED"
    done = svc.get_account(ctx, a["id"])
    assert done["reserved_cash"] == "0.00"
    assert D(done["current_cash"]) == Decimal("100000") - Decimal("1000.20")  # 10 @ 100.02
    assert svc.check_account_invariants(ctx, a["id"]) == []


def test_intent_and_order_are_separate(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a)
    assert i["state"] == "APPROVAL_REQUIRED"  # an intent is not an order
    assert svc.store.get_order_by_idempotency(ctx.org_id, i["idempotency_key"]) is None
    svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    assert svc.store.get_order_by_idempotency(ctx.org_id, i["idempotency_key"]) is not None


def test_insufficient_cash_rejected_no_reservation_no_order(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx, cash="500")
    i = _buy(svc, ctx, a, qty="10")  # ~1000 notional > 500
    with pytest.raises(PlatformContextError):
        svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    after = svc.get_account(ctx, a["id"])
    assert after["reserved_cash"] == "0.00" and svc.store.list_orders(ctx.org_id, account_id=a["id"]) == []


def test_oversell_rejected(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a, side="SELL", qty="5")  # no position
    with pytest.raises(PlatformContextError):
        svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())


def test_sell_realizes_pnl(tmp_path):
    svc = _svc(tmp_path, fee_model=ZERO_FEE, slippage_model=ZERO_SLIP); ctx = _ctx()
    a = _acct(svc, ctx)
    ib = _buy(svc, ctx, a, qty="10")
    rb = svc.submit_order(ctx, intent_id=ib["intent_id"], event=_ev())
    svc.process_market_event(ctx, order_id=rb["order"]["id"], event=_ev())  # bought @100.02
    isl = _buy(svc, ctx, a, side="SELL", qty="10")
    rs = svc.submit_order(ctx, intent_id=isl["intent_id"], event=_ev(bid="110.00", ask="110.02"))
    svc.process_market_event(ctx, order_id=rs["order"]["id"], event=_ev(bid="110.00", ask="110.02"))  # sold @110.00
    acct = svc.get_account(ctx, a["id"])
    assert D(acct["realized_pnl"]) == Decimal("99.80")  # (110.00-100.02)*10
    assert svc.check_account_invariants(ctx, a["id"]) == []


def test_partial_then_complete_across_events(tmp_path):
    svc = _svc(tmp_path, fee_model=ZERO_FEE, slippage_model=SlippageModel(bps=Decimal("0"), spread_aware=False,
               max_volume_participation=Decimal("0.25"))); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a, qty="20")
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev(liquidity="40"))
    f1 = svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev(liquidity="40", ref="e1"))
    assert f1["order"]["broker_state"] == "PARTIALLY_FILLED" and f1["order"]["filled_quantity"] == "10"
    f2 = svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev(liquidity="1000000", ref="e2"))
    assert f2["order"]["broker_state"] == "FILLED" and f2["order"]["remaining_quantity"] == "0"


def test_guardian_veto_before_submission(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a)
    with pytest.raises(PlatformContextError, match="guardian"):
        svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev(quality=DataQuality.STALE))
    intent = svc.get_intent(ctx, i["intent_id"])
    assert intent["state"] == "REJECTED" and intent["guardian"]["allowed"] is False
    assert intent["guardian"]["is_trade_approval"] is False


# ══════════════════════════════ IDEMPOTENCY ═════════════════════════════════
def test_duplicate_submission_one_order(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a)
    r1 = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    r2 = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    assert r1["order"]["id"] == r2["order"]["id"] and r2.get("idempotent_replay")
    assert len(svc.store.list_orders(ctx.org_id, account_id=a["id"])) == 1


def test_duplicate_market_event_one_fill(tmp_path):
    # low liquidity → partial fill keeps the order open, so the SAME event replayed
    # must be an idempotent no-op (event dedup), not a second fill.
    slip = SlippageModel(bps=Decimal("0"), spread_aware=False, max_volume_participation=Decimal("0.25"))
    svc = _svc(tmp_path, fee_model=ZERO_FEE, slippage_model=slip); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a, qty="20")
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev(liquidity="40"))
    first = svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev(liquidity="40", ref="same"))
    assert first["filled"] and first["order"]["broker_state"] == "PARTIALLY_FILLED"
    dup = svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev(liquidity="40", ref="same"))
    assert not dup["filled"] and "duplicate" in dup["reason"]
    assert len(svc.store.list_fills(ctx.org_id, r["order"]["id"])) == 1


# ══════════════════════════════ CANCELLATION ════════════════════════════════
def test_cancel_open_releases_reservation(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a)
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    assert D(svc.get_account(ctx, a["id"])["reserved_cash"]) > 0
    c = svc.cancel_order(ctx, order_id=r["order"]["id"])
    assert c["cancelled"] and c["order"]["broker_state"] == "CANCELLED"
    assert svc.get_account(ctx, a["id"])["reserved_cash"] == "0.00"


def test_cancel_after_fill_rejected(tmp_path):
    svc = _svc(tmp_path, fee_model=ZERO_FEE, slippage_model=ZERO_SLIP); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a)
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev())
    with pytest.raises(PlatformContextError):
        svc.cancel_order(ctx, order_id=r["order"]["id"])


def test_partial_fill_then_cancel_retains_fill(tmp_path):
    svc = _svc(tmp_path, fee_model=ZERO_FEE, slippage_model=SlippageModel(bps=Decimal("0"), spread_aware=False,
               max_volume_participation=Decimal("0.25"))); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a, qty="20")
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev(liquidity="40"))
    svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev(liquidity="40", ref="e1"))
    c = svc.cancel_order(ctx, order_id=r["order"]["id"])
    assert c["order"]["filled_quantity"] == "10" and c["order"]["broker_state"] == "CANCELLED"
    assert svc.get_account(ctx, a["id"])["reserved_cash"] == "0.00"


def test_fill_after_cancel_rejected(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a)
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    svc.cancel_order(ctx, order_id=r["order"]["id"])
    fr = svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev())
    assert not fr["filled"]


# ══════════════════════════════ HALT ════════════════════════════════════════
def test_halt_blocks_new_orders(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx(role="owner")
    a = _acct(svc, ctx)
    svc.halt_account(ctx, a["id"], expected_version=a["version"], reason="test")
    i = _buy(svc, ctx, a)
    with pytest.raises(PlatformContextError):
        svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())


def test_halt_requires_owner(tmp_path):
    svc = _svc(tmp_path); op = _ctx(role="operator")
    a = _acct(svc, op)
    with pytest.raises(PlatformContextError):
        svc.halt_account(op, a["id"], expected_version=a["version"])


# ══════════════════════════════ PERSISTENCE / RESTART ═══════════════════════
def test_restart_preserves_order_and_reservation(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a)
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    reserved = svc.get_account(ctx, a["id"])["reserved_cash"]
    svc2 = PaperTradingService(PaperStore(db_path=tmp_path / "paper.db"))  # "restart"
    o = svc2.store.get_order(ctx.org_id, r["order"]["id"])
    assert o is not None and o.broker_state == BrokerOrderState.OPEN
    assert svc2.get_account(ctx, a["id"])["reserved_cash"] == reserved


def test_restart_after_partial_no_duplicate_fill(tmp_path):
    slip = SlippageModel(bps=Decimal("0"), spread_aware=False, max_volume_participation=Decimal("0.25"))
    svc = _svc(tmp_path, fee_model=ZERO_FEE, slippage_model=slip); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a, qty="20")
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev(liquidity="40"))
    svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev(liquidity="40", ref="e1"))
    svc2 = PaperTradingService(PaperStore(db_path=tmp_path / "paper.db"), fee_model=ZERO_FEE, slippage_model=slip)
    dup = svc2.process_market_event(ctx, order_id=r["order"]["id"], event=_ev(liquidity="40", ref="e1"))
    assert not dup["filled"]
    assert len(svc2.store.list_fills(ctx.org_id, r["order"]["id"])) == 1


def test_fill_records_are_immutable_append_only(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a)
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev())
    fills = svc.list_fills(ctx, r["order"]["id"])
    assert len(fills) == 1 and fills[0]["result_hash"]


# ══════════════════════════════ TENANT ISOLATION ════════════════════════════
def test_cross_tenant_cannot_read_or_mutate(tmp_path):
    svc = _svc(tmp_path); a_ctx = _ctx(org="orgA"); b_ctx = _ctx(org="orgB")
    a = _acct(svc, a_ctx)
    i = _buy(svc, a_ctx, a)
    r = svc.submit_order(a_ctx, intent_id=i["intent_id"], event=_ev())
    with pytest.raises(PlatformContextError):
        svc.get_order(b_ctx, r["order"]["id"])
    with pytest.raises(PlatformContextError):
        svc.cancel_order(b_ctx, order_id=r["order"]["id"])
    with pytest.raises(PlatformContextError):
        svc.get_account(b_ctx, a["id"])


# ══════════════════════════════ PERMISSIONS ═════════════════════════════════
def test_viewer_cannot_propose_or_submit(tmp_path):
    svc = _svc(tmp_path); owner = _ctx(role="owner"); viewer = _ctx(role="viewer")
    a = _acct(svc, owner)
    with pytest.raises(PlatformContextError):
        svc.create_intent(viewer, account_id=a["id"], symbol="TRENDING", side="BUY", order_type="MARKET", quantity="1")
    # viewer can read
    assert svc.list_accounts(viewer)


# ══════════════════════════════ ADVERSARIAL ═════════════════════════════════
def test_negative_quantity_rejected(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx)
    with pytest.raises(PlatformContextError):
        svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="BUY", order_type="MARKET", quantity="-5")


def test_unsupported_side_and_type_rejected(tmp_path):
    svc = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx)
    with pytest.raises(PlatformContextError):
        svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="SHORT", order_type="MARKET", quantity="1")
    with pytest.raises(PlatformContextError):
        svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="BUY", order_type="STOP", quantity="1")


def test_atomic_rollback_on_approval_failure(tmp_path):
    """A failing approval consume must leave NO order and NO reservation."""
    svc = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a, qty="50")  # >= approval threshold
    # no approval provided → verify raises before any write
    with pytest.raises(PlatformContextError):
        svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev(), approval_id="")
    assert svc.store.list_orders(ctx.org_id, account_id=a["id"]) == []
    assert svc.get_account(ctx, a["id"])["reserved_cash"] == "0.00"


def test_financial_execution_tool_prohibited():
    from saathi.tool_runtime.registry import default_registry
    from saathi.tool_runtime.service import ToolExecutionService
    from saathi.tool_runtime.contracts import ToolExecutionRequest, ToolOutcomeClass
    svc = ToolExecutionService(default_registry())
    res = svc.execute_tool(ToolExecutionRequest(run_id="r", tool_id="m49.financial_execution_stub",
                                                arguments={"symbol": "X"}))
    assert res.outcome_class == ToolOutcomeClass.PROHIBITED


def test_no_broker_import_in_research_or_strategy():
    import saathi.platform.research.service as rs
    import saathi.platform.strategy.service as ss
    for mod in (rs, ss):
        src = open(mod.__file__).read()
        assert "paper_trading" not in src and "PaperBroker" not in src


def test_fixture_manifest_stable():
    assert fixtures.fixture_manifest() == fixtures.fixture_manifest()


# ══════════════════════ GATEWAY INTEGRATION (Runtime→Gateway→tool) ══════════
def _wire_gateway(tmp_path, monkeypatch):
    """Share ONE sqlite file across platform + paper stores so approval consumption
    is atomic with the order write, then inject the paper service singleton."""
    db = str(tmp_path / "shared.db")
    monkeypatch.setenv("SAATHI_PAPER_DB", db)
    monkeypatch.setenv("SAATHI_PLATFORM_DB", db)
    from saathi.platform.service import reset_platform_for_tests
    from saathi.platform.paper_trading import set_paper_service_for_tests
    from saathi.tool_runtime.registry import reset_registry_for_tests
    platform = reset_platform_for_tests(tmp_path / "shared.db")
    reset_registry_for_tests()  # re-bootstraps paper tools
    svc = PaperTradingService(PaperStore(db_path=db), platform_store=platform.store).bind_audit(platform.store)
    set_paper_service_for_tests(svc)
    return platform, svc


def _approval(platform, *, org="o1", tool="paper.order.submit", status="approved", expires=None):
    from saathi.platform.models import ApprovalRecord, new_id
    ap = ApprovalRecord(approval_id=new_id("appr_"), user_id="owner", org_id=org, workspace_id="w1", project_id="",
                        mission_id="", tool_id=tool, action="paper_order_submit", target_resource="",
                        authority="LOCAL_MUTATION", side_effect_class="LOCAL_IRREVERSIBLE", status=status,
                        decided_by="owner", expires_at=expires if expires is not None else time.time() + 3600)
    platform.store.save_approval(ap)
    return ap


def test_gateway_submit_consumes_approval_and_fills(tmp_path, monkeypatch):
    from saathi.platform.paper_trading import orchestration
    from saathi.tool_runtime.contracts import ToolOutcomeClass
    platform, svc = _wire_gateway(tmp_path, monkeypatch)
    ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a, qty="50")  # triggers approval requirement
    ap = _approval(platform)
    r = orchestration.submit_via_gateway(ctx, intent_id=i["intent_id"], market=fixtures.VALID_TIGHT,
                                         approval_id=ap.approval_id, expires_at=ap.expires_at)
    assert r.outcome_class == ToolOutcomeClass.SUCCESS_CONFIRMED and r.data["broker_state"] == "OPEN"
    assert platform.store.get_approval(ap.approval_id).status == "consumed"
    # fill through the gateway too
    order_id = r.data["order_id"]
    fr = orchestration.process_event_via_gateway(ctx, order_id=order_id, market=fixtures.VALID_TIGHT)
    assert fr.outcome_class == ToolOutcomeClass.SUCCESS_CONFIRMED and fr.data["filled"] is True


def test_gateway_reused_approval_blocked(tmp_path, monkeypatch):
    from saathi.platform.paper_trading import orchestration
    from saathi.tool_runtime.contracts import ToolOutcomeClass
    platform, svc = _wire_gateway(tmp_path, monkeypatch)
    ctx = _ctx()
    a = _acct(svc, ctx)
    ap = _approval(platform)
    i1 = _buy(svc, ctx, a, qty="50")
    orchestration.submit_via_gateway(ctx, intent_id=i1["intent_id"], market=fixtures.VALID_TIGHT,
                                     approval_id=ap.approval_id, expires_at=ap.expires_at)
    i2 = _buy(svc, ctx, a, qty="50")
    r2 = orchestration.submit_via_gateway(ctx, intent_id=i2["intent_id"], market=fixtures.VALID_TIGHT,
                                          approval_id=ap.approval_id, expires_at=ap.expires_at)
    assert r2.outcome_class != ToolOutcomeClass.SUCCESS_CONFIRMED
    assert svc.store.get_order_by_idempotency(ctx.org_id, i2["idempotency_key"]) is None


def test_gateway_cross_tenant_approval_rejected(tmp_path, monkeypatch):
    from saathi.platform.paper_trading import orchestration
    from saathi.tool_runtime.contracts import ToolOutcomeClass
    platform, svc = _wire_gateway(tmp_path, monkeypatch)
    ctx = _ctx(org="orgA")
    a = _acct(svc, ctx)
    ap = _approval(platform, org="orgB")  # approval belongs to a different tenant
    i = _buy(svc, ctx, a, qty="50")
    r = orchestration.submit_via_gateway(ctx, intent_id=i["intent_id"], market=fixtures.VALID_TIGHT,
                                         approval_id=ap.approval_id, expires_at=ap.expires_at)
    assert r.outcome_class != ToolOutcomeClass.SUCCESS_CONFIRMED
    assert svc.store.list_orders("orgA", account_id=a["id"]) == []


def test_gateway_missing_approval_blocked(tmp_path, monkeypatch):
    from saathi.platform.paper_trading import orchestration
    from saathi.tool_runtime.contracts import ToolOutcomeClass
    platform, svc = _wire_gateway(tmp_path, monkeypatch)
    ctx = _ctx()
    a = _acct(svc, ctx)
    i = _buy(svc, ctx, a, qty="50")
    r = orchestration.submit_via_gateway(ctx, intent_id=i["intent_id"], market=fixtures.VALID_TIGHT)  # no approval
    assert r.outcome_class != ToolOutcomeClass.SUCCESS_CONFIRMED


# ══════════════════════════════ HTTP CONTRACT ═══════════════════════════════
def test_http_paper_lifecycle(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from saathi.tool_runtime.contracts import ToolOutcomeClass  # noqa
    platform, svc = _wire_gateway(tmp_path, monkeypatch)
    owner = platform.bootstrap_owner_secure(email="o@m625.local", name="O", password="OwnerPassw0rd!",
                                            org_name="Org", workspace_name="WS")
    from saathi.server import app
    client = TestClient(app)
    h = {"X-Platform-Token": owner["token"]}
    assert client.get("/api/v1/platform/paper/accounts").status_code == 401  # unauth
    acct = client.post("/api/v1/platform/paper/accounts", json={"starting_cash": "100000"}, headers=h).json()["account"]
    intent = client.post("/api/v1/platform/paper/order-intents",
                         json={"account_id": acct["id"], "symbol": "TRENDING", "side": "BUY",
                               "order_type": "MARKET", "quantity": "5"}, headers=h).json()["intent"]
    # every gateway submission requires a server-owned approval (tool policy)
    ap = _approval(platform, org=acct["org_id"])
    sub = client.post(f"/api/v1/platform/paper/order-intents/{intent['intent_id']}/submit",
                      json={"market": fixtures.VALID_TIGHT, "approval_id": ap.approval_id}, headers=h)
    assert sub.status_code == 200, sub.text
    order_id = sub.json()["result"]["order_id"]
    proc = client.post(f"/api/v1/platform/paper/orders/{order_id}/process-event",
                       json={"market": fixtures.VALID_TIGHT}, headers=h)
    assert proc.status_code == 200 and proc.json()["result"]["filled"] is True
    assert client.get(f"/api/v1/platform/paper/orders/{order_id}/fills", headers=h).json()["fills"]
    assert client.get(f"/api/v1/platform/paper/accounts/{acct['id']}/positions", headers=h).json()["positions"]
    # NO live-environment / provider / credential fields accepted, NO order route outside /paper
    assert client.post("/api/v1/platform/orders", json={}, headers=h).status_code in (404, 405)
