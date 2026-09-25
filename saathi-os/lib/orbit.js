// SaathiOS Orbit — deterministic constellation geometry and status mapping.
//
// The design language is already called SOVEREIGN_ORBIT; this is the surface that
// finally means it. A core (the operator's own system) with specialist agents in
// orbit around it, edges showing who reports through what.
//
// Everything here is PURE: same input -> same coordinates, every render, every test.
// No randomness, no time dependence, so layout is reproducible and snapshot-safe.

export const CORE_ID = "core";

// Ring radii as a fraction of the viewport half-size. Tier 1 is the inner ring of
// primary functions; tier 2 is supporting agents further out.
export const RING_FRACTIONS = { 1: 0.42, 2: 0.72 };

/** Map an agent state to a semantic status token (never a raw hex). */
export function statusToneFor(state) {
  const s = String(state || "").toLowerCase();
  if (["active", "running", "healthy", "ok", "online"].includes(s)) return "success";
  if (["degraded", "warning", "slow", "stale"].includes(s)) return "warning";
  if (["blocked", "halted", "kill", "killed"].includes(s)) return "blocked";
  if (["error", "failed", "down", "danger"].includes(s)) return "danger";
  if (["paused", "idle", "standby"].includes(s)) return "paused";
  if (["pending", "starting", "queued"].includes(s)) return "pending";
  if (["info", "observing"].includes(s)) return "info";
  return "neutral";
}

export function statusVar(tone) {
  return `var(--status-${tone})`;
}

/**
 * Deterministic radial layout.
 * Angle comes from the node's index within its tier, so ordering is stable and a
 * re-render never reshuffles the constellation under the operator's cursor.
 *
 * @returns {{core:object, nodes:Array, size:number}}
 */
export function layoutOrbit(agents = [], { size = 720, rotation = -90 } = {}) {
  const half = size / 2;
  const byTier = new Map();
  for (const a of agents) {
    const tier = a.tier === 2 ? 2 : 1;
    if (!byTier.has(tier)) byTier.set(tier, []);
    byTier.get(tier).push(a);
  }

  const nodes = [];
  for (const [tier, list] of [...byTier.entries()].sort((x, y) => x[0] - y[0])) {
    const radius = half * (RING_FRACTIONS[tier] ?? RING_FRACTIONS[1]);
    const count = list.length || 1;
    list.forEach((a, i) => {
      // Offset alternate rings so outer labels don't collide with inner ones.
      const offset = tier === 2 ? 180 / count : 0;
      const deg = rotation + offset + (360 / count) * i;
      const rad = (deg * Math.PI) / 180;
      const tone = statusToneFor(a.state);
      nodes.push({
        ...a,
        tier,
        angle: +deg.toFixed(4),
        x: +(half + radius * Math.cos(rad)).toFixed(3),
        y: +(half + radius * Math.sin(rad)).toFixed(3),
        radius: +radius.toFixed(3),
        tone,
        color: statusVar(tone),
      });
    });
  }

  return {
    core: { id: CORE_ID, x: half, y: half },
    nodes,
    size,
  };
}

/** Core -> node edges. Peer edges only where a node declares `reportsTo`. */
export function orbitEdges(layout) {
  const byId = new Map(layout.nodes.map((n) => [n.id, n]));
  const edges = [];
  for (const n of layout.nodes) {
    const parent = n.reportsTo && byId.get(n.reportsTo);
    if (parent) {
      edges.push({ from: parent.id, to: n.id, x1: parent.x, y1: parent.y, x2: n.x, y2: n.y, kind: "peer" });
    } else {
      edges.push({ from: CORE_ID, to: n.id, x1: layout.core.x, y1: layout.core.y, x2: n.x, y2: n.y, kind: "core" });
    }
  }
  return edges;
}

// Worst-first: an operator must see the worst state, never an average.
const SEVERITY = {
  danger: 5, blocked: 4, warning: 3, pending: 2, paused: 1,
  info: 0, success: 0, neutral: 0,
};

/** Roll up the constellation into a headline an operator can act on. */
export function orbitSummary(agents = []) {
  const counts = {};
  let worst = "neutral";
  for (const a of agents) {
    const tone = statusToneFor(a.state);
    counts[tone] = (counts[tone] || 0) + 1;
    if ((SEVERITY[tone] ?? 0) > (SEVERITY[worst] ?? 0)) worst = tone;
  }
  return {
    total: agents.length,
    counts,
    worst,
    healthy: counts.success || 0,
    attention: (counts.danger || 0) + (counts.blocked || 0) + (counts.warning || 0),
  };
}

/** Accessible text equivalent — the constellation must never be image-only. */
export function orbitTextSummary(agents = []) {
  const s = orbitSummary(agents);
  if (!s.total) return "No agents in orbit.";
  return `${s.total} agents in orbit; ${s.healthy} healthy, ${s.attention} needing attention. Worst state: ${s.worst}.`;
}
