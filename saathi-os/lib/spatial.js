/**
 * M58 Glass Frame — spatial semantics (pure, framework-free, unit-testable).
 *
 * This module is the single source of truth for:
 *   - the module registry (what floats around the central SaathiCore)
 *   - status → signal mapping (cyan / amber / red / idle)
 *   - connection meaning (active data / authority / blocked / inactive)
 *   - deterministic ring geometry (node placement around the core)
 *
 * It performs NO fetching and holds NO React. It only interprets already-fetched,
 * already-certified platform data. Every value it derives is grounded in real
 * API fields; when a field is absent it yields "unknown" — never an invented value.
 */

/* ---------------------------------------------------------------------------
 * Signals — the four canonical operational states (+ unknown).
 * These map 1:1 to the reference design's colour language.
 * ------------------------------------------------------------------------- */
export const SIGNAL = {
  ACTIVE: "active", // cyan — healthy / operating / ready
  ATTENTION: "attention", // amber — attention / approval / authority
  DANGER: "danger", // red — blocked / unsafe / failed
  IDLE: "idle", // muted blue-grey — idle / offline / inactive
  SUCCESS: "success", // green — completed verification only (sparingly)
  UNKNOWN: "unknown", // dashed grey — data unavailable
};

/* Semantic CSS custom properties each signal resolves to (defined in globals.css). */
export const SIGNAL_TOKENS = {
  [SIGNAL.ACTIVE]: { color: "var(--signal-active)", glow: "var(--glow-active)", label: "Active" },
  [SIGNAL.ATTENTION]: { color: "var(--signal-attention)", glow: "var(--glow-attention)", label: "Attention" },
  [SIGNAL.DANGER]: { color: "var(--signal-danger)", glow: "var(--glow-danger)", label: "Blocked" },
  [SIGNAL.IDLE]: { color: "var(--signal-idle)", glow: "none", label: "Idle" },
  [SIGNAL.SUCCESS]: { color: "var(--signal-success)", glow: "var(--glow-active)", label: "Verified" },
  [SIGNAL.UNKNOWN]: { color: "var(--signal-unknown)", glow: "none", label: "Unknown" },
};

/* Connection semantics — every visible path must correspond to a real relationship. */
export const CONNECTION = {
  ACTIVE: "active", // cyan — operational data flow
  AUTHORITY: "authority", // amber — approval / authority path
  BLOCKED: "blocked", // red — blocked / unsafe / failed
  INACTIVE: "inactive", // grey-blue — inactive
  SUCCESS: "success", // green — completed verification only
};

/* ---------------------------------------------------------------------------
 * Module registry — first-level system areas that float around the core.
 * `flow` documents the real relationship the connection encodes; `route` the
 * navigation target. Order is stable so ring geometry is deterministic.
 * ------------------------------------------------------------------------- */
export const MODULES = [
  { id: "missions", label: "Missions", route: "/missions", icon: "mission", flow: CONNECTION.ACTIVE, group: "work" },
  { id: "projects", label: "Projects", route: "/projects", icon: "project", flow: CONNECTION.ACTIVE, group: "work" },
  { id: "agents", label: "Agents", route: "/agents", icon: "agent", flow: CONNECTION.ACTIVE, group: "work" },
  { id: "runtime", label: "Runtime", route: "/platform#runtime", icon: "runtime", flow: CONNECTION.ACTIVE, group: "core" },
  { id: "approvals", label: "Approvals", route: "/approvals", icon: "approval", flow: CONNECTION.AUTHORITY, group: "authority" },
  { id: "attention", label: "Attention", route: "/platform#attention", icon: "attention", flow: CONNECTION.ACTIVE, group: "core" },
  { id: "bindings", label: "Bindings", route: "/platform#bindings", icon: "binding", flow: CONNECTION.AUTHORITY, group: "authority" },
  { id: "evidence", label: "Evidence", route: "/evidence", icon: "evidence", flow: CONNECTION.SUCCESS, group: "record" },
  { id: "operations", label: "Operations", route: "/platform/ops", icon: "operations", flow: CONNECTION.ACTIVE, group: "core" },
  { id: "memory", label: "Memory", route: "/knowledge", icon: "memory", flow: CONNECTION.ACTIVE, group: "record" },
  { id: "automation", label: "Automation", route: "/automation", icon: "automation", flow: CONNECTION.ACTIVE, group: "work" },
  { id: "settings", label: "Settings", route: "/settings", icon: "settings", flow: CONNECTION.INACTIVE, group: "system" },
];

