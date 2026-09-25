# NEPSE-CAL-1 — Authoritative NEPSE Trading Calendar

`saathi/platform/nepse/calendar.py`

> Historical milestone record. NEPSE-CAL-1.1 subsequently removed the active
> legacy weekday/holiday implementation and migrated its consumers. Current
> policy and evidence live in `docs/trading/nepse/cal-1-1/`.

## The defect this replaces

At the time NEPSE-CAL-1 shipped,
`saathi/platform/tg/historical/calendars.py` defined NEPSE as:

```python
NEPSE = MarketCalendar(
    name="NEPSE",
    open_utc=time(4, 0),
    close_utc=time(9, 15),
    open_weekdays=frozenset({0, 1, 2, 3, 4}),      # ← Monday–Friday
    closed_dates=NEPSE_HOLIDAYS_2024_2025,
)
```

**NEPSE trades Sunday through Thursday and is closed Friday and Saturday.**

`{0,1,2,3,4}` is Monday–Friday. The calendar is therefore wrong at *both* ends:

- every **Sunday** — a real NEPSE trading day — was treated as closed
- every **Friday** — a NEPSE weekend day — was treated as open

Roughly two days in five were misclassified. Any backtest, session check, bar
alignment, or staleness rule built on it inherited that.

The holiday set is separately annotated in-source as an *"illustrative
operator-supplied set; not exhaustive"*, with individual entries carrying
"(example fixture)" and "(approx fixture)" comments — fabricated dates presented
as a calendar.

## The rule adopted

**The weekly pattern is CONFIRMED.** It is stable and independently verifiable,
so Friday and Saturday are known-closed in any year, sourced or not.

**Holidays are data, not code.** They arrive as a versioned dataset carrying a
status and a source reference per date. Nepali public holidays follow the Bikram
Sambat lunisolar calendar and are announced annually by the Government of Nepal;
they cannot be derived from a formula. Hardcoding a speculative permanent table
is exactly how the previous calendar became fiction.

**Unknown fails closed.** A trading weekday in a year with no loaded dataset
resolves to `UNKNOWN`, and `is_trading_day()` returns `False`. Assuming an
unverified future date traded produces fabricated fills in a backtest, which is
worse than refusing to answer.

**The default calendar ships zero holidays.** An empty sourced set is honest.

## States

| Type | Members |
|---|---|
| `HolidayStatus` | `CONFIRMED` (sourced announcement) · `EXPECTED` (anticipated, unpublished) · `UNKNOWN` |
| `DayStatus` | `TRADING` · `WEEKEND` · `HOLIDAY_CONFIRMED` · `HOLIDAY_EXPECTED` · `SPECIAL_SESSION` · `UNKNOWN` |
| `SessionState` | `PRE_OPEN` · `OPEN` · `CLOSED` · `UNKNOWN` |

## Timezone

`Asia/Kathmandu` is **UTC+05:45 year-round, no DST**. A non-whole-hour offset is
exactly what a hand-rolled UTC constant gets wrong, so sessions are defined in
local time and converted through `ZoneInfo`. A test asserts the January and July
offsets are identical and equal to 5h45m.

Session boundaries (local): pre-open 10:30, open 11:00, close 15:00. Documented
limitation: NEPSE has revised session hours over the years and has run shortened
sessions; these constants describe the current regular session only.

## Defect found by fresh-context review

An independent reviewer caught a bug **I had introduced**: `__post_init__`
promoted any year containing a holiday entry into `covered_years`.

```python
NepseCalendar(holidays={"2027-04-14": ("New Year", "CONFIRMED", "src")})
# → is_trading_day(date(2027, 6, 10)) returned True
```

One sourced April holiday marked the whole of 2027 as sourced, so an unbacked
June Tuesday reported as a trading day — the exact fabrication this class exists
to refuse, contradicting its own docstring. The inference is removed; coverage
is now only what the caller explicitly declares. A sourced holiday is still
honoured in an uncovered year, because holiday lookup runs before the coverage
check. Both behaviours have regression tests.

## Relationship to the old calendar

NEPSE-CAL-1 deliberately left `tg/historical/calendars.py` unchanged pending a
semantic-impact audit. NEPSE-CAL-1.1 completed that follow-up: the historical
surface now delegates to `NepseCalendar`, fabricated fixture holidays are gone,
import preserves uncovered weekly candidates with provenance, and certified
backtests require complete calendar coverage. The old Monday-Friday policy is
retained only as an explicit legacy artifact label, never as executable policy.

## Authority

Reference data. No execution, approval, risk, or ledger authority. No network.
