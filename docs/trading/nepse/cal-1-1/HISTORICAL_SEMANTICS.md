# Historical Semantics

NEPSE raw import now uses the canonical weekly rule while keeping annual holiday
uncertainty explicit.

For the shipped `unsourced` calendar:

1. Sunday-Thursday rows are potential sessions and stay in the immutable raw
   dataset.
2. Quality includes `HOLIDAY_COVERAGE_UNKNOWN` and
   `nepse_holiday_coverage_unknown`.
3. The accepted state is `ACCEPTED_WITH_WARNINGS` when all non-calendar quality
   gates pass.
4. The dataset is not promotable to certified research while calendar coverage
   is incomplete.
5. Friday/Saturday rows are not silently deleted; they are recorded as
   `CONFIRMED_CLOSED_SESSION_BAR` and the dataset is quarantined/rejected.

New manifests record:

- `calendar_version=NEPSE_CALENDAR_V2_CANONICAL`
- `calendar_source_version` (currently `unsourced`)
- `calendar_coverage_status`
- `calendar_policy=REQUIRE_CALENDAR_COVERAGE`

The calendar metadata participates in the schema fingerprint. Existing files,
bars, accepted versions, and evidence are not rewritten by this migration.

An old NEPSE manifest without calendar metadata serializes as
`NEPSE_CALENDAR_V1_LEGACY_INVALID` with `LEGACY_MON_FRI_INVALID`. This is a read
compatibility classification, not a mutation of the old artifact.
