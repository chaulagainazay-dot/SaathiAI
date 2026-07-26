import test from "node:test";
import assert from "node:assert/strict";
import {
  CAPABILITY_MATRIX, capability, capabilityBehavior,
  ONBOARDING_STEPS, onboardingProgress, onboardingFacts,
  validateScope,
  normalizeRiskSelection, normalizeMissionDraft, validateMissionDraft, missionCreateBody,
  buildMissionPlan, validateMissionPlan,
  agentSelectionBlockers, isAgentSelectable,
  buildApprovalRequest,
  READINESS, classifyExecutionReadiness,
  aggregateOperatorActions,
  deriveNotifications,
  buildEvidenceTimeline,
  validateSavedView,
  searchAuthorizedRecords,
  WORKFLOW_TEMPLATES, normalizeTemplate,
  actionPermission, canPerform,
  reconcileResult,
  classifyError, errorMessage,
} from "./operator.js";

/* -------------------------------------------------------- capability matrix */
test("capability matrix reflects real API surface", () => {
  assert.equal(capabilityBehavior("mission"), "LIVE"); // POST /missions exists
  assert.equal(capabilityBehavior("approval"), "LIVE"); // POST /approvals exists
  assert.equal(capabilityBehavior("execution"), "LIVE"); // POST /execute governed
  assert.equal(capabilityBehavior("attention"), "READ_ONLY"); // no ack/resolve
  assert.equal(capabilityBehavior("notification"), "DERIVED");
  assert.equal(capabilityBehavior("saved_view"), "LOCAL_ONLY");
  assert.equal(capabilityBehavior("workflow_template"), "LOCAL_ONLY");
  assert.equal(capabilityBehavior("mission_plan"), "DRAFT_ONLY");
  assert.equal(capabilityBehavior("nonexistent"), "BLOCKED");
  assert.ok(capability("mission").create === true);
  assert.equal(CAPABILITY_MATRIX.length, 13);
});

/* ---------------------------------------------------------------- onboarding */
test("onboarding progress gates safety steps", () => {
  const p0 = onboardingProgress([]);
  assert.equal(p0.complete, false);
  assert.equal(p0.safetyAcknowledged, false);
  assert.equal(p0.nextStep, "welcome");
  const all = ONBOARDING_STEPS.map((s) => s.id);
  const pAll = onboardingProgress(all);
  assert.equal(pAll.complete, true);
  assert.equal(pAll.safetyAcknowledged, true);
  assert.equal(pAll.pct, 100);
  // safety not acknowledged if a safety step missing
  const noSafety = all.filter((id) => id !== "safety");
  assert.equal(onboardingProgress(noSafety).safetyAcknowledged, false);
});

test("onboardingFacts reads real state, never fabricates", () => {
  const f = onboardingFacts({
    health: { identity: "ACTIVE", runtime: { gateway: "TOOL_GATEWAY_ENFORCED" } },
    me: { context: { org_id: "o1", workspace_id: "w1", role: "owner" } },
    config: { connectors: { mutations: "DRY_RUN_ONLY" } },
    diagnostics: { environment: { production_authorized: false } },
    projects: [{}], bindings: [{}, {}],
  });
  assert.equal(f.platformHealthy, true);
  assert.equal(f.productionAuthorized, false);
  assert.equal(f.connectorMode, "DRY_RUN_ONLY");
  assert.equal(f.financialExecution, "DISABLED");
  assert.equal(f.tradingExecution, "DISABLED");
  assert.equal(f.role, "owner");
  assert.equal(f.projectCount, 1);
  assert.equal(f.bindingCount, 2);
  const empty = onboardingFacts({});
  assert.equal(empty.org, null);
  assert.equal(empty.platformHealthy, false);
});

/* ------------------------------------------------------------------- scope */
test("validateScope requires org+workspace+project", () => {
  assert.equal(validateScope({ orgId: "o", workspaceId: "w", projectId: "p" }).valid, true);
  assert.equal(validateScope({ orgId: "o", workspaceId: "w" }).valid, false);
  assert.equal(validateScope({}).errors.length, 3);
});

/* --------------------------------------------------------------- mission */
test("mission draft normalize/validate/body", () => {
  assert.equal(normalizeRiskSelection("HIGH"), "high");
  assert.equal(normalizeRiskSelection("bogus"), "unknown");
  const bad = validateMissionDraft({ title: "", objective: "", projectId: "" });
  assert.equal(bad.valid, false);
  assert.equal(bad.errors.length, 3);
  const ok = validateMissionDraft({ title: "Launch Alpha", objective: "Ship it", projectId: "p1" });
  assert.equal(ok.valid, true);
  const body = missionCreateBody({ title: "Launch Alpha!", projectId: "p1" });
  assert.equal(body.project_id, "p1");
  assert.equal(body.name, "Launch Alpha!");
  assert.equal(body.key, "LAUNCH-ALPHA"); // deterministic slug, no Date/random
});

