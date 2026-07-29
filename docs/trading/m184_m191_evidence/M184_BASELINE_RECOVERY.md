# M184 — Authoritative Baseline Recovery

## Recovery point

| Field | Value |
| --- | --- |
| Pre-work branch | `milestone/m176-m183-trading-guardian-paper-validation` |
| Authoritative baseline SHA (verified) | `ba66cca5e0ffd8874f8e8c3a4cb25a7dde74425e` |
| Working branch | `milestone/m184-m191-trading-guardian-historical-research` |
| Prior terminal verdict | `TRADING_GUARDIAN_PAPER_VALIDATION_CERTIFIED_WITH_LIMITATIONS` |
| Live trading authorized | false |
| Production trading authorized | false |
| Broker credentials supported | false |

## Preserved pre-existing unstaged / untracked (DO NOT MODIFY OR COMMIT)

- `docs/evidence/m25/LATEST_ENVIRONMENT_OBSERVATION.json`
- `docs/evidence/m25/LIVE_CERT_EVIDENCE.json`
- `docs/evidence/m25/LIVE_CERT_SUMMARY.md`
- `docs/evidence/m27/connector_events.jsonl`
- `docs/evidence/m28/deprecation_events.jsonl`
- `docs/design-spec/` (untracked)

## Architecture to compose (do not redesign)

| Layer | Location |
| --- | --- |
| Trading Guardian facade | `saathi/platform/tg/` |
| Data classification | `tg/data_contract.py` |
| Walk-forward | `tg/walk_forward.py` |
| Stress lab | `tg/stress_lab.py` |
| Strategy evaluation | `tg/evaluation.py` |
| M62 market data | `saathi/platform/market_data/` |
| M62 strategy engine | `saathi/platform/strategy/` |
| Paper broker | `saathi/platform/paper_trading/` |

## Gaps before M185+ (documented, not yet implemented)

1. No versioned historical dataset registry with immutable acceptance.
2. No local CSV/Parquet import path labeled `HISTORICAL_LOCAL_DATASET`.
3. No Binance public-history or NEPSE local importers.
4. No corporate-action adjustment audit trail (raw vs adjusted).
5. No NEPSE market calendar fixture.
6. No Monte Carlo / risk-of-ruin lab.
7. No full multi-period historical research runner over authoritative history.
8. PAPER_ELIGIBLE still blocked for all strategies because prior validation used synthetic/fixture data only.

## Non-negotiable policy

- `AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA`
- System remains paper-only; no live order path.
- Do not silently substitute fixture data.
- Do not claim profitability or live readiness.
