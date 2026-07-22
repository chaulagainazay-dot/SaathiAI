# M17.14 Architecture — Governed Mission Scheduler & Trusted Event Triggers

## Position in the stack
The scheduler and the trusted-event bridge sit strictly ABOVE the MissionEngine.
Neither ever executes a pipeline, harness, adapter, shell, tool, or external
service. Their only power is to create/claim a valid mission OCCURRENCE (or, for an
event, one mission) and DELEGATE it to the existing MissionEngine.

```
Scheduler / Trusted Event
        ↓ create + claim a valid occurrence / accept a trusted event
Mission instance
        ↓
MissionEngine            (create → approve gate → enqueue → run)
        ↓ delegates ONE PipelineSpec
PipelineRunner           (sequential, fail-closed, confined)
        ↓ per step
run_harness_action       (ownership → trust → risk/approval → sole adapter → verify)
        ↓
Adapter → independent verification → durable ledger
```

Static guarantee: `scheduler.py` and `event_triggers.py` reference NONE of
`PipelineRunner`, `run_harness_action`, `ApplicationHarnessAdapter`, `subprocess`,
`Popen`, or `os.system` in code (asserted by a test). The ONLY downward call is
`MissionEngine.create/.launch/.inspect`.

## Components (all additive, in the same lineage)
- `run_ledger.py` — 4 additive tables + states + owner-safe methods.
- `scheduler.py` — `MissionScheduler` (validation, deterministic due math,
  occurrence generation, dispatch-via-engine, reconcile, health) + pure due
  functions (`compute_next_due`, `validate_expression`, `validate_timezone`).
- `event_triggers.py` — `MissionEventTriggerService` (allowlist, `ingest_event`,
  payload allowlist mapping, receipt dedup, delegate to engine).
- `scheduler_runner.py` — opt-in interval runner (default DISABLED), overlap-safe,
  restart-safe; one tick = one `sweep()`.
- `control_center/aggregator.py` — owner-safe scheduler cell + attention.
- `cli.py` — `scheduler-health` (always) + admin-gated owner-safe commands.

## Schedule model
`mission_schedule`: schedule_id, owner, mission_template_id, schedule_type,
timezone, expression (JSON), validated params (JSON), enabled, status, description,
retry_policy, version, next_due_at, last_due_at, last_occurrence_id, created_at,
updated_at.

Supported types: `one_time` (`{run_at}`), `interval` (`{interval_sec, anchor}`),
`daily` (`{time:"HH:MM"}`), `weekly` (`{weekday:0-6, time:"HH:MM"}`). Cron is
deliberately NOT implemented (deterministic parsing + strict validation + bounded
complexity not worth the surface this milestone; the smaller model is preferred).

### Determinism & timezone / DST
Timestamps are UTC epoch seconds internally. `daily`/`weekly` wall-clock times are
computed in the schedule's IANA zone via `zoneinfo`, so DST is handled by the
library: a daily 06:00 job stays at 06:00 LOCAL across a DST change and its UTC
epoch shifts by the offset (proven: a US/Eastern spring-forward day is 23h, not
24h). Nonexistent/ambiguous wall-clock times at a DST boundary resolve via
`zoneinfo`'s deterministic `fold` rule. `interval` advances on a stable grid from
its anchor, so the same `(after)` always yields the same next due.

## Schedule states
`active → {paused, completed, disabled, invalid}`, `paused → {active, disabled,
invalid}`. `{completed, disabled, invalid}` are terminal and never silently
reactivate. Only `active` schedules generate occurrences; a `completed` one_time
schedule never runs again.

## Occurrence model & state machine
`mission_occurrence`: occurrence_id, schedule_id, owner, due_at, dedup_key (UNIQUE),
state, claim_owner, lease_expires_at, attempt_count, next_attempt_at, mission_id,
mission_run_id, failure_category, failure_summary, created_at, started_at,
completed_at.

