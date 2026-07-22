# Operations Runbook (M13.5)

All commands are real and defined in `saathi/ops/`.

## Startup / status / stale backend
```
uvicorn saathi.server:app --host 0.0.0.0 --port 8765   # start backend
python -m saathi.ops status      # is it listening? duplicate? STALE? (compares running commit vs working tree)
python -m saathi.ops identity    # backend build identity
```
**Stale-backend recovery** (the M11 bug): if `ops status` reports `"stale": true`, the running process predates the code on disk. Identify its PID from `ops status`, confirm ownership, stop it (`kill <pid>`), restart. NEVER kill an unowned/unknown process.

## Health / storage / cleanup
```
python -m saathi.ops health              # storage + db integrity + config
python -m saathi.ops storage             # disk report + thresholds
python -m saathi.ops cleanup             # PREVIEW only (default)
python -m saathi.ops cleanup --apply     # remove temp/partial (never user artifacts)
```
Disk levels: ok (>10GB) · warning (<10GB) · block (<5GB, heavy tasks refused) · critical (<2GB).

## Database
```
python -m saathi.ops db-check    # PRAGMA integrity_check on all app dbs
```

## Backup / restore — see DISASTER_RECOVERY_RUNBOOK.md

## Config / release
```
python -m saathi.ops config-check    # validate env (secrets redacted)
python -m saathi.ops release-check   # staging gates, exit codes 0-12
```

## Incident severity
SEV-0 security/data-loss · SEV-1 outage · SEV-2 major workflow failure · SEV-3 degraded · SEV-4 minor.
Flow: detect (ops status/health) → contain (stop affected process, no destructive action) → diagnose (ops db-check / logs) → recover (restart / restore backup into isolation → verify → swap) → verify (ops health + release-check) → post-incident note.
