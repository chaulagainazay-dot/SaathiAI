"""M62.4 — deterministic position sizing.

Turns a signal into a target quantity, bounded by the strategy's risk cap. Sizing
NEVER produces leverage: EQUITY_FRACTION is clamped to ``max_position_fraction``
(<= 1), and a request above the cap is flagged so validation can reject a strategy
that depends on leverage it is not authorized to use.
"""
from __future__ import annotations

from decimal import Decimal

from saathi.platform.strategy.models import SizingRule, SizingMethod, D


class SizingError(Exception):
    pass


def target_quantity(
    rule: SizingRule,
    *,
    equity: Decimal,
    price: Decimal,
    quantity_precision: int,
    risk_max_fraction: Decimal,
) -> Decimal:
    """Compute a non-negative target LONG quantity. Raises SizingError on an
    unbounded / leverage-seeking request (fraction > 1 or > risk cap)."""
    if price <= 0:
        raise SizingError("non-positive price")
    cap = min(D(rule.max_position_fraction), D(risk_max_fraction))
    if cap > Decimal("1"):
        raise SizingError(f"position fraction {cap} exceeds 1.0 (leverage not authorized)")

    if rule.method == SizingMethod.FIXED_QUANTITY:
        qty = D(rule.value)
        if qty < 0:
            raise SizingError("negative fixed quantity")
        # even fixed quantity may not exceed the equity cap in notional
        max_notional = equity * cap
        if qty * price > max_notional:
            qty = (max_notional / price)
    elif rule.method == SizingMethod.EQUITY_FRACTION:
        frac = D(rule.value)
        if frac < 0:
            raise SizingError("negative equity fraction")
        if frac > cap:
            raise SizingError(f"requested fraction {frac} exceeds risk cap {cap} (leverage)")
        qty = (equity * frac) / price
    else:
        raise SizingError(f"unknown sizing method {rule.method}")

    # floor to quantity precision, deterministic
    if quantity_precision <= 0:
        return Decimal(int(qty))
    step = Decimal(1).scaleb(-quantity_precision)
    return (qty // step) * step
