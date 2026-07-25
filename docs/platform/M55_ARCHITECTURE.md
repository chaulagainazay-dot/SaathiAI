# M55 Architecture

M55 is an additive operational-excellence layer that turns the M50–M54 platform
into a private-alpha **Release Candidate**. It adds no runtime, gateway, RBAC,
identity, approval engine, or database.

## Layering

```
        Operator browser (/platform, /platform/ops)
                     │  X-Platform-Token
                     ▼
     FastAPI platform router (saathi/platform/api.py)
                     │
     ReleaseOperationsService (saathi/platform/release.py)
        health · metrics · backup · recovery · release-validate
                     │ composes
     OperationalReadinessService (M54) → RuntimeOperationsService (M53)
                     │
               PlatformStore (single-host SQLite)
```

`ReleaseOperationsService` is read/analysis only. It never calls adapters,
`ToolExecutionService`, or `ToolRegistry`, never dispatches tools, and never
mutates operator data (backup + recovery run against **isolated temp stores**).

## Components (all additive)

| Service | Purpose | Auth |
|---|---|---|
| HealthService | expanded operational health (uptime, memory, queue, sessions, tenant/workspace counts, latency) | RUNTIME_READ |
| MetricsService | dashboard counters (executions, approvals, exports, attention reasons, recovery, errors) | RUNTIME_READ |
| BackupValidator | manifest + checksum + integrity + restore **simulation** | ORG_MANAGE |
| RecoveryCertifier | restart/dispatch/binding scenarios proving no duplicate/escalation/replay/corruption | ORG_MANAGE |
| ReleaseValidator | PASS/WARNING/FAIL/UNKNOWN checks + aggregate readiness score | ORG_MANAGE |
| Release Gate CLI | `python -m saathi.platform.release_check` deterministic RC report | isolated |
| Operator Console | read-only `/platform/ops` dashboard | session |

## Invariants preserved
- `PlatformAgentRuntime` canonical; `ExecutionGateway` sole registered-tool authority.
- No parallel execution path; Approval Center, Runtime Attention, and Binding
  Administration are never bypassed.
- Tenant isolation, RBAC, approval lifecycle, audit, and evidence redaction unchanged.
- Advisory, fail-closed, deterministic, backwards compatible. No production
  enablement; connectors dry-run; financial/trading disabled.

## New store helpers
`count_active_sessions`, `count_tenants`, `count_workspaces` — bounded read-only
COUNT queries exposing integers only (no data). No schema migration.
