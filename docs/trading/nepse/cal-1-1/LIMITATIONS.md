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

- **`exchange` is free text and the registration API defaults it to `XNAS`.**
  `tg/market_data/quality.py` selects the NEPSE calendar on
  `exchange == "NEPSE"`, but `MdRegisterBody.exchange` in
  `saathi/platform/api.py` defaults to `"XNAS"` independently of `market`. A
  NEPSE dataset registered with `market="NEPSE"` and the default `exchange`
  is judged under generic weekend rules. Deliberately not fixed here: the
  default lives outside the migration's file set and has other consumers.
  The backtest path — where fills are produced — is closed by the
  `NEPSE_INSTRUMENT_REQUIRES_NEPSE_CALENDAR` guard; the residual exposure is
  dataset quality classification being too lenient. Full detail and the
  intended fix are in `REVIEW_FINDINGS.md` (R-B).

- **`_write_default_fixture` in `tg/market_data/service.py` still generates
  Monday-Friday synthetic bars.** It is already labelled `SYNTHETIC_TEST_DATA`
  / `REAL_HISTORICAL_DATA_VALIDATION_INCOMPLETE` and never represents sourced
  NEPSE truth, so it is left as-is rather than given a calendar it would only
  pretend to honour. Any real NEPSE fixture must come from a sourced dataset.

- **`is_bar_fresh()` is NEPSE-unaware and currently unreferenced.** Noted above
  as a generic helper; recorded again here because the review confirmed that
  wiring it up without a calendar would report a bar carried over a NEPSE
  weekend as stale on wall-clock age alone.
