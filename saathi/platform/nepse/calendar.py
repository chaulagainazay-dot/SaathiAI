"""NEPSE-CAL-1 — authoritative NEPSE trading calendar.

Two defects in the calendar this replaces
-----------------------------------------
``saathi/platform/tg/historical/calendars.py`` defines its NEPSE entry with
``open_weekdays=frozenset({0, 1, 2, 3, 4})`` — Monday to Friday, the Western
week.

**NEPSE trades Sunday through Thursday and is closed Friday and Saturday.**

That calendar is therefore wrong at both ends: it treats every Sunday as closed
(losing a real trading day) and every Friday as open (inventing one). Any
backtest, session check, or staleness rule built on it is wrong roughly two days
in five.

Its holiday set is also annotated in-source as an *"illustrative
operator-supplied set; not exhaustive"*, with individual entries labelled
"(example fixture)" and "(approx fixture)".

What this module does differently
---------------------------------
The **weekly pattern is CONFIRMED** — it is stable and independently verifiable,
so Friday and Saturday are known-closed in any year, covered or not.

**Individual holidays are data, not code.** They arrive as a versioned dataset
with a status and a source reference per date. Nepali public holidays follow the
Bikram Sambat lunisolar calendar and are announced annually by the Government of
Nepal; they cannot be derived from a formula, and hardcoding a speculative
permanent table is how the previous calendar became fiction.

A trading weekday in a year with no loaded dataset resolves to **UNKNOWN**, and
``is_trading_day`` returns ``False`` for it. That is deliberate: assuming an
unverified future date traded produces fabricated fills in a backtest, which is
worse than refusing to answer.

Timezone
--------
``Asia/Kathmandu`` is **UTC+05:45 year-round with no DST**. The offset is not a
whole number of hours, which is exactly the sort of thing a hand-rolled UTC
constant gets wrong. Session boundaries are defined in local time and converted.

Authority
---------
Reference data. No execution, approval, risk, or ledger authority. No network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

__all__ = [
    "NEPAL_TZ",
    "NEPAL_TZ_NAME",
    "NEPSE_OPEN_LOCAL",
    "NEPSE_CLOSE_LOCAL",
    "NEPSE_TRADING_WEEKDAYS",
    "DayStatus",
    "SessionState",
    "HolidayStatus",
    "NepseCalendar",
]

NEPAL_TZ_NAME = "Asia/Kathmandu"
NEPAL_TZ = ZoneInfo(NEPAL_TZ_NAME)

# Continuous trading session in Nepal local time.
# Documented limitation: NEPSE has revised session hours over the years, and
# has run shortened sessions. These constants describe the current regular
# session only; a historical session-hours dataset is future work.
NEPSE_OPEN_LOCAL = time(11, 0)
NEPSE_CLOSE_LOCAL = time(15, 0)
NEPSE_PRE_OPEN_LOCAL = time(10, 30)

# Python weekday(): Mon=0 … Sun=6. NEPSE trades Sunday–Thursday.
NEPSE_TRADING_WEEKDAYS = frozenset({6, 0, 1, 2, 3})
_WEEKDAY_LABEL = {6: "SUN", 0: "MON", 1: "TUE", 2: "WED", 3: "THU", 4: "FRI", 5: "SAT"}
_ORDERED_TRADING_LABELS = ["SUN", "MON", "TUE", "WED", "THU"]


class HolidayStatus(str, Enum):
    """How much is actually known about a holiday date."""

    CONFIRMED = "CONFIRMED"    # from a sourced, dated announcement
    EXPECTED = "EXPECTED"      # anticipated but not yet officially published
    UNKNOWN = "UNKNOWN"


class DayStatus(str, Enum):
    TRADING = "TRADING"
    WEEKEND = "WEEKEND"
    HOLIDAY_CONFIRMED = "HOLIDAY_CONFIRMED"
    HOLIDAY_EXPECTED = "HOLIDAY_EXPECTED"
    SPECIAL_SESSION = "SPECIAL_SESSION"
    UNKNOWN = "UNKNOWN"


class SessionState(str, Enum):
    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


def _require_aware(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"expected a datetime, got {type(value).__name__}")
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(
            "timestamp must be timezone-aware; NEPSE is UTC+05:45 and a naive "
            "datetime silently mis-resolves every session boundary"
        )
    return value


@dataclass(frozen=True)
class HolidayRecord:
    name: str
    status: HolidayStatus
    source_ref: str = ""


@dataclass(frozen=True)
class NepseCalendar:
    """NEPSE trading calendar.

    ``holidays`` maps ``YYYY-MM-DD`` to ``(name, status, source_ref)``.
    ``covered_years`` declares which years the holiday dataset actually covers;
    a trading weekday outside it is UNKNOWN rather than assumed open.
    """

    holidays: Mapping[str, tuple[str, str, str]] = field(default_factory=dict)
    covered_years: frozenset[int] = field(default_factory=frozenset)
    special_sessions: Mapping[str, str] = field(default_factory=dict)
    dataset_version: str = "unsourced"

    # No __post_init__ coverage inference.
    #
    # An earlier version promoted "any year with a holiday entry" into
    # covered_years. That was wrong: one sourced holiday in 2027 marked the whole
    # of 2027 as sourced, so is_trading_day(2027-06-10) returned True with
    # nothing backing June 2027 — exactly the fabrication this class exists to
    # refuse, and a direct contradiction of its own rule below.
    #
    # covered_years reflects only what the caller explicitly declares as fully
    # sourced. Holiday lookup runs before the coverage check in day_status, so a
    # sourced holiday is still honoured in an otherwise-uncovered year.

    # ── weekly pattern (confirmed in every year) ───────────────────────────

    def is_trading_weekday(self, day: date) -> bool:
        return day.weekday() in NEPSE_TRADING_WEEKDAYS

    # ── day classification ─────────────────────────────────────────────────

    def _holiday(self, day: date) -> HolidayRecord | None:
        raw = self.holidays.get(day.isoformat())
        if raw is None:
            return None
        name, status, source_ref = raw
        try:
            parsed = HolidayStatus(str(status).upper())
        except ValueError:
            parsed = HolidayStatus.UNKNOWN
        return HolidayRecord(name=name, status=parsed, source_ref=source_ref)

    def day_status(self, day: date) -> DayStatus:
        if not self.is_trading_weekday(day):
            # The weekend is known in every year, sourced or not.
            if day.isoformat() in self.special_sessions:
                return DayStatus.SPECIAL_SESSION
            return DayStatus.WEEKEND

        holiday = self._holiday(day)
        if holiday is not None:
            if holiday.status is HolidayStatus.CONFIRMED:
                return DayStatus.HOLIDAY_CONFIRMED
            if holiday.status is HolidayStatus.EXPECTED:
                return DayStatus.HOLIDAY_EXPECTED
            return DayStatus.UNKNOWN

        if day.year not in self.covered_years:
            return DayStatus.UNKNOWN

        return DayStatus.TRADING

    def is_trading_day(self, day: date) -> bool:
        """True only when the day is *known* to trade. UNKNOWN is not True."""
        return self.day_status(day) in (DayStatus.TRADING, DayStatus.SPECIAL_SESSION)

    # ── navigation ─────────────────────────────────────────────────────────

    def _step(self, start: date, delta: int) -> date:
        day = start + timedelta(days=delta)
        for _ in range(370):
            if day.year not in self.covered_years and self.is_trading_weekday(day):
                raise ValueError(
                    f"cannot resolve a trading day at {day.isoformat()}: year "
                    f"{day.year} is outside the sourced calendar "
                    f"(covered: {sorted(self.covered_years) or 'none'})"
                )
            if self.is_trading_day(day):
                return day
            day += timedelta(days=delta)
        raise ValueError(f"no trading day found within a year of {start.isoformat()}")

    def next_trading_day(self, day: date) -> date:
        return self._step(day, 1)

    def previous_trading_day(self, day: date) -> date:
        return self._step(day, -1)

    # ── sessions ───────────────────────────────────────────────────────────

    def session_state(self, moment: datetime) -> SessionState:
        _require_aware(moment)
        local = moment.astimezone(NEPAL_TZ)
        day = local.date()

        status = self.day_status(day)
        if status is DayStatus.UNKNOWN:
            return SessionState.UNKNOWN
        if status in (DayStatus.WEEKEND, DayStatus.HOLIDAY_CONFIRMED, DayStatus.HOLIDAY_EXPECTED):
            return SessionState.CLOSED

        t = local.time()
        if NEPSE_PRE_OPEN_LOCAL <= t < NEPSE_OPEN_LOCAL:
            return SessionState.PRE_OPEN
        if NEPSE_OPEN_LOCAL <= t < NEPSE_CLOSE_LOCAL:
            return SessionState.OPEN
        return SessionState.CLOSED

    def is_open(self, moment: datetime) -> bool:
        return self.session_state(moment) is SessionState.OPEN

    # ── introspection ──────────────────────────────────────────────────────

    @property
    def holiday_count(self) -> int:
        return len(self.holidays)

    def sources(self) -> list[str]:
        return sorted({ref for _, _, ref in self.holidays.values() if ref})

    def to_dict(self) -> dict[str, Any]:
        return {
            "timezone": NEPAL_TZ_NAME,
            "utc_offset": "+05:45",
            "observes_dst": False,
            "trading_weekdays": list(_ORDERED_TRADING_LABELS),
            "weekend": ["FRI", "SAT"],
            "session_local": {
                "pre_open": NEPSE_PRE_OPEN_LOCAL.isoformat(),
                "open": NEPSE_OPEN_LOCAL.isoformat(),
                "close": NEPSE_CLOSE_LOCAL.isoformat(),
            },
            "dataset_version": self.dataset_version,
            "covered_years": sorted(self.covered_years),
            "holiday_count": self.holiday_count,
            "sources": self.sources(),
        }
