# Legacy Semantic Impact

The pre-change proof used 13:00 Nepal time for the canonical calendar and 07:00
UTC, inside the legacy approximate session, for the legacy calendar.

| Date | Day | Legacy result | Canonical weekly result | Default canonical truth |
|---|---|---|---|---|
| 2026-08-30 | Sunday | CLOSED | open candidate | POTENTIAL_OPEN_HOLIDAY_UNKNOWN |
| 2026-08-31 | Monday | OPEN | open candidate | POTENTIAL_OPEN_HOLIDAY_UNKNOWN |
| 2026-09-03 | Thursday | OPEN | open candidate | POTENTIAL_OPEN_HOLIDAY_UNKNOWN |
| 2026-09-04 | Friday | OPEN | closed | CONFIRMED_CLOSED |
| 2026-09-05 | Saturday | CLOSED | closed | CONFIRMED_CLOSED |

With an explicitly covered 2026 calendar, the Sunday through Thursday
candidates become `CONFIRMED_OPEN`. No such production holiday dataset ships in
this milestone.

`INTENTIONAL_SEMANTIC_CORRECTION` effects:

- Historical coverage now expects Sunday and excludes Friday.
- An uncovered Sunday-Thursday import is retained with unknown-calendar
  provenance; it is not certified as a trading day.
- A confirmed-closed Friday/Saturday bar becomes a calendar-quality defect.
- Certified NEPSE backtests reject an uncovered dataset rather than generating
  fills from assumed sessions.
- Sunday is no longer flagged as a Western weekend by NEPSE bar checks.
- A Friday/Saturday NEPSE quote is classified `MARKET_CLOSED`, not `STALE`.

Holiday correctness is not claimed. Individual holidays remain unknown until a
sourced, versioned calendar is loaded.
