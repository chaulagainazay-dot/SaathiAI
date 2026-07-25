# M54 Architecture

M54 is an operational-readiness layer, not a new runtime tier.

## Layering

```
                 Operator browser (/platform)
                          │  X-Platform-Token (session)
                          ▼
        FastAPI platform router (saathi/platform/api.py)
                          │
        OperationalReadinessService (saathi/platform/readiness.py)
                          │  reuses
        RuntimeOperationsService (M53)  ── redaction, tenant scoping, attention
                          │
                    PlatformStore (single-host SQLite)
```

The readiness service composes the M53 operations service; it never calls
adapters, `ToolExecutionService`, or `ToolRegistry`, and it never dispatches
tools. Governed execution still flows only through `PlatformAgentRuntime` →
`ExecutionGateway`.

## Invariants preserved

- No second runtime, gateway, approval engine, RBAC system, identity system, or
  operational database.
- `PlatformAgentRuntime` remains canonical; `ExecutionGateway` remains the sole
  registered-tool execution authority.
- Uncertain recorded dispatches are never automatically replayed.
- Terminal execution states remain immutable.
- Tenant isolation: every readiness query is scoped by `ctx.org_id` /
  `ctx.workspace_id`; cross-tenant lookups fail closed (`EXECUTION_NOT_FOUND`).

## New authority mapping

| Surface | Permission | Roles |
|---|---|---|
| diagnostics, export | `RUNTIME_READ` | viewer+ |
| audit export | `RUNTIME_READ` + `AUDIT_READ` | viewer+ |
| retention preview, holds | `ORG_MANAGE` | owner, admin |
| record certification time | `SETTINGS_WRITE` | owner, admin |

## Isolated certification database

`PlatformStore` honors `SAATHI_PLATFORM_DB`. The browser certification harness
sets it to a disposable temp file so certification never reads or mutates the
operator's default single-host database, and teardown removes it.

## Data classes touched

No schema migration. M54 reads existing `platform_executions`,
`platform_agent_bindings`, `approvals`, `audit_events`, and
`runtime_reconciliations`, and stores two bounded config keys
(`m54_last_certification`, `m54_retention_holds`).
