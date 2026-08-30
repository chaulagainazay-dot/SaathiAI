# Final Certification

Verdict:

`NEPSE_CALENDAR_LEGACY_MIGRATION_CERTIFIED_WITH_LIMITATIONS`

Implementation gates satisfied:

- no active NEPSE consumer owns an independent Monday-Friday rule;
- historical import uses canonical weekly semantics;
- unknown holiday coverage remains unknown and is retained with provenance;
- NEPSE backtests require complete sourced coverage;
- old unversioned NEPSE manifests remain legacy-invalid;
- Sunday/Friday/Saturday/Thursday, Kathmandu timezone, year boundary, import,
  backtest, staleness, adapter, and bar-alignment behavior are tested;
- financial authorities, live trading, brokers, and TradingAgents remain
  untouched.
- migration-specific, focused consumer, trading-authority, and canonical
  offline regressions pass with zero failures.

## Independent fresh-context review round

The completed migration was handed to a reviewer with no prior context, given
only the diff and the NEPSE facts. It returned **four findings**; three are
fixed in this milestone, one is recorded as a limitation. Full analysis in
`REVIEW_FINDINGS.md`.

| Id | Defect | Disposition |
|---|---|---|
| R-A | `run_backtest` gate keyed on `calendar_name`, so a NEPSE instrument left at the `DEFAULT_24_5` default skipped the coverage check entirely | **Fixed** — `NEPSE_INSTRUMENT_REQUIRES_NEPSE_CALENDAR` derives the requirement from instrument identity |
| R-C | A confirmed-closed session bar was scored but not blocking in `tg/market_data/quality.py`, so the two quality engines disagreed on the same dataset | **Fixed** — added to `blocking` and to the `_finalize` escalation list; both now force `QUARANTINED` |
| R-D | An offset-less timestamp bypassed the Kathmandu conversion and was string-sliced; at +05:45 that misplaces every instant after 18:15 UTC by one day | **Fixed** — naive timestamps are treated as UTC and always converted |
| R-B | `exchange` is free text and `MdRegisterBody.exchange` defaults to `"XNAS"`, so a mis-registered NEPSE dataset falls into Western weekend rules | **Recorded, not fixed** — outside the migration's file set; see `LIMITATIONS.md` |

Six regression tests were added for the three fixes, written before each fix.
The review reported **NONE** for historical-import relabelling, quote
staleness classification, and `NepseCalendar` fail-closed behaviour.

Intentional semantic corrections — Sunday moving from CLOSED to an open
candidate, Friday from OPEN to CONFIRMED_CLOSED — are tabulated in
`LEGACY_IMPACT.md`. They are corrections of a wrong calendar, not regressions.

Limitations remain material: no annual NEPSE holiday dataset ships, historical
session-hour regimes are not modelled, and certified NEPSE backtests therefore
remain blocked until genuine complete coverage is supplied. These are
fail-closed limitations, not legacy fallbacks.

## Canonical offline regression — green after storage recovery

`OFFLINE_REGRESSION_GREEN_AFTER_STORAGE_RECOVERY`

Superseding the blocker recorded below: HOST-STORAGE-1 reclaimed 7.4 GB of
gitignored Next.js build output, taking the host from 5 GB to 13.6 GB free.
The canonical offline suite then completed **7798 passed, 2 skipped, 12
deselected, 0 failed in 633.78s**, with all eight storage-dependent tests
passing and the focused NEPSE/trading ladder unchanged. Details in
`TEST_REPORT.md`.

### Superseded record — the original blocker

The last full offline run reported `8 failed, 7790 passed`. Every one of the
eight is the host sitting at ~2.9 GB free against a 5.0 GB storage gate, in
`test_m157_private_alpha`, `test_ops`, `test_studio_os`, and the release-gate
report test. All eight reproduce in isolation in nine seconds and none touches
calendar, NEPSE, trading, market-data, historical, or backtest code. The
evidence is in `TEST_REPORT.md`.

That suite has since been re-run green. The record is retained because the
attribution work is what justified continuing rather than treating the eight
failures as milestone defects.

`SAFE_TO_CONTINUE -> NEPSE-TXN-1`

Genuine export headers are still required before any importer schema is
upgraded to `VERIFIED`; real export files are not a prerequisite to begin
NEPSE-TXN-1.
