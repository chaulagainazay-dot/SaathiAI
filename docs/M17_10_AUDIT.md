# M17.10 Audit — Harness Run Monitoring & Deterministic Stuck-Run Alerting

Start / rollback point: HEAD `73e97f9` (M17.9 durable run ledger). Branch
`milestone/m7-security-engine`. Full suite at start: 1,583 passed / 1 skipped.

## Next milestone (from repository evidence, not invented)
**M17.10 — Harness Run Monitoring & Deterministic Stuck-Run Alerting.**

Why this is the correct next milestone:
- `docs/AUTONOMOUS_ROADMAP.md` lists "production monitoring" as a next candidate
  "once … a bounded design exists" — this milestone IS that bounded design (the
  first slice, not the full dashboard).
- `docs/AUTONOMOUS_LOOP_STATE.json` unverified_items: "production monitoring/
  alerting dashboard (not built; M17.9 read model + reconcile_stale is the
  substrate)".
- `docs/TECHNICAL_DEBT.md`: "Production monitoring/alerting/incident-response
  automation absent (M17.9 ledger read model + reconcile_stale attention items are
  the substrate for it)."
- `docs/CAPABILITY_MATURITY_MATRIX.md`: "Production monitoring/alerting | not built
  (substrate ready)".
- It is fully local — no credential/install/deploy blocker (unlike browser-auth,
  GUI apps, native TCC actuation, staging deploy — all still blocked).
- It **extends** existing subsystems (M17.9 run ledger, Control Center
  `_attention` + `/attention` API/CLI, event bus) rather than building a parallel
  monitoring stack.

Rejected alternatives (ranked): (2) multi-user LOAD concurrency — a validation
exercise, not a new capability, lower value; (3) pause/resume/checkpoint — deferred,
larger, risky (process suspension), explicitly `contract_ready` only; workflow
intelligence — explicitly gated/premature; registry-persist-on-boot — bounded but
low strategic value and off the reliability thread.

## Current capabilities already present
- M17.9 ledger: transactional state machine, `classify()` →
  active|heartbeat_stale|process_missing|cancellation_stuck|terminal,
  `reconcile_stale()` (idempotent, live-safe), `read_model()` (owner-safe),
  `list_active()`, event-bus emission, `health()`.
- Control Center: `_attention()` severity-ranked composition, `/control/attention`
  API, `control_center attention` CLI, `harnesses()` cell.
- Event bus: `publish_sync`.

## Gaps this milestone closes
- Classification exists but produces **no persistent, deduplicated alert** — a
  stuck run is re-observed every sweep with no memory, so there is no operator
  signal that survives, no de-duplication, and no acknowledge/resolve lifecycle.
- Control Center attention does **not** surface stuck harness runs.
- No deterministic, schedulable **sweep** operation.

## Design (extends, no parallel architecture)
- Ledger: add `run_alert` table (same DB) + methods `raise_alert` (idempotent via
  UNIQUE `state_key`), `resolve_alerts` (open→resolved; called on every terminal
  transition + crash reconcile → self-consistent), `open_alerts` (owner-safe),
  `acknowledge_alert` (admin-audited, fail-closed). Severity is deterministic:
  process_missing/cancellation_stuck = high, heartbeat_stale = medium.
- New `run_monitor.py`: `HarnessRunMonitor.sweep()` — classify active runs; raise
  dedup alerts for heartbeat_stale/cancellation_stuck; reconcile process_missing
  (delegates to the ledger's existing idempotent, live-safe path — the ONLY
  mutation of a run); self-heal (resolve stale/cancel alerts for runs that became
  active again). Deterministic; `now`/thresholds/`is_alive` injectable.
- Control Center: `harnesses()` cell gains owner-safe `open_alerts`; `_attention()`
  folds harness stuck-run alerts into the ranked list (`kind: harness_run`).
- CLI (existing admin-maintenance gate, `SAATHI_HARNESS_ADMIN=1`, verified OS
  identity, audited): `runs-monitor` (sweep), `run-alerts` (open alerts),
  `alert-ack <id>` (audited acknowledge).

## Files likely to change
- `saathi/application_harness/run_ledger.py` (add alert table + methods; wire
  resolve into complete/reconcile_run).
- `saathi/application_harness/run_monitor.py` (NEW).
- `saathi/application_harness/cli.py` (3 admin-gated commands).
- `saathi/control_center/aggregator.py` (`harnesses` cell + `_attention` + overview).
- `saathi/repair/critical_checks.json` (1 blocking entry).
- `tests/test_m17_10_run_monitor.py` (NEW).
- docs: this audit, `M17_10_VALIDATION.md`, TECHNICAL_DEBT, CAPABILITY matrix,
  ROADMAP, LOOP_STATE, Brain/Business/Writing.

## Tests required
happy-path sweep; invalid input; unauthorized/privilege-escalation (ack without
admin; caller identity never trusted); concurrent (multi-process) sweep — no
duplicate alerts; duplicate/replay idempotency; partial failure; restart/recovery
(alert persistence); integrity; auto-resolve on terminal; self-heal; audit
evidence (alert + ack events); backward compatibility (all M17.9 tests unchanged);
Control Center attention contract; CLI admin gating.

## Security implications
- Alerts are **owner-safe** — no argv, output, secrets, approval material.
- The sweep's only run-mutation is reconciling genuinely dead runs (M17.9-proven
  idempotent, never overwrites a live process). `raise_alert` never mutates a run.
- `acknowledge_alert` is admin-only, audited with the verified OS operator id, and
  fails closed (not found / not open → refused). No caller-supplied identity is
  trusted (reuses the M17.9 CLI security model).
- No weakening of M17.9 authn/authz/audit/CAS/terminal-immutability/critical checks.

## Migration / compatibility risks
- Additive `CREATE TABLE IF NOT EXISTS run_alert` — existing ledger DBs gain the
  table on next open; no destructive migration, no data rewrite. Fully backward
  compatible; M17.9 behavior preserved.

## Trading Guardian
This milestone touches **no** financial action, external API, portfolio operation,
or autonomous execution. It is harness-run observability only. Trading Guardian
gates are therefore **not engaged**; no live autonomous trading is enabled or
altered. (Explicitly out of scope.)

## Out of scope
- `verification_stuck` alerting (needs a verification-pipeline hook that does not
  exist yet).
- Full monitoring dashboard / external alert transports (email/Slack/PagerDuty).
- Multi-user LOAD testing; deploy/rollback drill; pause/resume/checkpoint.
- Live scheduler cron wiring (sweep is exposed as a deterministic, schedulable
  call; no background side effect is started in this milestone).

## Acceptance criteria
1. Sweep raises a deduplicated alert per (run, class); a second sweep raises none.
2. Reaching a terminal state auto-resolves that run's open alerts.
3. A run that resumes heartbeating self-heals (its stale alert resolves).
4. `open_alerts` is owner-scoped and owner-safe.
5. `acknowledge_alert` is admin-audited and fails closed for non-admin / unknown.
6. Concurrent multi-process sweeps produce no duplicate alerts; integrity ok.
7. Alerts persist across a ledger restart.
8. Control Center attention surfaces stuck harness runs, severity-ranked.
9. A dedicated **blocking** Critical Manifest entry is green.
10. All M17.9 tests still pass; full suite green.

## Rollback strategy
Single bounded commit on top of `73e97f9`. Revert restores M17.9 exactly. The new
table is additive and unused by M17.9 code paths, so a revert leaves no orphaned
behavior (an existing DB simply retains an unused table).
