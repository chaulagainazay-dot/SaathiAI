# M52 Migration Report

## Removed functional bypasses

- Removed `AgentExecutor._gateway_execute` construction of
  `ExecutionGateway`.
- Removed `AgentExecutor._gateway_execute` construction of
  `SaathiExecutionSystem`, `MemoryQueue`, `ToolIntent`, and
  `ExecutionContext`.
- Removed direct platform API/service gateway dispatch.
- Removed approval validation and consumption from the service wrapper so
  there is one platform approval orchestration implementation.

## Canonicalized surfaces

- Both user-facing platform execute endpoints enter `PlatformAgentRuntime`.
- `PlatformAgentBinding` creates a scope fingerprint and delegates to runtime.
- `PlatformService.execute_tool` is compatibility-only.
- Bound legacy agents can enter only with a runtime and platform token.

## Compatibility contract changes

Unbound `AgentExecutor.request_tool` calls that previously reached a gateway now
return `PLATFORM_RUNTIME_REQUIRED`. This is an intentional security correction:
the legacy request has no token-trusted user, active session, organization,
workspace, or platform agent binding.

Existing platform execute response fields remain; runtime identifiers are
additive.

## Rollback

The M52 table is additive. Rolling code back leaves an unused
`platform_executions` table. M49 gateway/tool schemas and M50/M51 identity,
membership, and approval schemas are unchanged.
