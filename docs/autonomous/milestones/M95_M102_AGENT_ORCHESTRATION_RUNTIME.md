# M95–M102 — SaathiOS Agent Orchestration and Planning Runtime

Date: 2026-07-29

Terminal verdict: `AGENT_ORCHESTRATION_RUNTIME_COMPLETE_WITH_LIMITATIONS`

## Milestone map

| Milestone | Scope | Status |
| --- | --- | --- |
| M95 | Orchestration domain model and lifecycle | Complete |
| M96 | Plan compiler, validator, work graph | Complete |
| M97 | Agent roles, assignment, separation of duties | Complete |
| M98 | Execution coordination via Mission Runtime / gateway | Complete |
| M99 | Checkpoints, recovery, retry, replan | Complete |
| M100 | Operator workspace + conversational controls | Complete |
| M101 | Browser certification + regressions | Complete with limitations |
| M102 | Final certification | Complete with limitations |

## Architecture

Central package: `saathi/platform/orchestration/`

- `AgentOrchestrationService` — intake, compile, create, start/pause/cancel, replan, checkpoint, certify
- `PlanCompiler` + templates — bounded reusable plans
- `PlanValidator` — DAG, roles, forbidden capabilities, retry bounds
- `AgentRoleRegistry` — 12 policy-bound roles
- `AgentAssignmentService` — deterministic assignment + SoD
- `FailureClassifier` + `RetryPolicy` — no infinite retry, no auto-retry of auth/security

**Does not replace** Mission Runtime, PlatformAgentRuntime, ExecutionGateway, Approval Center, Evidence, Audit, or KnowledgeService.

Flow:

```
Objective → Knowledge grounding → Plan compile/validate → MissionRuntime.plan
→ MissionRuntimeOrchestrator (PlatformAgentRuntime → ExecutionGateway)
→ checkpoints / evidence / audit → certify
```

## Security posture

- Model cannot execute tools
- Plans fail closed on validation errors
- Trading / production claims blocked
- Tenant/workspace isolation on orchestration records
- Conversation commands still require RBAC

## Evidence

- Tests: `tests/test_m95_orchestration_runtime.py`
- Browser: `docs/evidence/m101/browser/M101_BROWSER_CERT.json`
- Summary: `docs/evidence/m102/M102_CERTIFICATION_SUMMARY.json`

## Limitations

- Single-host SQLite / in-memory orchestration session store
- Deterministic readonly analysis tool (`m49.echo_readonly`) for local planning runs
- No distributed workers
- Production not authorized
- English-primary UI

## Production

Not authorized. No push, merge, deploy, credentials, or Trading Guardian change.
