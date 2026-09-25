"""Venue-neutral instrument conventions for multi-market paper OMS convergence.

OMS-MULTI-MARKET-1. The existing paper OMS (matching / exchange / ledger) is kept
as the single canonical order path. This module adds the *venue-neutral contract*
both crypto and NEPSE conform to, so one OMS can accept both without branching its
core:

  * crypto (BTCUSDT / ETHUSDT ...): fractional quantity on a fixed step, 24/7, tick
    price, minimum notional-free min-qty.
  * NEPSE (NEPSE:*): WHOLE shares only, board-lot enforced, paisa price tick,
    session-bound (calendar handled elsewhere).
  * equity / unknown: permissive passthrough (preserves pre-existing behaviour).

Everything here is deterministic and side-effect free. It PROPOSES normalized
order terms and REJECTS invalid ones with stable reason codes; it never executes,
never touches the ledger, and never rounds a quantity *up* (no size inflation).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_EVEN
from enum import Enum


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    NEPSE_EQUITY = "nepse_equity"
    EQUITY = "equity"


class ConventionReason(str, Enum):
    OK = "OK"
    QTY_BELOW_MIN = "QTY_BELOW_MIN"
    QTY_NOT_WHOLE = "QTY_NOT_WHOLE"
    QTY_NOT_LOT_MULTIPLE = "QTY_NOT_LOT_MULTIPLE"
    QTY_ROUNDED_DOWN = "QTY_ROUNDED_DOWN"
    QTY_ZERO_AFTER_STEP = "QTY_ZERO_AFTER_STEP"
    PRICE_ROUNDED_TO_TICK = "PRICE_ROUNDED_TO_TICK"


@dataclass(frozen=True)
class InstrumentConvention:
    """Deterministic order-shaping rules for one instrument/venue."""

    asset_class: AssetClass
    quantity_step: Decimal      # smallest quantity increment
    min_quantity: Decimal       # reject below this (after step rounding)
    price_tick: Decimal         # smallest price increment (Decimal("0") = free)
    lot_size: Decimal           # order qty must be a multiple of this
    allow_fractional: bool
    is_247: bool

    @property
    def passthrough(self) -> bool:
        # Permissive equity default: no rounding, no rejection surface change.
        return (
            self.asset_class == AssetClass.EQUITY
            and self.quantity_step == 0
            and self.min_quantity == 0
            and self.price_tick == 0
            and self.lot_size == 0
        )


# Canonical profiles. Crypto values match the certified BTC/ETH SPOT dataset scope.
CRYPTO_CONVENTION = InstrumentConvention(
    asset_class=AssetClass.CRYPTO,
    quantity_step=Decimal("0.000001"),
    min_quantity=Decimal("0.000001"),
    price_tick=Decimal("0.01"),
    lot_size=Decimal("0"),           # no board lot on spot crypto
    allow_fractional=True,
    is_247=True,
)

NEPSE_CONVENTION = InstrumentConvention(
    asset_class=AssetClass.NEPSE_EQUITY,
    quantity_step=Decimal("1"),      # whole shares only
    min_quantity=Decimal("1"),
    price_tick=Decimal("0.10"),      # paisa tick (provisional; cost policy unverified)
    lot_size=Decimal("10"),          # NEPSE odd-lot boundary (provisional)
    allow_fractional=False,
    is_247=False,
)

EQUITY_PASSTHROUGH = InstrumentConvention(
    asset_class=AssetClass.EQUITY,
    quantity_step=Decimal("0"),
    min_quantity=Decimal("0"),
    price_tick=Decimal("0"),
    lot_size=Decimal("0"),
    allow_fractional=True,
    is_247=False,
)


def convention_for(symbol: str) -> InstrumentConvention:
    """Resolve the convention for a symbol. Mirrors TradingCalendar's routing so
    the OMS session view and the convention view never disagree on asset class."""
    sym = str(symbol or "").upper()
    if sym.endswith("USDT") or sym in ("BTC", "ETH"):
        return CRYPTO_CONVENTION
    if sym.startswith("NEPSE:"):
        return NEPSE_CONVENTION
    return EQUITY_PASSTHROUGH


@dataclass(frozen=True)
class NormalizedOrder:
    symbol: str
    quantity: Decimal
    price: Decimal | None
    accepted: bool
    reasons: tuple[str, ...]


def _dec(v) -> Decimal:
    if isinstance(v, Decimal):
        return v
    # str() first so float noise (0.1 -> 0.1000000000000000055) never leaks in.
    return Decimal(str(v))


def normalize_order(symbol: str, quantity, price=None) -> NormalizedOrder:
    """Return venue-normalized order terms + deterministic reason codes.

    Quantity is only ever rounded DOWN to the step (never inflated). NEPSE
    fractional or non-lot quantities are rejected outright rather than silently
    reshaped past the board-lot rule. Passthrough instruments are returned as-is.
    """
    conv = convention_for(symbol)
    reasons: list[str] = []
    qty = _dec(quantity)
    px = None if price is None else _dec(price)

    if conv.passthrough:
        return NormalizedOrder(str(symbol).upper(), qty, px, qty > 0, (ConventionReason.OK.value,))

    if qty <= 0:
        return NormalizedOrder(str(symbol).upper(), qty, px, False, (ConventionReason.QTY_BELOW_MIN.value,))

    # Whole-share instruments: a fractional request is a hard reject (no silent trunc).
    if not conv.allow_fractional and qty != qty.to_integral_value(rounding=ROUND_DOWN):
        return NormalizedOrder(str(symbol).upper(), qty, px, False, (ConventionReason.QTY_NOT_WHOLE.value,))

    # Round quantity DOWN to the step.
    norm_qty = qty
    if conv.quantity_step > 0:
        steps = (qty / conv.quantity_step).to_integral_value(rounding=ROUND_DOWN)
        norm_qty = steps * conv.quantity_step
        if norm_qty != qty:
            reasons.append(ConventionReason.QTY_ROUNDED_DOWN.value)

    if norm_qty <= 0:
        return NormalizedOrder(str(symbol).upper(), norm_qty, px, False, (ConventionReason.QTY_ZERO_AFTER_STEP.value,))

    if conv.min_quantity > 0 and norm_qty < conv.min_quantity:
        return NormalizedOrder(str(symbol).upper(), norm_qty, px, False, (ConventionReason.QTY_BELOW_MIN.value,))

    # Board-lot enforcement (reject, don't reshape).
    if conv.lot_size > 0 and (norm_qty % conv.lot_size) != 0:
        return NormalizedOrder(str(symbol).upper(), norm_qty, px, False, (ConventionReason.QTY_NOT_LOT_MULTIPLE.value,))

    # Price to tick (round to nearest even tick — display/limit hygiene, not truth).
    norm_px = px
    if px is not None and conv.price_tick > 0:
        ticks = (px / conv.price_tick).to_integral_value(rounding=ROUND_HALF_EVEN)
        norm_px = ticks * conv.price_tick
        if norm_px != px:
            reasons.append(ConventionReason.PRICE_ROUNDED_TO_TICK.value)

    if not reasons:
        reasons.append(ConventionReason.OK.value)
    return NormalizedOrder(str(symbol).upper(), norm_qty, norm_px, True, tuple(reasons))
