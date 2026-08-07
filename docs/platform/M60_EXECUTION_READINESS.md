# M60 — Execution Readiness Review

`classifyExecutionReadiness(ctx)` in `lib/operator.js`, rendered in mission planning.

Checks (blocking unless noted): mission exists, scope valid, agent/binding valid,
tool registered, approval present & valid, runtime & gateway available, no blocking
attention, evidence destination (non-blocking), production unauthorized (safe),
connectors dry-run (safe).

States: `READY_FOR_GOVERNED_EXECUTION`, `READY_WITH_LIMITATIONS`,
`BLOCKED_MISSING_APPROVAL`, `BLOCKED_INVALID_SCOPE`, `BLOCKED_AGENT_UNAVAILABLE`,
`BLOCKED_TOOL_UNREGISTERED`, `BLOCKED_RUNTIME_UNAVAILABLE`, `BLOCKED_UNSAFE_CONFIGURATION`,
`BLOCKED_UNKNOWN`. It is **never** READY when a mandatory condition is unknown
(unit-tested). `executeAllowed` is true only for the two READY states, and the
governed execute button submits the existing `POST /execute` path — no new dispatcher.
