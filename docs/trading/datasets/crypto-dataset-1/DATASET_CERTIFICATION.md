# CRYPTO-DATASET-1 certification

**CRYPTO_REAL_HISTORICAL_DATASET_CERTIFIED_WITH_LIMITATIONS**

The official public Binance Spot archive dataset is locally certified for the frozen
STRATEGY-CRYPTO-1 experiment.

- Dataset ID: `binance-spot-1d-2018-01-01-2025-12-31-btcusdt-ethusdt`.
- Dataset version:
  `sha256-0f1290db14ab0037e6a69e25bcd1d7928087629cf11630f0ac2c52dbb27768e8`.
- Canonical content SHA-256:
  `2e7df608235789aec05a3170cd70158e1d628d8118e058658c491de3b0640858`.
- Retrieved at: `2026-09-03T01:09:56.972981+00:00`.
- Official source archives: 192/192 present and checksum-matched.
- Companion checksum files: 192/192 retained.
- Canonical bars: 5,844 total; 2,922 each for BTC and ETH.
- Continuity: 2,922 expected and observed per instrument; zero gaps, duplicates,
  conflicts, or out-of-order rows.
- Data mode: `HISTORICAL`.
- Source market: `SPOT`; no futures, margin, account, or private data.
- Local source permissions: zero writable raw ZIP/checksum files.
- Persisted reproducibility: passed from retained archives and checksums.
- Dataset footprint: 6.9 MB.
- Strategy evaluations during certification: 0.
- Final TEST periods spent during certification: 0.
- Focused dataset/backtest/signal/security regression: 327 passed.
- Canonical offline regression: 7,944 passed, 8 skipped, 12 deselected; exit code 0.
- Canonical log: `/tmp/saathios-crypto-dataset1-final.log`, SHA-256
  `0526c518ee543c068bc06f7586fe2f9f586e0280c9a72bcb6161ed699a27dbd4`.

## Frozen split timestamps

Both instruments have common valid coverage and identical sequence boundaries:

- TRAIN: `2018-01-02T00:00:00Z` through `2022-10-20T00:00:00Z`
  (`as_of`, 1,753 observations).
- VALIDATION: `2022-10-21T00:00:00Z` through `2024-05-26T00:00:00Z`
  (584 observations).
- TEST: `2024-05-27T00:00:00Z` through `2026-01-01T00:00:00Z`
  (585 observations), untouched at dataset-certification time.

These are exclusive-close timestamps. They are produced mechanically by the existing
60/20/20 preregistration and were frozen without calculating strategy performance.

## Limitations

- `ARCHIVE_PUBLICATION_HISTORY_NOT_RECONSTRUCTED`.
- `BAR_CLOSE_AVAILABILITY_PRECISION`.
- `OFFICIAL_ARCHIVES_MAY_PUBLISH_LATER_REVISIONS`.
- A published checksum proves exact fidelity to Binance's archived object, not that an
  exchange archive can never contain an economic-data error. Future official checksum
  changes create a new local dataset revision.

The ignored runtime dataset is stored at
`data/historical/certified/crypto-dataset-1/sha256-0f1290db14ab0037e6a69e25bcd1d7928087629cf11630f0ac2c52dbb27768e8/`.
Its immutable `manifest.json` is the authoritative per-archive checksum and provenance set.

After certification, STRATEGY-CRYPTO-1 was resumed once with the unchanged
preregistration. Dataset certification itself did not evaluate TEST returns; the later
qualification spent six separate strategy/instrument TEST evaluation keys.