test("mission plan build + validate", () => {
  const plan = buildMissionPlan({ mission_id: "m1", name: "Launch" }, { bindings: [], approvals: [{ status: "pending" }], executions: [] });
  assert.ok(plan.stages.find((s) => s.id === "objective"));
  assert.equal(plan.blocked, true); // pending approval
  const v = validateMissionPlan(plan, { bindings: [] });
  assert.equal(v.executionReady, false);
  assert.ok(v.issues.some((i) => i.code === "AGENT_UNAVAILABLE"));
  const v2 = validateMissionPlan({ blocked: false }, { bindings: [{}] });
  assert.equal(v2.executionReady, true);
});

/* --------------------------------------------------------------- agents */
test("agentSelectionBlockers rejects inactive/cross-workspace/missing-capability", () => {
  assert.equal(isAgentSelectable({ state: "ACTIVE", workspace_id: "w1", allowed_tools: ["t1"] }, { workspaceId: "w1", requiredCapability: "t1" }), true);
  assert.deepEqual(agentSelectionBlockers({ state: "SUSPENDED" }), ["Binding inactive"]);
  assert.ok(agentSelectionBlockers({ state: "REVOKED" })[0].includes("revoked"));
  assert.ok(agentSelectionBlockers({ state: "ACTIVE", workspace_id: "w2" }, { workspaceId: "w1" }).includes("Cross-workspace identity"));
  assert.ok(agentSelectionBlockers({ state: "ACTIVE", allowed_tools: [] }, { requiredCapability: "tX" }).includes("Missing required capability"));
});

/* ------------------------------------------------------------- approval req */
test("buildApprovalRequest validates + emits real POST body", () => {
  const bad = buildApprovalRequest({ toolId: "", reason: "", acknowledged: false });
  assert.equal(bad.valid, false);
  assert.equal(bad.errors.length, 3);
  const good = buildApprovalRequest({ toolId: "m49.echo_readonly", reason: "audit", acknowledged: true, authority: "READ_ONLY", missionId: "m1", projectId: "p1", ttlSec: 1800 });
  assert.equal(good.valid, true);
  assert.equal(good.body.tool_id, "m49.echo_readonly");
  assert.equal(good.body.mission_id, "m1");
  assert.equal(good.body.ttl_sec, 1800);
  assert.equal(good.preview.singleUse, true);
});

/* ---------------------------------------------------------- exec readiness */
test("classifyExecutionReadiness never READY on unknown mandatory condition", () => {
  const base = { mission: {}, orgId: "o", workspaceId: "w", projectId: "p", agentValid: true, toolRegistered: true, approvalValid: true, runtimeAvailable: true, blockingAttention: false, productionAuthorized: false, connectorSafe: true, evidenceAvailable: true };
  assert.equal(classifyExecutionReadiness(base).state, READINESS.READY);
  assert.equal(classifyExecutionReadiness(base).executeAllowed, true);
  assert.equal(classifyExecutionReadiness({ ...base, approvalValid: false }).state, READINESS.BLOCKED_APPROVAL);
  assert.equal(classifyExecutionReadiness({ ...base, agentValid: false }).state, READINESS.BLOCKED_AGENT);
  assert.equal(classifyExecutionReadiness({ ...base, toolRegistered: false }).state, READINESS.BLOCKED_TOOL);
  assert.equal(classifyExecutionReadiness({ ...base, runtimeAvailable: false }).state, READINESS.BLOCKED_RUNTIME);
  assert.equal(classifyExecutionReadiness({ ...base, productionAuthorized: true }).state, READINESS.BLOCKED_UNSAFE);
  assert.equal(classifyExecutionReadiness({ ...base, mission: null }).state, READINESS.BLOCKED_SCOPE);
  assert.equal(classifyExecutionReadiness({ ...base, evidenceAvailable: false }).state, READINESS.READY_LIMITED);
  // unknown mandatory → BLOCKED_UNKNOWN, never READY
  const unknown = classifyExecutionReadiness({ mission: {}, orgId: "o", workspaceId: "w", projectId: "p", agentValid: undefined });
  assert.notEqual(unknown.state, READINESS.READY);
});

/* ------------------------------------------------------------ action queue */
test("aggregateOperatorActions surfaces only real supported actions", () => {
  const items = aggregateOperatorActions({
    approvals: [{ approval_id: "a1", tool_id: "x", status: "pending", side_effect_class: "DESTRUCTIVE" }, { approval_id: "a2", tool_id: "y", status: "approved" }],
    missions: [{ mission_id: "m1", name: "Blocked", status: "blocked" }],
    executions: [{ execution_id: "e1", tool_id: "t", state: "FAILED", error_code: "X" }],
    attention: [{ execution_id: "e2", tool_id: "t2", attention_reasons: ["failed"] }],
    onboardingComplete: false,
  });
  assert.equal(items[0].category, "urgent"); // high-risk pending approval first
  assert.ok(items.some((i) => i.id === "onboarding"));
  // no invented acknowledge/resolve/rerun
  assert.ok(!items.some((i) => /acknowledge|resolve|rerun/i.test(i.action)));
});

