# M49.4 Gateway Closure

## Target architecture

```text
caller → ExecutionGateway.execute_registered_tool → ToolExecutionService
       → ToolRegistry + durable idempotency + policy → Governed Adapter
       → Canonical Result / Events / Evidence
```

## Coverage audit

`validate_tool_gateway_coverage()` → **PASS**, `TOOL_GATEWAY_ENFORCED`

## Callers

| Caller | Path | Class |
|---|---|---|
| AgentExecutor | execute_tool | LEGACY_BOUNDED + CANONICAL_WRAPPER |
| agent_runtime.gateway_exec | execute_registered_tool | CANONICAL |
| Compatibility wrapper | try_canonical_legacy_tool → gateway | CANONICAL for 11 names |
| Subprocess | m49.allowlisted_command / run_bounded | CANONICAL |
| Connector actions | m49.connector.* manifests | CANONICAL dry-run/fixture |

## Bypass detections

| Bypass class | Result |
|---|---|
| Direct adapter call from public API | not the supported path |
| Generic fallback for unknown tools | BLOCKED |
| Generic connector execution | ABSENT |
| Freeform shell | BLOCKED |
| Financial execution | PROHIBITED, adapter_invoked=False |

## State

`TOOL_GATEWAY_ENFORCED`