/* ---------------------------------------------------------------------------
 * Core status — the central intelligence's operational state.
 * Priority: danger > attention > active > idle. Blocked always dominates.
 * ------------------------------------------------------------------------- */
export function coreSignal({ health, metrics, diagnostics } = {}) {
  // Blocked / unsafe: only an EXPLICIT failure word from the runtime gateway.
  // Enforced/healthy states (e.g. "TOOL_GATEWAY_ENFORCED", "ACTIVE", "READY")
  // must NOT read as blocked — only down/degraded/failed/disabled/offline/error do.
  const gw = health && health.runtime && health.runtime.gateway;
  const gatewayDown = typeof gw === "string" && /down|degraded|fail|disabled|offline|error|unavailable/i.test(gw);
  const failed = metrics && Number(metrics.failed_executions) > 0;
  if (gatewayDown) return SIGNAL.DANGER;

  // Attention: pending approvals or executions flagged for review.
  const pendingApprovals = num(metrics && metrics.waiting_approvals) + num(diagnostics && diagnostics.runtime && diagnostics.runtime.waiting_approval);
  const attentionCount = num(metrics && metrics.executions_requiring_attention) + num(diagnostics && diagnostics.runtime && diagnostics.runtime.attention_count);
  if (pendingApprovals > 0 || attentionCount > 0 || failed) return SIGNAL.ATTENTION;

  // Active: identity live and runtime present.
  if (health && (health.identity === "ACTIVE" || health.identity === "READY")) return SIGNAL.ACTIVE;
  if (metrics && num(metrics.active_executions) > 0) return SIGNAL.ACTIVE;

  // Nothing to report and no positive health signal.
  if (!health && !metrics && !diagnostics) return SIGNAL.UNKNOWN;
  return SIGNAL.IDLE;
}

/* Compact metric summary rendered inside / beside the core. Every value real or null. */
export function coreMetrics({ metrics, approvals, attention } = {}) {
  return {
    activeMissions: numOrNull(metrics && metrics.active_executions),
    runningExecutions: numOrNull(metrics && metrics.active_executions),
    pendingApprovals: numOrNull(metrics ? metrics.waiting_approvals : approvalsCount(approvals)),
    attentionCount: numOrNull(metrics ? metrics.executions_requiring_attention : (attention ? attention.length : null)),
    total: numOrNull(metrics && metrics.total_executions),
    failed: numOrNull(metrics && metrics.failed_executions),
  };
}

/* ---------------------------------------------------------------------------
 * Per-module signal + count derived from live data. Modules with no bound
 * datasource resolve to IDLE (present but quiet), never a fake status.
 * ------------------------------------------------------------------------- */
export function moduleState(id, data = {}) {
  const { metrics, approvals, attention, bindings, projects, diagnostics, executions } = data;
  switch (id) {
    case "approvals": {
      const n = metrics ? num(metrics.waiting_approvals) : approvalsCount(approvals);
      return signalCount(n > 0 ? SIGNAL.ATTENTION : SIGNAL.IDLE, n, n > 0 ? `${n} pending` : "None pending");
    }
    case "attention": {
      const n = metrics ? num(metrics.executions_requiring_attention) : (attention ? attention.length : null);
      const v = num(n);
      return signalCount(v > 0 ? SIGNAL.ATTENTION : SIGNAL.IDLE, n, v > 0 ? `${v} require review` : "Clear");
    }
    case "runtime": {
      const active = num(metrics && metrics.active_executions);
      const failed = num(metrics && metrics.failed_executions);
      if (failed > 0) return signalCount(SIGNAL.ATTENTION, active, `${active} active · ${failed} failed`);
      if (active > 0) return signalCount(SIGNAL.ACTIVE, active, `${active} active`);
      return signalCount(metrics ? SIGNAL.IDLE : SIGNAL.UNKNOWN, metrics ? 0 : null, metrics ? "Idle" : "Unavailable");
    }
    case "bindings": {
      if (!bindings) return signalCount(SIGNAL.UNKNOWN, null, "Unavailable");
      const activeB = bindings.filter((b) => b.state === "ACTIVE").length;
      return signalCount(activeB > 0 ? SIGNAL.ACTIVE : SIGNAL.IDLE, bindings.length, `${activeB}/${bindings.length} active`);
    }
    case "projects": {
      if (!projects) return signalCount(SIGNAL.UNKNOWN, null, "Unavailable");
      return signalCount(projects.length > 0 ? SIGNAL.ACTIVE : SIGNAL.IDLE, projects.length, `${projects.length} project${projects.length === 1 ? "" : "s"}`);
    }
    case "missions": {
      const n = num(executions && executions.length);
      return signalCount(n > 0 ? SIGNAL.ACTIVE : SIGNAL.IDLE, executions ? n : null, executions ? `${n} runs` : "Unavailable");
    }
    case "operations": {
      const prodAuth = diagnostics && diagnostics.environment && diagnostics.environment.production_authorized;
      return signalCount(SIGNAL.ACTIVE, null, prodAuth ? "Production" : "Local · non-prod");
    }
    default:
      return signalCount(SIGNAL.IDLE, null, "");
  }
}