/* ----------------------------------------------------------- notifications */
test("deriveNotifications from real records, newest first", () => {
  const n = deriveNotifications({
    approvals: [{ approval_id: "a1", tool_id: "x", status: "pending", created_at: 10 }],
    executions: [{ execution_id: "e1", tool_id: "t", state: "FAILED", updated_at: 30 }, { execution_id: "e2", tool_id: "t", state: "SUCCEEDED", updated_at: 20 }],
    attention: [],
  });
  assert.equal(n[0].time, 30); // sorted desc
  assert.ok(n.some((x) => x.type === "execution_failed" && x.severity === "danger"));
  assert.ok(n.some((x) => x.type === "approval_requested"));
});

/* -------------------------------------------------------- evidence timeline */
test("buildEvidenceTimeline orders desc and marks states", () => {
  const ev = buildEvidenceTimeline({
    missions: [{ mission_id: "m1", name: "M", created_at: 5 }],
    approvals: [{ approval_id: "a1", tool_id: "x", status: "approved", created_at: 10, decided_at: 20 }],
    executions: [{ execution_id: "e1", tool_id: "t", state: "FAILED", created_at: 15, error_code: "X" }],
  });
  assert.equal(ev[0].time, 20); // decision newest
  assert.ok(ev.find((e) => e.kind === "execution_start").state === "Invalid");
});

/* ------------------------------------------------------------ saved views */
test("validateSavedView strips forbidden fields", () => {
  const bad = validateSavedView({ name: "", route: "/nope" });
  assert.equal(bad.valid, false);
  const withSecret = validateSavedView({ name: "High risk", route: "/platform/approvals", token: "secret", filters: { risk: "high" } });
  assert.equal(withSecret.valid, false); // token forbidden
  assert.ok(!("token" in withSecret.view)); // stripped from clean view
  const ok = validateSavedView({ name: "High risk", route: "/platform/approvals", filters: { risk: "high" } });
  assert.equal(ok.valid, true);
  assert.deepEqual(ok.view.filters, { risk: "high" });
});

/* ----------------------------------------------------------------- search */
test("searchAuthorizedRecords only over loaded records, honest scope", () => {
  const data = { missions: [{ mission_id: "m1", name: "Launch", key: "LN" }], bindings: [{ binding_id: "b1", name: "Worker", agent_id: "w" }], approvals: [], attention: [], executions: [], projects: [] };
  assert.equal(searchAuthorizedRecords("", data).length, 0);
  assert.equal(searchAuthorizedRecords("launch", data).length, 1);
  assert.equal(searchAuthorizedRecords("worker", data, "mission").length, 0); // type filter
  assert.equal(searchAuthorizedRecords("worker", data, "agent").length, 1);
});

/* ---------------------------------------------------------------- templates */
test("templates are local planning aids, no execution", () => {
  assert.ok(WORKFLOW_TEMPLATES.length >= 5);
  const t = normalizeTemplate(WORKFLOW_TEMPLATES[0]);
  assert.equal(t.local, true);
  for (const tpl of WORKFLOW_TEMPLATES) {
    assert.ok(tpl.name && tpl.objective && Array.isArray(tpl.stages));
  }
});

/* --------------------------------------------------------- role-aware actions */
test("role-aware action permissions", () => {
  assert.equal(actionPermission("viewer", "decide_approval"), "insufficient");
  assert.equal(actionPermission("viewer", "inspect"), "permitted");
  assert.equal(actionPermission("operator", "request_approval"), "permitted");
  assert.equal(actionPermission("operator", "decide_approval"), "requires_approval");
  assert.equal(actionPermission("owner", "decide_approval"), "permitted");
  assert.equal(actionPermission("bogus", "inspect"), "unknown");
  assert.equal(canPerform("owner", "create_mission"), true);
  assert.equal(canPerform("viewer", "create_mission"), false);
});

/* --------------------------------------------------------- reconciliation */
test("reconcileResult never reports success from client alone", () => {
  assert.equal(reconcileResult({ submitted: false }), "idle");
  assert.equal(reconcileResult({ submitted: true, serverStatus: "rejected" }), "server_rejected");
  assert.equal(reconcileResult({ submitted: true, serverStatus: "accepted" }), "reconciling"); // no expected/actual yet
  assert.equal(reconcileResult({ submitted: true, serverStatus: "accepted", expected: "approved", actual: "approved" }), "reconciled");
  assert.equal(reconcileResult({ submitted: true, serverStatus: "accepted", expected: "approved", actual: "pending" }), "conflict");
  assert.equal(reconcileResult({ submitted: true, serverStatus: "stale" }), "stale");
});

/* -------------------------------------------------------------- error taxonomy */
test("classifyError maps status/message to safe codes", () => {
  assert.equal(classifyError({ status: 401 }), "AUTH_REQUIRED");
  assert.equal(classifyError({ status: 403 }), "PERMISSION_DENIED");
  assert.equal(classifyError({ message: "approval expired" }), "APPROVAL_EXPIRED");
  assert.equal(classifyError({ message: "Failed to fetch" }), "SERVER_UNAVAILABLE");
  assert.equal(classifyError({ message: "weird" }), "UNKNOWN");
  assert.equal(errorMessage("AUTH_REQUIRED"), "Authentication required");
});
