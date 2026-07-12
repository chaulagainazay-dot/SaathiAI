# M17.9 Validation — Durable Run Ledger, Concurrency Safety & Recovery Ops

Closes the top M17.8 limitation set (single-process append-only journal;
concurrency unproven at scale; no blocking Critical Manifest entry) by upgrading
long-running harness run-tracking into a transactional, ownership-safe SQLite run
ledger. No new execution engine: every task still runs through the ONE
`ApplicationHarnessAdapter` — the adapter is byte-unchanged; a `RunLedger` passed
as its `journal=` durably ledgers the same lifecycle.

## What was built
- `run_ledger.py` — SQLite ledger (`data/application_harness_runs/ledger.db`, WAL +
  busy_timeout). Explicit state set + transition graph; one write primitive
  (`_transition`) does `BEGIN IMMEDIATE` + terminal/edge/`require_from`/stale-version
  checks + **compare-and-set on `state_version`** + transition-row insert. Lifecycle
  (`create_run`/`claim`/`mark_running`/`request_cancellation`/`admin_cancel`/
  `complete`/`record_heartbeat`), recovery (`reconcile_run`/`reconcile_stale`/
  `mark_recovery`/`cleanup`/`classify`), reads (`inspect`/`list_active`/
  `transitions`/`read_model`/`health`), and an M17.8 journal drop-in.
- `ledger_migration.py` — read-only JSONL → ledger migration: backup, provenance +
  timestamp preservation, malformed/injection rejection, idempotent, reversible.
- `cli.py` — `ledger-health` (aggregate, always); all other ledger ops
  admin-maintenance-only (`SAATHI_HARNESS_ADMIN=1`), actor = verified local OS
  identity, audited. No caller-supplied identity is ever trusted.
- `control_center/aggregator.py` — owner-scoped `run_ledger` read model +
  `ledger_health` in the harness cell (degrades gracefully; owner-safe).
- `db_integrity.py` — ledger db added to release DB-integrity/backup/restore gates.
- `critical_checks.json` — 11 dedicated **blocking** `ledger.*` entries.

## State machine (fail closed)
`queued → starting → running → {succeeded|failed|timed_out|cancellation_requested
|crash_recovered|stop_uncertain}`; `cancellation_requested → {cancelled|succeeded|
failed|timed_out|crash_recovered|stop_uncertain}`. Terminal set is immutable. Any
edge not in the graph is rejected.

## Proven properties (executed evidence)
Environment: `.venv` Python 3.12, macOS/darwin, POSIX; multiprocessing start
method `spawn` (genuine separate interpreters, NOT threads).

- **One claimant per run** — 8 spawned processes race `claim` on the same queued
  run; exactly 1 wins (`test_concurrent_claim_exactly_one_winner`, `..._duplicate_claim`).
- **Terminal immutability / no resurrection** — a terminal run rejects every
  transition back to an active state (`test_terminal_state_is_immutable`,
  `test_probe_terminal_resurrection`).
- **Stale writer fails closed** — a transition with an out-of-date `state_version`
  raises, never applies (`test_stale_version_rejected`, `test_probe_stale_writer`).
- **Cancellation/completion race** — multi-process race converges on a single legal
  state with ≤1 `succeeded` transition and `integrity=ok`
  (`test_completion_cancel_race_is_deterministic`).
- **Ownership-safe cancel** — cross-user `request_cancellation` denied; CLI never
  trusts `--requester`/`--owner`; mutations gated to admin + OS identity
  (`test_cross_user_cancel_denied`, `test_cli_mutations_and_reads_require_admin_mode`,
  `test_cli_no_requester_or_owner_flag_is_trusted`).
- **Exactly-once, idempotent crash recovery** — a dead-PID run reconciles to
  `crash_recovered` once; repeat sweeps do nothing; a live PID is never overwritten
  (`test_live_crash_reconciled`, `test_reconcile_dead_pid_once_and_idempotent`,
  `test_probe_recovery_of_live_process`).
- **Restart persistence** — a fresh ledger object on the same db file sees prior
  terminal state; `integrity=ok` (`test_restart_persistence`).
- **Backup + isolated restore** — WAL-checkpointed single-file backup restored into
  an isolated dir preserves terminal results + transition history + integrity
  (`test_backup_and_isolated_restore_preserves_ledger`).
