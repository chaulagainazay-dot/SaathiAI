# M17.13 Migration — Autonomous Mission Engine

## Summary
Purely additive. No data migration, no destructive change, no config change.
Backward compatible with M17.9–M17.12. Revert = single-commit rollback (rollback
point `186a72f`); the two unused tables would simply remain (harmless).

## Schema (additive, self-materializing)
Two new tables are added to the SAME harness ledger DB via the existing
`_SCHEMA` `executescript` (idempotent `CREATE TABLE IF NOT EXISTS`):

- `mission` — one row per mission (PK `mission_id`).
- `mission_run` — one row per execution attempt (UNIQUE(mission_id, attempt),
  FK → `mission`).

Plus two indexes: `idx_mission_owner(owner, state)`, `idx_mission_run(mission_id,
attempt)`.

No existing table (`run`, `run_transition`, `run_alert`, `run_alert_delivery`,
`pipeline_run`, `pipeline_step`) is altered. An existing ledger DB gains the new
tables on first open (schema is applied on every `RunLedger.__init__`); existing
rows are untouched. `PRAGMA integrity_check` and backup/restore continue to pass
(release gate exit 0).

## Code changes
- `saathi/application_harness/run_ledger.py` — new mission constants, transition
  graph, safe-field whitelist, `_mission_params` helper, 12 mission methods, and a
  `missions` count added to `health()`.
- `saathi/application_harness/mission.py` — NEW module (MissionEngine, templates,
  parameter validation, default `data_bundle` template).
- `saathi/control_center/aggregator.py` — missions cell + `harness_mission`
  attention (additive; degrades gracefully like the other harness reads).
- `saathi/application_harness/cli.py` — 6 mission subcommands (additive; same
  admin-gate + verified-OS-identity model as the M17.9–M17.12 ledger commands).
- `saathi/repair/critical_checks.json` — 7 additive blocking `mission.*` checks.
- `tests/test_m17_13_mission_engine.py` — NEW (32 tests).

## Compatibility & rollback
- All prior tests pass unchanged (full suite 1687 passed / 1 skipped / 0 failed).
- No public signature of an existing function changed; only new methods/commands
  were added.
- To roll back: revert the M17.13 commit. The new tables/indexes, if already
  created in a DB, are inert without the M17.13 code and can be left in place or
  dropped manually (`DROP TABLE mission_run; DROP TABLE mission;`).

## Operator notes
- `mission-health` needs no privilege (aggregate census, no secrets).
- `missions`, `mission-inspect`, `mission-history`, `mission-run`, `mission-retry`
  require `SAATHI_HARNESS_ADMIN=1`; the audited operator is the verified local OS
  user (never a caller-supplied identity). `mission-run` executes under the
  mission's OWN stored owner and halts an approval-required mission safely.
- The older `saathi/missions/` package and its store are unaffected.
