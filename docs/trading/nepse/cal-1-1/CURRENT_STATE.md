# NEPSE-CAL-1.1 Current State

Starting commit: `23cc62482539820bb642031beb7e5aa7cd3fdb2b`.

The canonical authority remains `saathi/platform/nepse/calendar.py`. It now
identifies itself as `NEPSE_CALENDAR_V2_CANONICAL` and exposes typed date-level
session truth. The repository ships no NEPSE holiday dates and the default
source version is `unsourced`.

The historical calendar module is now a compatibility surface. Its NEPSE entry
delegates to `NepseCalendar`; the independent Monday-Friday definition and the
illustrative 2024-2025 holiday set have been removed.

Current consumer state:

- Historical NEPSE import retains potential weekly sessions and records unknown
  holiday coverage rather than discarding the rows.
- Historical research and direct strategy backtests require complete calendar
  coverage for NEPSE and reject uncovered data.
- Quote freshness, market-data bar alignment/quality, and paper-session
  descriptions use canonical NEPSE session semantics.
- Old unversioned NEPSE manifests are exposed as
  `NEPSE_CALENDAR_V1_LEGACY_INVALID`; they are never relabelled canonical.

No execution, approval, portfolio-risk, construction, fund-ledger, or
reconciliation authority changed. There is no network, broker, TradingAgents,
or live-trading dependency.
