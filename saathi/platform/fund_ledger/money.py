"""Deterministic money / quantity representation (no binary float accounting)."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any

# Default scales (Decimal quantize exponents)
MONEY_SCALE = Decimal("0.01")       # cash, NAV, fees, P&L display
PRICE_SCALE = Decimal("0.000001")   # prices
QTY_SCALE = Decimal("0.000001")     # share quantities
ROUNDING = ROUND_HALF_EVEN


class MoneyError(ValueError):
    """Invalid monetary operation (e.g. currency mix, bad input)."""


# Longest input we will even attempt to parse. Decimal will happily consume a
# megabyte of digits; a financial parser reachable from provider and model output
# should not.
MAX_NUMERIC_CHARS = 128

# A financial string is a plain number: optional sign, digits, optional fraction,
# optional exponent. Decimal itself is far more permissive — it accepts PEP-515
# underscores ("1_000"), leading/trailing whitespace and special words — and this
# parser is reachable from provider and model output, where an unexpected accepted
# syntax is an unexpected accepted VALUE.
# \Z not $ — Python's $ also matches BEFORE a trailing newline, so "1\n" slipped
# through an otherwise strict pattern.
_NUMERIC_RE = re.compile(r"\A[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\Z")

# Beyond this magnitude a value is not money, it is an attack or a bug.
MAX_ADJUSTED_EXPONENT = 30


def _reject_non_finite(value: Decimal, original: Any) -> Decimal:
    """NaN and Infinity must never enter financial state.

    Python's Decimal does not fail loudly where it matters most. NaN PROPAGATES
    silently through arithmetic (``nan + 1`` is NaN), compares equal-to-nothing
    (``nan == 0`` is False, so a zero check misses it) and is TRUTHY, so ``if
    amount:`` passes. It only raises later, on an ordering comparison — typically
    far from whatever produced it. Infinity is worse: it compares silently, so a
    limit check against it simply returns the wrong answer.

    Refusing both at the parser is the one place this is catchable at the source.
    """
    if value.is_nan():
        raise MoneyError(f"NaN is not a financial value: {original!r}")
    if not value.is_finite():
        raise MoneyError(f"infinity is not a financial value: {original!r}")
    if value != 0 and abs(value.adjusted()) > MAX_ADJUSTED_EXPONENT:
        raise MoneyError(f"value out of financial range: {original!r}")
    return value


def D(value: Any, default: str = "0") -> Decimal:
    """Coerce to Decimal via str — never via binary float arithmetic.

    FAIL CLOSED. An invalid representation raises; it never becomes zero. The one
    substitution left is the documented optional path — ``None`` and ``""`` yield
    ``default`` — and that is the caller's declared policy, not a parse result.
    """
    # bool BEFORE any numeric handling: isinstance(True, int) is True in Python,
    # so an unguarded parser turns True into 1 and False into 0. Neither is money.
    if isinstance(value, bool):
        raise MoneyError(f"bool is not a financial value: {value!r}")
    try:
        if isinstance(value, Decimal):
            return _reject_non_finite(value, value)
        if value is None or value == "":
            return Decimal(default)
        if isinstance(value, float):
            # reject silent float contamination for money paths
            raise MoneyError(f"binary float not allowed for money: {value!r}")
        text = str(value)
        if not _NUMERIC_RE.match(text):
            raise MoneyError(f"not a plain numeric representation: {value!r}")
        if len(text) > MAX_NUMERIC_CHARS:
            raise MoneyError(f"numeric input too long ({len(text)} chars)")
        return _reject_non_finite(Decimal(text), value)
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
