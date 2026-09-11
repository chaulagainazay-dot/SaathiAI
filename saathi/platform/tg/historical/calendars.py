"""Historical calendar compatibility surface.

Generic M62/US/crypto calendars remain here.  NEPSE is a compatibility adapter
over :class:`saathi.platform.nepse.calendar.NepseCalendar`; this module owns no
NEPSE weekday or holiday policy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from saathi.platform.market_data.calendar import (
    MarketCalendar,
    DEFAULT_24_5,
    RTH_UTC,
    get_calendar as m62_get_calendar,
    SUPPORTED_CALENDARS as M62_SUPPORTED,
)
from saathi.platform.nepse.calendar import (
    NEPAL_TZ,
    NEPAL_TZ_NAME,
    NEPSE_CALENDAR_V2_CANONICAL,
    NEPSE_CLOSE_LOCAL,
    NEPSE_OPEN_LOCAL,
    NEPSE_TRADING_WEEKDAYS,
    CalendarCoverageStatus,
    NepseCalendar,
    SessionClassification,
    SessionState,
)
from saathi.platform.tg.historical.models import MarketCalendarSpec, TradingSession
from saathi.platform.trading_models import MarketState


NEPSE_CALENDAR_V1_LEGACY_INVALID = "NEPSE_CALENDAR_V1_LEGACY_INVALID"
NEPSE_BACKTEST_POLICY = "REQUIRE_CALENDAR_COVERAGE"

# US RTH sample holidays
US_RTH_HOLIDAYS = frozenset({
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29",
    "2024-05-27", "2024-06-19", "2024-07-04", "2024-09-02",
    "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01",
    "2025-11-27", "2025-12-25",
})

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


@dataclass(frozen=True)
class CanonicalNepseCalendarAdapter:
    """Legacy shape backed entirely by the canonical NEPSE calendar."""

    canonical: NepseCalendar = field(default_factory=NepseCalendar)
    name: str = "NEPSE"

    @property
    def open_weekdays(self) -> frozenset[int]:
        return NEPSE_TRADING_WEEKDAYS

    @property
    def closed_dates(self) -> frozenset[str]:
        return frozenset(
            day
            for day in self.canonical.holidays
            if self.canonical.classify_session(date.fromisoformat(day))
            is SessionClassification.CONFIRMED_CLOSED
        )

    @property
    def open_utc(self) -> time:
        # Compatibility only. Public specs use the authoritative local value.
        return time(5, 15)

    @property
    def close_utc(self) -> time:
        return time(9, 15)

    @property
    def calendar_version(self) -> str:
        return self.canonical.calendar_version

    @property
    def calendar_source_version(self) -> str:
        return self.canonical.calendar_source_version

    def state_at(self, moment: datetime) -> MarketState:
        state = self.canonical.session_state(moment)
        if state is SessionState.OPEN:
            return MarketState.OPEN
        if state is SessionState.UNKNOWN:
            return MarketState.UNKNOWN
        return MarketState.CLOSED

    def is_open(self, moment: datetime) -> bool:
        return self.state_at(moment) is MarketState.OPEN


@dataclass(frozen=True)
class HistoricalSessionClassification:
    day: date
    classification: SessionClassification
    session_start_epoch: float

    @property
    def is_expected(self) -> bool:
        return self.classification in (
            SessionClassification.CONFIRMED_OPEN,
            SessionClassification.POTENTIAL_OPEN_HOLIDAY_UNKNOWN,
        )


@dataclass(frozen=True)
class ExpectedSessionAudit:
    sessions: tuple[HistoricalSessionClassification, ...]
    coverage_status: CalendarCoverageStatus
    calendar_version: str
    calendar_source_version: str

    @property
    def expected_session_count(self) -> int:
        return sum(item.is_expected for item in self.sessions)

    @property
    def confirmed_open_count(self) -> int:
        return sum(
            item.classification is SessionClassification.CONFIRMED_OPEN
            for item in self.sessions
        )

    @property
    def potential_open_count(self) -> int:
        return sum(
            item.classification is SessionClassification.POTENTIAL_OPEN_HOLIDAY_UNKNOWN
            for item in self.sessions
        )

    @property
    def confirmed_closed_count(self) -> int:
        return sum(
            item.classification is SessionClassification.CONFIRMED_CLOSED
            for item in self.sessions
        )


_CANONICAL_NEPSE_ADAPTER = CanonicalNepseCalendarAdapter()
_EXTRA = {c.name: c for c in (US_RTH, BINANCE_24_7)}
SUPPORTED_MARKET_CALENDARS = tuple(dict.fromkeys(list(M62_SUPPORTED) + ["NEPSE"] + list(_EXTRA.keys())))


def get_market_calendar(name: str) -> MarketCalendar | CanonicalNepseCalendarAdapter | None:
    if name == "NEPSE":
        return _CANONICAL_NEPSE_ADAPTER
    if name in _EXTRA:
        return _EXTRA[name]
    return m62_get_calendar(name)


def calendar_spec(name: str) -> MarketCalendarSpec | None:
    cal = get_market_calendar(name)
    if cal is None:
        return None
    if name == "NEPSE":
        return MarketCalendarSpec(
            name="NEPSE",
            timezone=NEPAL_TZ_NAME,
            session=TradingSession(
                name="NEPSE_session",
                open_local=NEPSE_OPEN_LOCAL.strftime("%H:%M"),
                close_local=NEPSE_CLOSE_LOCAL.strftime("%H:%M"),
                timezone=NEPAL_TZ_NAME,
                weekdays=sorted(NEPSE_TRADING_WEEKDAYS),
            ),
            holidays=[],
            calendar_version=NEPSE_CALENDAR_V2_CANONICAL,
            calendar_source_version=cal.calendar_source_version,
            calendar_coverage_status=CalendarCoverageStatus.HOLIDAY_COVERAGE_UNKNOWN.value,
            calendar_policy=NEPSE_BACKTEST_POLICY,
            notes=[
                "Canonical weekly rule; Friday and Saturday are confirmed closed.",
                "Holiday coverage is unsourced, so trading weekdays remain potential sessions.",
            ],
        )
    tz = {
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
        calendar_version="GENERIC_CALENDAR_UNVERSIONED",
        calendar_source_version="",
        calendar_coverage_status=CalendarCoverageStatus.UNKNOWN.value,
        calendar_policy="GENERIC",
        notes=[
            "Calendar is a bounded operator fixture, not a live exchange feed.",
            "Timezone conversions for US calendars are approximate for research labeling.",
        ],
    )


def is_trading_day(name: str, dt: datetime) -> bool:
    cal = get_market_calendar(name)
    if cal is None:
        return False
    return cal.state_at(dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)) == MarketState.OPEN


def expected_session_audit(
    calendar_name: str,
    start_ts: float,
    end_ts: float,
    *,
    timeframe: str = "1d",
    nepse_calendar: NepseCalendar | None = None,
) -> ExpectedSessionAudit:
    """Return date-level truth used by import quality and provenance."""
    calendar = nepse_calendar or NepseCalendar()
    if calendar_name != "NEPSE" or timeframe != "1d":
        return ExpectedSessionAudit(
            sessions=(),
            coverage_status=CalendarCoverageStatus.UNKNOWN,
            calendar_version="GENERIC_CALENDAR_UNVERSIONED",
            calendar_source_version="",
        )

    start_day = datetime.fromtimestamp(start_ts, tz=timezone.utc).astimezone(NEPAL_TZ).date()
    end_day = datetime.fromtimestamp(end_ts, tz=timezone.utc).astimezone(NEPAL_TZ).date()
    sessions: list[HistoricalSessionClassification] = []
    day = start_day
    while day <= end_day:
        classification = calendar.classify_session(day)
        local_midnight = datetime.combine(day, time.min, tzinfo=NEPAL_TZ)
        sessions.append(
            HistoricalSessionClassification(
                day=day,
                classification=classification,
                session_start_epoch=local_midnight.timestamp(),
            )
        )
        day += timedelta(days=1)
    return ExpectedSessionAudit(
        sessions=tuple(sessions),
        coverage_status=calendar.coverage_status(item.day for item in sessions),
        calendar_version=calendar.calendar_version,
        calendar_source_version=calendar.calendar_source_version,
    )


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
    if calendar_name == "NEPSE":
        audit = expected_session_audit(
            calendar_name,
            start_ts,
            end_ts,
            timeframe=timeframe,
        )
        return [item.session_start_epoch for item in audit.sessions if item.is_expected]
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
