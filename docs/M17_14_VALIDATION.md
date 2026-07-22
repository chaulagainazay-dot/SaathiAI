# M17.14 Validation — Governed Mission Scheduler & Trusted Event Triggers

Start/rollback point: HEAD `73fd251` (M17.13). Branch `milestone/m7-security-engine`.
Verdict: **GOVERNED MISSION SCHEDULING & TRUSTED EVENT TRIGGERS STAGING READY**
(not production).

## What was built
A durable, deterministic, restart-safe scheduling + trusted-event layer for the
existing MissionEngine. The scheduler/event bridge sit ABOVE the engine and only
create/claim a valid occurrence (or accept a trusted event) and DELEGATE it:

```
Scheduler / Trusted Event → Mission instance → MissionEngine → PipelineRunner →
run_harness_action → Adapter → independent verification → durable ledger
```

No second scheduler DB, job runner, execution engine, approval system, event bus, or
ledger was added. All state lives in the SAME ledger DB (additive
`mission_schedule`, `mission_occurrence`, `mission_event_trigger`,
`mission_event_receipt` tables).

### Deliverables
- **Ledger** (`run_ledger.py`): 4 additive tables + states/transition graphs +
  owner-safe methods for schedules, occurrences (lease claim, retry, reconcile),
  triggers, and receipts. `health()` extended (`schedules`, `occurrences`,
  `occurrence_collisions`).
- **Scheduler** (`scheduler.py`): `MissionScheduler` + pure deterministic due math
  (`compute_next_due`, `validate_expression`, `validate_timezone`) for one_time /
  interval / daily / weekly.
- **Event triggers** (`event_triggers.py`): `MissionEventTriggerService` with an
  event-type allowlist, static template binding, allowlisted scalar payload mapping,
  and durable receipt dedup.
- **Runner** (`scheduler_runner.py`): opt-in interval runner (default DISABLED).
- **Control Center**: owner-safe scheduler cell + attention (invalid schedule,
  failed/approval-required occurrence, stale lease, trigger-rejection threshold).
- **CLI**: `scheduler-health` (always) + 11 admin-gated owner-safe commands.
- **Ops**: 8 dedicated BLOCKING `scheduler.*` critical-manifest checks.
- **Tests**: `tests/test_m17_14_mission_scheduler.py` (49).

## Evidence
- New tests: **49 passed**.
- 8 `scheduler.*` manifest checks: **ALL GREEN** via the real manifest runner.
- Harness lineage + CC regression (m17_14/13/12/11/10/9/3, m16): **214 passed**.
- Full suite: **1736 passed / 1 skipped / 0 failed** (+49 over the 1687 baseline).
- Release gate: exit 0 (database_ok / backup_ok / restore_verified true).
- Backup/restore: dedicated test proves schedules + occurrences survive a sqlite
  online backup with `integrity_check == ok`.
- `git diff --check`: clean. Secret scan over changed files: 0 real matches.
- Live CLI: `scheduler-health` works with no admin; `schedules`/`triggers` return
  rc 3 without `SAATHI_HARNESS_ADMIN=1`.

## Security properties proven (deterministic)
- **Delegation only**: static assertion that the scheduler/event modules reference
  no PipelineRunner/adapter/subprocess/run_harness_action; dispatch drives the
  MissionEngine, which produces a real governed pipeline.
- **Idempotency**: one occurrence per due time (unique dedup key); one mission per
  occurrence (deterministic id); re-sweep/re-dispatch create no duplicates.
- **Concurrency**: multi-thread AND multi-process duplicate creation each yield
  exactly one winner; one claim winner; active lease not stealable; expired lease
  recovered.
- **Restart recovery**: crash before claim / after claim (no mission) / after mission
  creation / after mission completion all reconcile safely with no duplicate mission.
- **Approval + ownership**: approval-required scheduled mission stops at
  `approval_required` (never auto-approved); owner mismatch and invalid template
  execute nothing; no retry bypasses approval/owner/param controls.
- **Event trust**: only allowlisted event types accepted; unknown rejected; duplicate
  source event deduplicated; static template binding preserved; unexpected/secret
  payload fields rejected; owner/approval/risk cannot be mapped or overridden; raw
  payload never stored/exposed; one mission per accepted event.
- **Trading Guardian**: not engaged; scheduler/event modules contain no trading
  surface (asserted); scheduling never converts advisory into execution permission.

## Deferred (documented, not pretended)
Cron expressions; arbitrary public webhook ingestion; untrusted JSON mission
definitions; distributed/multi-region scheduling; parallel mission execution;
NL calendar parsing; external SaaS schedulers; production auto-scheduling (the
interval runner is opt-in, default disabled — no OS/cron/cloud provisioning).
