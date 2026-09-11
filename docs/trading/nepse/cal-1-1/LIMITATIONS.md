# Limitations

- No NEPSE holiday dates ship. Holiday coverage is unknown by design.
- Current regular 11:00-15:00 Nepal session hours are not a historical
  session-hours dataset; past shortened or changed sessions remain unsupported.
- Covered years and holiday records must be supplied by a genuine versioned
  source. This milestone provides the injection path but no source loader.
- Quote/session auto-detection currently requires the canonical `NEPSE:`
  instrument prefix. An unqualified symbol cannot safely imply a venue.
- No persisted registry of every historical artifact exists. Tracked evidence
  contains documentation references but no serialized legacy NEPSE backtest
  output to rewrite or date-audit.
- A legacy artifact with Sunday/Friday participation is
  `LEGACY_CALENDAR_AFFECTED`; an unversioned NEPSE artifact without sufficient
  dates is `UNKNOWN`. Non-NEPSE artifacts are
  `LEGACY_CALENDAR_NOT_AFFECTED`.
- Generic US calendar samples and approximate US session conversion are outside
  this NEPSE migration.
- `is_bar_fresh` remains a generic unused helper because its model has no venue;
  active NEPSE quote freshness is migrated.

These limitations block certified NEPSE backtests without coverage. They do not
authorize live data, orders, brokers, or production deployment.

## Added after the fresh-context review

- **Resolved by MD-1.1:** generic registration no longer defaults
  `MdRegisterBody.exchange` or dataset registration to `XNAS`. Contradictory
  NEPSE/XNAS identity is rejected, and unknown dataset venue makes calendar
  checks fail closed. The historical review finding remains in the archive;
  the implementation evidence is in `docs/trading/md-1-1/`.

- **`_write_default_fixture` in `tg/market_data/service.py` still generates
  Monday-Friday synthetic bars.** It is already labelled `SYNTHETIC_TEST_DATA`
  / `REAL_HISTORICAL_DATA_VALIDATION_INCOMPLETE` and never represents sourced
  NEPSE truth, so it is left as-is rather than given a calendar it would only
  pretend to honour. Any real NEPSE fixture must come from a sourced dataset.

- **`is_bar_fresh()` is NEPSE-unaware and currently unreferenced.** Noted above
  as a generic helper; recorded again here because the review confirmed that
  wiring it up without a calendar would report a bar carried over a NEPSE
  weekend as stale on wall-clock age alone.
