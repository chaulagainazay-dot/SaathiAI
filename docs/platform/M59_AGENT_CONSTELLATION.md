# M59 — Agent Constellation (Workstream 2)

Routes: `/platform/agents` (list) · `/platform/agents/[agentId]` (detail).

## Truthful labelling

Records are platform **agent bindings** (`PlatformAgentBindingRecord`), durable
tenant-scoped runtime identities — not implied to be autonomous AI agents beyond
what the binding grants. `normalizeAgent()` labels each honestly:

- **Authority kind**: `advisory` (READ_ONLY / ADVISORY / NONE ceiling) vs
  `execution-capable` (any higher ceiling).
- **Status**: Available / Running / Waiting for approval / Inactive / Blocked /
  Unknown — derived from binding `state` plus live run facts (bound executions).
- **Bound**: whether the binding is currently ACTIVE.

Data: `GET /agent-bindings` (list) and `GET /agent-bindings/{id}` (detail exists).
Runs are matched to the binding via `binding_id` on executions.

## List

Glass cards with signal edge + a canonical-relationship legend
(`Agent → Binding → PlatformAgentRuntime → ExecutionGateway → Registered tools`).
Filter by state, search by name/identity. Inspect opens the drawer.

Signal colours: cyan = active operational, amber = approval-dependent authority,
red = blocked/invalid binding, muted = inactive.

## Detail

Identity · authority & scope (ceiling, org/workspace/project/mission) · capability
boundary (permitted allowed_tools/allowed_capabilities vs restricted: anything
above ceiling, plus connector mutations, financial and trading execution — disabled
platform-wide) · recent runs and failures.

**Never** renders secrets, tokens, or credential references. No unsupported
autonomy claims ("fully autonomous", "production agent") appear.
