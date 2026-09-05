# CRYPTO-DATASET-1 acquisition plan

Frozen before any STRATEGY-CRYPTO-1 return evaluation.

- Provider: Binance official public-data archive.
- Host: `https://data.binance.vision`.
- Market: Spot only.
- Symbols: `BTCUSDT`, `ETHUSDT`.
- Canonical instruments: `BINANCE:BTC/USDT`, `BINANCE:ETH/USDT`.
- Interval: `1d`, inherited unchanged from the STRATEGY-CRYPTO-1 preregistration.
- Coverage: UTC-open dates `2018-01-01` through `2025-12-31`, inclusive.
- Archives: 96 monthly ZIPs per symbol; 192 ZIPs and 192 companion checksum files.
- Coverage choice: complete calendar months selected without inspecting strategy outcomes.
- Common coverage policy: both instruments use the same interval and coverage because both
  official archive series exist from the first selected month.
- Expected footprint: under 10 MB for raw ZIPs, checksums, one canonical JSONL per symbol,
  manifest, and quality report. Representative ZIPs were 2,085–2,230 bytes.
- Baseline storage: `storage_report()` reported 12.5 GB free and healthy; `df` reported
  12 GiB available.
- Destination: ignored runtime data under
  `data/historical/certified/crypto-dataset-1/<source-revision-sha256>/`.

The source-revision SHA-256 is derived from the complete published checksum set,
normalization version, and this policy. A changed official checksum produces a new sibling
dataset version and never replaces an old revision.

## Frozen experiment split policy

- TRAIN: first 60% of each immutable instrument sequence.
- VALIDATION: next 20%.
- TEST: final 20%, untouched during acquisition and data-quality inspection.
- Walk-forward: unchanged expanding folds `0–40 / 40–50 / 50–60%` and
  `0–60 / 60–70 / 70–80%`.
- Strategy families, grids, trial budget, benchmark, costs, and fill semantics remain those
  in `docs/trading/strategy/crypto-1/PRE_REGISTRATION.md`.

Dataset certification may inspect bytes, checksums, schema, timestamps, OHLCV, ordering,
duplicates, and continuity. It must not calculate a strategy return.