/* ---------------------------------------------------------------------------
 * Ring geometry — deterministic placement of N nodes on an ellipse around a
 * centre. Pure trig; no randomness (safe for deterministic render / SSR).
 * Angle starts at top (-90°) and steps clockwise. Returns fractional coords
 * in [0,1] plus absolute px when a box is supplied.
 * ------------------------------------------------------------------------- */
export function ringLayout(count, { cx = 0.5, cy = 0.5, rx = 0.4, ry = 0.4, startDeg = -90 } = {}) {
  const out = [];
  if (count <= 0) return out;
  for (let i = 0; i < count; i += 1) {
    const deg = startDeg + (360 / count) * i;
    const rad = (deg * Math.PI) / 180;
    out.push({
      index: i,
      deg,
      x: cx + rx * Math.cos(rad),
      y: cy + ry * Math.sin(rad),
    });
  }
  return out;
}

/* ---------------------------------------------------------------------------
 * Coordinate rounding — CRITICAL for SSR hydration. Browsers reserialize
 * SSR-rendered inline styles (e.g. left:28.499999999999982% → 28.5%) before
 * React hydrates, so raw trig output causes an attribute mismatch. Emitting a
 * value already rounded to 2 decimals via Math.round (no float tail, no trailing
 * zeros) makes server render, DOM reserialization, and client render all agree.
 * ------------------------------------------------------------------------- */
export const round2 = (n) => Math.round(n * 100) / 100;
export const pct = (frac) => `${round2(frac * 100)}%`;

/* Deterministic, hydration-stable SVG path string for a centre→node curve. */
export function pathD(curve) {
  const { from, c1, to } = curve;
  return `M ${round2(from.x * 100)} ${round2(from.y * 100)} Q ${round2(c1.x * 100)} ${round2(c1.y * 100)} ${round2(to.x * 100)} ${round2(to.y * 100)}`;
}

/* Cubic Bézier control points for a gentle curve from centre to a node. */
export function curvePath(from, to, curvature = 0.18) {
  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2;
  // Perpendicular offset for a natural bow.
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const nx = -dy;
  const ny = dx;
  const c1 = { x: mx + nx * curvature, y: my + ny * curvature };
  return { from, c1, to };
}

/* Connection signal for a module edge given the module's own state. */
export function connectionSignal(module, state) {
  if (!state) return CONNECTION.INACTIVE;
  if (state.signal === SIGNAL.DANGER) return CONNECTION.BLOCKED;
  if (module.flow === CONNECTION.AUTHORITY) return CONNECTION.AUTHORITY;
  if (state.signal === SIGNAL.ATTENTION) return CONNECTION.AUTHORITY;
  if (state.signal === SIGNAL.SUCCESS) return CONNECTION.SUCCESS;
  if (state.signal === SIGNAL.IDLE || state.signal === SIGNAL.UNKNOWN) return CONNECTION.INACTIVE;
  return CONNECTION.ACTIVE;
}

/* ---- helpers ---- */
function num(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function numOrNull(v) {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
function approvalsCount(approvals) {
  return Array.isArray(approvals) ? approvals.length : null;
}
function signalCount(signal, count, detail) {
  return { signal, count: count === undefined ? null : count, detail: detail || "" };
}
