# M55 Backup Validation

`POST /api/v1/platform/release/backup` (owner/admin, `ORG_MANAGE`).
**Simulation only — no destructive restore. No operator data is deleted.**

## Manifest
schema version, database_name (**basename only**, no path), size_bytes, checksum
(`sha256:` of the DB file), integrity_check (`PRAGMA integrity_check`),
restore_simulation (PASS/FAIL), restore_verified_tables, restore_error,
`destructive_restore: false`, `mode: "SIMULATION_ONLY"`, history_count.

## Restore simulation
1. Copy the live SQLite file to a temporary path (never mutate the original).
2. Open the copy and run `PRAGMA integrity_check`.
3. Verify required tables exist (`sessions`, `organizations`, `workspaces`,
   `platform_executions`).
4. Remove the temporary copy.

The simulation proves a backup could be restored and verified, without performing
any destructive restore against the live database.

## Backup history
A bounded (last 20) history of `{checksum, size_bytes, integrity}` is persisted in
the `m55_backup_history` config key — metadata only, no data, no secrets.

## Audit
Each validation emits `release.backup_validated` with the checksum and integrity
outcome.

## Boundary
Real destructive restore and real retention purge remain deferred behind explicit
owner confirmation and a backup rehearsal in a later milestone.
