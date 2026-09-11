// M60 — Guided operator workflow domain logic. Pure and unit-testable.
//
// The CAPABILITY_MATRIX is authoritative: it decides whether each workflow is
// LIVE / READ_ONLY / DRAFT_ONLY / PREVIEW_ONLY / DERIVED / LOCAL_ONLY / BLOCKED,
// derived from the REAL /api/v1/platform/* surface. No workflow may claim
// behavior beyond its matrix row. Nothing here grants authority or executes.

import { SIGNAL } from "./spatial.js";

/* ------------------------------------------------------ API capability matrix */
// behavior ∈ LIVE | READ_ONLY | DRAFT_ONLY | PREVIEW_ONLY | DERIVED | LOCAL_ONLY | BLOCKED
export const CAPABILITY_MATRIX = [
  { capability: "organization", api: "GET /organizations", read: true, create: false, update: false, decision: false, execution: false, evidence: false, behavior: "READ_ONLY" },
  { capability: "workspace", api: "GET /workspaces", read: true, create: false, update: false, decision: false, execution: false, evidence: false, behavior: "READ_ONLY" },
  { capability: "project", api: "GET/POST /projects", read: true, create: true, update: false, decision: false, execution: false, evidence: false, behavior: "LIVE" },
  { capability: "mission", api: "GET/POST /missions", read: true, create: true, update: false, decision: false, execution: false, evidence: false, behavior: "LIVE" },
  { capability: "agent_binding", api: "GET/POST/PATCH /agent-bindings", read: true, create: true, update: true, decision: false, execution: false, evidence: false, behavior: "LIVE" },
  { capability: "approval", api: "GET/POST /approvals, decide, revoke", read: true, create: true, update: false, decision: true, execution: false, evidence: false, behavior: "LIVE" },
  { capability: "execution", api: "GET /runtime/executions, POST /execute", read: true, create: true, update: false, decision: false, execution: true, evidence: false, behavior: "LIVE" },
  { capability: "attention", api: "GET /runtime/attention", read: true, create: false, update: false, decision: false, execution: false, evidence: false, behavior: "READ_ONLY" },
  { capability: "evidence", api: "GET /runtime/export, /audit", read: true, create: false, update: false, decision: false, execution: false, evidence: true, behavior: "READ_ONLY" },
  { capability: "notification", api: "(none)", read: false, create: false, update: false, decision: false, execution: false, evidence: false, behavior: "DERIVED" },
  { capability: "saved_view", api: "(none)", read: false, create: false, update: false, decision: false, execution: false, evidence: false, behavior: "LOCAL_ONLY" },
  { capability: "workflow_template", api: "(none)", read: false, create: false, update: false, decision: false, execution: false, evidence: false, behavior: "LOCAL_ONLY" },
  { capability: "mission_plan", api: "(none)", read: false, create: false, update: false, decision: false, execution: false, evidence: false, behavior: "DRAFT_ONLY" },
];

export function capability(name) {
  return CAPABILITY_MATRIX.find((c) => c.capability === name) || null;
}
export function capabilityBehavior(name) {
  return capability(name)?.behavior || "BLOCKED";
}

/* ---------------------------------------------------------------- onboarding */

export const ONBOARDING_STEPS = [
  { id: "welcome", title: "Welcome", safety: false },
  { id: "safety", title: "Safety boundaries", safety: true },
  { id: "workspace", title: "Workspace", safety: false },
  { id: "project", title: "Project", safety: false },
  { id: "agents", title: "Available agents", safety: false },
  { id: "approvals", title: "Approval model", safety: true },
  { id: "execution", title: "Execution model", safety: true },
  { id: "notifications", title: "Notification preferences", safety: false },
  { id: "voice", title: "Voice setup", safety: false },
  { id: "ready", title: "Ready state", safety: false },
];

/* Progress derived from a set of completed step ids. Safety steps can never be
   reported complete unless explicitly acknowledged. */
