# M17.11 Audit — Scheduled Run Monitoring & Reliable Alert Delivery

Start / rollback point: HEAD `28ce958` (M17.10). Branch `milestone/m7-security-engine`.
Full suite at start: 1,598 passed / 1 skipped.

## Repository truth established
- `28ce958` present in branch history; M17.10 tests + docs exist.
- **Scheduler** (`saathi/scheduler.py`): a daily time-of-day job runner
  (`JOBS = [(hh,mm,weekday,fn)]`, checked every 30 s, each fires ≤ once/day). It is
  NOT sub-minute/interval. An **interval** monitor pattern already exists in-repo:
  `storage.service ... svc.start(interval_seconds=60)` (a daemon-thread interval
  loop). M17.11 mirrors that established interval pattern with a tiny opt-in
  adapter — NOT a new/parallel scheduler framework.
- **Event bus** (`saathi/events/bus.py`): `publish_sync(name, payload)` with
  per-handler exception isolation (errors collected, never raised) — reuse as-is.
- **Ledger** (`run_ledger.py`): M17.9 `run` + `run_transition`; M17.10 `run_alert`
  (dedup via partial-unique `state_key`), `resolve_alerts`, `acknowledge_alert`,
  `open_alerts`. `_conn()` WAL + busy_timeout; `_clean_str`/`_reject_secrets`
  sanitizers; `_event()` bus emitter.
- **Control Center** (`aggregator.py`): `_attention()` ranked items;
  `harnesses()` cell already surfaces `run_alerts`.
- **Config/secrets**: `saathi/config.py` env-based; secrets never in ledger/repo.
- No reusable notification/transport abstraction exists → add a NARROW harness-alert
  transport interface + one local durable transport (not a platform messaging rewrite).

## Why this implementation is bounded
Smallest coherent slice that makes M17.10 alerts operationally deliverable:
extends the existing ledger (additive delivery table), the existing event bus, the
existing Control Center attention, the existing admin gate + OS-identity model, and
the existing interval-loop pattern. One local transport (no creds). External
transports are fail-closed stubs only. No new engine/scheduler-framework/bus/DB/
auth/dashboard.

## Design
- **Delivery persistence** — additive `run_alert_delivery` table in the SAME
  ledger DB (FK → `run_alert`), unique `idem_key = alert_id:channel:dest:fingerprint`
  → one active delivery per (alert, channel, dest, payload version). Statuses:
  pending, attempting, delivered, retry_wait, suppressed, terminal_failed,
  cancelled. CAS transitions under `BEGIN IMMEDIATE`; lease-based claim
  (`claim_owner`/`claim_at`) for concurrency; delivered/terminal_failed immutable
  except admin retry.
- **Policy** (deterministic, no LLM): only OPEN alerts create deliveries; unknown
  alert class fails closed; resolved/acknowledged alerts suppress pending
  deliveries; deterministic `fingerprint = sha256(run_id|class|severity)` payload
  version; bounded retry schedule `[0, 60, 300, 900, 3600]` s, max 5 attempts →
  terminal_failed.
- **Transport** — `AlertTransport` Protocol (`name`, `send(notification)->DeliveryResult`).
  `LocalFileTransport` writes owner-safe JSONL under
  `data/application_harness_runs/notifications/<channel>.jsonl` (durable,
  inspectable, idempotent by fingerprint marker, gitignored, no creds).
  `DisabledTransport`/`UnconfiguredTransport` fail closed (no fake success).
- **Dispatcher** — `NotificationDispatcher.dispatch_once(now, worker, transports)`:
  claim (CAS) → build owner-safe `AlertNotification` → `send` → mark_delivered /
  mark_attempt_failed. Injectable clock; no real sleeps.
- **Scheduler adapter** — `run_scheduler.py` interval loop mirroring the storage
  svc pattern: ONE named job, idempotent registration (singleton + lock, duplicate
  register = no-op), overlap lock, **default DISABLED**
  (`SAATHI_HARNESS_MONITOR_ENABLED=1`), emits sweep_started/finished/failed.
  Restart-safe: on start `reclaim_stale` + resume retry_wait from persisted
  `next_attempt_at`. Not auto-started in server (no repo evidence for safe auto-enable).
- **Control Center** — `harnesses()` cell gains `delivery_health`
  (pending/retry_wait/terminal_failed counts, oldest pending age, last sweep,
  scheduler enabled, transports configured); `_attention()` folds terminal_failed
  deliveries (high). Owner-safe.
- **CLI** (existing admin gate, verified OS identity, audited): `notify-dispatch`,
  `alert-deliveries`, `retry-delivery <id>`, `monitor-schedule-status`.

## Send-before-persist strategy (documented)
At-least-once with **local transport idempotency** (fingerprint marker) + **stale-
claim reclaim**: a crash after send but before persist leaves the row `attempting`;
on restart `reclaim_stale` returns it to `retry_wait`; re-dispatch hits the
transport's idempotency marker → `idempotent=True` → `mark_delivered` (no duplicate
write). Delivery uncertainty is never hidden.

## Files likely to change
`run_ledger.py` (delivery table + methods; suppress wired into resolve/ack),
`notify.py` (NEW: payloads, transports, dispatcher, policy), `run_scheduler.py`
(NEW: interval adapter), `cli.py` (+4 admin commands), `control_center/aggregator.py`
(delivery_health + attention), `repair/critical_checks.json` (blocking entries),
`tests/test_m17_11_notification_delivery.py` (NEW), docs.

## Security
Preserve all M17.9/M17.10 controls. Admin-only retry + config visibility; verified
OS identity; no caller-supplied trusted identity; fail-closed authz; owner-scoped
visibility; owner-safe payloads (no argv/output/secrets/tokens); bounded error
summaries; destination validation; bounded payload; no shell/URL execution from
alert content; no SSRF generic webhook; no credential logging; audit every admin
action. Alert content is treated as DATA.

## Migration / compatibility
Additive `CREATE TABLE IF NOT EXISTS run_alert_delivery` — existing ledger DBs gain
it on next open; no destructive change, no rewrite. M17.9/M17.10 fully preserved.
Rollback = revert the single commit (existing DBs retain an unused table).

## Trading Guardian boundary
Not engaged. M17.11 executes no financial action. Notification architecture stays
compatible with future Trading Guardian alerts, but: no alert triggers a trade; no
delivery/acknowledgement authorizes financial execution; no notification command
bypasses approval gates; no withdrawal-capable API key introduced; future financial
alerts remain advisory unless separately approved through Trading Guardian.

## Out of scope
Automated run recovery/restart; pause/resume/checkpoint; incident-management
platform; live Slack/PagerDuty/email/Telegram; cloud scheduler provisioning; public
webhooks; autonomous trading; arbitrary user Python handlers; secrets in ledger/repo;
new bus/DB/auth/dashboard; unrelated refactor.

## Acceptance criteria
Per task §23 (delivery creation, dedup, local delivery, bounded retry, terminal
failure, restart recovery, concurrent-claim safety, resolve/ack suppression, stable
scheduler, owner+admin preserved, event evidence, Control Center health, additive
migration, M17.9/M17.10 green, critical checks, full suite, clean commit).

## Rollback
Single bounded commit on `28ce958`. Revert restores M17.10 exactly; additive table
left unused in existing DBs.
