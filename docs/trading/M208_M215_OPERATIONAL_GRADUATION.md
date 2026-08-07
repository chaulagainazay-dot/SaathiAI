# M208–M215 — Extended Paper Campaign Validation & Operational Graduation

**Terminal verdict:** `OPERATIONAL_GRADUATION_CERTIFIED_WITH_LIMITATIONS`

**Branch:** `milestone/m208-m215-ops-graduation`

**THE SYSTEM REMAINS PAPER ONLY.**

**LIVE TRADING IS NOT AUTHORIZED.**

**NO STRATEGY IS AUTOMATICALLY PROMOTED TO LIVE EXECUTION.**

**OPERATIONAL GRADUATION DOES NOT GRANT BROKER OR REAL-MONEY AUTHORITY.**

## Scope

Extends durable paper operations (M200–M207), paper activation (M192–M199), and historical research (M166–M191) with long-horizon multi-campaign operations and research-stage graduation.

Does **not** redesign historical research, qualification, paper activation, portfolio/risk engines, durable ledger, journal, analytics, or campaign manager — only composes and extends them.

## Package

```
saathi/platform/tg/paper_activation/ops/
  models.py            health / graduation / cert enums + LLM boundary
  schema.py            additive SQLite tables (pg_campaign_*, pg_ops_*, pg_graduation, …)
  campaign_manager.py  M208 multi-campaign manager
  monitoring.py        M209 operational health
  graduation.py        M210 strategy graduation engine
  intelligence.py      M211 recommend-only intelligence
  analytics_adv.py     M212 rolling analytics & reports
  simulation.py        M213 operational simulation suite
  evidence.py          M214 immutable evidence + certification
  dashboard.py         M215 ops dashboard read model
  service.py           OperationalGraduationService facade
```

API prefix: `/api/v1/platform/tg/paper/ops/*`  
UI: `/trading/ops-graduation`  
CLI: `python -m saathi.platform.tg paper-gov ops-*`  
Browser cert: `npm run cert:m215` (from `saathi-os/`)

## Milestone map

| ID | Capability | Result |
| --- | --- | --- |
| M208 | Multi-campaign: groups, templates, clone, compare, pause/resume, archive, schedule, ownership, notes, objectives, tags, metadata, version history, dependencies | Implemented + tested |
| M209 | Continuous health: portfolio/risk/campaign/system/storage/worker/recon/strategy/market/events/scheduler/disk/memory/recovery → HEALTHY…FAILED_SAFE | Implemented + tested |
| M210 | Graduation engine → RESEARCH_ONLY / PAPER_ACTIVE / PAPER_VALIDATED / PAPER_GRADUATE / MORE_EVIDENCE_REQUIRED / REJECTED — never live | Implemented + tested; never authorizes live |
| M211 | Drift, risk deterioration, stale data, interventions, storage/worker anomalies → recommendations only | Implemented + tested; not auto-applied |
| M212 | Rolling Sharpe/Sortino/DD/vol/expectancy, weekly/monthly/campaign/comparison reports, rankings | Implemented + tested |
| M213 | Holiday/outage/worker/storage/latency/missing candles/partial data/scheduler/disk/recovery/risk/kill-switch simulations | 12/12 suite passed |
| M214 | Immutable evidence bundles + campaign certification outcomes | Implemented + tested |
| M215 | Centralized ops dashboard surfaces (paper-only labelled) | UI + browser cert |

## Storage

- Additive ops schema applied during durable store migrate.
- ImportError (ops package absent) skips ops tables for M200-only installs.
- Ops SQL failure raises `OPS_SCHEMA_MIGRATION_FAILED` (fail closed).
- Schema is idempotent (`CREATE TABLE IF NOT EXISTS`).
- Existing M200 paper_gov tables remain readable.

## LLM boundary

LLM may explain, summarize, compare, recommend, generate reports, identify anomalies, draft docs.

LLM may **not** approve campaigns, graduate strategies, change metrics, modify journals/evidence, override risk/recon, execute trades, or authorize live trading.

## Verification (fresh recovery run)

| Gate | Result |
| --- | --- |
| Focused M208–M215 | 15 passed |
| M200 compatibility | 15 passed |
| Broader M192–M208 | 42 passed |
| TG M166–M215 regression | 115 passed |
| Full backend | 5568 passed, 1 skipped |
| Frontend M208 unit | 2 passed |
| Frontend trading unit | 33 passed |
| Full frontend suite | 240 passed |
| Production build | pass (`/trading/ops-graduation` present) |
| Browser cert | `OPS_GRADUATION_BROWSER_CERT_PASSED_WITH_LIMITATIONS` (0 hard fails; 1 soft journey) |
| Authority / credential / live-path scans | pass |

## Limitations

- Single-host SQLite (not multi-node)
- Graduation is paper research-stage only; not live eligibility
- Owner human sign-off not claimed
- Browser cert automated only; soft limitation on empty paper-approvals journey / cold compile on 8GB host
- Scheduler remains disabled by default

## Owner sign-off

`NOT_CLAIMED_AUTOMATED_ONLY`

## Explicit non-actions

No broker APIs, exchange auth, API keys, deployment, production, DNS, real orders, autonomous live trading, live execution, PR/push/merge.

## Evidence

`docs/trading/m208_m215_evidence/`