- **Idempotency uniqueness** — a duplicate idempotency key returns the first run,
  creates no second row, no second side effect (`test_idempotency_key_prevents_duplicate_run`).
- **Migration safe/reversible** — legacy JSONL backed up + left untouched; provenance
  + timestamps preserved; malformed/unknown-state/control-char records rejected;
  idempotent; `rollback` removes only migrated rows; never overwrites a live run
  (`test_migration_*`, `test_probe_migration_record_injection`).
- **No process-control bypass** — the ledger performs zero process signalling; the
  only `os.kill` is the signal-0 liveness probe (`test_probe_no_process_control_in_ledger`).
- **DB path safety** — NUL and symlink-substituted ledger paths are rejected
  (`test_probe_db_path_nul`, `test_probe_symlink_db_substitution`).
- **Secret-safe** — secret-shaped metadata rejected; read model / CLI expose no
  argv/output/secrets/approval material (`test_probe_secret_injection`,
  `test_read_model_is_owner_safe`, `test_cli_admin_mode_reads_are_owner_safe`).
- **Bounded history / lock DoS** — transition history capped; `busy_timeout` bounds
  lock waits (`test_probe_unbounded_history_capped`, `test_probe_lock_dos_has_busy_timeout`).

## Validation ladder (run, results)
1. M17.9 unit — `test_m17_9_run_ledger.py` → **33 passed**.
2. Multi-process concurrency — `test_m17_9_concurrency.py` (spawn) → **6 passed**.
3. Live lifecycle + backup/restore — `test_m17_9_live.py` → **7 passed**.
4. Red-team probes — `test_m17_9_redteam.py` → **19 passed**.
5. Integration/CLI/Control-Center/event-bus — `test_m17_9_integration.py` → **9 passed**.
   (M17.9 scoped total: **74 passed**.)
6. Regression batch (harness M17.3–8, task_control, run_journal, control_center,
   events, execution_gateway, m15_2 red-team) → **325 passed, 0 failed**.
7. Dedicated Critical Manifest — 11 blocking `ledger.*` checks executed through the
   real manifest runner → **all green** (verified: import/migration, valid
   transitions, terminal immutability, one claimant, ownership-safe cancel, crash
   recovery, stale reconciliation, no process-control bypass, idempotency
   uniqueness, database integrity, Control Center contract).
8. Server import + route count → **308 routes** (gate ≥ 290).
9. Release check (`release_check`) → exit 0; database_ok, backup_ok,
   restore_verified all true (ledger db now covered by `db_integrity.APP_DBS`).
10. Database integrity — `PRAGMA integrity_check = ok` on the ledger; foreign-key
    check clean.
11. Secret scan (regex over all M17.9 files) → **0 matches**.
12. Full suite → **see FINAL LINE below**.
13. `git diff --check` → clean.
14. Milestone-owned tree clean; unrelated `saathi/memory/conventions.md` left
    modified + **unstaged** (deliberately excluded).

FINAL FULL SUITE: 1,583 passed / 1 skipped / 0 failed (pre-existing environmental
skip; +74 M17.9 tests over the M17.8 baseline of 1,509).

## Pause/resume scope (truthful)
Capability = **contract_ready**: the contract is defined; process suspension
(SIGSTOP/SIGCONT) is deferred and, if later built, would be gateway-controlled,
identity-verified, ownership-gated, and classified as *process suspension, not
application checkpointing*. Checkpointing is NOT implemented and NOT claimed.

## Known limitations
- Single-node local ledger; not a distributed/multi-node store.
- No production monitoring/alerting dashboard yet (read model + `classify` +
  `reconcile_stale` attention items are the substrate for one).
- Multi-user proven by cross-user gates + local multi-process, not multi-user load.
- Pause/resume/checkpoint deferred (contract-only).

## Verdict
**RUN LEDGER STAGING READY** — transactional state, terminal immutability, one
claimant per run (multi-process proven), ownership isolation, deterministic
cancel/complete races, exactly-once idempotent crash recovery, restart + backup/
restore persistence, safe reversible JSONL migration, a dedicated green blocking
Critical Manifest entry, and a real Control Center read model — all through the
single adapter boundary. NOT production-ready (needs multi-user load, production
monitoring/alerting, representative deployment, and an incident-response drill).
