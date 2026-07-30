# M256–M263 — Market Data Foundation, Dataset Governance and Research-Grade Signal Validation

**Terminal verdict:** `RESEARCH_GRADE_MARKET_DATA_AND_SIGNAL_VALIDATION_CERTIFIED_WITH_LIMITATIONS`

**Maximum state:** `RESEARCH_DATA_AND_SIGNAL_VALIDATION_READY`

**Browser cert:** `RESEARCH_GRADE_MARKET_DATA_SIGNAL_VALIDATION_BROWSER_CERT_PASSED_WITH_LIMITATIONS`

---

## Authority boundary (immutable)

```text
RESEARCH ONLY
OFFLINE-FIRST
PAPER ONLY
SANDBOX ONLY
NO BROKER CONNECTIVITY
NO ACCOUNT ACCESS
NO ORDER EXECUTION
NO LIVE TRADING
NO GUARANTEED PROFITABILITY
```

This milestone does **not** connect any broker, accept credentials, activate a canary, or enable live trading.

Continues from:

- M216–M223 Broker Sandbox
- M224–M231 Read-Only Broker Readiness
- M232–M239 Reproducibility & Supply Chain
- M240–M247 Provider Canary Planning
- M248–M255 Institutional Investment Intelligence (`INSTITUTIONAL_INVESTMENT_INTELLIGENCE_CERTIFIED_WITH_LIMITATIONS`)

Primary weakness removed: ungoverned synthetic bars may no longer be silently treated as certified research history. Synthetic fixtures remain allowed only when labelled `SYNTHETIC_TEST_DATA`.

---

## Package layout

```text
saathi/platform/tg/market_data/
  models.py              # authority locks, enums
  registry.py            # M256 dataset identity
  catalog.py             # catalogue overview
  licensing.py           # M257 licence governance
  provenance.py          # M257 provenance
  ingestion.py           # M258 offline ingestion
  normalization.py       # canonical OHLCV schema
  quality.py             # M259 quality engine
  calendar.py            # exchange calendars
  corporate_actions.py   # CA registry
  adjustments.py         # adjusted_close only; raw preserved
  bias_controls.py       # M260 PIT / bias
  dataset_split.py       # train/val/test splits
  feature_store.py       # M261 versioned features
  signal_validation.py   # M262 strategy validation
  security.py            # threat model + refusals
  storage.py             # market_data_research.db
  service.py             # facade + control center data
  certification.py       # hard gates
  fixtures/              # bounded synthetic CSV
```

UI: `/trading/research-data`  
API: `/api/v1/platform/tg/research-data/*`  
CLI: `python -m saathi.platform.tg.cli md-*` and `paper-gov md-*`

---

## Milestone map

| ID | Capability |
|----|------------|
| M256 | Dataset registry, deterministic IDs, versions, supersession, revocation |
| M257 | Licence classifications, provenance, fail-closed unknown rights |
| M258 | CSV/JSON/JSONL ingestion, normalisation, idempotent re-ingest |
| M259 | Quality, calendars, corporate actions, raw vs adjusted |
| M260 | Look-ahead, survivorship, splits, embargo/purge, leakage |
| M261 | Versioned feature store + lineage |
| M262 | Signal validation with costs, OOS, WF, MC, regimes |
| M263 | Control Center UI/API/CLI + certification |

---

## Invariants

```text
certified_research_requires_registered_dataset = true
future_information_available = false
train_test_leakage_detected = false
survivorship_bias_unreported = false   # when unreported → limitation, not silent pass
evaluation_set_optimised_on = false
LIVE_TRADING_AUTHORIZED = false
```

---

## Data source policy

Allowed: local files, repository fixtures, bounded synthetic test data (labelled), public snapshots with recorded licence/provenance.

Certification does **not** depend on live APIs. When only fixtures are used:

`REAL_HISTORICAL_DATA_VALIDATION_INCOMPLETE`

---

## Security

File parsing is fail-closed. No pickle. No broker SDK imports. No credential acceptance. LLM may explain but cannot waive gates, approve unknown licences, or enable live trading.

Threat model: `docs/trading/m256_m263_evidence/M256_M263_THREAT_MODEL.json`

---

## Limitations

- Synthetic fixtures used for architecture proof
- Not regulatory-grade market data
- Incomplete holiday calendars
- No guaranteed strategy profitability
- Research validation ≠ live trading authority
- Parquet/SQLite export paths not required for offline cert

---

## Explicit non-actions

No broker credentials, no broker connectivity, no canary activation, no orders, no account access, no M264 auto-start.

---

## Recommended next milestone

**M264** — only after human review of research-data evidence. Remain research/paper/sandbox. Do not auto-start live connectivity.
