"""Market calendars for historical research (M187).

Extends M62 calendar with NEPSE and US equity holiday fixtures.
Unsupported calendars fail closed.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any

from saathi.platform.market_data.calendar import (
    MarketCalendar,
    DEFAULT_24_5,
    RTH_UTC,
    get_calendar as m62_get_calendar,
    SUPPORTED_CALENDARS as M62_SUPPORTED,
)
from saathi.platform.tg.historical.models import MarketCalendarSpec, TradingSession
from saathi.platform.trading_models import MarketState


# Bounded NEPSE holidays fixture (illustrative operator-supplied set; not exhaustive)
NEPSE_HOLIDAYS_2024_2025 = frozenset({
    "2024-01-15",  # Maghe Sankranti (example fixture)
    "2024-02-19",  # Democracy Day
    "2024-03-08",  # Holi (approx fixture)
    "2024-04-13",  # Nepali New Year
    "2024-05-01",  # Labour Day
    "2024-08-19",  # Janai Purnima (fixture)
    "2024-10-11",  # Dashain (fixture window start)
    "2024-10-12",
    "2024-10-13",
    "2024-11-01",  # Tihar (fixture)
    "2024-11-02",
    "2025-01-15",
    "2025-02-19",
    "2025-04-14",
    "2025-05-01",
})

# US RTH sample holidays
US_RTH_HOLIDAYS = frozenset({
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29",
    "2024-05-27", "2024-06-19", "2024-07-04", "2024-09-02",
    "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01",
    "2025-11-27", "2025-12-25",
})

NEPSE = MarketCalendar(
    name="NEPSE",
    open_utc=time(4, 0),   # ~09:45 NPT ≈ 04:00 UTC (approx; documented limitation)
    close_utc=time(9, 15),  # ~15:00 NPT
    open_weekdays=frozenset({0, 1, 2, 3, 4}),
    closed_dates=NEPSE_HOLIDAYS_2024_2025,
)

US_RTH = MarketCalendar(
    name="US_RTH",
    open_utc=time(14, 30),  # 09:30 ET winter approx → documented limitation
    close_utc=time(21, 0),
    open_weekdays=frozenset({0, 1, 2, 3, 4}),
    closed_dates=US_RTH_HOLIDAYS,
)

BINANCE_24_7 = MarketCalendar(
    name="BINANCE_24_7",
    open_utc=None,
    close_utc=None,
    open_weekdays=frozenset({0, 1, 2, 3, 4, 5, 6}),
    closed_dates=frozenset(),
)

_EXTRA = {c.name: c for c in (NEPSE, US_RTH, BINANCE_24_7)}
SUPPORTED_MARKET_CALENDARS = tuple(list(M62_SUPPORTED) + list(_EXTRA.keys()))


def get_market_calendar(name: str) -> MarketCalendar | None:
    if name in _EXTRA:
        return _EXTRA[name]
    return m62_get_calendar(name)


def calendar_spec(name: str) -> MarketCalendarSpec | None:
    cal = get_market_calendar(name)
    if cal is None:
        return None
    tz = {
        "NEPSE": "Asia/Kathmandu",
        "US_RTH": "America/New_York",
        "RTH_UTC": "UTC",
        "BINANCE_24_7": "UTC",
        "DEFAULT_24_5": "UTC",
    }.get(name, "UTC")
    session = TradingSession(
        name=f"{name}_session",
        open_local=cal.open_utc.strftime("%H:%M") if cal.open_utc else "00:00",
        close_local=cal.close_utc.strftime("%H:%M") if cal.close_utc else "23:59",
        timezone=tz,
        weekdays=sorted(cal.open_weekdays),
    )
    return MarketCalendarSpec(
        name=name,
        timezone=tz,
        session=session,
        holidays=sorted(cal.closed_dates),
        notes=[
            "Calendar is a bounded operator fixture, not a live exchange feed.",
            "Timezone conversions for NEPSE/US are approximate for research labeling.",
        ],
    )


def is_trading_day(name: str, dt: datetime) -> bool:
    cal = get_market_calendar(name)
    if cal is None:
        return False
    return cal.state_at(dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)) == MarketState.OPEN


def expected_sessions(
    calendar_name: str,
    start_ts: float,
    end_ts: float,
    *,
    timeframe: str = "1d",
) -> list[float]:
    """Generate expected daily session starts (UTC midnight) for coverage analysis."""
    if timeframe != "1d":
        # Intraday coverage requires denser calendars; report empty → honest incomplete
        return []
    cal = get_market_calendar(calendar_name)
    if cal is None:
        return []
    out: list[float] = []
    # step by day
    t = int(start_ts // 86400) * 86400
    end = end_ts
    while t <= end:
        dt = datetime.fromtimestamp(t, tz=timezone.utc)
        if cal.open_utc is None:
            # 24/7 — every day
            out.append(float(t))
        else:
            if dt.weekday() in cal.open_weekdays and dt.strftime("%Y-%m-%d") not in cal.closed_dates:
                out.append(float(t))
        t += 86400
    return out


def list_calendars_public() -> list[dict[str, Any]]:
    out = []
    for name in SUPPORTED_MARKET_CALENDARS:
        spec = calendar_spec(name)
        if spec:
            out.append(spec.to_public())
    return out
