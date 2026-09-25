"""SHADOW-1 — shadow execution engine (no order is ever sent).

Shadow runs the whole decision chain — observation, strategy, signal, intent,
construction, risk, Guardian, approval logic — and then measures what WOULD have
happened: hypothetical allocation, hypothetical order, reference price, estimated
fill, fees, spread, slippage, forward PnL, drawdown, and Guardian blocks.

The defining invariant: NO ORDER IS SENT. This module has no submit/execute entry
point and no venue client; `orders_sent` is structurally always 0.

NEPSE shadow deliberately does NOT fake a live run: without a licensed real-time
feed its honest state is NEPSE_SHADOW_ARCHITECTURE_READY_LIVE_FEED_BLOCKED_LICENSE.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from saathi.platform.backtest.cost import CryptoCostModel


class ShadowMarket(str, Enum):
    CRYPTO = "CRYPTO"
    NEPSE = "NEPSE"


class ShadowStatus(str, Enum):
    ACTIVE = "ACTIVE"
    BLOCKED_EXTERNAL_LICENSE = "BLOCKED_EXTERNAL_LICENSE"


@dataclass(frozen=True)
class ShadowOrder:
    symbol: str
    side: str
    quantity: Decimal
    reference_price: Decimal
    estimated_fill_price: Decimal
    fee: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    total_cost: Decimal
    notional: Decimal


@dataclass
class ShadowObservation:
    cycle: int
    outcome: str
    guardian_blocked: bool
    orders: tuple[ShadowOrder, ...] = ()
    reason_codes: tuple[str, ...] = ()
    # structural: a shadow observation can never carry a sent order
    orders_sent: int = field(default=0, init=False)


class NepseShadowEngine:
    """NEPSE shadow — architecture ready, live feed blocked by licensing."""

    market = ShadowMarket.NEPSE
    status = ShadowStatus.BLOCKED_EXTERNAL_LICENSE
    verdict = "NEPSE_SHADOW_ARCHITECTURE_READY_LIVE_FEED_BLOCKED_LICENSE"

    def observe(self, *_args, **_kwargs) -> dict:
        """Refuse to fabricate a live shadow run without a licensed feed."""
        return {
            "market": self.market.value,
            "status": self.status.value,
            "verdict": self.verdict,
            "observations": [],
            "orders_sent": 0,
            "detail": "licensed NEPSE real-time feed is an external dependency",
        }


class CryptoShadowEngine:
    """Crypto shadow — measures hypothetical execution against real cost policy."""

    market = ShadowMarket.CRYPTO
    status = ShadowStatus.ACTIVE

    def __init__(self, cost_model: CryptoCostModel | None = None) -> None:
        self.cost = cost_model or CryptoCostModel()
        if self.cost.is_zero:
            # NO_ZERO_COST_FALLBACK: a costless shadow would flatter every strategy.
            raise ValueError("shadow requires a non-zero cost model")
        self._observations: list[ShadowObservation] = []
        self._cycle = 0

    # No submit/execute/send method exists on purpose.

    def observe(self, decision, price_map: dict) -> ShadowObservation:
        """Record one shadow cycle from a PaperCycleDecision (never executes)."""
        self._cycle += 1
        outcome = getattr(decision.outcome, "value", str(decision.outcome))
        guardian_blocked = "GUARDIAN" in outcome

        orders: list[ShadowOrder] = []
        if getattr(decision, "ready", False):
            for planned in decision.planned_orders:
                ref = price_map.get(planned.symbol)
                if ref is None or planned.quantity is None:
                    continue
                ref_price = Decimal(str(ref))
                ask, bid = self.cost.quote(ref_price)
                fill = self.cost.fill_price("BUY", ask, bid)
                est = self.cost.estimate(
                    planned.symbol, "BUY", ref_price, fill, planned.quantity
                )
                orders.append(ShadowOrder(
                    symbol=planned.symbol, side="BUY", quantity=planned.quantity,
                    reference_price=ref_price, estimated_fill_price=fill,
                    fee=est.explicit_fee, spread_cost=est.spread_cost,
                    slippage_cost=est.slippage_cost, total_cost=est.total_cost,
                    notional=planned.quantity * fill,
                ))

        obs = ShadowObservation(
            cycle=self._cycle, outcome=outcome, guardian_blocked=guardian_blocked,
            orders=tuple(orders), reason_codes=tuple(decision.reason_codes),
        )
        self._observations.append(obs)
        return obs

    def mark_to_market(self, observation: ShadowObservation, future_price_map: dict) -> dict:
        """Forward-path PnL for one observation, net of the costs it would have paid."""
        gross = Decimal("0")
        costs = Decimal("0")
        for o in observation.orders:
            future = future_price_map.get(o.symbol)
            if future is None:
                continue
            gross += (Decimal(str(future)) - o.estimated_fill_price) * o.quantity
            costs += o.total_cost
        return {
            "cycle": observation.cycle,
            "gross_pnl": gross,
            "cost_drag": costs,
            "net_pnl": gross - costs,
            "orders_sent": 0,
        }

    def summary(self, marks: list[dict] | None = None) -> dict:
        marks = marks or []
        net = [m["net_pnl"] for m in marks]
        cumulative = Decimal("0")
        peak = Decimal("0")
        max_dd = Decimal("0")
        for n in net:
            cumulative += n
            peak = max(peak, cumulative)
            max_dd = max(max_dd, peak - cumulative)
        return {
            "market": self.market.value,
            "status": self.status.value,
            "cycles": len(self._observations),
            "guardian_blocks": sum(1 for o in self._observations if o.guardian_blocked),
            "hypothetical_net_pnl": cumulative,
            "max_drawdown": max_dd,
            "total_cost_drag": sum((m["cost_drag"] for m in marks), Decimal("0")),
            "orders_sent": 0,
            "cost_policy_version": self.cost.version,
        }
