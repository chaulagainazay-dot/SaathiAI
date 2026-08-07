"""Safe monetary arithmetic for HCG — integer minor units only.

Never use binary float for financial totals. NPR is the initial operating
currency (100 paisa = 1 NPR). Storage is currency-aware.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_CURRENCY = "NPR"
MINOR_PER_MAJOR = 100


class MoneyError(ValueError):
    """Invalid monetary input."""


@dataclass(frozen=True, slots=True)
class Money:
    """Immutable amount in integer minor units (e.g. paisa)."""

    amount_minor: int
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int) or isinstance(self.amount_minor, bool):
            raise MoneyError("amount_minor must be int")
        cur = (self.currency or DEFAULT_CURRENCY).upper()
        if len(cur) != 3 or not cur.isalpha():
            raise MoneyError("currency must be ISO-like 3-letter code")
        object.__setattr__(self, "currency", cur)

    @classmethod
    def zero(cls, currency: str = DEFAULT_CURRENCY) -> Money:
        return cls(0, currency)

    @classmethod
    def from_major(cls, major: Any, currency: str = DEFAULT_CURRENCY) -> Money:
        """Parse major units via string to avoid binary float contamination."""
        if isinstance(major, bool):
            raise MoneyError("bool is not money")
        if isinstance(major, float):
            raise MoneyError("binary float not allowed for money; use minor units or string")
        s = str(major).strip()
        if not s:
            raise MoneyError("empty money")
        neg = s.startswith("-")
        if neg:
            s = s[1:]
        if "." in s:
            whole, frac = s.split(".", 1)
            if not whole:
                whole = "0"
            if not whole.isdigit() or not frac.isdigit():
                raise MoneyError("invalid major amount")
            if len(frac) > 2:
                raise MoneyError("more than 2 decimal places")
            frac = (frac + "00")[:2]
            minor = int(whole) * MINOR_PER_MAJOR + int(frac)
        else:
            if not s.isdigit():
                raise MoneyError("invalid major amount")
            minor = int(s) * MINOR_PER_MAJOR
        if neg:
            minor = -minor
        return cls(minor, currency)

    @classmethod
    def from_minor(cls, minor: Any, currency: str = DEFAULT_CURRENCY) -> Money:
        if isinstance(minor, bool) or not isinstance(minor, int):
            raise MoneyError("minor units must be int")
        return cls(int(minor), currency)

    def ensure_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise MoneyError(f"currency mismatch {self.currency}!={other.currency}")

    def add(self, other: Money) -> Money:
        self.ensure_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def sub(self, other: Money) -> Money:
        self.ensure_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def neg(self) -> Money:
        return Money(-self.amount_minor, self.currency)

    def is_negative(self) -> bool:
        return self.amount_minor < 0

    def is_zero(self) -> bool:
        return self.amount_minor == 0

    def require_non_negative(self) -> Money:
        if self.amount_minor < 0:
            raise MoneyError("amount must be non-negative")
        return self

    def require_positive(self) -> Money:
        if self.amount_minor <= 0:
            raise MoneyError("amount must be positive")
        return self

    def to_public(self) -> dict[str, Any]:
        sign = "-" if self.amount_minor < 0 else ""
        abs_m = abs(self.amount_minor)
        major = abs_m // MINOR_PER_MAJOR
        frac = abs_m % MINOR_PER_MAJOR
        return {
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "display": f"{sign}{major}.{frac:02d} {self.currency}",
            "major_string": f"{sign}{major}.{frac:02d}",
        }


def parse_money_input(
    *,
    amount_minor: Any = None,
    amount_major: Any = None,
    currency: str = DEFAULT_CURRENCY,
) -> Money:
    """Accept minor (preferred) or major-string; reject binary float."""
    if amount_minor is not None and amount_minor != "":
        if isinstance(amount_minor, float):
            raise MoneyError("binary float not allowed")
        return Money.from_minor(int(amount_minor), currency).require_non_negative()
    if amount_major is not None and amount_major != "":
        return Money.from_major(amount_major, currency).require_non_negative()
    raise MoneyError("amount required")


def sum_money(items: list[Money], currency: str = DEFAULT_CURRENCY) -> Money:
    total = Money.zero(currency)
    for m in items:
        total = total.add(m)
    return total
