/**
 * M47.3 — Multi-source approval normalization.
 * UNAVAILABLE_IS_NOT_ZERO · READ_SAFE_BY_DEFAULT · NO_AUTHORITY_BYPASS
 */

function stableId(parts) {
  return parts.filter(Boolean).join(":").replace(/\s+/g, "_").slice(0, 160);
}

export const APPROVAL_SOURCE_DEFS = [
  { id: "connectors", label: "Connector approvals", integrated: true },
  { id: "control_cell", label: "Control Center approvals cell", integrated: true },
  { id: "recommendations", label: "Learning recommendations", integrated: true },
  { id: "missions", label: "Mission proposal decisions", integrated: false },
  { id: "deploy", label: "Deploy / release approvals", integrated: false },
  { id: "trading", label: "Trading approvals", integrated: false },
  { id: "finance", label: "Finance approvals", integrated: false },
  { id: "security", label: "Security / credential approvals", integrated: false },
];

/**
 * Normalize a connector pending approval row.
 * canDecide=true only for connector path with known id (existing platformDecideApproval contract).
 */
export function normalizeConnectorApproval(raw, idx = 0) {
  if (!raw || typeof raw !== "object") return null;
  const id = raw.id || raw.approval_id || raw.request_id;
  const title = raw.title || raw.action || raw.tool || raw.capability || `Connector approval ${idx + 1}`;
  return {
    id: stableId(["conn", id || title, idx]),
    type: "connector",
    title: String(title).slice(0, 200),
    summary: raw.summary || raw.description || [raw.connector_id, raw.account_id, raw.status].filter(Boolean).join(" · "),
    source: "connectors",
    sourceStatus: "connected",
    requester: raw.requester || raw.owner || raw.agent || null,
    createdAt: raw.created_at || raw.createdAt || null,
    expiresAt: raw.expires_at || raw.expiresAt || null,
    environment: raw.environment || null,
    authorityRequired: "approval-required",
    risk: raw.risk || raw.side_effect || "elevated",
    status: raw.status || "pending",
    targetType: "connector",
    targetId: raw.connector_id || raw.account_id || null,
    evidenceRefs: raw.evidence_ids || raw.evidence || [],
    canDecide: Boolean(id),
    decisionRoute: "/approvals",
    decideKind: id ? "connector" : null,
    decideId: id || null,
    raw,
  };
}

export function normalizeRecommendation(raw, idx = 0) {
  if (!raw || typeof raw !== "object") return null;
  const id = raw.id || raw.recommendation_id;
  const title = raw.title || raw.summary || raw.category || `Recommendation ${idx + 1}`;
  const st = String(raw.status || "pending").toLowerCase();
  if (st && !["pending", "open", "awaiting", "proposed", ""].includes(st)) {
    // only surface pending-like
    if (st === "accepted" || st === "rejected" || st === "implemented") return null;
  }
  return {
    id: stableId(["rec", id || title, idx]),
    type: "recommendation",
    title: String(title).slice(0, 200),
    summary: raw.summary || raw.rationale || raw.category || "Learning recommendation awaiting decision",
    source: "recommendations",
    sourceStatus: "connected",
    requester: raw.source || "learning",
    createdAt: raw.created_at || null,
    expiresAt: null,
    environment: null,
    authorityRequired: "approval-required",
    risk: "elevated",
    status: st || "pending",
    targetType: "recommendation",
    targetId: id || null,
    evidenceRefs: raw.evidence_ids || [],
    canDecide: Boolean(id),
    decisionRoute: "/learning",
    decideKind: id ? "recommendation" : null,
    decideId: id || null,
    raw,
  };
}

/**
 * Control cell may be { status, value: [...] } or similar Cell shape.
 */
export function normalizeControlApprovalsCell(cell) {
  if (!cell) return { items: [], sourceStatus: "unavailable", error: "empty cell" };
  const status = cell.status || (cell.value != null ? "ok" : "unavailable");
  if (status !== "ok") {
    return {
      items: [],
      sourceStatus: status === "unavailable" || status === "error" ? "unavailable" : "partial",
      error: cell.error || cell.message || `cell status ${status}`,
    };
  }
  const val = cell.value;
  const list = Array.isArray(val) ? val : val?.items || val?.approvals || val?.pending || [];
  if (!Array.isArray(list)) {
    return { items: [], sourceStatus: "partial", error: "unexpected cell value shape", rawKeys: val && typeof val === "object" ? Object.keys(val) : [] };
  }
  // Map loosely — may already be connector-shaped or summary counts
  const items = list
    .map((r, i) => {
      if (typeof r === "string") {
        return {
          id: stableId(["ctrlcell", r, i]),
          type: "control_summary",
          title: r,
          summary: "From Control Center approvals cell",
          source: "control_cell",
          sourceStatus: "connected",
          requester: null,
          createdAt: null,
          expiresAt: null,
          environment: null,
          authorityRequired: "approval-required",
          risk: "unknown",
          status: "pending",
          targetType: null,
          targetId: null,
          evidenceRefs: [],
          canDecide: false,
          decisionRoute: "/approvals",
          decideKind: null,
          decideId: null,
          raw: r,
        };
      }
      const n = normalizeConnectorApproval(r, i);
      if (!n) return null;
      return { ...n, source: "control_cell", canDecide: false, decideKind: null, decisionRoute: "/command" };
    })
    .filter(Boolean);
  return { items, sourceStatus: "connected", error: null };
}

