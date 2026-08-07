# M53 Architecture

## Canonical execution path

```text
User → token-trusted Session → Organization membership → Workspace
     → Project/Mission scope → durable PlatformAgentBinding
     → PlatformExecutionContext → PlatformAgentRuntime
     → Approval Center → ExecutionGateway
     → ToolExecutionService → ToolRegistry → Adapter → Audit
```

M53 administration operates around this path:

```text
Authenticated RBAC context
  ├─ BindingAdministrationService → PlatformStore → audit
  └─ RuntimeOperationsService
       ├─ safe persisted views / attention / metrics
       ├─ state-only eligible reconciliation → PlatformStore → audit
       └─ resumable execution → PlatformAgentRuntime → canonical path
```

Neither administrative service calls `ToolExecutionService`, `ToolRegistry`, or
an adapter. Resumes use `PlatformAgentRuntime`; actual registered-tool
execution remains exclusively delegated to `ExecutionGateway`.

## Authority and state

- Platform SQLite remains the sole platform operational store.
- Binding policy narrows gateway authority; it never grants financial/trading
  authority or widens owner safety policy.
- Version changes invalidate stale bound calls and mark nonterminal executions
  for attention.
- Terminal runtime states remain immutable.
- Recorded dispatch is classified uncertain and cannot be resumed.
- Metrics are bounded persisted-state summaries, not real-time distributed
  telemetry.
