# M184–M191 — Historical Market Data, Strategy Qualification & Paper Eligibility

**Terminal verdict:** `TRADING_GUARDIAN_HISTORICAL_RESEARCH_CERTIFIED_WITH_LIMITATIONS`

**Date:** 2026-07-29

## Authority

| Claim | Status |
| --- | --- |
| Paper only | YES |
| Historical research only | YES |
| Live trading authorized | NO |
| Broker credentials | NO |
| Production authorized | NO |
| Profitability claim | NO |
| Owner sign-off | Automated browser only — not human owner sign-off |

## Hard policy

`AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA`

- Fixture/synthetic results remain research-only.
- `PAPER_ELIGIBLE` requires non-fixture authoritative historical data + full gate checklist (including Monte Carlo).
- No live order path. No LLM approval of qualification or metric alteration.
- Dataset versions are immutable after acceptance.
- Quarantined/rejected datasets cannot promote strategies.

## Architecture (composed, not redesigned)

```
Local CSV/Parquet | Binance public file | NEPSE local | Yahoo local cache
        ↓
  HistoricalImportService (quality + corporate actions + fingerprint)
        ↓
  HistoricalDatasetStore (immutable accepted versions)
        ↓
  HistoricalResearchRunner
        → Regime segmentation → Strategy run → Walk-forward → Stress
        → Monte Carlo → Portfolio → Scorecard → Eligibility
```

Reuses: `tg/data_contract`, `tg/walk_forward`, `tg/stress_lab`, `tg/evaluation`,
M62 `market_data`, M62 `strategy` engine, paper broker / ExecutionGateway (unchanged).

## Modules

| Module | Role |
| --- | --- |
| `tg/historical/models.py` | Dataset entities, quality verdicts, fingerprints |
| `tg/historical/store.py` | Immutable store + quarantine + disk preflight |
| `tg/historical/quality.py` | OHLC/session/coverage gates |
| `tg/historical/normalize.py` | Corporate actions; raw preserved |
| `tg/historical/calendars.py` | NEPSE, US_RTH, BINANCE_24_7 + M62 calendars |
| `tg/historical/adapters/*` | Local, Binance public, NEPSE, Yahoo (file-first) |
| `tg/historical/import_service.py` | Import orchestration |
| `tg/historical/monte_carlo.py` | Bounded MC + risk of ruin |
| `tg/historical/research.py` | Multi-period research runner |
| `tg/historical/qualification.py` | 26-gate PAPER_ELIGIBLE checklist |

## Adapters

1. **Local CSV/Parquet** — primary; deterministic; fingerprint; quarantine invalid.
2. **Binance public** — file-first exports; optional public klines only (`allow_network=False` by default); no credentials/orders.
3. **Yahoo public** — local CSV cache only (network fetch disabled by design).
4. **NEPSE local** — operator CSV/Parquet; NPR; NEPSE calendar; no scraping.

## PAPER_ELIGIBLE

All mandatory gates in `QualificationGates` must pass. Includes:

- non-fixture authoritative dataset
- accepted data quality
- walk-forward + untouched final OOS
- stress + Monte Carlo
- realistic fees/spread/slippage
- acceptable drawdown and risk-of-ruin
- immutable strategy + dataset versions
- owner approval still required before paper activation

## API (permission-aware)

- `POST /tg/historical/import`
- `GET /tg/historical/datasets`
- `GET /tg/historical/datasets/{id}`
- `GET /tg/historical/datasets/{id}/quality`
- `POST /tg/historical/datasets/{id}/quarantine`
- `GET /tg/historical/quarantine`
- `GET /tg/historical/calendars`
- `POST /tg/historical/research`
- `GET /tg/historical/research`
- `GET /tg/historical/research/{run_id}`
- `POST /tg/historical/monte-carlo`
- `POST /tg/historical/qualify`
- `GET /tg/historical/scorecard/{slug}`

## CLI

```
python -m saathi.platform.tg data import <path> [--adapter local_file|binance|nepse|yahoo]
python -m saathi.platform.tg data list|inspect|quarantine
python -m saathi.platform.tg calendar inspect
python -m saathi.platform.tg research run --dataset-id ... --strategy ...
python -m saathi.platform.tg research monte-carlo
python -m saathi.platform.tg strategy-qualify --dataset-id ...
```

## UI

- `/trading/historical` — datasets, calendars, quarantine
- `/trading/monte-carlo` — MC lab
- `/trading/qualification` — scorecards / gates

## Disclaimers (mandatory)

- This is historical research; all trading remains simulated.
- No live broker is connected; no live order path exists.
- Historical performance does not predict future performance.
- Adjusted-data methodology can affect results.
- Poor-quality data can invalidate conclusions.
- Simulated costs may differ from real execution.
- Strategy eligibility does not equal profitability.
- Paper eligibility does not authorize live trading.
- Human approval remains required.
