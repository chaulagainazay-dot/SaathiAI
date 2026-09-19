// SaathiOS AI Company — pure view-model helpers for the Company View.
//
// Everything here is PURE (no DOM, no fetch) so it is unit-tested with node --test.
// The backend (/api/v1/organization/company) is the single source of truth; this
// module only shapes it. Unknown or missing values stay visibly unknown.

/** Visible status vocabulary. `glyph` gives every state a non-colour cue. */
export const STATUS_META = {
  IDLE: { label: "Idle", tone: "neutral", glyph: "·", motion: "none", group: "idle" },
  ASSIGNED: { label: "Assigned", tone: "info", glyph: "◷", motion: "none", group: "active" },
  RESEARCHING: { label: "Researching", tone: "info", glyph: "⌕", motion: "scan", group: "active" },
  ANALYZING: { label: "Analyzing", tone: "info", glyph: "∿", motion: "chart", group: "active" },
  WORKING: { label: "Working", tone: "success", glyph: "▸", motion: "type", group: "active" },
  WAITING: { label: "Waiting", tone: "paused", glyph: "‖", motion: "none", group: "waiting" },
  REVIEWING: { label: "Reviewing", tone: "pending", glyph: "✎", motion: "review", group: "review" },
  CHALLENGING: { label: "Challenging", tone: "warning", glyph: "⚔", motion: "review", group: "review" },
  AWAITING_EVIDENCE: { label: "Awaiting evidence", tone: "warning", glyph: "?", motion: "none", group: "waiting" },
  AWAITING_APPROVAL: { label: "Awaiting approval", tone: "pending", glyph: "⚑", motion: "none", group: "review" },
  BLOCKED: { label: "Blocked", tone: "blocked", glyph: "■", motion: "none", group: "attention" },
  COMPLETE: { label: "Complete", tone: "success", glyph: "✓", motion: "done", group: "done" },
  ERROR: { label: "Error", tone: "danger", glyph: "✕", motion: "none", group: "attention" },
  UNAVAILABLE: { label: "Unavailable", tone: "neutral", glyph: "⊘", motion: "none", group: "unavailable" },
  OFFLINE: { label: "Offline", tone: "neutral", glyph: "○", motion: "none", group: "unavailable" },
  UNKNOWN: { label: "Unknown", tone: "neutral", glyph: "¿", motion: "none", group: "unknown" },
};

export const BUSY = new Set(["RESEARCHING", "ANALYZING", "WORKING", "REVIEWING", "CHALLENGING"]);

export function statusMeta(status) {
  return STATUS_META[status] || STATUS_META.UNKNOWN;
}

/** Human status incl. availability nuance (NOT CONNECTED beats a generic label). */
export function statusLabel(role) {
  if (!role) return STATUS_META.UNKNOWN.label;
  if (role.status === "UNAVAILABLE" && role.availability === "NOT_CONNECTED") return "Not connected";
  return statusMeta(role.status).label;
}

/** Motion is purely presentational; reduced-motion or non-busy → none. */
export function motionFor(status, reducedMotion = false) {
  if (reducedMotion) return "none";
  return statusMeta(status).motion;
}

export function agentAriaLabel(role) {
  const parts = [role.name, role.title && role.title !== role.name ? role.title : null,
    `status ${statusLabel(role)}`];
  if (role.reason) parts.push(role.reason);
  if (role.activity?.objective) parts.push(`working on ${role.activity.objective}`);
  return parts.filter(Boolean).join(", ");
}

/** Index a company snapshot into floors → offices → roles, preserving charter order. */
export function indexCompany(snap) {
  if (!snap || !Array.isArray(snap.roles)) return null;
  const roles = Object.fromEntries(snap.roles.map((r) => [r.role_id, r]));
  const offices = Object.fromEntries((snap.offices || []).map((o) => [o.office_id, {
    ...o,
    roles: (o.members || []).map((id) => roles[id]).filter(Boolean),
  }]));
  const floors = (snap.floors || []).map((f) => ({
    ...f,
    offices: (f.offices || []).map((id) => offices[id]).filter(Boolean),
  }));
  return { roles, offices, floors };
}

