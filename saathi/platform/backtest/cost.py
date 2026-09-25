"""Versioned deterministic simulation cost policies; no production authority."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


def _decimal(value: object, *, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field}") from exc
    if not result.is_finite():
        raise ValueError(f"invalid {field}")
    return result


@dataclass(frozen=True)
class CostEstimate:
    explicit_fee: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    total_cost: Decimal
    currency: str
    status: str
    policy_version: str


class CryptoCostModel:
    """Conservative public spot assumptions, never an account fee claim.

    ``spread_bps`` is retained separately so qualification can stress fees,
    spread and slippage independently. ``estimate`` still accepts the observed
    best price for compatibility with the certified BACKTEST-COST-1 boundary.
    """

    status = "CONFIGURED_CONSERVATIVE_ASSUMPTION"

    def __init__(
        self,
        fee_bps: object = "10",
        slippage_bps: object = "5",
        version: str = "crypto-spot-v1",
        spread_bps: object = "10",
    ) -> None:
        self.fee_bps = _decimal(fee_bps, field="fee_bps")
        self.spread_bps = _decimal(spread_bps, field="spread_bps")
        self.slippage_bps = _decimal(slippage_bps, field="slippage_bps")
        if min(self.fee_bps, self.spread_bps, self.slippage_bps) < 0:
            raise ValueError("invalid cost input")
        self.version = str(version)

    @property
    def is_zero(self) -> bool:
        return self.fee_bps + self.spread_bps + self.slippage_bps == 0

    def stress(self, multiple: object) -> "CryptoCostModel":
        factor = _decimal(multiple, field="stress")
        if factor < 0:
            raise ValueError("invalid stress")
        return self.with_multipliers(fee=factor, spread=factor, slippage=factor)

    def with_multipliers(
        self,
        *,
        fee: object = 1,
        spread: object = 1,
        slippage: object = 1,
        scenario: str = "stress",
    ) -> "CryptoCostModel":
        fee_factor = _decimal(fee, field="fee multiplier")
        spread_factor = _decimal(spread, field="spread multiplier")
        slippage_factor = _decimal(slippage, field="slippage multiplier")
        if min(fee_factor, spread_factor, slippage_factor) < 0:
            raise ValueError("invalid stress")
        suffix = f":{scenario}:f{fee_factor}:p{spread_factor}:s{slippage_factor}"
        return CryptoCostModel(
            fee_bps=self.fee_bps * fee_factor,
            spread_bps=self.spread_bps * spread_factor,
            slippage_bps=self.slippage_bps * slippage_factor,
            version=self.version + suffix,
        )

    def estimate(
        self,
        instrument: str,
        side: str,
        reference: object,
        best_price: object,
        quantity: object,
    ) -> CostEstimate:
        if side not in {"BUY", "SELL"}:
            raise ValueError("invalid side")
        ref = _decimal(reference, field="reference")
        price = _decimal(best_price, field="best_price")
        qty = _decimal(quantity, field="quantity")
        if min(ref, price, qty) < 0:
            raise ValueError("invalid cost input")
        spread = abs(price - ref) * qty
        fee = price * qty * self.fee_bps / Decimal("10000")
        slip = price * qty * self.slippage_bps / Decimal("10000")
        return CostEstimate(
            explicit_fee=fee,
            spread_cost=spread,
            slippage_cost=slip,
            total_cost=fee + spread + slip,
            currency="USDT",
            status=self.status,
            policy_version=self.version,
        )

    def quote(self, reference: object) -> tuple[Decimal, Decimal]:
        mid = _decimal(reference, field="reference")
        if mid <= 0:
            raise ValueError("invalid quote")
        half_spread = mid * self.spread_bps / Decimal("20000")
        return mid + half_spread, mid - half_spread

    def fill_price(self, side: str, ask: object, bid: object) -> Decimal:
        if side not in {"BUY", "SELL"}:
            raise ValueError("invalid side")
        ask_price = _decimal(ask, field="ask")
        bid_price = _decimal(bid, field="bid")
        if bid_price <= 0 or ask_price <= 0 or bid_price > ask_price:
            raise ValueError("invalid quote")
        price = ask_price if side == "BUY" else bid_price
        adjustment = price * self.slippage_bps / Decimal("10000")
        return price + adjustment if side == "BUY" else price - adjustment


class UnverifiedCostModel:
    def estimate(self):
        return type("Unavailable", (), {"status": "COST_MODEL_UNAVAILABLE"})()


class NepseCostModel:
    def estimate(self):
        return type("Unavailable", (), {"status": "NEPSE_COST_POLICY_UNVERIFIED"})()
