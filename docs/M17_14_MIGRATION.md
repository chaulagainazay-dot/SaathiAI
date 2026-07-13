# M17.14 Migration — Governed Mission Scheduler & Trusted Event Triggers

## Summary
Purely additive. No data migration, no destructive change, no config change.
Backward compatible with M17.8–M17.13. Revert = single-commit rollback (rollback
point `73fd251`); any already-created new tables remain inert and harmless.

## Schema (additive, self-materializing)
Four tables are added to the SAME harness ledger DB via the existing `_SCHEMA`
`executescript` (idempotent `CREATE TABLE IF NOT EXISTS`):

- `mission_schedule` — durable schedule definitions (PK `schedule_id`).
- `mission_occurrence` — one row per due time (PK `occurrence_id`,
  `UNIQUE(dedup_key)`).
- `mission_event_trigger` — trusted-event subscriptions (PK `trigger_id`).
- `mission_event_receipt` — durable event receipts (PK `receipt_id`,
  `UNIQUE(dedup_key)`).

Plus indexes on owner/status, due time, occurrence state/next_attempt, schedule
linkage, event type, and receipt owner.

Constraints enforcing the invariants:
- PK uniqueness on every table;
- `UNIQUE(dedup_key)` on `mission_occurrence` (one occurrence per due time);
- `UNIQUE(dedup_key)` on `mission_event_receipt` (one mission per source event);
- application-level owner consistency + schedule/occurrence relationship (a hard
  FK on `mission_occurrence` was intentionally NOT used, per the milestone's
  "FK OR application-level relationship" allowance, so occurrences can be created
  and reconciled independently and the schema stays flexible under `foreign_keys=ON`).

No existing table (`run`, `run_transition`, `run_alert`, `run_alert_delivery`,
`pipeline_run`, `pipeline_step`, `mission`, `mission_run`) is altered. An existing
ledger DB gains the new tables on first open; existing rows are untouched.
`PRAGMA integrity_check` and backup/restore continue to pass (release gate exit 0;
dedicated backup/restore test green).

## Code changes
- `saathi/application_harness/run_ledger.py` — new constants, transition graphs,
  safe-field whitelists, ~30 schedule/occurrence/trigger/receipt methods, and
  `health()` census extension.
- `saathi/application_harness/scheduler.py` — NEW (MissionScheduler + due math).
- `saathi/application_harness/event_triggers.py` — NEW (trusted event bridge).
- `saathi/application_harness/scheduler_runner.py` — NEW (opt-in interval runner).
- `saathi/control_center/aggregator.py` — scheduler cell + attention (additive;
  degrades gracefully).
- `saathi/application_harness/cli.py` — 12 scheduler subcommands (additive; same
  admin-gate + verified-OS-identity model as M17.9–M17.13).
- `saathi/repair/critical_checks.json` — 8 additive blocking `scheduler.*` checks.
- `tests/test_m17_14_mission_scheduler.py` — NEW (49 tests).

## Compatibility & rollback
- All prior tests pass unchanged (full suite 1736 passed / 1 skipped / 0 failed).
- No public signature of an existing function changed; only new methods/commands
  and new modules were added.
- Roll back by reverting the M17.14 commit. New tables/indexes, if already created,
  are inert without the M17.14 code and may be left or dropped
  (`DROP TABLE mission_event_receipt; mission_event_trigger; mission_occurrence;
  mission_schedule;`).

## Operator notes
- `scheduler-health` needs no privilege (aggregate census, no secrets).
- All other scheduler commands require `SAATHI_HARNESS_ADMIN=1`; the audited
  operator is the verified local OS user. The interval runner is opt-in via
  `SAATHI_MISSION_SCHEDULER_ENABLED=1` (default off; no OS/cron/cloud provisioning).
