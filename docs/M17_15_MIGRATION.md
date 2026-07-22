# M17.15 Migration — Governed Pipeline Retry, Resume & Checkpoints

## Summary
Purely additive. No data migration, no destructive change, no config change.
Backward compatible with M17.8–M17.14. Revert = single-commit rollback (rollback
point `4cad92a`); any already-created new tables remain inert and harmless.

## Schema (additive, self-materializing)
Two tables added to the SAME harness ledger DB via the existing `_SCHEMA`
`executescript` (`CREATE TABLE IF NOT EXISTS`):
- `pipeline_checkpoint` — one row per `(pipeline_id, step_index)` (UNIQUE), durable
  per-step verified evidence.
- `pipeline_recovery` — one row per `pipeline_id`, recovery/attempt/lease state.

Plus indexes on checkpoint (pipeline, owner) and recovery (owner, state,
next_retry_at). No existing table is altered; the M17.12 `pipeline_run` /
`pipeline_step` records are preserved. An existing ledger DB gains the new tables on
first open; existing rows are untouched. `PRAGMA integrity_check` and backup/restore
continue to pass (release gate exit 0; dedicated backup/restore test green).

## Behavioural change (bounded, governed)
`complete_pipeline` remains terminal-immutable for NORMAL runs. A NEW governed
`reopen_pipeline` transition (failed → running) is the single audited,
attempt-bounded exception used ONLY by the recovery coordinator to resume from the
first non-reusable step. No other pipeline semantics changed: the step loop, the sole
`run_harness_action` path, workspace confinement, and independent verification are
identical (M17.12 pipeline tests unchanged).

## Code changes
- `run_ledger.py` — new checkpoint/recovery constants, safe-field whitelists, ~14
  methods, `reopen_pipeline`, `health()` extension.
- `pipeline.py` — checkpoint writing on verified success; fingerprint helpers;
  `execute_resume`; `_record_failure` recovery seed.
- `pipeline_recovery.py` — NEW coordinator.
- `control_center/aggregator.py` — recovery cell + attention (additive).
- `cli.py` — `pipeline-recovery-health` + 7 admin-gated commands + `_recovery_spec`
  helper.
- `saathi/repair/critical_checks.json` — 9 additive blocking `pipeline_recovery.*`.
- `tests/test_m17_15_pipeline_recovery.py` — NEW (35 tests).

## Compatibility & rollback
- All prior tests pass unchanged (full suite 1771 passed / 1 skipped / 0 failed).
- No public signature of an existing function changed; only new methods/commands and
  one new module were added.
- Roll back by reverting the M17.15 commit. New tables/indexes, if already created,
  are inert without the M17.15 code and may be left or dropped
  (`DROP TABLE pipeline_recovery; pipeline_checkpoint;`).

## Operator notes
- `pipeline-recovery-health` needs no privilege (aggregate census, no secrets).
- Recovery mutations require `SAATHI_HARNESS_ADMIN=1`; the audited operator is the
  verified local OS user. An operator may INVALIDATE a checkpoint but can never mark
  one valid (no force-success command exists).