```
pending → claimed → running → {succeeded | failed | blocked | approval_required | cancelled}
   ↑         └→ retry_wait ─┘ (infrastructure failure only)
   └────────────── requeue (crash-before-mission reconcile)
also: pending → {cancelled | expired}
```
Terminal states are immutable. An occurrence is `succeeded` ONLY when its linked
mission reached `completed` — never merely because a mission was created.

- **Dedup key** = `schedule_id:normalized_due_at:version` → `UNIQUE(dedup_key)` ⇒
  each due time yields exactly one occurrence (concurrent creators: one winner).
- **Deterministic mission id** = `ms_ + sha256(occurrence_id)` ⇒ a crash-after-create
  re-attempt maps to the SAME mission (create returns duplicate), so an occurrence
  yields at most one mission.

## Lease-based claiming
`claim_occurrence` is an atomic `BEGIN IMMEDIATE` CAS: only `pending`/due
`retry_wait` with no live lease (`lease_expires_at ≤ now`) can move to `claimed`
with a bounded lease. An ACTIVE lease is never stealable; an expired lease is
recoverable. Durable ledger is the source of truth (not an in-memory lock).

## Dispatch flow (`dispatch_occurrence`)
1. schedule not paused/disabled/invalid (a completed one_time is fine); 2. owner
consistency (occurrence.owner == schedule.owner) BEFORE the engine; 3. template
still exists; 4. params valid (MissionEngine validation); 5. atomic claim;
6. create ONE mission (deterministic id, idempotent); 7–8. link + `engine.launch`;
9. read the AUTHORITATIVE mission state; 10. finish the occurrence with the mapped
terminal state; retry only on a caught infrastructure exception. Mission-outcome and
authority failures (owner/template/params/approval/pipeline-failed) go straight to a
terminal occurrence — never onto the retry path.

## Restart & reconciliation
`reconcile` scans stale-lease occurrences: no mission yet → `requeue` to pending;
mission exists and terminal/approval_required → finalize occurrence from it; mission
mid-flight → re-`launch` (idempotent) then finalize. Never creates a duplicate
mission (deterministic id) or duplicate occurrence (unique dedup key).

## Retry policy
Infrastructure-only, via the shared `RETRY_SCHEDULE` `[0,60,300,900,3600]`s →
`terminal_failed` after the bound. Reuses `retry_delay`; no competing framework.
NOT applied to approval_required / owner mismatch / invalid template / invalid
params / verification / mission terminal failure.

## Trusted event trigger trust model
`ingest_event(event_type, source_event_id, payload)`:
- event_type MUST be in `TRUSTED_EVENT_TYPES` (allowlist) else rejected — no mission.
- a trigger STATICALLY binds owner + template + static params; a payload can never
  choose the template, change the owner, alter risk, or grant approval (a mapping to
  any forbidden field is refused at registration).
- only allowlisted SCALAR payload fields (the trigger's `payload_map` values) are
  read; any unexpected or secret-shaped payload key is rejected; nested objects are
  rejected.
- durable `UNIQUE(dedup_key = trigger_id:source_event_id)` receipt ⇒ a repeated
  source event creates no duplicate mission. Receipts store no raw payload.
- accepted events create ONE mission (deterministic id) via the MissionEngine, so
  approval and per-step risk gates still apply underneath.

## Interval runner
Opt-in (`SAATHI_MISSION_SCHEDULER_ENABLED=1`), default DISABLED. One named daemon
thread; idempotent registration; overlap-protected; restart-safe; a tick exception
never fakes success or kills the loop. No OS launch agent / cron / cloud scheduler
is created.

## Trading Guardian boundary
Not engaged. `scheduler.py`/`event_triggers.py` contain no trading/withdraw/
leverage/order/broker references (asserted). Scheduling never converts advisory
permission into execution permission; approval-required scheduled missions stop at
`approval_required`; risk-4 remains manual-only through the unchanged
`run_harness_action`.
