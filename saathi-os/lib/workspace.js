// M59 — Spatial workspace domain logic. Pure and unit-testable.
//
// Normalizes real /api/v1/platform/* records (missions, agent bindings,
// approvals, runtime executions) into workspace view-models for the four
// standalone spatial workspaces. It invents NO data: absent fields resolve to
// explicit "Unavailable"/"Unknown" sentinels, never to fabricated values.
//
// Authority truth is preserved: this module classifies and labels records but
// never grants authority. Decisions still route through server-authorized APIs.

import { SIGNAL } from "./spatial.js";
import { attentionSeverity } from "./platform-ops.js";
import { severityRank } from "./attention.js";

export const UNAVAILABLE = "Unavailable";
export const NOT_CONFIGURED = "Not configured";
export const NO_RECORDS = "No active records";
export const UNKNOWN = "Unknown";

/* Resolve a possibly-missing scalar to a truthful display value. */
export function fmt(value, fallback = UNKNOWN) {
  if (value === null || value === undefined) return fallback;
  const s = typeof value === "string" ? value.trim() : value;
  if (s === "") return fallback;
  return s;
}

/* Epoch-seconds → ISO string, or an explicit unknown sentinel. Deterministic. */
export function fmtTime(ts, fallback = UNKNOWN) {
  const n = Number(ts);
  if (!Number.isFinite(n) || n <= 0) return fallback;
  try {
    return new Date(n * 1000).toISOString().replace(".000Z", "Z");
  } catch {
    return fallback;
  }
}

/* Relative age in whole seconds from a fixed `now` (seconds). Null when unknown. */
export function ageSeconds(ts, now) {
  const n = Number(ts);
  if (!Number.isFinite(n) || n <= 0 || !Number.isFinite(now)) return null;
  return Math.max(0, Math.round(now - n));
}

const titleCase = (s) =>
  String(s || "")
    .toLowerCase()
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

/* ------------------------------------------------------------------ Missions */

const MISSION_SIGNAL = {
  active: SIGNAL.ACTIVE,
  running: SIGNAL.ACTIVE,
  blocked: SIGNAL.DANGER,
  failed: SIGNAL.DANGER,
  error: SIGNAL.DANGER,
  completed: SIGNAL.SUCCESS,
  done: SIGNAL.SUCCESS,
  draft: SIGNAL.IDLE,
  paused: SIGNAL.ATTENTION,
};

export function missionSignal(mission, related = {}) {
  const status = String(mission?.status || "").toLowerCase();
  if (MISSION_SIGNAL[status] === SIGNAL.DANGER) return SIGNAL.DANGER;
  if ((related.attentionCount || 0) > 0) return SIGNAL.ATTENTION;
  if ((related.pendingApprovals || 0) > 0) return SIGNAL.ATTENTION;
  return MISSION_SIGNAL[status] || (mission ? SIGNAL.IDLE : SIGNAL.UNKNOWN);
}

export function missionStatusLabel(status) {
  return status ? titleCase(status) : UNKNOWN;
}

/* Compose a mission view-model from its record plus related runtime records.
   There is no per-mission API, so related counts are derived by matching the
   mission_id carried on executions / approvals / attention items. */
export function normalizeMission(mission, ctx = {}) {
  const id = mission?.mission_id || mission?.id || "";
  const executions = (ctx.executions || []).filter((e) => e.mission_id === id);
  const approvals = (ctx.approvals || []).filter((a) => a.mission_id === id);
  const attention = (ctx.attention || []).filter((a) => a.mission_id === id);
  const activeExecutions = executions.filter(
    (e) => !TERMINAL_EXEC.has(String(e.state || "").toUpperCase())
  ).length;
  const pendingApprovals = approvals.filter(
    (a) => String(a.status || "").toLowerCase() === "pending"
  ).length;
  const related = { attentionCount: attention.length, pendingApprovals };
  return {
    id,
    name: fmt(mission?.name),
    key: fmt(mission?.key),
    status: String(mission?.status || "").toLowerCase() || "unknown",
    statusLabel: missionStatusLabel(mission?.status),
    signal: missionSignal(mission, related),
    owner: fmt(mission?.owner_id),
    projectId: fmt(mission?.project_id, UNAVAILABLE),
    workspaceId: fmt(mission?.workspace_id, UNAVAILABLE),
    createdAt: fmtTime(mission?.created_at),
    activeExecutions,
    executionCount: executions.length,
    pendingApprovals,
    attentionCount: attention.length,
    executions,
    approvals,
    attention,
  };
}

