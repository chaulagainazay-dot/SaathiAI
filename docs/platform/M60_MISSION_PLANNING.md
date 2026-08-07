# M60 — Mission Planning + Execution Readiness

Route: `/platform/missions/[missionId]/plan`.

- **Plan** (DRAFT_ONLY — no plan API): `buildMissionPlan()` renders the governed
  lineage (Objective → Agents → Approvals → PlatformAgentRuntime → ExecutionGateway
  → Execution → Evidence) as `WorkflowStage` nodes with explicit states
  (proposed/approved/active/blocked/completed/failed/cancelled/unavailable).
  `validateMissionPlan()` surfaces issues (no agent, pending approvals/attention);
  an incomplete/unsafe plan never appears execution-ready.
- **Agent selection**: real bindings; `agentSelectionBlockers()` disables inactive,
  cross-workspace, revoked, or capability-missing bindings with an explicit reason.
- **Execution readiness**: `classifyExecutionReadiness()` → READY_FOR_GOVERNED_EXECUTION
  / READY_WITH_LIMITATIONS / BLOCKED_* — never READY when a mandatory condition is
  unknown. Each check is shown with pass/fail/warn.
- **Governed execution**: the execute button appears only when readiness allows and
  the role permits. It submits the real `POST /execute` (read-only tool
  `m49.echo_readonly`) through PlatformAgentRuntime → ExecutionGateway — the browser
  never calls a tool directly and shows no optimistic success; status comes from the
  server response, with a link to the runtime record.
