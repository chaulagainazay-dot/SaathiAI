# M55 Health Monitoring & Metrics

## Health — `GET /api/v1/platform/release/health` (RUNTIME_READ)
Tenant-safe, no secrets. Reports:
runtime_health, uptime_seconds, memory_rss_kib, queue_depth, pending_approvals,
attention_count, running/waiting/failed executions, recovered_executions,
storage_bytes, database_status, scheduler_state, api_latency_ms, tenant_counts,
workspace_counts, active_sessions, environment classification,
`production_authorized: false`, and the M54 safety block.

Memory is process RSS (via `resource`); latency is a trivial store round-trip;
counts are bounded integers (`count_active_sessions`/`count_tenants`/
`count_workspaces`) exposing no data. No secrets, environment, or database paths.

## Metrics — `GET /api/v1/platform/release/metrics` (RUNTIME_READ)
Dashboard-oriented, no PII, no secrets:
execution_totals, execution_duration_seconds (avg/max), approval_counts,
approval_latency_seconds, retention_previews, evidence_exports, login_activity,
binding_actions, runtime_attention_reasons (histogram), recovery_operations,
restart_count (UNKNOWN — not tracked cross-process on single host),
error_categories.

Counts derive from tenant-scoped executions, approvals, and audit events. Values
are bounded and tenant-scoped.

## Operator Console — `/platform/ops`
A read-only dashboard aggregating Platform Health, Metrics, Release Readiness,
Recovery Certification, Backup Validation, and Security Status, plus the
non-production safety banner. All mutating operations already flow through the
approved runtime paths; the console adds no new authority.