/** Per-office rollup used for office badges. */
export function officeSummary(office) {
  const rs = office?.roles || [];
  const count = (pred) => rs.filter(pred).length;
  return {
    members: rs.length,
    busy: count((r) => BUSY.has(r.status) || r.status === "ASSIGNED"),
    attention: count((r) => r.status === "BLOCKED" || r.status === "ERROR"),
    waiting: count((r) => r.status === "WAITING" || r.status === "AWAITING_EVIDENCE"),
    unavailable: count((r) => r.status === "UNAVAILABLE" || r.status === "OFFLINE"),
    unknown: count((r) => r.status === "UNKNOWN"),
  };
}

/** Header metrics — taken from the backend; recomputed only if absent. */
export function headerMetrics(snap) {
  if (snap?.metrics) return snap.metrics;
  const roles = snap?.roles || [];
  return {
    total: roles.length,
    active: roles.filter((r) => BUSY.has(r.status)).length,
    assigned: roles.filter((r) => r.status === "ASSIGNED").length,
    idle: roles.filter((r) => r.status === "IDLE").length,
    in_review: roles.filter((r) => ["REVIEWING", "CHALLENGING", "AWAITING_APPROVAL"].includes(r.status)).length,
    blocked: roles.filter((r) => r.status === "BLOCKED").length,
    errors: roles.filter((r) => r.status === "ERROR").length,
  };
}

/** Roles actually working right now (queued ASSIGNED roles are not "active"). */
export function activeRoles(snap) {
  return (snap?.roles || []).filter((r) => BUSY.has(r.status));
}

/** Depth-first flatten of a delegation tree with ASCII connectors. */
export function flattenTree(node, depth = 0, prefix = "", isLast = true, out = []) {
  if (!node) return out;
  const connector = depth === 0 ? "" : `${prefix}${isLast ? "└── " : "├── "}`;
  out.push({ ...node, depth, connector, children: undefined, childCount: (node.children || []).length });
  const nextPrefix = depth === 0 ? "" : `${prefix}${isLast ? "    " : "│   "}`;
  const kids = node.children || [];
  kids.forEach((c, i) => flattenTree(c, depth + 1, nextPrefix, i === kids.length - 1, out));
  return out;
}

/** Ancestry (owner → … → role) of the deepest currently-busy step in a tree. */
export function activePath(tree) {
  let best = null;
  const walk = (n, path) => {
    const here = [...path, n.role_id];
    if (BUSY.has(n.status) && (!best || here.length > best.length)) best = here;
    (n.children || []).forEach((c) => walk(c, here));
  };
  if (tree) walk(tree, []);
  return best || [];
}

/** Set of role ids participating in a mission tree. */
export function treeRoleIds(tree) {
  const ids = new Set();
  const walk = (n) => { if (!n) return; ids.add(n.role_id); (n.children || []).forEach(walk); };
  walk(tree);
  return ids;
}

export function formatAgo(ts, now = Date.now() / 1000) {
  if (!ts) return "—";
  const s = Math.max(0, now - ts);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function formatElapsed(start, end, now = Date.now() / 1000) {
  if (!start) return "—";
  const s = Math.max(0, (end || now) - start);
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}m ${Math.floor(s % 60)}s`;
}

const EVENT_VERBS = {
  "agent.started": "started",
  "agent.output_created": "produced output",
  "mission.created": "mission created",
  "mission.completed": "mission finished",
  "decision.proposed": "proposed a decision",
  "agent.error": "hit an error",
};

export function activityText(ev) {
  return `${ev.role_name || "Saathi"} — ${EVENT_VERBS[ev.name] || ev.name}`;
}

/** Should the view refresh for this SSE event? (org + agent-runtime traffic only) */
export function isRelevantEvent(name) {
  return typeof name === "string" && /^(org|agentrun)\./.test(name);
}

/** System-status tone; never green for UNKNOWN. */
export function systemTone(status) {
  return { OK: "success", DEGRADED: "warning", DOWN: "danger", NOT_CONNECTED: "neutral" }[status] || "neutral";
}

/** Fallback refresh interval (ms): fast only while a mission runs and live events are down. */
export function refreshInterval({ missionActive, liveConnected, visible }) {
  if (!visible) return null;
  if (missionActive && !liveConnected) return 2000;
  if (missionActive) return 8000;
  return 60000;
}