export function extractList(data) {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== "object") return null;
  const list = data.items || data.approvals || data.pending || data.recommendations;
  return Array.isArray(list) ? list : null;
}

/**
 * Aggregate approval sources. Failed sources never contribute a fake zero to totals.
 */
export function aggregateApprovals({
  connectors,
  connectorsStatus,
  connectorsError,
  controlCell,
  controlStatus,
  controlError,
  recommendations,
  recommendationsStatus,
  recommendationsError,
} = {}) {
  const sources = [];
  const items = [];
  const seen = new Set();

  // connectors
  if (connectorsStatus === "connected" && Array.isArray(connectors)) {
    sources.push({ id: "connectors", label: "Connector approvals", status: "connected", count: connectors.length, error: null });
    connectors.forEach((r, i) => {
      const n = normalizeConnectorApproval(r, i);
      if (n && !seen.has(n.id)) {
        seen.add(n.id);
        items.push(n);
      }
    });
  } else if (connectorsStatus === "loading") {
    sources.push({ id: "connectors", label: "Connector approvals", status: "partial", count: null, error: null });
  } else {
    sources.push({
      id: "connectors",
      label: "Connector approvals",
      status: connectorsStatus || "unavailable",
      count: null,
      error: connectorsError || null,
    });
  }

  // control cell
  if (controlStatus === "connected" && controlCell) {
    const parsed = normalizeControlApprovalsCell(controlCell);
    sources.push({
      id: "control_cell",
      label: "Control Center approvals cell",
      status: parsed.sourceStatus,
      count: parsed.sourceStatus === "connected" ? parsed.items.length : null,
      error: parsed.error,
    });
    if (parsed.sourceStatus === "connected") {
      parsed.items.forEach((n) => {
        // prefer connector-native duplicates
        if (!seen.has(n.id) && !seen.has(stableId(["conn", n.decideId]))) {
          seen.add(n.id);
          items.push(n);
        }
      });
    }
  } else {
    sources.push({
      id: "control_cell",
      label: "Control Center approvals cell",
      status: controlStatus || "unavailable",
      count: null,
      error: controlError || null,
    });
  }

  // recommendations
  if (recommendationsStatus === "connected" && Array.isArray(recommendations)) {
    const recs = recommendations.map((r, i) => normalizeRecommendation(r, i)).filter(Boolean);
    sources.push({ id: "recommendations", label: "Learning recommendations", status: "connected", count: recs.length, error: null });
    recs.forEach((n) => {
      if (!seen.has(n.id)) {
        seen.add(n.id);
        items.push(n);
      }
    });
  } else {
    sources.push({
      id: "recommendations",
      label: "Learning recommendations",
      status: recommendationsStatus || "unavailable",
      count: null,
      error: recommendationsError || null,
    });
  }

  // not integrated
  for (const def of APPROVAL_SOURCE_DEFS.filter((d) => !d.integrated)) {
    sources.push({ id: def.id, label: def.label, status: "not_integrated", count: null, error: null });
  }

  const connectedCounts = sources.filter((s) => s.status === "connected" && typeof s.count === "number");
  const pendingTotal = connectedCounts.length
    ? connectedCounts.reduce((a, s) => a + s.count, 0)
    : null;

  const partial =
    sources.some((s) => s.status === "connected") &&
    sources.some((s) => s.status === "unavailable" || s.status === "error" || s.status === "not_integrated");

  return {
    items,
    sources,
    partial,
    pendingTotal, // null when no connected source — never fabricate 0 from failures alone
    hasConnectedSource: sources.some((s) => s.status === "connected"),
  };
}

export function filterApprovals(items, { status, type, risk, q } = {}) {
  let out = items.slice();
  if (status && status !== "all") out = out.filter((i) => String(i.status).toLowerCase() === status);
  if (type && type !== "all") out = out.filter((i) => i.type === type);
  if (risk && risk !== "all") out = out.filter((i) => String(i.risk).toLowerCase().includes(risk));
  if (q?.trim()) {
    const s = q.trim().toLowerCase();
    out = out.filter(
      (i) =>
        i.title.toLowerCase().includes(s) ||
        (i.summary || "").toLowerCase().includes(s) ||
        (i.source || "").includes(s)
    );
  }
  return out;
}

export function sortApprovals(items, mode = "urgency") {
  const copy = items.slice();
  if (mode === "age") {
    copy.sort((a, b) => String(b.createdAt || "").localeCompare(String(a.createdAt || "")));
    return copy;
  }
  // urgency: canDecide first, then risk, then age
  const riskRank = { critical: 0, high: 1, elevated: 2, medium: 3, unknown: 4, low: 5 };
  copy.sort((a, b) => {
    if (a.canDecide !== b.canDecide) return a.canDecide ? -1 : 1;
    const ra = riskRank[String(a.risk).toLowerCase()] ?? 4;
    const rb = riskRank[String(b.risk).toLowerCase()] ?? 4;
    if (ra !== rb) return ra - rb;
    return String(b.createdAt || "").localeCompare(String(a.createdAt || ""));
  });
  return copy;
}
