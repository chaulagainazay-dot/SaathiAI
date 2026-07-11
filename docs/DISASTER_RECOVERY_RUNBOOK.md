# Disaster Recovery Runbook (M13.5)

## Backup
```
python -m saathi.ops backup [label]    # real checksum-verified backup of all app dbs
python -m saathi.ops backups           # list
python -m saathi.ops verify-backup <archive>   # restore into temp + verify (read-only to live)
python -m saathi.ops prune-backups --keep 5
```
Backups include: chat/memory/agent_runtime/voice_os/studio_os dbs + a redacted config manifest (presence-only). They EXCLUDE: provider keys, .env, firebase-admin.json, session cookies, temp render files, media binaries.

## Restore
```
python -m saathi.ops restore <archive> --target <isolated-dir>
python -m saathi.ops verify-restore <isolated-dir>
```
Restore ALWAYS goes to an isolated directory (refuses to overwrite the live `data/`). Verification re-checks every db checksum, runs `PRAGMA integrity_check`, and confirms schema versions.

## Real drill result (this milestone)
5 app dbs backed up (18KB), restored into an isolated temp dir, **all 5 checksums matched, all 5 integrity_check = ok, schema match, restored dbs queryable**. Live-dir restore correctly refused. Path-traversal archive correctly rejected.

## RPO / RTO
- **RPO**: last successful `ops backup` (run on a schedule; sub-second for the current db sizes).
- **RTO**: seconds (restore + verify of ~20KB completes in <1s locally; scales with db size).
- **Unavailable media**: media binaries are NOT in backups — they are regenerable artifacts referenced by storage_uri; a restored project reports missing media files, it does not fabricate them.

## Corruption handling
`ops db-check` detects corruption (`PRAGMA integrity_check` != ok); restore the latest verified backup into an isolated dir, verify, then (operator action) swap it in after stopping the backend.