export function filterMissions(items, { status = "all", q = "" } = {}) {
  const needle = q.trim().toLowerCase();
  return items.filter((m) => {
    if (status !== "all" && m.status !== status) return false;
    if (!needle) return true;
    return (
      m.name.toLowerCase().includes(needle) ||
      m.key.toLowerCase().includes(needle) ||
      m.id.toLowerCase().includes(needle)
    );
  });
}

export function sortMissions(items, mode = "activity") {
  const copy = [...items];
  if (mode === "risk") {
    const rank = { [SIGNAL.DANGER]: 0, [SIGNAL.ATTENTION]: 1, [SIGNAL.ACTIVE]: 2, [SIGNAL.IDLE]: 3, [SIGNAL.SUCCESS]: 4, [SIGNAL.UNKNOWN]: 5 };
    copy.sort((a, b) => (rank[a.signal] ?? 9) - (rank[b.signal] ?? 9));
  } else if (mode === "status") {
    copy.sort((a, b) => a.status.localeCompare(b.status));
  } else {
    copy.sort((a, b) => (b.executionCount || 0) - (a.executionCount || 0));
  }
  return copy;
}

/* -------------------------------------------------------------------- Agents */

const TERMINAL_EXEC = new Set(["SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT", "COMPLETED"]);

const AGENT_STATE_LABEL = {
  ACTIVE: "Available",
  SUSPENDED: "Inactive",
  REVOKED: "Blocked",
};

export function agentStatusLabel(state, { running = false, waitingApproval = false } = {}) {
  const s = String(state || "").toUpperCase();
  if (s === "ACTIVE" && running) return "Running";
  if (s === "ACTIVE" && waitingApproval) return "Waiting for approval";
  return AGENT_STATE_LABEL[s] || UNKNOWN;
}

export function agentSignal(state) {
  const s = String(state || "").toUpperCase();
  if (s === "ACTIVE") return SIGNAL.ACTIVE;
  if (s === "SUSPENDED") return SIGNAL.IDLE;
  if (s === "REVOKED") return SIGNAL.DANGER;
  return SIGNAL.UNKNOWN;
}

/* An agent binding is execution-capable only when its authority ceiling permits
   effects beyond read-only. Anything read-only (or unknown) is advisory. */
export function agentAuthorityKind(binding) {
  const ceiling = String(binding?.authority_ceiling || "").toUpperCase();
  if (!ceiling) return "advisory";
  if (ceiling === "READ_ONLY" || ceiling === "ADVISORY" || ceiling === "NONE") return "advisory";
  return "execution";
}

