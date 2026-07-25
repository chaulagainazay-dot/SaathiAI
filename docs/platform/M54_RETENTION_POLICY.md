# M54 Retention Policy

Bounded retention for private-alpha operational data. **Purge is DRY-RUN ONLY in
M54** — no operator data is deleted.

## Scope (covered record classes)
runtime executions, runtime timelines, audit events, reconciliation records,
approval metadata, browser-certification artifacts, exported evidence.

## Policy
- **Default retention period:** 90 days (`DEFAULT_RETENTION_DAYS`).
- **Protected records:** non-terminal executions; records updated within the
  retention window; records under a legal/operator hold.
- **Terminal eligibility:** only terminal executions older than the cutoff are
  eligible for purge.
- **Legal/operator hold:** `POST /runtime/retention/hold` marks an execution
  held (stored in the `m54_retention_holds` config key); held records are never
  eligible.
- **Dry-run preview:** `POST /runtime/retention/preview` returns `mode:
  "DRY_RUN"`, `purge_executed: false`, eligible count and (bounded) ids, and a
  protected breakdown.
- **Authorization:** owner/admin only (`ORG_MANAGE`).
- **Tenant isolation:** preview and holds are scoped to the caller's workspace.
- **Irreversibility:** the plan is marked `irreversible: true` and
  `confirmation_required: true` for any future real purge.
- **Audit:** every preview and hold change emits an audit event
  (`readiness.retention_preview`, `readiness.retention_hold`).

## M54 boundary
Even when a caller requests a non-dry-run purge, the service returns a dry-run
plan annotated `PURGE_DISABLED_IN_M54_DRY_RUN_ONLY`. Real deletion is deferred to
a later milestone behind explicit owner confirmation and a backup rehearsal.
