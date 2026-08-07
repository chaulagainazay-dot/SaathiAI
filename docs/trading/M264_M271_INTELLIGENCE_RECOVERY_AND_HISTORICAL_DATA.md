# M264–M271 — Intelligence Baseline Recovery, Clean-Clone Reproducibility and Historical Dataset Qualification

**Terminal verdict:** `INTELLIGENCE_BASELINE_RECOVERED_AND_HISTORICAL_DATA_QUALIFIED_WITH_LIMITATIONS`

**Historical data status:** `BOUNDED_REAL_HISTORICAL_DATA_VALIDATED_WITH_LIMITATIONS`

---

## Original defect

M248–M255 was certified locally but **never committed**.  
`git ls-tree` / `git log --all` for intelligence paths were empty; implementation lived only as untracked working-tree files while M256–M263 was committed and partially integrated against them.

## Recovery

- Branch: `milestone/m264-m271-intelligence-recovery-historical-data`
- Recovered backend, UI, tests, browser cert, docs, and evidence into Git history
- Shared surfaces (`api.py`, `cli.py`, TradingShell, package.json) already carried dual intelligence + research-data wiring from M256–M263
- **UNTRACKED_SOURCE_DEPENDENCIES = 0** after recovery

## Clean-clone certification

Clean clone path: `/tmp/saathiai-m267-clean` at recovery SHA.

| Gate | Result |
|------|--------|
| Backend M248–M263 tests | 37 passed |
| Frontend unit | 10 passed |
| Production build | both `/trading/intelligence` and `/trading/research-data` |
| `cert:m255` | passed |
| `cert:m263` | passed |

## Historical datasets (bounded, frozen, checksummed)

| Dataset | Source | Licence posture | Rows | Role |
|---------|--------|-----------------|------|------|
| AAPL daily | Plotly datasets (GitHub, MIT) | OPEN / attribution | 400 | Equity OHLCV |
| BTCUSDT daily | CryptoDataDownload public freeze | Attribution / no git redistribute | 400 | Crypto OHLCV |
| UNRATE | FRED | Attribution | 120 | Macro (LIMITED_USE, not OHLCV) |

Raw snapshots stored under `data/platform/historical_snapshots/` (**gitignored**). Evidence records checksums, provenance, and licences.

## Signal validation (pre-registered)

- Strategy: `tf_dual_ma` only (bounded, not mined)
- Costs: 5 bps commission + 8 bps slippage
- Chronological split + embargo; walk-forward / Monte Carlo / regimes recorded
- Results: **out-of-sample failed** on both equity and crypto samples (honest research outcome)
- Forbidden states (`PROFITABLE`, `LIVE_READY`, etc.) not used

## Authority

All of `REAL_CONNECTIVITY`, `BROKER_CONNECTIVITY`, `CREDENTIAL_PROVISIONING`, `CANARY_ACTIVATION`, `ORDER_EXECUTION`, `ORDER_SUBMISSION`, `LIVE_TRADING` remain **false**.

## Explicit non-actions

No broker connection, no credentials, no canary, no orders, no M272.

## Evidence

`docs/trading/m264_m271_evidence/`

## Recommended next

**M272** only after human review — remain research/paper/sandbox.
