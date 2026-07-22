# M17.9 Implementation Plan — Durable Run Ledger

No new execution engine. Preserve the canonical chain:

```
HarnessTaskController → ExecutionGateway → ApplicationHarnessAdapter → process
  → transactional run ledger → verification → evidence → event bus → Control Center
```

## 1. Ledger core (`saathi/application_harness/run_ledger.py`)
- SQLite store following the canonical `ConnectorStore` pattern (`data/*.db`,
  `_SCHEMA` executescript, row_factory, unique indexes, event-bus emission).
- `data/application_harness_runs/ledger.db`; WAL + `busy_timeout` for multi-process.
- `run` table with the full identity/lifecycle column set (owner, device, os_user,
  session, harness, installation, operation, intent digest, approval id,
  idempotency key, pid/pgid, state, **state_version**, timestamps, heartbeat,
  cancel-requested, terminal, exit/signal, timeout, failure code, verification
  status, artifact refs, recovery status, correlation id, origin).
- `run_transition` append table for bounded transition history.
- Explicit state set + transition graph (`VALID`); anything unlisted is rejected
  (fail closed). Terminal set immutable.
- `_transition()` = the ONE write primitive: `BEGIN IMMEDIATE` + read state/version
  + terminal/edge/`require_from`/stale-version checks + **CAS** UPDATE guarded by
  `state_version` + transition-row insert. Exactly one caller wins.
- Sanitization on the way in: reject secret-shaped metadata and control chars;
  validate db path (no NUL, no symlink substitution).

## 2. Lifecycle + recovery API
- `create_run` (queued, idempotency-unique), `claim` (queued→starting, one winner),
  `mark_running`, `request_cancellation` (owner-gated, idempotent),
  `admin_cancel` (operator-audited maintenance), `complete` (→terminal),
  `record_heartbeat` (active-only).
- Recovery: `reconcile_run`, `reconcile_stale` (dead→crash_recovered + attention),
  `mark_recovery` (evidence only, no rerun), `transitions`, `cleanup` (retention),
  `classify` (active|heartbeat_stale|process_missing|cancellation_stuck|terminal).
- `read_model` (owner-safe Control Center view), `health` (integrity + census).
- M17.8 journal drop-in (`record_start`/`record_end`/`active_runs`/`reconcile`/
  `latest_state`) so the adapter ledgers state with **no adapter change**.

## 3. Migration (`ledger_migration.py`)
- Legacy JSONL is READ-ONLY. `migrate_jsonl`: back up the file, fold records,
  import at final state with `origin='migrated_jsonl'`, preserve timestamps +
  terminal results, reject malformed/unknown-state/control-char records, be
  idempotent. `rollback` deletes only migrated rows. No secrets imported.

## 4. Surfaces
- CLI (`cli.py`): `ledger-health` (aggregate, always). All other ledger commands
  are **admin-maintenance-only** (`SAATHI_HARNESS_ADMIN=1`), actor = verified local
  OS identity, audited; no caller-supplied `--requester`/`--owner` is trusted.
- Control Center (`aggregator.harnesses`): owner-scoped `run_ledger` read model +
  aggregate `ledger_health`; degrades gracefully; never exposes argv/output/secrets.
- Release DB integrity (`db_integrity.APP_DBS`): add the ledger db so backup/restore
  + integrity gates cover it.

## 5. Pause/resume scope
- Capability = `contract_ready` (contract defined, not implemented). SIGSTOP/SIGCONT
  is real POSIX process suspension but is deferred; it is NOT application
  checkpointing and is not claimed as such.

## 6. Tests + gates
- Unit (`test_m17_9_run_ledger.py`), multi-**process** concurrency
  (`test_m17_9_concurrency.py`, `spawn`), live process lifecycle + backup/restore
  (`test_m17_9_live.py`), red-team probes (`test_m17_9_redteam.py`),
  integration/CLI/Control-Center/event-bus (`test_m17_9_integration.py`).
- Dedicated **blocking** Critical Manifest entries (`ledger.*`).
- Full validation ladder in `M17_9_VALIDATION.md`.

## Out of scope (explicit)
Application checkpointing; general pause/resume; production monitoring/alerting
dashboard; multi-user load; deploy/rollback. Production-ready is not claimed.
