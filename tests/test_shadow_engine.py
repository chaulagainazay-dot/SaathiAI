"""SHADOW-1 — shadow engine invariants. The defining property: no order is sent."""
from decimal import Decimal

import pytest

from saathi.platform.backtest.cost import CryptoCostModel
from saathi.platform.tg.shadow_engine import (
    CryptoShadowEngine, NepseShadowEngine, ShadowStatus,
)
from saathi.platform.tg.paper_crypto_pipeline import (
    PaperCycleDecision, PaperCycleOutcome, PaperCycleStage, PlannedOrder,
)


def _ready_decision(qty="1", symbol="BTCUSDT"):
    return PaperCycleDecision(
        PaperCycleStage.EXECUTION_PLAN, PaperCycleOutcome.READY_FOR_EXECUTION_GATEWAY,
        (), candidate_status="CANDIDATE_ALLOCATION", risk_result="ALLOW",
        planned_orders=(PlannedOrder(
            instrument_id="BINANCE:BTC/USDT", symbol=symbol, venue="CRYPTO",
            target_weight=Decimal("0.1"), target_notional=Decimal("10000"),
            quantity=Decimal(qty),
        ),),
    )


def _guardian_blocked_decision():
    return PaperCycleDecision(
        PaperCycleStage.GUARDIAN_VENUE, PaperCycleOutcome.BLOCKED_GUARDIAN,
        ("VENUE_DISABLED",), candidate_status="CANDIDATE_ALLOCATION", risk_result="ALLOW",
    )


# ── the core invariant ───────────────────────────────────────────────────────────
def test_engine_has_no_execution_entrypoint():
    eng = CryptoShadowEngine()
    for banned in ("submit", "execute", "send_order", "place_order", "client"):
        assert not hasattr(eng, banned)


def test_orders_sent_is_always_zero():
    eng = CryptoShadowEngine()
    obs = eng.observe(_ready_decision(), {"BTCUSDT": "100"})
    assert obs.orders_sent == 0
    assert eng.summary()["orders_sent"] == 0
    assert eng.mark_to_market(obs, {"BTCUSDT": "110"})["orders_sent"] == 0


def test_hypothetical_order_costed_never_free():
    eng = CryptoShadowEngine()
    obs = eng.observe(_ready_decision(), {"BTCUSDT": "100"})
    o = obs.orders[0]
    assert o.total_cost > 0
    assert o.fee > 0 and o.slippage_cost > 0
    assert o.estimated_fill_price > o.reference_price  # BUY pays the ask + slippage


def test_zero_cost_model_refused():
    with pytest.raises(ValueError):
        CryptoShadowEngine(cost_model=CryptoCostModel(fee_bps="0", slippage_bps="0", spread_bps="0"))


def test_guardian_block_recorded_with_no_orders():
    eng = CryptoShadowEngine()
    obs = eng.observe(_guardian_blocked_decision(), {"BTCUSDT": "100"})
    assert obs.guardian_blocked is True
    assert obs.orders == ()
    assert eng.summary()["guardian_blocks"] == 1


def test_forward_pnl_is_net_of_costs():
    eng = CryptoShadowEngine()
    obs = eng.observe(_ready_decision(qty="1"), {"BTCUSDT": "100"})
    mark = eng.mark_to_market(obs, {"BTCUSDT": "110"})
    assert mark["gross_pnl"] > 0
    assert mark["cost_drag"] > 0
    assert mark["net_pnl"] == mark["gross_pnl"] - mark["cost_drag"]


def test_summary_tracks_drawdown():
    eng = CryptoShadowEngine()
    o1 = eng.observe(_ready_decision(), {"BTCUSDT": "100"})
    m1 = eng.mark_to_market(o1, {"BTCUSDT": "120"})   # up
    o2 = eng.observe(_ready_decision(), {"BTCUSDT": "100"})
    m2 = eng.mark_to_market(o2, {"BTCUSDT": "80"})    # down
    s = eng.summary([m1, m2])
    assert s["cycles"] == 2
    assert s["max_drawdown"] > 0
    assert s["cost_policy_version"] == "crypto-spot-v1"


# ── NEPSE: honest blocker, never a faked live shadow ─────────────────────────────
def test_nepse_shadow_is_license_blocked_not_faked():
    eng = NepseShadowEngine()
    assert eng.status == ShadowStatus.BLOCKED_EXTERNAL_LICENSE
    out = eng.observe()
    assert out["verdict"] == "NEPSE_SHADOW_ARCHITECTURE_READY_LIVE_FEED_BLOCKED_LICENSE"
    assert out["observations"] == []
    assert out["orders_sent"] == 0
