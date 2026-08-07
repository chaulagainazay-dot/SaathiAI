# M192 — Baseline Recovery (Paper Activation Governance)

| Field | Value |
| --- | --- |
| Pre-work branch | `milestone/m184-m191-trading-guardian-historical-research` |
| Authoritative baseline SHA | `b116c04558399c5d4f90a44ec1e837165e822e2e` |
| Working branch | `milestone/m192-m199-paper-activation-governance` |
| Prior verdict | `TRADING_GUARDIAN_HISTORICAL_RESEARCH_CERTIFIED_WITH_LIMITATIONS` |
| Live trading authorized | false |
| Broker credentials | false |

## Preserved unstaged / untracked (DO NOT COMMIT)

- `docs/evidence/m25/*`
- `docs/evidence/m27/connector_events.jsonl`
- `docs/evidence/m28/deprecation_events.jsonl`
- `docs/design-spec/`

## Compose over (do not redesign)

- `saathi/platform/paper_trading/*` — paper broker, store, reconciliation
- `saathi/platform/tg/*` — registry, risk, kill switch, journal, historical qualification
- Platform ApprovalStatus enum and permission model

## Goal

Owner-approved `PAPER_ELIGIBLE` strategies only → `PAPER_ACTIVE` → simulated paper portfolio.
**No live broker. No exchange auth. No production deploy.**