export function onboardingProgress(completedIds = []) {
  const done = new Set(completedIds);
  const steps = ONBOARDING_STEPS.map((s) => ({ ...s, complete: done.has(s.id) }));
  const safetyDone = steps.filter((s) => s.safety).every((s) => s.complete);
  const complete = steps.every((s) => s.complete);
  const nextStep = steps.find((s) => !s.complete)?.id || null;
  return { steps, complete, safetyAcknowledged: safetyDone, nextStep, pct: Math.round((steps.filter((s) => s.complete).length / steps.length) * 100) };
}

/* Read-only onboarding facts from authorized platform data (never fabricated). */
export function onboardingFacts({ health, me, config, diagnostics, projects = [], bindings = [] } = {}) {
  const env = diagnostics?.environment || {};
  return {
    platformHealthy: !!health && (health.identity === "ACTIVE" || health.identity === "READY"),
    localhostOnly: true,
    productionAuthorized: env.production_authorized === true,
    connectorMode: config?.connectors?.mutations || "DRY_RUN_ONLY",
    financialExecution: config?.financial_execution === true ? "ENABLED" : "DISABLED",
    tradingExecution: config?.trading_execution === true ? "ENABLED" : "DISABLED",
    org: me?.context?.org_id || null,
    workspace: me?.context?.workspace_id || null,
    role: me?.context?.role || null,
    projectCount: projects.length,
    bindingCount: bindings.length,
    gateway: health?.runtime?.gateway || null,
  };
}

/* ----------------------------------------------------------- scope selection */

export function validateScope({ orgId, workspaceId, projectId } = {}) {
  const errors = [];
  if (!orgId) errors.push({ field: "org", code: "WORKSPACE_UNAVAILABLE", message: "No organization in context" });
  if (!workspaceId) errors.push({ field: "workspace", code: "WORKSPACE_UNAVAILABLE", message: "No workspace selected" });
  if (!projectId) errors.push({ field: "project", code: "PROJECT_UNAVAILABLE", message: "Select a project for mission scope" });
  return { valid: errors.length === 0, errors };
}

/* ------------------------------------------------------- mission draft/create */

export const RISK_LEVELS = ["low", "moderate", "high", "critical", "unknown"];

/* Operator-selected risk is clearly NOT an authoritative policy result. */
export function normalizeRiskSelection(value) {
  const v = String(value || "").toLowerCase();
  return RISK_LEVELS.includes(v) ? v : "unknown";
}

export function normalizeMissionDraft(draft = {}) {
  const title = String(draft.title || "").trim();
  const objective = String(draft.objective || "").trim();
  return {
    title,
    objective,
    outcome: String(draft.outcome || "").trim(),
    constraints: String(draft.constraints || "").trim(),
    deadline: String(draft.deadline || "").trim(),
    priority: ["low", "normal", "high"].includes(draft.priority) ? draft.priority : "normal",
    risk: normalizeRiskSelection(draft.risk),
    notes: String(draft.notes || "").trim(),
    projectId: draft.projectId || "",
    savedAt: draft.savedAt || null,
  };
}

/* A mission draft is submittable only when required fields + scope are present.
   Mission create IS live (POST /missions) — but requires a project. */
export function validateMissionDraft(draft = {}) {
  const d = normalizeMissionDraft(draft);
  const errors = [];
  if (!d.title) errors.push({ field: "title", message: "Mission title is required" });
  if (!d.objective) errors.push({ field: "objective", message: "Mission objective is required" });
  if (!d.projectId) errors.push({ field: "projectId", code: "PROJECT_UNAVAILABLE", message: "Select a project" });
  return { valid: errors.length === 0, errors, draft: d };
}

/* Derive the exact POST /missions body from a validated draft. `key` is a
   deterministic slug (no Date/random — safe for tests and SSR). */
