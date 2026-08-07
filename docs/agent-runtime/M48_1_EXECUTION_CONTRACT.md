# M48.1 — Execution Contract

## Canonical types

| Field | Source |
|---|---|
| run_id | `RunStore.create_run` |
| objective / input | Orchestrator + `AgentRunRequest` |
| agent_id | registry + Task.agent |
| requested_capability | `AgentRunRequest.requested_capability` (M48.1) |
| requested/resolved model | model_router / AgentDefinition.model_policy |
| tool policy | AgentDefinition allow/deny + policy.check_tool |
| approval | approval_request table + M48.1 token checks |
| authority scope | RiskClass + AuthorityClass mapping |
| status / RunState | `models.RunState` |
| timeout / retries | AgentDefinition + `AgentRunRequest` bounds |
| events | run_event table |
| evidence | gateway Evidence + artifacts |
| result / error | final_outcome + failure table |

## Run states (existing M10 — preserved)

```text
created, planning, awaiting_approval, approved, queued, running,
delegated, verifying, reviewing, completed, paused, cancelled,
timed_out, blocked, failed, rolled_back, partially_completed
```

M48.1 recommended names map onto these (e.g. WAITING_FOR_APPROVAL → `awaiting_approval`).

## Validation API

```text
saathi.agent_runtime.contracts.validate_run_request(AgentRunRequest)
saathi.agent_runtime.contracts.validate_state_transition_safe(src, dst)
```

Fail-closed: unknown capability, unknown authority, financial execution, missing/expired/revoked approval, invalid timeout, unbounded retries, secret-like fields.