export function normalizeAgent(binding, ctx = {}) {
  const id = binding?.binding_id || "";
  const runs = (ctx.executions || []).filter((e) => e.binding_id === id);
  const running = runs.some((e) => !TERMINAL_EXEC.has(String(e.state || "").toUpperCase()));
  const waitingApproval = runs.some((e) => String(e.state || "").toUpperCase() === "WAITING_APPROVAL");
  const failures = runs.filter((e) => String(e.state || "").toUpperCase() === "FAILED");
  const state = String(binding?.state || "").toUpperCase();
  return {
    id,
    name: fmt(binding?.name),
    agentId: fmt(binding?.agent_id),
    description: fmt(binding?.description, ""),
    role: fmt(binding?.agent_id), // no distinct role field; agent_id is the stable identity
    state: state || "UNKNOWN",
    statusLabel: agentStatusLabel(state, { running, waitingApproval }),
    signal: agentSignal(state),
    bound: state === "ACTIVE",
    authorityKind: agentAuthorityKind(binding),
    authorityCeiling: fmt(binding?.authority_ceiling, UNKNOWN),
    allowedTools: Array.isArray(binding?.allowed_tools) ? binding.allowed_tools : [],
    allowedCapabilities: Array.isArray(binding?.allowed_capabilities) ? binding.allowed_capabilities : [],
    version: binding?.version ?? null,
    orgId: fmt(binding?.org_id, UNAVAILABLE),
    workspaceId: fmt(binding?.workspace_id, UNAVAILABLE),
    projectId: fmt(binding?.project_id, ""),
    missionId: fmt(binding?.mission_id, ""),
    createdAt: fmtTime(binding?.created_at),
    updatedAt: fmtTime(binding?.updated_at),
    runs,
    recentFailures: failures,
  };
}

/* ----------------------------------------------------------------- Approvals */

const RISK_HIGH = /DESTRUCTIVE|SECURITY|FINANCIAL|TRADING|DELETE|IRREVERSIBLE/i;
const RISK_MED = /WRITE|MUTAT|CREATE|UPDATE|SEND|CONNECTOR/i;

export function approvalRiskLevel(approval) {
  const blob = `${approval?.side_effect_class || ""} ${approval?.authority || ""} ${approval?.action || ""}`;
  if (RISK_HIGH.test(blob)) return "high";
  if (RISK_MED.test(blob)) return "medium";
  if (/READ_ONLY|NONE/i.test(blob)) return "low";
  return "unknown";
}

export function isApprovalExpired(approval, now) {
  const exp = Number(approval?.expires_at);
  return Number.isFinite(exp) && exp > 0 && Number.isFinite(now) && exp < now;
}

/* Effective lifecycle status — honors server status but surfaces derived
   terminal facts (expired, consumed) the raw status field may not encode. */
export function approvalLifecycle(approval, now) {
  const status = String(approval?.status || "").toLowerCase();
  if (Number(approval?.consumed_at) > 0) return "consumed";
  if (status === "pending" && isApprovalExpired(approval, now)) return "expired";
  return status || "unknown";
}

export function approvalLifecycleLabel(lifecycle) {
  return lifecycle ? titleCase(lifecycle) : UNKNOWN;
}

/* Decidable only when the server would still accept a decision: genuinely
   pending, not expired, not already consumed. UI must never optimistically
   flip this — the server remains the authority. */
export function isApprovalDecidable(approval, now) {
  return approvalLifecycle(approval, now) === "pending";
}

export function approvalSignal(approval, now) {
  const lc = approvalLifecycle(approval, now);
  if (lc === "rejected" || lc === "revoked" || lc === "expired") return SIGNAL.DANGER;
  if (lc === "approved" || lc === "consumed") return SIGNAL.SUCCESS;
  if (lc === "pending") return approvalRiskLevel(approval) === "high" ? SIGNAL.DANGER : SIGNAL.ATTENTION;
  return SIGNAL.UNKNOWN;
}

