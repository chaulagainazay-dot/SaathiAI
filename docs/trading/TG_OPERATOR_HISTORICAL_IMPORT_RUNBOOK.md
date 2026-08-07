# Operator runbook — Historical data import

## Preconditions

- Localhost SaathiOS; paper research only
- Free disk ≥ 256 MB on import volume
- Operator-supplied file (CSV preferred)

## Import CSV

```bash
python -m saathi.platform.tg data import ./my_ohlcv.csv \
  --adapter local_file \
  --name equities_2020_2024 \
  --instrument SPY \
  --market US \
  --calendar US_RTH \
  --currency USD
```

Expected columns (aliases accepted): `date/timestamp`, `symbol`, `open`, `high`, `low`, `close`, `volume`.

## NEPSE

```bash
python -m saathi.platform.tg data import ./nepse_nabil.csv \
  --adapter nepse --instrument NABIL --calendar NEPSE --currency NPR
```

## Binance public export

```bash
python -m saathi.platform.tg data import ./btcusdt_1d.csv \
  --adapter binance --instrument BTCUSDT
```

## Validate / inspect

```bash
python -m saathi.platform.tg data list
python -m saathi.platform.tg data inspect <dataset_id>
```

## Quarantine

Invalid quality auto-quarantines. Manual:

```bash
python -m saathi.platform.tg data quarantine <dataset_id> <version> --reason "..."
```

Quarantined data cannot support PAPER_ELIGIBLE.

## Research

```bash
python -m saathi.platform.tg research run --dataset-id <id> --strategy trend_following --period FULL
python -m saathi.platform.tg strategy-qualify --dataset-id <id> --strategy kotegawa_mean_reversion
```

## Failures

| Symptom | Action |
| --- | --- |
| REJECTED schema | Fix headers; re-import new version |
| DUPLICATE_DATASET | Same content fingerprint already accepted |
| insufficient_disk | Free space; do not force |
| INSUFFICIENT_COVERAGE | Provide longer history or accept research-only |