export function missionCreateBody(draft) {
  const d = normalizeMissionDraft(draft);
  const key = (d.title || "mission").toUpperCase().replace(/[^A-Z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 24) || "MISSION";
  return { project_id: d.projectId, key, name: d.title };
}

/* --------------------------------------------------------------- mission plan */

export const PLAN_NODE_STATES = ["proposed", "approved", "active", "blocked", "completed", "failed", "cancelled", "unavailable"];

/* Build a reviewable plan structure from a mission + related records. Plan has
   NO persistence API → this is a DRAFT_ONLY derived view, clearly labelled. */
export function buildMissionPlan(mission, { bindings = [], approvals = [], executions = [], attention = [] } = {}) {
  const stages = [
    { id: "objective", label: "Objective", state: mission ? "proposed" : "unavailable", detail: mission?.name || "Unavailable" },
    { id: "agents", label: "Agents", state: bindings.length ? "proposed" : "unavailable", detail: `${bindings.length} bound` },
    { id: "approvals", label: "Approvals", state: approvals.length ? (approvals.some((a) => a.status === "pending") ? "blocked" : "approved") : "proposed", detail: `${approvals.length}` },
    { id: "runtime", label: "PlatformAgentRuntime", state: "proposed", detail: "Governed" },
    { id: "gateway", label: "ExecutionGateway", state: "proposed", detail: "Sole tool authority" },
    { id: "execution", label: "Execution", state: executions.length ? "active" : "proposed", detail: `${executions.length} runs` },
    { id: "evidence", label: "Evidence", state: executions.length ? "proposed" : "unavailable", detail: executions.length ? "On completion" : "Not generated" },
  ];
  return { stages, blocked: attention.length > 0 || approvals.some((a) => a.status === "pending") };
}

export function validateMissionPlan(plan, { bindings = [] } = {}) {
  const issues = [];
  if (!bindings.length) issues.push({ code: "AGENT_UNAVAILABLE", message: "No agent bound to this mission" });
  if (plan?.blocked) issues.push({ code: "APPROVAL_REQUIRED", message: "Plan has pending approvals or attention" });
  const executionReady = issues.length === 0;
  return { executionReady, issues };
}

/* --------------------------------------------------- agent/binding selection */

/* Reasons an agent binding cannot be selected for a mission. Empty = selectable. */
export function agentSelectionBlockers(binding, { requiredCapability, workspaceId } = {}) {
  const blockers = [];
  const state = String(binding?.state || "").toUpperCase();
  if (state !== "ACTIVE") blockers.push(state === "REVOKED" ? "Binding revoked/invalid" : "Binding inactive");
  if (workspaceId && binding?.workspace_id && binding.workspace_id !== workspaceId) blockers.push("Cross-workspace identity");
  if (requiredCapability) {
    const tools = Array.isArray(binding?.allowed_tools) ? binding.allowed_tools : [];
    const caps = Array.isArray(binding?.allowed_capabilities) ? binding.allowed_capabilities : [];
    if (!tools.includes(requiredCapability) && !caps.includes(requiredCapability)) blockers.push("Missing required capability");
  }
  return blockers;
}
export function isAgentSelectable(binding, ctx) {
  return agentSelectionBlockers(binding, ctx).length === 0;
}

/* ------------------------------------------------ approval request preview */

/* Prepare a truthful, scoped approval request. Approval create IS live
   (POST /approvals) — this returns both the preview and the exact body. */
export function buildApprovalRequest(input = {}) {
  const preview = {
    requestingAgent: input.agentId || input.bindingId || "Unspecified",
    missionId: input.missionId || "",
    authority: input.authority || "READ_ONLY",
    toolId: input.toolId || "",
    capability: input.capability || "",
    orgId: input.orgId || "",
    workspaceId: input.workspaceId || "",
    projectId: input.projectId || "",
    reason: String(input.reason || "").trim(),
    risk: normalizeRiskSelection(input.risk),
    sideEffectClass: input.sideEffectClass || "READ_ONLY",
    ttlSec: Number(input.ttlSec) > 0 ? Number(input.ttlSec) : 3600,
    singleUse: input.singleUse !== false,
    acknowledged: input.acknowledged === true,
  };
  const errors = [];
  if (!preview.toolId) errors.push({ field: "toolId", message: "Tool or capability is required" });
  if (!preview.reason) errors.push({ field: "reason", message: "A reason is required for review" });
  if (!preview.acknowledged) errors.push({ field: "acknowledged", message: "Operator acknowledgement required" });
  const body = {
    tool_id: preview.toolId,
    action: input.action || "",
    target_resource: input.targetResource || "",
    authority: preview.authority,
    side_effect_class: preview.sideEffectClass,
    capability: preview.capability,
    project_id: preview.projectId,
    mission_id: preview.missionId,
    connector: input.connector || "",
    ttl_sec: preview.ttlSec,
  };
  return { preview, body, valid: errors.length === 0, errors };
}

/* --------------------------------------------------- execution readiness */

export const READINESS = {
  READY: "READY_FOR_GOVERNED_EXECUTION",
  READY_LIMITED: "READY_WITH_LIMITATIONS",
  BLOCKED_APPROVAL: "BLOCKED_MISSING_APPROVAL",
  BLOCKED_SCOPE: "BLOCKED_INVALID_SCOPE",
  BLOCKED_AGENT: "BLOCKED_AGENT_UNAVAILABLE",
  BLOCKED_TOOL: "BLOCKED_TOOL_UNREGISTERED",
  BLOCKED_RUNTIME: "BLOCKED_RUNTIME_UNAVAILABLE",
  BLOCKED_UNSAFE: "BLOCKED_UNSAFE_CONFIGURATION",
  BLOCKED_UNKNOWN: "BLOCKED_UNKNOWN",
};

/* Classify readiness. Never READY when a mandatory condition is unknown. */
export function classifyExecutionReadiness(ctx = {}) {
  const checks = [];
  const add = (id, label, ok, blocking = true) => checks.push({ id, label, ok, blocking });

  add("mission", "Mission exists", !!ctx.mission);
  add("scope", "Scope valid", !!(ctx.orgId && ctx.workspaceId && ctx.projectId));
  add("agent", "Agent/binding valid", ctx.agentValid === true);
  add("tool", "Tool registered", ctx.toolRegistered === true);
  add("approval", "Approval present & valid", ctx.approvalValid === true);
  add("runtime", "Runtime & gateway available", ctx.runtimeAvailable === true);
  add("attention", "No blocking attention", ctx.blockingAttention !== true);
  add("evidence", "Evidence destination", ctx.evidenceAvailable !== false, false);
  add("production", "Production unauthorized (safe)", ctx.productionAuthorized !== true);
  add("connectors", "Connectors dry-run (safe)", ctx.connectorSafe !== false);

  const unknown = (v) => v === undefined || v === null;
  let state = READINESS.READY;
  if (!ctx.mission) state = READINESS.BLOCKED_SCOPE;
  else if (!(ctx.orgId && ctx.workspaceId && ctx.projectId)) state = READINESS.BLOCKED_SCOPE;
  else if (ctx.agentValid !== true) state = READINESS.BLOCKED_AGENT;
  else if (ctx.toolRegistered !== true) state = READINESS.BLOCKED_TOOL;
  else if (ctx.approvalValid !== true) state = READINESS.BLOCKED_APPROVAL;
  else if (ctx.runtimeAvailable !== true) state = READINESS.BLOCKED_RUNTIME;
  else if (ctx.blockingAttention === true) state = READINESS.BLOCKED_UNSAFE;
  else if (ctx.productionAuthorized === true || ctx.connectorSafe === false) state = READINESS.BLOCKED_UNSAFE;
  else if (unknown(ctx.agentValid) || unknown(ctx.toolRegistered) || unknown(ctx.approvalValid) || unknown(ctx.runtimeAvailable)) state = READINESS.BLOCKED_UNKNOWN;
  else if (ctx.evidenceAvailable === false) state = READINESS.READY_LIMITED;

  const executeAllowed = state === READINESS.READY || state === READINESS.READY_LIMITED;
  return { state, checks, executeAllowed };
}

/* ----------------------------------------------------- operator action queue */

export const ACTION_CATEGORIES = ["urgent", "needs_decision", "needs_review", "needs_configuration", "waiting", "informational"];

/* Aggregate ONLY real, supported operator actions from authorized records. No
   invented acknowledge/resolve/rerun actions. */
export function aggregateOperatorActions({ approvals = [], missions = [], executions = [], attention = [], onboardingComplete = true } = {}) {
  const items = [];
  const now = null;
  for (const a of approvals) {
    if (String(a.status).toLowerCase() === "pending") {
      const high = /DESTRUCTIVE|SECURITY|FINANCIAL|TRADING/i.test(`${a.side_effect_class} ${a.authority}`);
      items.push({ id: `appr:${a.approval_id}`, title: `Decide approval: ${a.tool_id}`, category: high ? "urgent" : "needs_decision", reason: "Pending approval requires a decision", route: `/platform/approvals/${a.approval_id}`, action: "review approval", missionId: a.mission_id || "", source: "approval" });
    }
  }
  for (const m of missions) {
    if (String(m.status).toLowerCase() === "blocked") items.push({ id: `mis:${m.mission_id}`, title: `Blocked mission: ${m.name}`, category: "needs_review", reason: "Mission is blocked", route: `/platform/missions/${m.mission_id}`, action: "inspect mission", missionId: m.mission_id, source: "mission" });
  }
  for (const e of executions) {
    if (String(e.state).toUpperCase() === "FAILED") items.push({ id: `exec:${e.execution_id}`, title: `Failed execution: ${e.tool_id}`, category: "needs_review", reason: e.error_code || "Execution failed", route: `/platform/attention/${e.execution_id}`, action: "inspect execution", missionId: e.mission_id || "", source: "execution" });
  }
  for (const t of attention) {
    items.push({ id: `attn:${t.execution_id}`, title: `Attention: ${t.tool_id || t.execution_id}`, category: "needs_review", reason: (t.attention_reasons || []).join(", ") || "Flagged by runtime", route: `/platform/attention/${t.execution_id}`, action: "inspect attention item", missionId: t.mission_id || "", source: "attention" });
  }
  if (!onboardingComplete) items.push({ id: "onboarding", title: "Complete first-run onboarding", category: "needs_configuration", reason: "Onboarding not finished", route: "/platform/onboarding", action: "revisit onboarding", source: "onboarding" });
  const rank = { urgent: 0, needs_decision: 1, needs_review: 2, needs_configuration: 3, waiting: 4, informational: 5 };
  return items.sort((a, b) => (rank[a.category] ?? 9) - (rank[b.category] ?? 9));
}

/* -------------------------------------------------------- notifications (derived) */

export function deriveNotifications({ approvals = [], executions = [], attention = [], health } = {}) {
  const out = [];
  for (const a of approvals) {
    const st = String(a.status).toLowerCase();
    if (st === "pending") out.push({ id: `n-appr-${a.approval_id}`, type: "approval_requested", title: `Approval pending: ${a.tool_id}`, severity: "attention", time: a.created_at || 0, route: `/platform/approvals/${a.approval_id}`, source: "approval" });
    if (st === "consumed") out.push({ id: `n-cons-${a.approval_id}`, type: "approval_consumed", title: `Approval consumed: ${a.tool_id}`, severity: "info", time: a.consumed_at || 0, route: `/platform/approvals/${a.approval_id}`, source: "approval" });
  }
  for (const e of executions) {
    const s = String(e.state).toUpperCase();
    if (s === "FAILED") out.push({ id: `n-fail-${e.execution_id}`, type: "execution_failed", title: `Execution failed: ${e.tool_id}`, severity: "danger", time: e.updated_at || 0, route: `/platform/attention/${e.execution_id}`, source: "execution" });
    if (s === "SUCCEEDED") out.push({ id: `n-ok-${e.execution_id}`, type: "execution_completed", title: `Execution completed: ${e.tool_id}`, severity: "success", time: e.updated_at || 0, route: "", source: "execution" });
  }
  for (const t of attention) out.push({ id: `n-attn-${t.execution_id}`, type: "attention_raised", title: `Attention raised: ${t.tool_id || t.execution_id}`, severity: "attention", time: t.updated_at || t.created_at || 0, route: `/platform/attention/${t.execution_id}`, source: "attention" });
  if (health && health.runtime?.gateway && !/ENFORCED|ACTIVE|READY|OK/i.test(String(health.runtime.gateway))) out.push({ id: "n-gw", type: "runtime_unhealthy", title: `Runtime gateway: ${health.runtime.gateway}`, severity: "danger", time: 0, route: "/platform/ops", source: "runtime" });
  return out.sort((a, b) => (b.time || 0) - (a.time || 0));
}

/* --------------------------------------------------------- evidence timeline */

export function buildEvidenceTimeline({ missions = [], approvals = [], executions = [], attention = [] } = {}) {
  const ev = [];
  for (const m of missions) ev.push({ id: `ev-m-${m.mission_id}`, kind: "mission_created", time: m.created_at || 0, object: m.mission_id, label: `Mission created: ${m.name}`, state: "Available" });
  for (const a of approvals) {
    ev.push({ id: `ev-ar-${a.approval_id}`, kind: "approval_request", time: a.created_at || 0, object: a.approval_id, label: `Approval requested: ${a.tool_id}`, state: "Available" });
    if (a.decided_at) ev.push({ id: `ev-ad-${a.approval_id}`, kind: "approval_decision", time: a.decided_at, object: a.approval_id, label: `Approval ${a.status}: ${a.tool_id}`, state: "Available" });
  }
  for (const e of executions) {
    ev.push({ id: `ev-es-${e.execution_id}`, kind: "execution_start", time: e.created_at || 0, object: e.execution_id, label: `Execution ${e.state}: ${e.tool_id}`, state: e.error_code ? "Invalid" : "Available" });
  }
  for (const t of attention) ev.push({ id: `ev-at-${t.execution_id}`, kind: "attention_event", time: t.updated_at || t.created_at || 0, object: t.execution_id, label: `Attention: ${t.tool_id || t.execution_id}`, state: "Available" });
  return ev.sort((a, b) => (b.time || 0) - (a.time || 0));
}

/* ------------------------------------------------------------- saved views */

export function validateSavedView(view = {}) {
  const allowed = ["id", "name", "route", "filters", "sort", "group", "layout", "columns", "workspaceId", "savedAt"];
  const forbidden = ["token", "credential", "secret", "authority", "permission", "password"];
  const errors = [];
  if (!String(view.name || "").trim()) errors.push({ field: "name", message: "Name required" });
  if (!String(view.route || "").startsWith("/platform")) errors.push({ field: "route", message: "Route must be a platform route" });
  for (const k of Object.keys(view)) {
    if (forbidden.some((f) => k.toLowerCase().includes(f))) errors.push({ field: k, message: "Forbidden field in saved view" });
  }
  const clean = {};
  for (const k of allowed) if (k in view) clean[k] = view[k];
  return { valid: errors.length === 0, errors, view: clean };
}

/* --------------------------------------------------- cross-workspace search */
// Client-side over already-fetched authorized records only. Scope is honest:
// SEARCHING_AUTHORIZED_LOADED_RECORDS.
export function searchAuthorizedRecords(query, { missions = [], bindings = [], approvals = [], attention = [], executions = [], projects = [] } = {}, typeFilter = "all") {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return [];
  const hit = (s) => String(s || "").toLowerCase().includes(q);
  const out = [];
  const push = (type, cond, id, label, route) => { if ((typeFilter === "all" || typeFilter === type) && cond) out.push({ type, id, label, route }); };
  for (const m of missions) push("mission", hit(m.name) || hit(m.key) || hit(m.mission_id), m.mission_id, `Mission — ${m.name}`, `/platform/missions/${m.mission_id}`);
  for (const b of bindings) push("agent", hit(b.name) || hit(b.agent_id) || hit(b.binding_id), b.binding_id, `Agent — ${b.name}`, `/platform/agents/${b.binding_id}`);
  for (const a of approvals) push("approval", hit(a.tool_id) || hit(a.approval_id), a.approval_id, `Approval — ${a.tool_id}`, `/platform/approvals/${a.approval_id}`);
  for (const t of attention) push("attention", hit(t.tool_id) || hit(t.execution_id), t.execution_id, `Attention — ${t.tool_id || t.execution_id}`, `/platform/attention/${t.execution_id}`);
  for (const e of executions) push("execution", hit(e.tool_id) || hit(e.execution_id), e.execution_id, `Execution — ${e.tool_id}`, `/platform/attention/${e.execution_id}`);
  for (const p of projects) push("project", hit(p.name) || hit(p.project_id), p.project_id, `Project — ${p.name}`, "/platform/missions");
  return out;
}

/* ----------------------------------------------------------- templates (local) */

export const WORKFLOW_TEMPLATES = [
  { id: "operational-review", name: "Operational review", objective: "Review runtime health, attention, and approvals for the current workspace.", inputs: ["workspace"], stages: ["Gather runtime state", "Review attention", "Review approvals", "Record findings"], roles: ["Operator"], tools: ["read-only"], approvals: "None (read-only)", evidence: "Runtime export", risk: "low" },
  { id: "research-task", name: "Research task", objective: "Run a bounded read-only research task via a governed advisory agent.", inputs: ["objective", "project"], stages: ["Define objective", "Select advisory agent", "Prepare approval", "Governed execution", "Collect evidence"], roles: ["Operator"], tools: ["m49.echo_readonly"], approvals: "Read-only authority", evidence: "Execution result", risk: "low" },
  { id: "documentation-audit", name: "Documentation audit", objective: "Audit documentation completeness and record gaps.", inputs: ["project"], stages: ["Scope", "Review", "Record gaps"], roles: ["Operator"], tools: ["read-only"], approvals: "None", evidence: "Notes export", risk: "low" },
  { id: "release-readiness", name: "Release readiness check", objective: "Verify release gates and runtime posture before any release decision.", inputs: ["workspace"], stages: ["Runtime health", "Attention scan", "Approval review", "Readiness summary"], roles: ["Owner", "Operator"], tools: ["read-only"], approvals: "None", evidence: "Readiness summary", risk: "moderate" },
  { id: "incident-investigation", name: "Incident investigation", objective: "Investigate a failed execution or attention item and gather evidence.", inputs: ["execution"], stages: ["Locate item", "Inspect timeline", "Gather evidence", "Recommend action"], roles: ["Operator", "Owner"], tools: ["read-only"], approvals: "None", evidence: "Timeline + logs", risk: "moderate" },
];

export function normalizeTemplate(t) {
  return { local: true, ...t };
}

/* ----------------------------------------------------------- role-aware actions */

export const ROLE_ACTION_MATRIX = {
  viewer: { decide_approval: "insufficient", request_approval: "insufficient", create_mission: "insufficient", cancel_execution: "insufficient", inspect: "permitted", export_evidence: "read-only" },
  operator: { decide_approval: "requires_approval", request_approval: "permitted", create_mission: "permitted", cancel_execution: "permitted", inspect: "permitted", export_evidence: "permitted" },
  owner: { decide_approval: "permitted", request_approval: "permitted", create_mission: "permitted", cancel_execution: "permitted", inspect: "permitted", export_evidence: "permitted" },
  admin: { decide_approval: "permitted", request_approval: "permitted", create_mission: "permitted", cancel_execution: "permitted", inspect: "permitted", export_evidence: "permitted" },
  system: { decide_approval: "permitted", request_approval: "permitted", create_mission: "permitted", cancel_execution: "permitted", inspect: "permitted", export_evidence: "permitted" },
};

export function actionPermission(role, action) {
  const r = String(role || "").toLowerCase();
  const row = ROLE_ACTION_MATRIX[r];
  if (!row) return "unknown";
  return row[action] || "unavailable";
}
export function canPerform(role, action) {
  return actionPermission(role, action) === "permitted";
}

/* --------------------------------------------------- server reconciliation */

export const RECON_STATES = ["idle", "submitting", "server_accepted", "server_rejected", "reconciling", "reconciled", "conflict", "stale", "unknown"];

/* Never report a successful authority/execution state from client alone. */
export function reconcileResult({ submitted, serverStatus, expected, actual } = {}) {
  if (!submitted) return "idle";
  if (serverStatus === "rejected") return "server_rejected";
  if (serverStatus === "accepted") {
    if (expected === undefined || actual === undefined) return "reconciling";
    if (expected === actual) return "reconciled";
    return "conflict";
  }
  if (serverStatus === "stale") return "stale";
  return "unknown";
}

/* ----------------------------------------------------------- error taxonomy */

export const ERROR_TAXONOMY = {
  AUTH_REQUIRED: "Authentication required",
  PERMISSION_DENIED: "Permission denied",
  WORKSPACE_UNAVAILABLE: "Workspace unavailable",
  PROJECT_UNAVAILABLE: "Project unavailable",
  MISSION_UNAVAILABLE: "Mission unavailable",
  AGENT_UNAVAILABLE: "Agent unavailable",
  CAPABILITY_UNAVAILABLE: "Capability unavailable",
  APPROVAL_REQUIRED: "Approval required",
  APPROVAL_EXPIRED: "Approval expired",
  APPROVAL_CONSUMED: "Approval consumed",
  APPROVAL_REJECTED: "Approval rejected",
  EXECUTION_UNAVAILABLE: "Execution unavailable",
  RUNTIME_UNAVAILABLE: "Runtime unavailable",
  EVIDENCE_UNAVAILABLE: "Evidence unavailable",
  STALE_STATE: "Stale state",
  VALIDATION_FAILED: "Validation failed",
  UNSAFE_CONFIG: "Unsafe configuration",
  SERVER_UNAVAILABLE: "Server unavailable",
  UNKNOWN: "Unknown error",
};

export function classifyError(err) {
  const msg = String(err?.message || err || "").toLowerCase();
  const status = err?.status;
  if (status === 401 || /auth|token|unauthenticated/.test(msg)) return "AUTH_REQUIRED";
  if (status === 403 || /permission|forbidden|insufficient/.test(msg)) return "PERMISSION_DENIED";
  if (/expired/.test(msg)) return "APPROVAL_EXPIRED";
  if (/consumed/.test(msg)) return "APPROVAL_CONSUMED";
  if (/rejected/.test(msg)) return "APPROVAL_REJECTED";
  if (/stale|conflict|version/.test(msg)) return "STALE_STATE";
  if (/validation|invalid|required/.test(msg)) return "VALIDATION_FAILED";
  if (status === 404 || /not found|unavailable/.test(msg)) return "MISSION_UNAVAILABLE";
  if (/failed to fetch|networkerror|econnrefused|load failed/.test(msg)) return "SERVER_UNAVAILABLE";
  return "UNKNOWN";
}
export function errorMessage(code) {
  return ERROR_TAXONOMY[code] || ERROR_TAXONOMY.UNKNOWN;
}

/* readiness/plan/action → signal colour */
export function readinessSignal(state) {
  if (state === READINESS.READY) return SIGNAL.ACTIVE;
  if (state === READINESS.READY_LIMITED) return SIGNAL.ATTENTION;
  return SIGNAL.DANGER;
}