export function normalizeApproval(approval, now) {
  const lifecycle = approvalLifecycle(approval, now);
  return {
    id: approval?.approval_id || "",
    toolId: fmt(approval?.tool_id),
    action: fmt(approval?.action, ""),
    targetResource: fmt(approval?.target_resource, ""),
    authority: fmt(approval?.authority, UNKNOWN),
    sideEffectClass: fmt(approval?.side_effect_class, UNKNOWN),
    capability: fmt(approval?.capability, ""),
    connector: fmt(approval?.connector, ""),
    status: String(approval?.status || "").toLowerCase() || "unknown",
    lifecycle,
    lifecycleLabel: approvalLifecycleLabel(lifecycle),
    signal: approvalSignal(approval, now),
    risk: approvalRiskLevel(approval),
    decidable: isApprovalDecidable(approval, now),
    expired: isApprovalExpired(approval, now),
    consumed: Number(approval?.consumed_at) > 0,
    requestedBy: fmt(approval?.requested_by || approval?.user_id, UNKNOWN),
    decidedBy: fmt(approval?.decided_by, ""),
    reason: fmt(approval?.reason, ""),
    orgId: fmt(approval?.org_id, UNAVAILABLE),
    workspaceId: fmt(approval?.workspace_id, UNAVAILABLE),
    projectId: fmt(approval?.project_id, ""),
    missionId: fmt(approval?.mission_id, ""),
    runId: fmt(approval?.run_id, ""),
    createdAt: fmtTime(approval?.created_at),
    expiresAt: fmtTime(approval?.expires_at, NOT_CONFIGURED),
    decidedAt: fmtTime(approval?.decided_at, ""),
    consumedAt: fmtTime(approval?.consumed_at, ""),
  };
}

export function filterPlatformApprovals(items, { lifecycle = "all", risk = "all", q = "" } = {}) {
  const needle = q.trim().toLowerCase();
  return items.filter((a) => {
    if (lifecycle !== "all" && a.lifecycle !== lifecycle) return false;
    if (risk !== "all" && a.risk !== risk) return false;
    if (!needle) return true;
    return (
      a.toolId.toLowerCase().includes(needle) ||
      a.id.toLowerCase().includes(needle) ||
      a.action.toLowerCase().includes(needle)
    );
  });
}

export function summarizePlatformApprovals(items) {
  return {
    pending: items.filter((a) => a.lifecycle === "pending").length,
    highRisk: items.filter((a) => a.lifecycle === "pending" && a.risk === "high").length,
    consumed: items.filter((a) => a.lifecycle === "consumed").length,
    rejected: items.filter((a) => a.lifecycle === "rejected").length,
    expired: items.filter((a) => a.lifecycle === "expired").length,
  };
}

/* ---------------------------------------------------------------- Attention */
/* Attention items are runtime executions the backend flagged as requiring
   attention (they carry `attention_reasons`). There is no acknowledge/resolve
   API, so the workspace is inspect + navigate + governed retry/cancel only. */

export function attentionItemSeverity(item) {
  const reasons = Array.isArray(item?.attention_reasons) ? item.attention_reasons : [];
  if (!reasons.length) return "informational";
  let worst = "informational";
  for (const r of reasons) {
    const sev = attentionSeverity(r);
    if (severityRank(sev) > severityRank(worst)) worst = sev;
  }
  return worst;
}

const SEV_SIGNAL = {
  critical: SIGNAL.DANGER,
  high: SIGNAL.DANGER,
  medium: SIGNAL.ATTENTION,
  low: SIGNAL.ATTENTION,
  informational: SIGNAL.IDLE,
};

export function normalizeAttention(execution, now) {
  const reasons = Array.isArray(execution?.attention_reasons) ? execution.attention_reasons : [];
  const severity = attentionItemSeverity(execution);
  return {
    id: execution?.execution_id || "",
    title: `${fmt(execution?.tool_id, "execution")} · ${fmt(execution?.state, UNKNOWN)}`,
    reasons,
    reason: reasons.length ? reasons.join(", ") : fmt(execution?.error_code, "Flagged by runtime"),
    severity,
    severityLabel: titleCase(severity),
    signal: SEV_SIGNAL[severity] || SIGNAL.ATTENTION,
    objectType: "execution",
    state: fmt(execution?.state, UNKNOWN),
    missionId: fmt(execution?.mission_id, ""),
    agentId: fmt(execution?.agent_id, ""),
    bindingId: fmt(execution?.binding_id, ""),
    approvalId: fmt(execution?.approval_id, ""),
    errorCode: fmt(execution?.error_code, ""),
    recoveryCount: execution?.recovery_count ?? 0,
    createdAt: fmtTime(execution?.created_at),
    updatedAt: fmtTime(execution?.updated_at),
    ageSeconds: ageSeconds(execution?.updated_at || execution?.created_at, now),
  };
}

