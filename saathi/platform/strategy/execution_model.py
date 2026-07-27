"""M62.4 — deterministic simulated execution (fill) model.

Fill assumptions (documented, conservative — see docs/trading/TRANSACTION_COSTS.md):

* NEXT-BAR fill. A signal generated on the decision bar's close fills on the NEXT
  bar. This structurally forbids same-bar hindsight (you cannot trade on a close you
  are simultaneously "deciding" at).
* MARKET orders fill at the next bar's OPEN, adjusted by slippage AGAINST the trader
  (buys pay up, sells receive less).
* LIMIT orders fill only if the next bar trades through the limit: BUY fills when
  next.low <= limit (fill at min(limit, open)); SELL fills when next.high >= limit.
  Ambiguous intra-bar ordering is resolved conservatively; never the favourable path.
* Volume participation caps quantity to ``max_volume_participation * bar.volume``
  (partial fill). Insufficient liquidity => PARTIAL or REJECTED.

The model returns pure data; it never mutates accounts or reaches a broker.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.market_data.models import MDBar
from saathi.platform.strategy.models import (
    CostModel, SimulatedOrder, SimOrderStatus, D, q2,
)

_BPS = Decimal("10000")


def compute_fees(cost: CostModel, quantity: Decimal, price: Decimal) -> Decimal:
    notional = abs(quantity * price)
    fee = D(cost.fixed_fee) + notional * D(cost.pct_fee) + abs(quantity) * D(cost.per_unit_fee)
    if fee < D(cost.min_fee) and quantity != 0:
        fee = D(cost.min_fee)
    return q2(fee)


def apply_slippage(cost: CostModel, side: str, ref_price: Decimal, bar: MDBar) -> tuple[Decimal, Decimal]:
    """Return (fill_price, slippage_per_unit). Slippage is always adverse."""
    slip = ref_price * (D(cost.slippage_bps) / _BPS)
    if cost.spread_slippage:
        # half-spread proxy from the bar range (deterministic, bounded)
        slip += (bar.high - bar.low) / Decimal("4")
    if side == "BUY":
        return (ref_price + slip, slip)
    return (ref_price - slip, slip)


def simulate_fill(
    *,
    seq: int,
    side: str,
    order_type: str,
    quantity: Decimal,
    decision_bar: MDBar,
    fill_bar: MDBar,
    cost: CostModel,
    limit_price: Decimal | None = None,
    signal_ref: str = "",
) -> SimulatedOrder:
    """Simulate a single order against the FILL bar (the bar AFTER the decision bar)."""
    ref = fill_bar.open
    reject = ""
    status = SimOrderStatus.FILLED
    qty = D(quantity)

    if qty <= 0:
        return _order(seq, decision_bar, fill_bar, side, order_type, Decimal("0"), ref, ref,
                      Decimal("0"), Decimal("0"), SimOrderStatus.REJECTED, signal_ref, "non-positive quantity")

    # LIMIT executability
    if order_type == "LIMIT":
        if limit_price is None or limit_price <= 0:
            return _order(seq, decision_bar, fill_bar, side, order_type, qty, ref, ref,
                          Decimal("0"), Decimal("0"), SimOrderStatus.REJECTED, signal_ref, "invalid limit price")
        if side == "BUY":
            if fill_bar.low > limit_price:
                return _order(seq, decision_bar, fill_bar, side, order_type, qty, limit_price, limit_price,
                              Decimal("0"), Decimal("0"), SimOrderStatus.REJECTED, signal_ref, "limit not reached")
            ref = min(limit_price, fill_bar.open)
        else:
            if fill_bar.high < limit_price:
                return _order(seq, decision_bar, fill_bar, side, order_type, qty, limit_price, limit_price,
                              Decimal("0"), Decimal("0"), SimOrderStatus.REJECTED, signal_ref, "limit not reached")
            ref = max(limit_price, fill_bar.open)

    fill_price, slip = apply_slippage(cost, side, ref, fill_bar)

    # volume participation cap => partial fill
    cap = D(cost.max_volume_participation) * D(fill_bar.volume)
    if cap > 0 and qty > cap:
        qty = cap
        status = SimOrderStatus.PARTIAL
        reject = "capped by volume participation"

    fees = compute_fees(cost, qty, fill_price)
    return _order(seq, decision_bar, fill_bar, side, order_type, qty, ref, fill_price,
                  fees, q2(slip), status, signal_ref, reject)


def _order(seq, dbar, fbar, side, otype, qty, ref, fill, fees, slip, status, sref, reason) -> SimulatedOrder:
    return SimulatedOrder(
        seq=seq, decision_epoch=dbar.start_time.timestamp(), fill_epoch=fbar.start_time.timestamp(),
        instrument=fbar.instrument, side=side, order_type=otype, quantity=q2(qty) if qty else Decimal("0"),
        reference_price=q2(ref), fill_price=q2(fill), fees=fees, slippage=slip, status=status,
        signal_ref=sref, reject_reason=reason,
    )
