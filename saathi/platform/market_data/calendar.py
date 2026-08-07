"""M62.2 — bounded, deterministic market calendar. No global exchange encyclopedia.

Two bounded calendars sufficient for certification:
 - DEFAULT_24_5: crypto-like, open 24h Mon-Sun (always open) — used by fixtures.
 - RTH_UTC: a simple regular-trading-hours calendar (Mon-Fri, 13:30-20:00 UTC ~ US
   equities), with explicit closed dates supplied by fixtures.

Unsupported calendars are documented and rejected (fail-closed to CLOSED/UNKNOWN).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone

from saathi.platform.market_data.models import is_aware
from saathi.platform.trading_models import MarketState


@dataclass(frozen=True)
class MarketCalendar:
    name: str
    open_utc: time | None          # None => always open
    close_utc: time | None
    open_weekdays: frozenset = field(default_factory=lambda: frozenset({0, 1, 2, 3, 4}))  # Mon-Fri
    closed_dates: frozenset = field(default_factory=frozenset)  # frozenset of "YYYY-MM-DD"

    def state_at(self, dt: datetime) -> MarketState:
        if not is_aware(dt):
            return MarketState.UNKNOWN
        u = dt.astimezone(timezone.utc)
        if u.strftime("%Y-%m-%d") in self.closed_dates:
            return MarketState.CLOSED
        if self.open_utc is None:  # always-open (24/7)
            return MarketState.OPEN
        if u.weekday() not in self.open_weekdays:
            return MarketState.CLOSED
        t = u.timetz().replace(tzinfo=None)
        if self.open_utc <= t < self.close_utc:
            return MarketState.OPEN
        return MarketState.CLOSED

    def is_open(self, dt: datetime) -> bool:
        return self.state_at(dt) == MarketState.OPEN


DEFAULT_24_5 = MarketCalendar(name="DEFAULT_24_5", open_utc=None, close_utc=None,
                              open_weekdays=frozenset({0, 1, 2, 3, 4, 5, 6}))
RTH_UTC = MarketCalendar(name="RTH_UTC", open_utc=time(13, 30), close_utc=time(20, 0))

_CALENDARS = {c.name: c for c in (DEFAULT_24_5, RTH_UTC)}
SUPPORTED_CALENDARS = tuple(_CALENDARS.keys())


def get_calendar(name: str) -> MarketCalendar | None:
    """Return a supported calendar, or None for unsupported (caller fails closed)."""
    return _CALENDARS.get(name)
