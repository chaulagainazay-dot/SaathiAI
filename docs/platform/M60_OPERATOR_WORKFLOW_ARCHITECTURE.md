# M60 — Operator Workflow Architecture

M60 turns the M59 spatial workspaces into guided, safe operator journeys:

```
Onboarding → Mission intent → Scope → Plan → Agent selection
→ Approval preparation → Execution readiness → Governed server action
→ Monitoring → Evidence → Completion / recovery
```

No new execution authority is introduced. All effects flow through the existing
`PlatformAgentRuntime → ExecutionGateway`. Approvals stay server-owned.

## Layers

- `lib/operator.js` — pure, unit-tested domain logic (the CAPABILITY_MATRIX is
  authoritative): onboarding, scope validation, mission draft, plan, agent
  selection blockers, approval-request builder, execution-readiness classifier,
  action aggregation, notification derivation, evidence timeline, saved-view
  validation, search scope, templates, role-aware permissions, reconciliation,
  error taxonomy.
- `lib/local-store.js` — safe local-only store for NON-sensitive workflow state
  (onboarding progress, drafts, saved views, prefs, search history). Never stores
  tokens/credentials/authority/secrets.
- `components/spatial/GuidedWorkflow.jsx` — `WorkflowStepper`, `WorkflowStage`,
  `RoleBoundaryNotice`, `DraftRecoveryBanner`, `ServerReconciliationState`,
  `WorkflowCompletionSummary`.
- Routes under `app/platform/*` reuse the M59 `SpatialWorkspaceShell`, primitives,
  and `usePlatformData` hook.

## API Capability Matrix (authoritative)

| Capability | Existing API | Read | Create | Update | Decision | Execution | Evidence | M60 behavior |
|---|---|---|---|---|---|---|---|---|
| organization | GET /organizations | ✓ | ✗ | ✗ | — | — | — | READ_ONLY |
| workspace | GET /workspaces | ✓ | ✗ | ✗ | — | — | — | READ_ONLY |
| project | GET/POST /projects | ✓ | ✓ | ✗ | — | — | — | LIVE |
| mission | GET/POST /missions | ✓ | ✓ | ✗ | — | — | — | LIVE (create); no per-mission GET/update |
| agent_binding | GET/POST/PATCH /agent-bindings | ✓ | ✓ | ✓ | — | — | — | LIVE |
| approval | GET/POST /approvals, decide, revoke | ✓ | ✓ | ✗ | ✓ | — | — | LIVE (request + decide) |
| execution | GET /runtime/executions, POST /execute | ✓ | ✓ | ✗ | — | ✓ governed | — | LIVE governed |
| attention | GET /runtime/attention | ✓ | ✗ | ✗ | ✗ | — | — | READ_ONLY (ack/resolve BLOCKED) |
| evidence | GET /runtime/export, /audit | ✓ | ✗ | — | — | — | ✓ | READ_ONLY (export/read) |
| notification | (none) | ✗ | ✗ | ✗ | ✗ | — | — | DERIVED |
| saved_view | (none) | ✗ | ✗ | ✗ | — | — | — | LOCAL_ONLY |
| workflow_template | (none) | ✗ | ✗ | ✗ | — | — | — | LOCAL_ONLY |
| mission_plan | (none) | ✗ | ✗ | — | — | — | — | DRAFT_ONLY |

This matrix is encoded in `lib/operator.js` (`CAPABILITY_MATRIX`) and gates every
workflow's behavior. No workflow claims mutation the matrix does not grant.