export const ATTENTION_GROUPS = ["critical", "high", "medium", "informational"];

/* Group into the four documented severity lanes; low folds into medium. */
export function groupAttentionBySeverity(items) {
  const groups = { critical: [], high: [], medium: [], informational: [] };
  for (const it of items) {
    const sev = it.severity === "low" ? "medium" : it.severity;
    (groups[sev] || groups.informational).push(it);
  }
  return groups;
}

/* ----------------------------------------------------------- Command palette */

const ROUTE_COMMANDS = [
  { id: "go-home", label: "Go to Home", route: "/platform", keywords: "home core spatial" },
  { id: "go-missions", label: "Go to Missions", route: "/platform/missions", keywords: "mission control" },
  { id: "go-agents", label: "Go to Agents", route: "/platform/agents", keywords: "agent constellation binding" },
  { id: "go-approvals", label: "Go to Approvals", route: "/platform/approvals", keywords: "approval authority" },
  { id: "go-attention", label: "Go to Attention", route: "/platform/attention", keywords: "attention runtime alert" },
  { id: "go-ops", label: "Go to Operations", route: "/platform/ops", keywords: "operations constellation" },
];

/* Build the palette command list. Navigation + safe local actions are always
   present; per-object "open" commands come only from ALREADY-fetched authorized
   records (never an unauthorized index). Mutation commands are NOT synthesized
   here — decisions live on their server-authorized detail routes. */
export function buildCommands({ missions = [], agents = [], approvals = [], attention = [], actions = [] } = {}) {
  const cmds = ROUTE_COMMANDS.map((c) => ({ ...c, group: "Navigate", type: "nav" }));
  cmds.push(
    { id: "help", label: "Open command help", group: "Help", type: "help", keywords: "help shortcuts keyboard" },
    { id: "toggle-motion", label: "Toggle reduced motion preference", group: "Preferences", type: "action", keywords: "motion accessibility animation" },
  );
  for (const a of actions) cmds.push({ ...a, group: a.group || "Actions", type: a.type || "action" });
  for (const m of missions.slice(0, 20))
    cmds.push({ id: `mission:${m.id}`, label: `Mission — ${m.name}`, route: `/platform/missions/${m.id}`, group: "Missions", type: "nav", keywords: `${m.key} ${m.status}` });
  for (const g of agents.slice(0, 20))
    cmds.push({ id: `agent:${g.id}`, label: `Agent — ${g.name}`, route: `/platform/agents/${g.id}`, group: "Agents", type: "nav", keywords: `${g.agentId} ${g.statusLabel}` });
  for (const a of approvals.slice(0, 20))
    cmds.push({ id: `approval:${a.id}`, label: `Approval — ${a.toolId}`, route: `/platform/approvals/${a.id}`, group: "Approvals", type: "nav", keywords: `${a.lifecycle} ${a.risk}` });
  for (const t of attention.slice(0, 20))
    cmds.push({ id: `attention:${t.id}`, label: `Attention — ${t.title}`, route: `/platform/attention/${t.id}`, group: "Attention", type: "nav", keywords: `${t.severity} ${t.reason}` });
  return cmds;
}

export function filterCommands(commands, query) {
  const needle = String(query || "").trim().toLowerCase();
  if (!needle) return commands;
  return commands.filter((c) =>
    `${c.label} ${c.keywords || ""} ${c.group || ""}`.toLowerCase().includes(needle)
  );
}

export function groupCommands(commands) {
  const order = ["Navigate", "Actions", "Missions", "Agents", "Approvals", "Attention", "Preferences", "Help"];
  const map = new Map();
  for (const c of commands) {
    if (!map.has(c.group)) map.set(c.group, []);
    map.get(c.group).push(c);
  }
  return [...map.entries()]
    .sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]))
    .map(([group, items]) => ({ group, items }));
}
