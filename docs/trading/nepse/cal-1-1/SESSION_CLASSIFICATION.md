# Session Classification

`NepseCalendar.classify_session(date)` is the ingestion-safe API. It does not
weaken `is_trading_day()`, which remains true only for confirmed sessions.

| Classification | Meaning | Raw import | Certified backtest |
|---|---|---|---|
| `CONFIRMED_OPEN` | Covered trading weekday or sourced special session | accept subject to other quality gates | eligible |
| `CONFIRMED_CLOSED` | Friday/Saturday or sourced confirmed holiday | retain as quality evidence; quarantine/reject dataset | reject |
| `POTENTIAL_OPEN_HOLIDAY_UNKNOWN` | Sunday-Thursday weekly candidate without annual holiday coverage | retain with warning and provenance | reject |
| `UNKNOWN` | Truth cannot be resolved, including an expected/unconfirmed holiday | retain only as unverified evidence | reject |

Coverage summaries are `COMPLETE`, `HOLIDAY_COVERAGE_UNKNOWN`, or `UNKNOWN`.
The current default is `HOLIDAY_COVERAGE_UNKNOWN` for any range containing an
uncovered Sunday-Thursday candidate. Friday/Saturday remain confirmed closed in
all years.

Timezone conversion is always through `Asia/Kathmandu` (`UTC+05:45`, no DST).
Naive session datetimes remain invalid.
