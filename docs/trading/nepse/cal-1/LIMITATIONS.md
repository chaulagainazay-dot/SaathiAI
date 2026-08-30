# Limitations

> Historical milestone record. The active legacy-calendar limitation below was
> resolved by NEPSE-CAL-1.1. Current limitations are in
> `docs/trading/nepse/cal-1-1/LIMITATIONS.md`.

## The wrong calendar was still in the tree

At the NEPSE-CAL-1 boundary, `saathi/platform/tg/historical/calendars.py` still
defined NEPSE as Monday–Friday with fabricated holidays, and
`historical/import_service.py` still used it.
NEPSE-CAL-1 adds a correct calendar; it does not remove the incorrect one.

Migrating those consumers is deliberately out of scope — swapping the trading
week underneath existing historical imports changes what their outputs mean, and
that needs its own analysis. **Until that migration happens, anything importing
from `tg/historical/calendars` is still wrong two days in five.**

NEPSE-CAL-1.1 removed that active policy after auditing and versioning its
semantic impact.

## The default calendar has no holidays

Shipped empty on purpose. Consequences to understand:

- `is_trading_day()` returns `False` for **every** trading weekday until a
  dataset is loaded, because coverage must be declared
- `next_trading_day()` / `previous_trading_day()` **raise** outside covered years
  rather than inventing a date

That is fail-closed, and it means the calendar is not yet usable for a real
backtest. It becomes usable when an annual holiday dataset with source
references is loaded — which needs a published source, not code.

## Session hours are current-regime only

Open 11:00, close 15:00, pre-open 10:30 Nepal time. NEPSE has revised session
hours over the years and has run shortened sessions. A historical
session-hours-by-date dataset is not implemented, so a backtest over an older
period will use today's hours for that period.

## Not modelled

Intraday auction phases beyond a single pre-open window, circuit-breaker halts,
per-instrument suspension, settlement calendar (distinct from the trading
calendar), and half-day sessions.

## Verification status

The Sunday–Thursday trading week and the UTC+05:45 no-DST offset are asserted
from general knowledge of NEPSE and `ZoneInfo` respectively. The offset is
verified against the tz database in a test. The trading week is **not** verified
against a NEPSE publication in this milestone — it is a well-established fact,
but if a sourced holiday dataset is ever loaded, the same source should be used
to confirm the weekly pattern at the same time.
