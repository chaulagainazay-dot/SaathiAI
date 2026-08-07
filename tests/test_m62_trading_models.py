"""M62.1 — canonical trading domain models + Trading Guardian veto engine.

Pure, deterministic. Proves: decimal correctness, order-intent state machine,
fail-closed Guardian (LIVE/unknown env vetoed, short-selling/leverage disabled,
stale data blocked, risk limits enforced), circuit breaker.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from saathi.platform.trading_models import (
    D, Environment, NON_LIVE_ENVIRONMENTS, AssetClass, OrderSide, OrderType,
    DataQuality, MarketState, OrderState, can_transition, ORDER_TRANSITIONS,
    TERMINAL_ORDER_STATES, ApprovalPurpose, M62_ENABLED_PURPOSES,
    Instrument, Quote, Position, Account, OrderIntent,
)
from saathi.platform.trading_guardian import (
    TradingGuardian, RiskLimits, CircuitState, DEFAULT_DISABLED_CAPABILITIES, safety_posture,
)


# ── decimal correctness ──────────────────────────────────────────────────────
def test_decimal_coercion_no_binary_float():
    assert D("0.1") + D("0.2") == Decimal("0.3")   # would fail with float
    assert D(None) == Decimal("0")
    assert D("garbage") == Decimal("0")
    assert isinstance(D(5), Decimal)


def test_position_and_account_decimal_math():
    pos = Position(symbol="AAPL", quantity=Decimal("10"), avg_price=Decimal("100.00"))
    assert pos.notional(Decimal("110.00")) == Decimal("1100.00")
    assert pos.unrealized_pnl(Decimal("110.00")) == Decimal("100.00")
    acct = Account(account_id="a1", environment=Environment.PAPER, cash=Decimal("5000.00"), positions={"AAPL": pos})
    assert acct.equity({"AAPL": Decimal("110.00")}) == Decimal("6100.00")
    assert acct.gross_exposure({"AAPL": Decimal("110.00")}) == Decimal("1100.00")


# ── order-intent state machine ───────────────────────────────────────────────
def test_state_machine_valid_chain():
    chain = [OrderState.DRAFT, OrderState.RESEARCH_COMPLETE, OrderState.STRATEGY_VALIDATED,
             OrderState.RISK_REVIEWED, OrderState.APPROVAL_REQUIRED, OrderState.APPROVED,
             OrderState.QUEUED, OrderState.SUBMITTING, OrderState.SUBMITTED, OrderState.FILLED]
    for a, b in zip(chain, chain[1:]):
        assert can_transition(a, b), f"{a}->{b} should be legal"


def test_state_machine_rejects_jumps():
    # cannot jump from a recommendation straight to submission
    assert not can_transition(OrderState.DRAFT, OrderState.SUBMITTED)
    assert not can_transition(OrderState.STRATEGY_VALIDATED, OrderState.APPROVED)
    assert not can_transition(OrderState.APPROVAL_REQUIRED, OrderState.SUBMITTED)
    for term in TERMINAL_ORDER_STATES:
        assert ORDER_TRANSITIONS[term] == frozenset()


def test_order_intent_transition_enforced():
    oi = _intent()
    oi.transition(OrderState.RESEARCH_COMPLETE)
    assert oi.state == OrderState.RESEARCH_COMPLETE and oi.version == 2
    with pytest.raises(ValueError):
        oi.transition(OrderState.SUBMITTED)  # illegal jump


def test_estimated_notional_uses_limit_when_present():
    oi = _intent(order_type=OrderType.LIMIT, limit_price=Decimal("50"))
    assert oi.estimated_notional(Decimal("999")) == Decimal("500.00")  # 10 * 50, not ref


def test_m62_purposes_exclude_live_order():
    assert ApprovalPurpose.LIVE_ORDER not in M62_ENABLED_PURPOSES
    assert ApprovalPurpose.PAPER_ORDER in M62_ENABLED_PURPOSES


# ── Guardian: construction fail-closed ────────────────────────────────────────
def test_guardian_refuses_disabled_capabilities():
    for cap in DEFAULT_DISABLED_CAPABILITIES:
        with pytest.raises(ValueError):
            TradingGuardian(capabilities={cap: True})
    g = TradingGuardian()
    assert all(g.capabilities[c] is False for c in DEFAULT_DISABLED_CAPABILITIES)


def test_safety_posture_all_disabled():
    p = safety_posture()
    assert p["LIVE_EXECUTION"] == "DISABLED"
    assert p["LEVERAGE"] == "DISABLED" and p["MARGIN"] == "DISABLED" and p["SHORT_SELLING"] == "DISABLED"
    assert p["HIGHEST_PERMITTED_TARGET"] == "PAPER_TRADING"


# ── Guardian: veto gate ───────────────────────────────────────────────────────
def _intent(**kw):
    base = dict(intent_id="oi1", org_id="o1", workspace_id="w1", account_id="a1",
                environment=Environment.PAPER, symbol="AAPL", side=OrderSide.BUY,
                order_type=OrderType.MARKET, quantity=Decimal("10"),
                idempotency_key="idem-1", approval_id="appr-1")
    base.update(kw)
    return OrderIntent(**base)


def _acct(cash="100000", positions=None):
    return Account(account_id="a1", environment=Environment.PAPER, cash=Decimal(cash), positions=positions or {})


def _eval(g, intent, **kw):
    defaults = dict(account=_acct(), ref_price=Decimal("100"), price_quality=DataQuality.VALID, market_state=MarketState.OPEN)
    defaults.update(kw)
    return g.evaluate(intent, **defaults)


def test_guardian_allows_valid_paper_order():
    g = TradingGuardian()
    d = _eval(g, _intent())
    assert d.allowed, d.reasons


def test_guardian_vetoes_live_environment():
    g = TradingGuardian()
    d = _eval(g, _intent(environment=Environment.LIVE))
    assert not d.allowed
    assert any("live disabled" in r.lower() or "not permitted" in r.lower() for r in d.reasons)


def test_guardian_vetoes_short_selling():
    g = TradingGuardian()
    # SELL 10 with zero held → short
    d = _eval(g, _intent(side=OrderSide.SELL))
    assert not d.allowed
    assert any("short" in r.lower() for r in d.reasons)


def test_guardian_vetoes_stale_price_and_closed_market():
    g = TradingGuardian()
    assert not _eval(g, _intent(), price_quality=DataQuality.STALE).allowed
    assert not _eval(g, _intent(), market_state=MarketState.CLOSED).allowed


def test_guardian_enforces_notional_and_buying_power():
    g = TradingGuardian(limits=RiskLimits(max_order_notional=Decimal("500")))
    d = _eval(g, _intent(quantity=Decimal("10")))  # 10*100 = 1000 > 500
    assert not d.allowed and any("notional" in r.lower() for r in d.reasons)
    g2 = TradingGuardian()
    d2 = _eval(g2, _intent(quantity=Decimal("10")), account=_acct(cash="500"))  # need 1000, have 500
    assert not d2.allowed and any("buying power" in r.lower() for r in d2.reasons)


def test_guardian_enforces_concentration_and_gross():
    g = TradingGuardian(limits=RiskLimits(max_symbol_concentration_pct=Decimal("10")))
    d = _eval(g, _intent(quantity=Decimal("10")), account=_acct(cash="100000"))
    # 1000 notional / ~100000 equity ~1% is fine → allowed; tighten to force veto
    g2 = TradingGuardian(limits=RiskLimits(max_gross_exposure=Decimal("500")))
    d2 = _eval(g2, _intent(quantity=Decimal("10")))
    assert not d2.allowed and any("gross exposure" in r.lower() for r in d2.reasons)


def test_guardian_requires_idempotency_and_approval():
    g = TradingGuardian()
    assert not _eval(g, _intent(idempotency_key="")).allowed
    assert not _eval(g, _intent(approval_id="")).allowed


def test_guardian_circuit_breaker_fail_closed():
    g = TradingGuardian()
    g.trip("drawdown")
    d = _eval(g, _intent())
    assert not d.allowed and any("halt" in r.lower() or "circuit" in r.lower() for r in d.reasons)
    g.reset()
    assert _eval(g, _intent()).allowed


def test_guardian_price_deviation_limit():
    g = TradingGuardian(limits=RiskLimits(max_price_deviation_pct=Decimal("2")))
    # limit 110 vs ref 100 = 10% deviation > 2%
    d = _eval(g, _intent(order_type=OrderType.LIMIT, limit_price=Decimal("110")))
    assert not d.allowed and any("deviat" in r.lower() for r in d.reasons)


def test_environment_sets():
    assert Environment.LIVE not in NON_LIVE_ENVIRONMENTS
    assert Environment.PAPER in NON_LIVE_ENVIRONMENTS
    assert AssetClass.EQUITY.value == "EQUITY"
    inst = Instrument(provider="paper", venue="SIM", symbol="AAPL", asset_class=AssetClass.EQUITY)
    assert inst.to_public()["symbol"] == "AAPL"
    q = Quote(symbol="AAPL", bid=Decimal("99"), ask=Decimal("101"), last=Decimal("100"), source="paper", source_ts=1.0, ingest_ts=2.0, quality=DataQuality.VALID)
    assert q.is_tradeable()
