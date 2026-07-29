"""Deterministic paper order simulator.

Simulates MARKET, LIMIT, STOP, STOP_LIMIT with IOC/FOK, partial fills,
gap opens, slippage, fees, liquidity caps. No exchange communication.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any

from saathi.platform.tg.paper_activation.models import (
    D,
    RiskLimits,
    SimOrder,
    SimOrderStatus,
    SimOrderType,
    SimTimeInForce,
)


@dataclass
class MarketTick:
    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume: Decimal = Decimal("1000000")
    gap_open: bool = False
    quality: str = "VALID"
    market_open: bool = True
    ts: float = 0.0
    liquidity_available: Decimal | None = None

    def __post_init__(self) -> None:
        self.bid = D(self.bid)
        self.ask = D(self.ask)
        self.last = D(self.last)
        self.volume = D(self.volume)
        if self.liquidity_available is not None:
            self.liquidity_available = D(self.liquidity_available)


class OrderSimulator:
    """Stateless fill engine for paper orders. Deterministic given same inputs."""

    def __init__(self, limits: RiskLimits | None = None, *, seed: int = 0):
        self.limits = limits or RiskLimits()
        self.seed = seed

    def _fee(self, qty: Decimal, price: Decimal) -> Decimal:
        notional = qty * price
        fee = notional * (self.limits.fee_bps / Decimal("10000"))
        return max(fee, Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    def _slip_price(self, side: str, ref: Decimal) -> Decimal:
        slip = ref * (self.limits.slippage_bps / Decimal("10000"))
        spread = ref * (self.limits.spread_bps / Decimal("10000"))
        adverse = slip + spread / Decimal("2")
        if side.upper() == "BUY":
            return (ref + adverse).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
        return (ref - adverse).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)

    def _liquidity_cap(self, tick: MarketTick) -> Decimal:
        if tick.liquidity_available is not None:
            return max(tick.liquidity_available, Decimal("0"))
        # max 25% of volume participation
        return max(tick.volume * Decimal("0.25"), Decimal("0"))

    def try_fill(self, order: SimOrder, tick: MarketTick) -> dict[str, Any]:
        """Attempt to fill order against tick. Mutates order. Returns result dict."""
        if order.status in (
            SimOrderStatus.FILLED, SimOrderStatus.CANCELLED,
            SimOrderStatus.REJECTED, SimOrderStatus.EXPIRED,
        ):
            return {"filled": False, "reason": f"terminal:{order.status.value}"}

        if tick.symbol != order.symbol:
            return {"filled": False, "reason": "symbol_mismatch"}
        if not tick.market_open:
            return {"filled": False, "reason": "market_closed"}
        if tick.quality not in ("VALID", "OK", ""):
            order.status = SimOrderStatus.REJECTED
            order.reject_reason = f"stale_or_invalid_quality:{tick.quality}"
            return {"filled": False, "reason": order.reject_reason}

        side = order.side.upper()
        remaining = order.remaining
        if remaining <= 0:
            order.status = SimOrderStatus.FILLED
            return {"filled": False, "reason": "nothing_remaining"}

        # Stop trigger check
        triggered = True
        if order.order_type in (SimOrderType.STOP, SimOrderType.STOP_LIMIT):
            if order.stop_price is None:
                order.status = SimOrderStatus.REJECTED
                order.reject_reason = "stop_requires_stop_price"
                return {"filled": False, "reason": order.reject_reason}
            sp = D(order.stop_price)
            if side == "BUY":
                triggered = tick.ask >= sp or tick.last >= sp
            else:
                triggered = tick.bid <= sp or tick.last <= sp
            if not triggered:
                order.status = SimOrderStatus.OPEN
                return {"filled": False, "reason": "stop_not_triggered"}

        # Reference price
        if order.order_type == SimOrderType.MARKET or (
            order.order_type == SimOrderType.STOP and order.limit_price is None
        ):
            ref = tick.ask if side == "BUY" else tick.bid
            # gap open: worse fill
            if tick.gap_open:
                gap = abs(tick.last - ((tick.bid + tick.ask) / 2)) * Decimal("0.5")
                ref = ref + gap if side == "BUY" else ref - gap
            px = self._slip_price(side, ref)
            eligible = True
        elif order.order_type in (SimOrderType.LIMIT, SimOrderType.STOP_LIMIT):
            if order.limit_price is None:
                order.status = SimOrderStatus.REJECTED
                order.reject_reason = "limit_requires_limit_price"
                return {"filled": False, "reason": order.reject_reason}
            lim = D(order.limit_price)
            if side == "BUY":
                eligible = tick.ask <= lim
                ref = min(tick.ask, lim)
            else:
                eligible = tick.bid >= lim
                ref = max(tick.bid, lim)
            px = self._slip_price(side, ref)
            # never fill through limit adversely beyond limit
            if side == "BUY" and px > lim:
                px = lim
            if side == "SELL" and px < lim:
                px = lim
        else:
            order.status = SimOrderStatus.REJECTED
            order.reject_reason = f"unsupported_type:{order.order_type.value}"
            return {"filled": False, "reason": order.reject_reason}

        if not eligible:
            order.status = SimOrderStatus.OPEN
            if order.tif == SimTimeInForce.IOC:
                order.status = SimOrderStatus.CANCELLED
                order.reject_reason = "ioc_no_liquidity"
            elif order.tif == SimTimeInForce.FOK:
                order.status = SimOrderStatus.CANCELLED
                order.reject_reason = "fok_not_fully_fillable"
            return {"filled": False, "reason": "price_not_marketable"}

        liq = self._liquidity_cap(tick)
        fill_qty = min(remaining, liq)
        if fill_qty <= 0:
            if order.tif in (SimTimeInForce.IOC, SimTimeInForce.FOK):
                order.status = SimOrderStatus.CANCELLED
                order.reject_reason = "no_liquidity"
            else:
                order.status = SimOrderStatus.OPEN
            return {"filled": False, "reason": "no_liquidity"}

        if order.tif == SimTimeInForce.FOK and fill_qty < remaining:
            order.status = SimOrderStatus.CANCELLED
            order.reject_reason = "fok_partial_not_allowed"
            return {"filled": False, "reason": order.reject_reason}

        fee = self._fee(fill_qty, px)
        slip_amt = abs(px - (tick.ask if side == "BUY" else tick.bid)) * fill_qty

        # update averages
        prev_filled = order.filled_qty
        new_filled = prev_filled + fill_qty
        if new_filled > 0:
            order.avg_fill_price = (
                (order.avg_fill_price * prev_filled + px * fill_qty) / new_filled
            ).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
        order.filled_qty = new_filled
        order.fees += fee
        order.slippage += slip_amt
        order.updated_at = tick.ts or order.updated_at
        fill_rec = {
            "qty": str(fill_qty),
            "price": str(px),
            "fee": str(fee),
            "slippage": str(slip_amt),
            "ts": tick.ts,
            "gap_open": tick.gap_open,
            "paper_only": True,
        }
        order.fills.append(fill_rec)

        if order.remaining <= 0:
            order.status = SimOrderStatus.FILLED
        elif order.tif == SimTimeInForce.IOC:
            order.status = SimOrderStatus.CANCELLED  # remainder cancelled
            order.reject_reason = "ioc_remainder_cancelled"
        else:
            order.status = SimOrderStatus.PARTIALLY_FILLED

        return {
            "filled": True,
            "qty": str(fill_qty),
            "price": str(px),
            "fee": str(fee),
            "status": order.status.value,
            "paper_only": True,
            "exchange_connected": False,
        }

    def reject(self, order: SimOrder, reason: str) -> SimOrder:
        order.status = SimOrderStatus.REJECTED
        order.reject_reason = reason
        return order
