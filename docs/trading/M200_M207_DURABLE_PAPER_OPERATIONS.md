# M200–M207 — Durable Multi-Process Paper Ledger & Long-Horizon Operations

**Terminal verdict:** `DURABLE_PAPER_OPERATIONS_CERTIFIED_WITH_LIMITATIONS`

**THE SYSTEM REMAINS PAPER ONLY.**

**LIVE TRADING IS NOT AUTHORIZED.**

## Architecture

Extends `saathi/platform/tg/paper_activation/` with:

```
durable/
  schema.py      versioned SQLite schema (m200.paper_gov.v1)
  store.py       WAL + BEGIN IMMEDIATE multi-process store
  events.py      append-only event ledger
  recovery.py    backup / verify / isolated restore / cash replay
  service.py     DurablePaperGovernanceService
```

API default: durable store when `SAATHI_PAPER_GOV_DURABLE != 0` (default on).

## Guarantees

| Area | Mechanism |
| --- | --- |
| Durability | SQLite WAL, transactional writes |
| Concurrency | BEGIN IMMEDIATE, OCC version columns, unique idempotency keys |
| Single-use approval | Atomic `UPDATE … WHERE status=APPROVED AND consumed_at IS NULL` |
| Exactly-once fills | `pg_processed_effects` effect keys |
| Restart | Persist all aggregates + queue + events; reload after restart |
| Recovery | File backup + isolated restore; source never overwritten |
| Campaigns | DRAFT→…→COMPLETED never becomes live-eligible |
| Scheduler | Disabled by default; local opt-in |

## LLM boundary

`llm_may_approve=false`, `llm_may_execute=false`, `llm_may_modify_ledger=false`,
`llm_may_release_kill_switch=false`, `llm_may_authorize_live=false`

## Limitations

- Single-host SQLite (not multi-node distributed)
- Process-local M192 service still available when durable disabled
- Browser cert may soft-gate on cold Next compile
- Owner human sign-off not claimed

## Explicit non-actions

No push, merge, PR, deploy, DNS, broker APIs, private exchange endpoints, credentials, live orders.
