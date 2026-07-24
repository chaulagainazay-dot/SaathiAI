# M52 Architecture — Canonical Platform-Agent Path

## Canonical flow

```text
User
→ token-trusted Identity + Session
→ Organization membership
→ Workspace
→ Project / Mission when supplied
→ PlatformExecutionContext
→ PlatformAgentBinding
→ PlatformAgentRuntime
→ Approval Center validation
→ ExecutionGateway.execute_registered_tool
→ ToolExecutionService
→ ToolRegistry
→ Adapter
→ M49 evidence + platform audit
```

`PlatformAgentRuntime` is an orchestration layer above the gateway. It does not
execute adapters and cannot grant authority. Manifest authority, tool
idempotency, tool cancellation, approval-reference validation, registry policy,
and adapter dispatch remain owned by M49.

## State machine

Externally meaningful states:

```text
CREATED → QUEUED → READY → RUNNING → COMPLETED | FAILED | CANCELLED | TIMED_OUT
                   ↘ WAITING_APPROVAL → READY
                   ↘ RECOVERING → PAUSED → READY
RUNNING → PAUSED | RECOVERING
```

The complete legal edge set is code-owned in
`PLATFORM_EXECUTION_TRANSITIONS`. Terminal states have no outgoing edges.
State updates use a version predicate on the existing single-host SQLite
connection. This is not a distributed consensus or exactly-once claim.

## Persistence and recovery

`platform_executions` lives in the existing platform SQLite database and stores
scope, request fingerprint, serialized arguments, lifecycle state, dispatch
marker, cancellation marker, deadline, safe result JSON, and recovery decision.

- Waiting approvals remain waiting across restart.
- Cancellation and expired deadlines settle without dispatch.
- Pre-dispatch interruptions become `PAUSED` and may be explicitly resumed.
- A recorded running/dispatch state becomes `PAUSED` with
  `dispatch_recorded_manual_review`; it is never automatically replayed.
- Terminal results replay safely for the same platform idempotency key.
- M49 durable idempotency remains the mutation authority.

## API contract

Existing execute responses are preserved and add `execution_id` and
`execution_state`. Lifecycle read/cancel/resume routes are additive under
`/api/v1/platform/runtime/executions/*`.
