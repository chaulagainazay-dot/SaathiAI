# Migration Map

| Surface | Classification | Decision |
|---|---|---|
| `nepse/calendar.py::NepseCalendar` | MIGRATE_NOW | Canonical policy and typed classification authority. |
| `tg/historical/calendars.py` NEPSE entry | COMPATIBILITY_ADAPTER | Delegates to `NepseCalendar`; zero independent NEPSE weekday/holiday logic. |
| Legacy NEPSE `MarketCalendar` and illustrative holidays | REMOVE_LEGACY | Removed, not preserved as fixtures. |
| `tg/historical/import_service.py` | MIGRATE_NOW | Records policy/source/coverage and retains potential sessions with warning. |
| `tg/historical/quality.py` | MIGRATE_NOW | Canonical expected-session audit and confirmed-closed detection. |
| Historical manifest/coverage models | MIGRATE_NOW | Backward-compatible metadata path; unversioned NEPSE remains legacy-invalid. |
| `tg/historical/research.py` | MIGRATE_NOW | `REQUIRE_CALENDAR_COVERAGE` before any NEPSE run. |
| `strategy/engine.py::run_backtest` | MIGRATE_NOW | Canonical validation and versioned backtest manifest. |
| `market_data/quality.py::classify_quote` | MIGRATE_NOW | NEPSE closed/unknown/open classification precedes age staleness. |
| `tg/market_data/calendar.py` | MIGRATE_NOW | Canonical NEPSE session metadata and bar classification. |
| `tg/market_data/quality.py` | MIGRATE_NOW | No Western weekend rule on NEPSE datasets. |
| `tg/paper_simulation/calendar.py` | MIGRATE_NOW | NEPSE-prefixed symbols report Kathmandu hours/weekdays. |
| `platform/market_data/calendar.py` | GENERIC_NON_NEPSE | Generic M62 default/RTH calendars; no NEPSE registration remains there. |
| Historical `US_RTH` and `BINANCE_24_7` | GENERIC_NON_NEPSE | Separate US/crypto policy; unchanged. |
| `tg/research_orchestrator/calendar.py` | GENERIC_NON_NEPSE | Research cadence only, explicitly not a market calendar. |
| `safety/models.py::trading_day` | GENERIC_NON_NEPSE | Timezone-aware risk day window, not an exchange-session predicate. |
| `tg/intelligence/backtest_v2.py` | GENERIC_NON_NEPSE | Synthetic index-based bars with no NEPSE calendar input. |
| `strategy/service.py` fixture backtests | GENERIC_NON_NEPSE | M62 fixture datasets only. |
| `tg/market_data/service.py::_write_default_fixture` | GENERIC_NON_NEPSE | Deterministic `DEMO` fixture explicitly registered as US/XNAS; its Monday-Friday generator is not a NEPSE path. |
| `market_data/quality.py::is_bar_fresh` | DEFER | No inbound production caller in the graph; venue is absent from its API. |
| Annual holidays and historical shortened sessions | DEFER | Requires genuine sourced data; none fabricated here. |

The graph traced `get_market_calendar` into historical quality, expected-session
coverage, import, public calendar listing, service, API, and CLI surfaces. Those
NEPSE paths now reach the compatibility adapter or typed canonical audit.

Post-migration graph/static scan found no executable `NEPSE = MarketCalendar`,
no legacy holiday table, and no NEPSE consumer containing `weekday() < 5`. The
remaining Western weekday set belongs to `US_RTH`; the remaining production
`weekday() < 5` belongs to the explicitly US/XNAS synthetic fixture above.
