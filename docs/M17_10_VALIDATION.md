# M17.10 Validation — Harness Run Monitoring & Deterministic Stuck-Run Alerting

Start / rollback point: HEAD `73e97f9` (M17.9). Bounded first slice of "production
monitoring" — the deterministic stuck-run alerting the roadmap gated on a bounded
design. Extends the M17.9 run ledger + Control Center attention + event bus; no
second monitoring stack.

## What was built
- `run_ledger.py` — added a deduplicated alert store to the SAME ledger DB:
  `run_alert` table + partial-unique index `idx_alert_dedup(state_key) WHERE
  status!='resolved'` (at most one non-resolved alert per run+class). Methods:
  `raise_alert` (idempotent), `resolve_alerts` (open→resolved), `open_alerts`
  (owner-safe), `acknowledge_alert` (admin-audited, fail-closed). Auto-resolve
  wired into `complete()` + `reconcile_run()`; alerts purged with runs in
  `cleanup()`; `health()` reports `open_alerts`. Deterministic severity:
  process_missing/cancellation_stuck = high, heartbeat_stale = medium.
- `run_monitor.py` (NEW) — `HarnessRunMonitor.sweep()`: classify active runs,
  raise dedup alerts for heartbeat_stale/cancellation_stuck, reconcile
  process_missing via the ledger's idempotent live-safe path (the ONLY run
  mutation), self-heal (resolve alerts for runs that became active again).
  Deterministic; `now`/thresholds/`is_alive` injectable.
- `control_center/aggregator.py` — `harnesses()` cell exposes owner-safe
  `run_alerts`; `_attention()` folds harness stuck-run alerts into the ranked list
  (`kind: harness_run`, `link: /control/harnesses`); `overview()` passes the
  harness cell.
- `cli.py` — 3 admin-maintenance commands (`SAATHI_HARNESS_ADMIN=1`, verified OS
  identity, audited): `runs-monitor` (sweep), `run-alerts` (open alerts),
  `alert-ack <id>` (acknowledge). No caller-supplied identity trusted.
- `critical_checks.json` — 2 dedicated **blocking** entries
  (`ledger.monitor_alerting`, `ledger.monitor_control_center_contract`).

## Proven properties (executed)
Environment: `.venv` Python 3.12, macOS/darwin, POSIX; spawn multiprocessing.

- **Dedup / replay idempotency** — a second sweep over the same stuck run raises no
  new alert; `raise_alert` repeat is a no-op (`test_repeated_sweep_...`).
- **Deterministic severity** — heartbeat_stale=medium, cancellation_stuck=high
  (`test_sweep_raises_heartbeat_stale_alert`, `..._cancellation_stuck_high`).
- **Self-heal** — a run that resumes heartbeating clears its alert
  (`test_self_heal_resolves_when_run_active_again`).
- **Terminal auto-resolve** — completion and crash-reconcile both clear open alerts
  (`test_terminal_auto_resolves_open_alerts`, `test_crash_reconcile_auto_resolves_alerts`).
- **process_missing reconciled** — sweep recovers a dead-PID run, no lingering
  alert (`test_sweep_reconciles_process_missing`).
- **Owner scoping + owner-safe** — `open_alerts` is owner-filtered and exposes no
  argv/output/secrets (`test_open_alerts_owner_scoped_and_safe`).
- **Admin-audited acknowledge, fail-closed** — audited with the verified OS
  operator id; unknown alert and empty operator refused
  (`test_acknowledge_alert_audited_and_fail_closed`).
- **Concurrent multi-PROCESS sweep** — 6 spawned processes sweep the same stuck
  run → exactly 1 alert; integrity ok (`test_concurrent_sweeps_no_duplicate_alerts`).
- **Restart persistence** — alerts survive a fresh ledger object on the same file
  (`test_alerts_persist_across_restart`).
- **Control Center attention contract** — stuck harness runs surface in
  `/control` attention, severity-ranked, owner-safe
  (`test_control_center_attention_surfaces_alerts`).
- **CLI admin gating** — monitor/alerts/ack refused (exit 3) without
  `SAATHI_HARNESS_ADMIN=1`; audited under admin (`test_cli_monitor_commands_admin_gated`).
- **Backward compatibility** — M17.9 `health` still ok; all M17.9 suites unchanged
  (`test_m17_9_health_still_reports_ok`).

## Validation ladder (run, results)
1. M17.10 suite (`test_m17_10_run_monitor.py`) → **15 passed**.
2. M17.9 suites (unit/concurrency/live/redteam/integration) + Control Center →
   **100 passed** together (M17.9 unchanged; control_center unchanged).
3. Dedicated Critical Manifest — 2 blocking monitor entries via the real manifest
   runner → **green** (dedup, auto-resolve, concurrency, owner-scope, audited ack,
   attention contract, CLI gating).
4. Server import + route count → **308 routes** (≥290).
5. Release check → exit 0; database_ok / backup_ok / restore_verified true.
6. Secret scan over M17.10 files → **0 matches**.
7. Full suite → **1598 passed / 1 skipped / 0 failed** (+15 over the 1,583 M17.9
   baseline).
8. `git diff --check` → clean.
9. Milestone-owned tree clean; `saathi/memory/conventions.md` modified + **unstaged**.

## Security
Alerts owner-safe (no argv/output/secrets/approval material). The sweep's only
run-mutation is reconciling genuinely dead runs (M17.9-proven idempotent, never
overwrites a live process); `raise_alert` never mutates a run. `acknowledge_alert`
admin-only, audited with verified OS identity, fail-closed. No weakening of M17.9
authn/authz/audit/CAS/terminal-immutability/critical checks.

## Trading Guardian
Not engaged — this milestone touches no financial action, external API, portfolio
operation, or autonomous execution. No live autonomous trading is enabled or
altered.

## Migration / compatibility
Additive `CREATE TABLE IF NOT EXISTS run_alert` — existing ledger DBs gain the
table on next open; no destructive migration, no data rewrite. M17.9 fully
preserved. Rollback = revert the single commit (existing DBs retain an unused table).

## Known limitations
- `verification_stuck` alerting deferred (needs a verification-pipeline hook).
- No external alert transports (email/Slack/PagerDuty) and no live scheduler cron
  wiring — the sweep is a deterministic, schedulable call; no background side
  effect is started here.
- Single-node local; multi-user LOAD still unproven.

## Verdict
**HARNESS RUN MONITORING STAGING READY** — deterministic, deduplicated, self-
resolving stuck-run alerting over the M17.9 ledger, surfaced through the existing
Control Center attention + event bus, with an admin-audited acknowledge path and a
green blocking Critical Manifest entry. NOT production-ready (external alert
transports, scheduled sweeps, multi-user load, and an incident-response drill
remain).
