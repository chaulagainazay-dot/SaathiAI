# M17.11 Validation — Scheduled Run Monitoring & Reliable Alert Delivery

Start / rollback point: HEAD `28ce958` (M17.10). Makes the M17.10 monitoring
substrate operationally useful by wiring deterministic scheduled sweeps and durable,
deduplicated, retryable alert delivery through existing SaathiOS systems. No second
monitoring engine / scheduler / bus / ledger / permission model / Control Center.

## What was built
- `run_ledger.py` — additive `run_alert_delivery` table (FK → `run_alert`) in the
  SAME ledger DB. Unique `idem_key = alert_id:channel:destination:fingerprint` →
  one active delivery per alert+channel+destination+payload version. Methods:
  `create_delivery` (idempotent), `claim_delivery` (lease CAS), `mark_delivered`,
  `mark_attempt_failed` (retry_wait / terminal_failed), `suppress_deliveries_for_alert`,
  `reclaim_stale_deliveries`, `admin_retry_delivery` (audited), `delivery`,
  `deliveries_for_alert`, `pending_dispatchable`, `open_deliveries` (owner-safe),
  `delivery_health`, `alert_by_id`. Suppression wired into `resolve_alerts` +
  `acknowledge_alert`. Deterministic `RETRY_SCHEDULE = (0, 60, 300, 900, 3600)` s,
  `MAX_DELIVERY_ATTEMPTS = 5`.
- `notify.py` (NEW) — `AlertNotification`/`DeliveryResult` (frozen, owner-safe),
  `AlertTransport` Protocol, `LocalFileTransport` (durable JSONL under the
  gitignored ledger data dir, credential-free, fingerprint-idempotent, never fakes
  success), `DisabledTransport`/`UnconfiguredTransport` (fail closed),
  `NotificationDispatcher` (`enqueue` policy + `dispatch_once` + `run_once`;
  injectable clock; no real sleeps).
- `run_scheduler.py` (NEW) — `MonitorScheduler`: one named job (`harness.monitor.sweep`),
  idempotent `register_once`/`start`, overlap lock, **default DISABLED**
  (`SAATHI_HARNESS_MONITOR_ENABLED=1`), restart-safe (reclaim stale leases + resume
  retry_wait from persisted timing), sweep_started/finished/failed events. Mirrors
  the existing `storage svc.start(interval_seconds=60)` pattern — not a new framework.
- `control_center/aggregator.py` — `harnesses()` cell exposes owner-safe
  `run_deliveries` + `delivery_health` + `monitor_schedule`; `_attention()` folds
  terminal delivery failures (`kind: harness_notification`, high).
- `cli.py` — 4 admin-maintenance commands (`SAATHI_HARNESS_ADMIN=1`, verified OS
  identity, audited): `notify-dispatch`, `alert-deliveries`, `retry-delivery <id>`,
  `monitor-schedule-status`.
- `critical_checks.json` — 7 dedicated **blocking** `notification.*` entries.

## Delivery state machine
`pending → attempting → {delivered | retry_wait | terminal_failed}`;
`retry_wait → attempting`; `pending|retry_wait → suppressed` (alert resolved/ack);
`terminal_failed → retry_wait` (admin retry only). delivered/suppressed/cancelled
immutable; terminal_failed immutable except audited admin retry. CAS under
`BEGIN IMMEDIATE`; lease-based claim (`claim_owner`/`claim_at`).

## Notification policy (deterministic, no LLM)
Only OPEN alerts create deliveries (acknowledged → none); unknown alert class fails
closed; resolved/acknowledged alerts suppress pending deliveries;
`fingerprint = sha256(run_id|class|severity)` is the payload version; repeated
sweeps create no duplicate (idem_key dedup).

## Retry (bounded, deterministic)
Attempt N delay = `RETRY_SCHEDULE[N]` (0/60/300/900/3600 s); attempt 5 exhausted →
`terminal_failed`. `next_attempt_at` persisted → restart-safe. No jitter, no real
sleeps (injectable clock). Delivered records never retried; terminal failures
require explicit audited admin retry.

## Send-before-persist strategy
At-least-once with **local transport idempotency** (fingerprint marker) + **stale-
claim reclaim**: crash after send / before persist leaves the row `attempting`; on
restart `reclaim_stale_deliveries` returns it to `retry_wait`; re-dispatch hits the
transport idempotency marker → `idempotent=True` → `mark_delivered` (no duplicate
write). Uncertainty is never hidden.

## Proven properties (executed)
Environment: `.venv` Python 3.12, macOS/darwin, POSIX; spawn multiprocessing.

- Alert → exactly one delivery; repeated enqueue no duplicate
  (`test_alert_creates_one_delivery`, `test_repeated_enqueue_no_duplicate`).
- Successful local delivery writes ONE owner-safe JSONL line (no argv/output/secrets);
  transport idempotent (`test_successful_local_delivery_writes_durable_evidence`,
  `test_local_transport_idempotent`).
- Resolved + acknowledged alerts suppress pending deliveries; acknowledged creates
  no new delivery (`test_resolved_alert_suppresses_pending_delivery`,
  `test_acknowledged_alert_suppresses_pending_delivery`,
  `test_acknowledged_alert_creates_no_new_delivery`).
