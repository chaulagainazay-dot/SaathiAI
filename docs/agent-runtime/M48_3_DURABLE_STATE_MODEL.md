# M48.3 — Durable State Model

Additive columns on `orchestration_run`:

attempt, heartbeat_at, lease_owner, lease_expires_at, cancel_requested_at,
cancel_reason, cancel_status, deadline_at, terminal_reason, last_error_code, parent_run_id

Migration: `RunStore._migrate_lifecycle` via PRAGMA + ALTER TABLE.

Guarantees: terminal outcome immutable; attempt monotonic; one lease owner;
cancel/timeout recorded before propagation; no silent terminal reactivation.
