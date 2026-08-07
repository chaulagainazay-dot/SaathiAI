"""Deterministic money / quantity representation (no binary float accounting)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any

# Default scales (Decimal quantize exponents)
MONEY_SCALE = Decimal("0.01")       # cash, NAV, fees, P&L display
PRICE_SCALE = Decimal("0.000001")   # prices
QTY_SCALE = Decimal("0.000001")     # share quantities
ROUNDING = ROUND_HALF_EVEN


class MoneyError(ValueError):
    """Invalid monetary operation (e.g. currency mix, bad input)."""


def D(value: Any, default: str = "0") -> Decimal:
    """Coerce to Decimal via str — never via binary float arithmetic."""
    try:
        if isinstance(value, Decimal):
            return value
        if value is None or value == "":
            return Decimal(default)
        if isinstance(value, float):
            # reject silent float contamination for money paths
            raise MoneyError(f"binary float not allowed for money: {value!r}")
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as e:
        if isinstance(e, MoneyError):
            raise
        raise MoneyError(f"invalid decimal: {value!r}") from e


def q_money(value: Any) -> Decimal:
    return D(value).quantize(MONEY_SCALE, rounding=ROUNDING)


def q_price(value: Any) -> Decimal:
    return D(value).quantize(PRICE_SCALE, rounding=ROUNDING)


def q_qty(value: Any) -> Decimal:
    return D(value).quantize(QTY_SCALE, rounding=ROUNDING)


class Money:
    """Currency-tagged amount. Never mix currencies without explicit conversion."""

    __slots__ = ("amount", "currency")

    def __init__(self, amount: Any, currency: str = "USD"):
        if not currency or not isinstance(currency, str):
            raise MoneyError("currency required")
        self.amount = q_money(amount)
        self.currency = currency.upper()

    def __add__(self, other: "Money") -> "Money":
        self._same_ccy(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same_ccy(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self.currency == other.currency and self.amount == other.amount

    def __repr__(self) -> str:
        return f"Money({self.amount}, {self.currency})"

    def _same_ccy(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise MoneyError("operand must be Money")
        if self.currency != other.currency:
            raise MoneyError(f"currency mismatch {self.currency} != {other.currency}")

    def to_public(self) -> dict:
        return {"amount": str(self.amount), "currency": self.currency}
