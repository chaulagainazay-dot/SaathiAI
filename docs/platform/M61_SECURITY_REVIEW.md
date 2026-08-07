# M61 — Security Review

| Check | Result |
|---|---|
| Authorization on every mutation | PASS — `ctx.require_permission(...)` on all writes (WORKFLOW/NOTIFICATION/ATTENTION _WRITE) |
| Tenant isolation | PASS — all queries scoped by org_id/workspace_id (+user for views/drafts); cross-tenant read returns nothing (certified) |
| No privilege escalation | PASS — viewer read-only; writes require operator+; server enforces regardless of UI |
| No browser authority / execution | PASS — WorkflowService never touches PlatformAgentRuntime/ExecutionGateway; no tool execution |
| No raw database exposure | PASS — only `to_public`-style dicts returned; no secret columns |
| No unrestricted search | PASS — tenant-scoped, capped limit |
| No unsafe mutation | PASS — `_reject_secrets` fails closed on secret-shaped keys in persisted blobs |
| Audit completeness | PASS — every create/update/decision/attention mutation writes an audit_event with actor + timestamp |
| Optimistic concurrency | PASS — stale writes rejected (409), never silent overwrite |
| Approvals / runtime authority | UNCHANGED — still server-owned; no new execution path |
| Localhost-only / production | UNCHANGED — no networking/production/connector/financial/trading enablement |
