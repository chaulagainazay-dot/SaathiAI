"""NEPSE-CAL-1 — authoritative NEPSE trading calendar.

Written before the implementation.

Two defects in the calendar this replaces:

1. **The trading week was inverted at both ends.** The existing
   ``tg/historical/calendars.py`` NEPSE entry uses
   ``open_weekdays={0,1,2,3,4}`` — Monday to Friday. NEPSE trades **Sunday
   through Thursday** and is closed Friday and Saturday. Every backtest using
   that calendar treated Sunday as closed and Friday as open.

2. **The holiday set is fabricated.** It is annotated in-source as an
   "illustrative operator-supplied set; not exhaustive", with entries labelled
   "(example fixture)" and "(approx fixture)".

The rule adopted here: the weekly pattern is CONFIRMED because it is stable and
verifiable; individual holiday dates are only CONFIRMED when they come from a
sourced dataset, and an unsourced date resolves to UNKNOWN rather than being
assumed open.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from saathi.platform.nepse.calendar import (
    NEPAL_TZ,
    NEPSE_CLOSE_LOCAL,
    NEPSE_OPEN_LOCAL,
    DayStatus,
    NepseCalendar,
    SessionState,
)


@pytest.fixture()
def cal():
    return NepseCalendar()


# ── the trading week: Sunday–Thursday ──────────────────────────────────────
#
# 2026-08-30 is a Sunday. The week that follows it is used throughout.

SUNDAY = date(2026, 8, 30)
MONDAY = date(2026, 8, 31)
TUESDAY = date(2026, 9, 1)
WEDNESDAY = date(2026, 9, 2)
THURSDAY = date(2026, 9, 3)
FRIDAY = date(2026, 9, 4)
SATURDAY = date(2026, 9, 5)


def test_the_reference_dates_really_are_the_weekdays_named():
    """Guards the fixture itself — a wrong anchor would make every other
    assertion in this file meaningless."""
    assert SUNDAY.weekday() == 6
    assert THURSDAY.weekday() == 3
    assert FRIDAY.weekday() == 4
    assert SATURDAY.weekday() == 5


@pytest.mark.parametrize("day", [SUNDAY, MONDAY, TUESDAY, WEDNESDAY, THURSDAY])
def test_sunday_through_thursday_are_trading_weekdays(cal, day):
    assert cal.is_trading_weekday(day) is True


@pytest.mark.parametrize("day", [FRIDAY, SATURDAY])
def test_friday_and_saturday_are_the_nepse_weekend(cal, day):
    assert cal.is_trading_weekday(day) is False


def test_saturday_is_closed_not_merely_unknown(cal):
    assert cal.day_status(SATURDAY) is DayStatus.WEEKEND


def test_friday_is_closed_not_merely_unknown(cal):
    assert cal.day_status(FRIDAY) is DayStatus.WEEKEND


def test_the_old_monday_to_friday_assumption_would_have_been_wrong_both_ways(cal):
    """Documents the inversion explicitly so it cannot quietly return."""
    western_week = {0, 1, 2, 3, 4}          # Mon–Fri
    assert SUNDAY.weekday() not in western_week and cal.is_trading_weekday(SUNDAY)
    assert FRIDAY.weekday() in western_week and not cal.is_trading_weekday(FRIDAY)


# ── holiday status: confirmed / expected / unknown ─────────────────────────

def test_a_sourced_holiday_is_confirmed(cal):
    c = NepseCalendar(holidays={"2026-09-01": ("Constitution Day", "CONFIRMED", "src://ref")})
    assert c.day_status(date(2026, 9, 1)) is DayStatus.HOLIDAY_CONFIRMED


def test_an_unsourced_expected_holiday_is_distinguishable(cal):
    c = NepseCalendar(holidays={"2026-09-01": ("Expected festival", "EXPECTED", "")})
    assert c.day_status(date(2026, 9, 1)) is DayStatus.HOLIDAY_EXPECTED


def test_a_trading_weekday_with_no_holiday_data_for_that_year_is_unknown(cal):
    """Fail closed. A future date with no sourced calendar must not be assumed
    open — a backtest that assumes it traded produces fabricated fills."""
    far_future = date(2031, 6, 3)           # a Tuesday, no dataset loaded
    assert cal.day_status(far_future) is DayStatus.UNKNOWN


def test_an_unknown_day_is_not_reported_as_a_trading_day(cal):
    far_future = date(2031, 6, 3)
    assert cal.is_trading_day(far_future) is False


def test_a_weekend_in_an_uncovered_year_is_still_known_to_be_closed(cal):
    """The weekly pattern is confirmed independently of holiday coverage."""
    far_future_saturday = date(2031, 6, 7)
    assert far_future_saturday.weekday() == 5
    assert cal.day_status(far_future_saturday) is DayStatus.WEEKEND


def test_covered_years_must_be_declared_not_inferred_from_holidays(cal):
    """R1 (fresh-context review): an earlier version promoted any year with a
    holiday entry into covered_years, so one sourced 2027 holiday marked the
    whole of 2027 as sourced. Coverage is a claim the caller makes explicitly."""
    c = NepseCalendar(holidays={"2027-04-14": ("New Year", "CONFIRMED", "src")})
    assert c.covered_years == frozenset()

    unsourced_tuesday = date(2027, 6, 8)
    assert unsourced_tuesday.weekday() == 1
    assert c.day_status(unsourced_tuesday) is DayStatus.UNKNOWN
    assert c.is_trading_day(unsourced_tuesday) is False


def test_a_sourced_holiday_is_honoured_even_in_an_uncovered_year():
    """Removing the inference must not make a sourced date resolve to UNKNOWN."""
    c = NepseCalendar(holidays={"2027-04-14": ("New Year", "CONFIRMED", "src")})
    assert c.day_status(date(2027, 4, 14)) is DayStatus.HOLIDAY_CONFIRMED


def test_declared_coverage_is_what_enables_trading_days():
    c = NepseCalendar(covered_years={2026})
    assert 2026 in c.covered_years
    assert 2031 not in c.covered_years


# ── trading-day navigation ─────────────────────────────────────────────────

def test_next_trading_day_skips_the_friday_saturday_weekend(cal):
    c = NepseCalendar(covered_years={2026})
    assert c.next_trading_day(THURSDAY) == SUNDAY + __import__("datetime").timedelta(days=7)


def test_previous_trading_day_from_sunday_is_the_prior_thursday(cal):
    c = NepseCalendar(covered_years={2026})
    prior_thursday = date(2026, 8, 27)
    assert prior_thursday.weekday() == 3
    assert c.previous_trading_day(SUNDAY) == prior_thursday


def test_navigation_skips_a_confirmed_holiday(cal):
    c = NepseCalendar(
        covered_years={2026},
        holidays={"2026-08-31": ("Holiday", "CONFIRMED", "s")},   # the Monday
    )
    assert c.next_trading_day(SUNDAY) == TUESDAY


def test_navigation_refuses_to_run_past_the_covered_range(cal):
    """Rather than inventing trading days beyond the sourced calendar."""
    c = NepseCalendar(covered_years={2026})
    with pytest.raises(ValueError):
        c.next_trading_day(date(2026, 12, 31))


# ── sessions and timezone ──────────────────────────────────────────────────

def test_nepal_is_utc_plus_five_forty_five_with_no_dst():
    """Asia/Kathmandu is UTC+05:45 year-round. Assuming a whole-hour offset, or
    any DST, shifts every session boundary."""
    jan = datetime(2026, 1, 15, 12, 0, tzinfo=NEPAL_TZ).utcoffset()
    jul = datetime(2026, 7, 15, 12, 0, tzinfo=NEPAL_TZ).utcoffset()
    assert jan == jul
    assert jan.total_seconds() == 5 * 3600 + 45 * 60


def test_session_times_are_local_not_utc_constants():
    assert NEPSE_OPEN_LOCAL.hour == 11 and NEPSE_OPEN_LOCAL.minute == 0
    assert NEPSE_CLOSE_LOCAL.hour == 15 and NEPSE_CLOSE_LOCAL.minute == 0


def test_market_is_open_during_the_session_on_a_trading_day(cal):
    c = NepseCalendar(covered_years={2026})
    midday = datetime(2026, 8, 30, 13, 0, tzinfo=NEPAL_TZ)      # Sunday 13:00 NPT
    assert c.session_state(midday) is SessionState.OPEN


def test_market_is_closed_before_the_session_opens(cal):
    c = NepseCalendar(covered_years={2026})
    early = datetime(2026, 8, 30, 9, 0, tzinfo=NEPAL_TZ)
    assert c.session_state(early) in (SessionState.CLOSED, SessionState.PRE_OPEN)


def test_market_is_closed_after_the_session_ends(cal):
    c = NepseCalendar(covered_years={2026})
    evening = datetime(2026, 8, 30, 17, 0, tzinfo=NEPAL_TZ)
    assert c.session_state(evening) is SessionState.CLOSED


def test_market_is_closed_all_day_on_the_weekend(cal):
    c = NepseCalendar(covered_years={2026})
    saturday_midday = datetime(2026, 9, 5, 13, 0, tzinfo=NEPAL_TZ)
    assert c.session_state(saturday_midday) is SessionState.CLOSED


def test_session_state_is_unknown_on_an_uncovered_trading_weekday(cal):
    unknown_day = datetime(2031, 6, 3, 13, 0, tzinfo=NEPAL_TZ)
    assert cal.session_state(unknown_day) is SessionState.UNKNOWN


def test_a_utc_instant_is_converted_before_the_session_is_judged(cal):
    """04:00 UTC is 09:45 NPT — before the open. 07:00 UTC is 12:45 NPT — inside
    the session. A calendar that compares UTC clock time directly gets both
    wrong."""
    c = NepseCalendar(covered_years={2026})
    assert c.session_state(datetime(2026, 8, 30, 4, 0, tzinfo=timezone.utc)) is not SessionState.OPEN
    assert c.session_state(datetime(2026, 8, 30, 7, 0, tzinfo=timezone.utc)) is SessionState.OPEN


def test_a_naive_datetime_is_rejected(cal):
    with pytest.raises(ValueError):
        cal.session_state(datetime(2026, 8, 30, 13, 0))


# ── year boundaries ────────────────────────────────────────────────────────

def test_year_boundary_navigation_is_correct_when_both_years_are_covered():
    c = NepseCalendar(covered_years={2026, 2027})
    dec31 = date(2026, 12, 31)              # a Thursday
    assert dec31.weekday() == 3
    assert c.next_trading_day(dec31) == date(2027, 1, 3)   # the Sunday


# ── provenance and honesty ─────────────────────────────────────────────────

def test_calendar_reports_its_own_coverage_and_sources(cal):
    c = NepseCalendar(
        holidays={"2026-09-01": ("Constitution Day", "CONFIRMED", "src://x")},
        covered_years={2026},
        dataset_version="np-2026.1",
    )
    d = c.to_dict()
    assert d["timezone"] == "Asia/Kathmandu"
    assert d["utc_offset"] == "+05:45"
    assert d["observes_dst"] is False
    assert d["trading_weekdays"] == ["SUN", "MON", "TUE", "WED", "THU"]
    assert d["weekend"] == ["FRI", "SAT"]
    assert d["covered_years"] == [2026]
    assert d["holiday_count"] == 1
    assert d["sources"] == ["src://x"]
    assert d["dataset_version"] == "np-2026.1"


def test_default_calendar_ships_no_fabricated_holidays(cal):
    """An empty sourced set is honest. A fabricated one is not — the calendar it
    replaces contained dates labelled "(example fixture)"."""
    assert cal.holiday_count == 0
    assert cal.covered_years == frozenset()


def test_calendar_has_no_network_dependency():
    import pathlib

    import saathi.platform.nepse.calendar as m

    src = pathlib.Path(m.__file__).read_text(encoding="utf-8")
    for forbidden in ("requests", "httpx", "urllib", "socket", "aiohttp"):
        assert forbidden not in src
