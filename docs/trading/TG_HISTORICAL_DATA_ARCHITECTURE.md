# Trading Guardian — Historical Data Architecture (M185)

## Entities

- `HistoricalDataset`, `DatasetVersion` (immutable after accept)
- `DatasetManifest`, `DatasetSource`, `DatasetFingerprint`, `DatasetCoverage`
- `InstrumentMetadata`, `MarketCalendarSpec`, `TradingSession`
- `CorporateAction`, `AdjustedPriceBar` (raw + adj_*)
- `DataQualityReport`, `DataImportRun`, `DatasetQuarantineRecord`

## Classifications

| Code | Authoritative? |
| --- | --- |
| `HISTORICAL_AUTHENTICATED` | Yes |
| `HISTORICAL_LOCAL_DATASET` | Yes |
| `SYNTHETIC_VALIDATION` | No |
| `FIXTURE_TEST_ONLY` | No |
| `INCOMPLETE` | No |
| `REJECTED` | No |

## Quality verdicts

`ACCEPTED` | `ACCEPTED_WITH_WARNINGS` | `QUARANTINED` | `REJECTED` | `INSUFFICIENT_COVERAGE`

## Storage / resources (8 GB class)

- Chunked/streaming CSV parse; max_rows bound
- Disk preflight (`min_free_mb`, default 256)
- Monte Carlo ≤ 500 sims; trades capped
- No automatic large downloads without operator action
- Do not delete operator source files

## LLM boundary

May explain quality/scorecards. Must not alter data, approve datasets/strategies, invent prices, or authorize live trading.