- Deterministic retry (+60 s), max attempts → terminal_failed, delivered never
  retried, restart resumes retry_wait, admin retry of terminal failure, empty
  operator rejected (`test_first_failure_...`, `test_max_attempts_...`,
  `test_delivered_is_never_retried`, `test_restart_resumes_retry_wait`,
  `test_admin_retry_of_terminal_failure`).
- Disabled/unconfigured transports fail closed (no fake success).
- Scheduler: idempotent registration, disabled-by-default, overlap skipped, sweep
  failure isolated from dispatch, tick emits sweep_started/finished evidence +
  dispatches (`test_scheduler_*`).
- Multi-PROCESS concurrency: concurrent delivery creation dedups to 1;
  concurrent claim → 1 winner; concurrent dispatch → 1 durable line (transport
  idempotency); stale claim reclaimed (`test_concurrent_*`, `test_stale_claim_reclaimed`).
- Security: owner-scoped deliveries; forged/empty identity rejected; bounded error
  summaries with no secret dump; malicious alert content handled as inert data;
  CLI admin-gated (exit 3 without opt-in), retry audited with verified OS identity
  (`test_open_deliveries_owner_scoped`, `test_admin_retry_forged_empty_identity_rejected`,
  `test_error_summary_bounded_and_no_secret_dump`,
  `test_malicious_alert_content_is_data_not_executed`, `test_cli_*`).
- Control Center exposes delivery health; terminal failures surface in attention,
  owner-safe (`test_control_center_exposes_delivery_health`).
- Backward compat: M17.10 alert self-resolve intact (`test_m17_10_alert_flow_unchanged`).

## Validation ladder (run, results)
1. M17.11 suite (`test_m17_11_notification_delivery.py`) → **34 passed**.
2. M17.9 (5 suites) + M17.10 + Control Center + M17.11 → **134 passed** (no regression).
3. Dedicated Critical Manifest — 7 blocking `notification.*` entries via the real
   manifest runner → **all green** (dedup+local, retry+terminal, suppression,
   concurrency, security, scheduler, control-center).
4. Server import + route count → **308 routes** (≥290).
5. Release check → exit 0; database_ok / backup_ok / restore_verified true (ledger
   db with the new delivery table passes integrity + backup/restore).
6. Secret scan over M17.11 files → **0 matches**.
7. Full suite → **1613 passed / 1 skipped / 0 failed** (+15 over the 1,598 M17.10
   baseline; note: the M17.11 file adds 34 tests, of which 3 multi-process tests are
   POSIX-run here).
8. `git diff --check` → clean.
9. Milestone-owned tree clean; `saathi/memory/conventions.md` modified + **unstaged**.

## Security controls
Preserve all M17.9/M17.10 controls. Admin-only retry + config; verified OS identity;
no caller-supplied trusted identity; fail-closed authz; owner-scoped visibility;
owner-safe payloads (no argv/output/secrets/tokens/provider dumps); bounded error
summaries (≤200 chars); no shell/URL execution from alert content (templated
message, content stored as data); no SSRF generic webhook; no credential logging;
no secrets persisted; audit every admin action.

## Event taxonomy
`harness.notification.queued|attempted|delivered|retry_scheduled|suppressed|
terminal_failed|admin_retry`; `harness.monitor.sweep_started|finished|failed`
(plus the existing M17.10 `harness.run.alert*` / `harness.run.completed` /
`harness.run.crash_recovered`). Per-handler exception isolation is provided by the
existing bus; delivery success does not depend on non-critical consumers.

## Migration / compatibility
Additive `CREATE TABLE IF NOT EXISTS run_alert_delivery` — existing ledger DBs gain
it on next open; no destructive change, no rewrite. M17.9/M17.10 fully preserved.
Terminal runs remain immutable. Rollback = revert the single commit (existing DBs
retain an unused table).

## Trading Guardian boundary
Not engaged. M17.11 executes no financial action. No alert triggers a trade; no
delivery/acknowledgement authorizes financial execution; no notification command
bypasses approval gates; no withdrawal-capable API key introduced; no live/autonomous
financial action enabled. The transport contract stays compatible with future
Trading Guardian alerts, which remain advisory unless separately approved.

## Known limitations / deferred
- External transports (Telegram/email/Slack/PagerDuty) are fail-closed stubs only —
  not implemented (no live-provider dependency).
- The interval scheduler is opt-in and not auto-started in the server (no repo
  evidence for safe auto-enable); no cron/launchd/systemd/cloud provisioning.
- No escalation policy beyond suppression; `verification_stuck` still deferred.
- Single-node local; multi-user LOAD still unproven.

## Verdict
**RELIABLE LOCAL ALERT DELIVERY STAGING READY** — M17.10 alerts deterministically
create deduplicated durable deliveries, deliver through a credential-free local
transport, retry with bounded deterministic timing to a durable terminal failure,
survive restart, resist concurrent double-delivery, respect resolve/ack suppression,
integrate with a stable opt-in scheduler + the event bus + Control Center, all with
a green blocking Critical Manifest entry. NOT production-ready (external transports,
production scheduling, multi-user load, incident-response drill outstanding).
