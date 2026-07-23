/**
 * M47.3 — Normalized attention model (frontend aggregator).
 * Never fabricates operational data. Partial source failure is preserved.
 */

const SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

const KIND_TO_CATEGORY = {
  approval: "approval_required",
  browser_approval: "approval_required",
  execution_approval: "approval_required",
  pending_approval: "approval_required",
  connector_approval: "approval_required",
  execution_failed: "failed_run",
  browser_execution: "failed_run",
  pipeline_failed: "failed_run",
  failed: "failed_run",
  registry_health: "degraded_system",
  mcp_health: "degraded_system",
  platform_health: "degraded_system",
  degraded: "degraded_system",
  execution_latency: "degraded_system",
  browser_policy: "security_attention",
  browser_injection: "security_attention",
  security: "security_attention",
  connector: "connector_attention",
  evidence: "evidence_ready",
  engineering: "informational",
  scheduler: "informational",
};

export function severityRank(sev) {
  return SEV_ORDER[sev] ?? 9;
}

function stableId(parts) {
  return parts.filter(Boolean).join(":").replace(/\s+/g, "_").slice(0, 160);
}

function mapLink(link) {
  if (!link) return "/command";
  if (link.startsWith("/control")) return "/monitoring";
  if (link.startsWith("/approvals") || link.includes("approval")) return "/approvals";
  if (link.startsWith("/missions")) return link;
  if (link.startsWith("/")) return link;
  return "/command";
}

/**
 * Normalize a control-center attention item { severity, kind, message, link }.
 */
export function normalizeControlItem(raw, idx = 0) {
  if (!raw || typeof raw !== "object") return null;
  const kind = String(raw.kind || raw.type || "informational");
  const category = KIND_TO_CATEGORY[kind] || (kind.includes("approval") ? "approval_required" : "informational");
  const severity = ["critical", "high", "medium", "low", "info"].includes(raw.severity)
    ? raw.severity
    : "medium";
  const title = raw.title || raw.message || kind;
  const summary = raw.summary || raw.message || raw.title || "";
  const href = mapLink(raw.link || raw.href);
  return {
    id: stableId(["ctrl", kind, raw.id, title, idx]),
    category,
    severity,
    title: String(title).slice(0, 200),
    summary: String(summary).slice(0, 400),
    status: raw.status || "open",
    source: "control.attention",
    sourceStatus: "connected",
    href,
    createdAt: raw.created_at || raw.createdAt || null,
    updatedAt: raw.updated_at || raw.updatedAt || null,
    projectId: raw.project_id || null,
    missionId: raw.mission_id || null,
    approvalId: raw.approval_id || null,
    evidenceId: raw.evidence_id || null,
    authority: category === "approval_required" ? "approval-required" : "advisory",
    environment: null,
    actionable: true,
    actionRoute: category === "approval_required" ? "/approvals" : href,
    rawKind: kind,
  };
}

export function normalizeMissionAttention(mission) {
  if (!mission) return null;
  const st = String(mission.status || "").toLowerCase();
  if (!["blocked", "failed", "error", "paused", "stale"].includes(st) && !mission.needs_attention) {
    return null;
  }
  const severity = st === "failed" || st === "error" ? "high" : "medium";
  const category = st === "blocked" || st === "paused" ? "blocked_mission" : "failed_run";
  return {
    id: stableId(["mission", mission.id, st]),
    category,
    severity,
    title: mission.name || mission.key || `Mission ${mission.id}`,
    summary: `Status: ${mission.status}${mission.objectives?.[0] ? ` · ${mission.objectives[0]}` : ""}`,
    status: mission.status,
    source: "missions.list",
    sourceStatus: "connected",
    href: `/missions/${mission.id}`,
    createdAt: mission.created_at || null,
    updatedAt: mission.updated_at || null,
    projectId: null,
    missionId: mission.id,
    approvalId: null,
    evidenceId: null,
    authority: "advisory",
    environment: null,
    actionable: true,
    actionRoute: `/missions/${mission.id}`,
    rawKind: "mission_status",
  };
}

export function normalizeInfraDegraded(health) {
  if (!health || typeof health !== "object") return [];
  const items = [];
  const score = health.score ?? health.overall_score ?? health.status;
  const statusStr = String(health.status || health.overall || "").toLowerCase();
  if (statusStr.includes("degrad") || statusStr.includes("down") || statusStr === "critical" || statusStr === "red") {
    items.push({
      id: "infra:degraded",
      category: "degraded_system",
      severity: statusStr === "critical" || statusStr === "red" ? "critical" : "high",
      title: "Infrastructure degraded",
      summary: typeof score === "number" ? `Health score ${score}` : `Status: ${statusStr}`,
      status: statusStr || "degraded",
      source: "infrastructure.health",
      sourceStatus: "connected",
      href: "/monitoring",
      createdAt: null,
      updatedAt: null,
      projectId: null,
      missionId: null,
      approvalId: null,
      evidenceId: null,
      authority: "advisory",
      environment: null,
      actionable: true,
      actionRoute: "/monitoring",
      rawKind: "infra",
    });
  }
  // Subsystems if present
  for (const [key, val] of Object.entries(health)) {
    if (!val || typeof val !== "object") continue;
    const s = String(val.status || val.state || "").toLowerCase();
    if (["down", "degraded", "error", "unavailable", "critical"].includes(s)) {
      items.push({
        id: stableId(["infra", key, s]),
        category: "degraded_system",
        severity: s === "critical" || s === "down" ? "high" : "medium",
        title: `${key} ${s}`,
        summary: val.message || val.detail || `Subsystem ${key} reports ${s}`,
        status: s,
        source: "infrastructure.health",
        sourceStatus: "connected",
        href: "/monitoring",
        createdAt: null,
        updatedAt: null,
        projectId: null,
        missionId: null,
        approvalId: null,
        evidenceId: null,
        authority: "advisory",
        environment: null,
        actionable: true,
        actionRoute: "/monitoring",
        rawKind: "infra_subsystem",
      });
    }
  }
  return items;
}

export function normalizeApprovalAsAttention(approval) {
  if (!approval) return null;
  const title = approval.title || approval.action || approval.tool || approval.id || "Pending approval";
  return {
    id: stableId(["appr", approval.id || approval.approval_id, title]),
    category: "approval_required",
    severity: "high",
    title: String(title).slice(0, 200),
    summary: approval.summary || approval.connector_id || approval.status || "Requires operator decision",
    status: "pending",
    source: approval._source || "connectors.approvals",
    sourceStatus: "connected",
    href: "/approvals",
    createdAt: approval.created_at || approval.createdAt || null,
    updatedAt: null,
    projectId: null,
    missionId: approval.mission_id || null,
    approvalId: approval.id || approval.approval_id || null,
    evidenceId: null,
    authority: "approval-required",
    environment: approval.environment || null,
    actionable: true,
    actionRoute: "/approvals",
    rawKind: "approval",
  };
}

export function normalizeEvidenceAttention(ev, idx = 0) {
  if (!ev) return null;
  const id = ev.id || ev.evidence_id || idx;
  return {
    id: stableId(["ev", id]),
    category: "evidence_ready",
    severity: "info",
    title: ev.title || ev.kind || ev.type || `Evidence ${id}`,
    summary: ev.summary || ev.department || ev.project || "",
    status: "available",
    source: "evidence.list",
    sourceStatus: "connected",
    href: "/evidence",
    createdAt: ev.created_at || ev.ts || null,
    updatedAt: null,
    projectId: ev.project || null,
    missionId: ev.mission_id || null,
    approvalId: null,
    evidenceId: id,
    authority: "advisory",
    environment: null,
    actionable: true,
    actionRoute: "/evidence",
    rawKind: "evidence",
  };
}

/**
 * Merge multi-source attention. sourceMeta records per-source health.
 * @returns {{ items: object[], sources: object[], partial: boolean, generatedAt: string|null }}
 */
export function aggregateAttention({
  controlItems,
  controlStatus = "unavailable",
  controlError = null,
  missions = [],
  missionsStatus = "unavailable",
  missionsError = null,
  approvals = [],
  approvalsStatus = "unavailable",
  approvalsError = null,
  infra = null,
  infraStatus = "unavailable",
  infraError = null,
  evidence = [],
  evidenceStatus = "unavailable",
  evidenceError = null,
  generatedAt = null,
} = {}) {
  const sources = [];
  const items = [];
  const seen = new Set();

  const push = (item) => {
    if (!item?.id || seen.has(item.id)) return;
    seen.add(item.id);
    items.push(item);
  };

  sources.push({
    id: "control.attention",
    label: "Control attention",
    status: controlStatus,
    error: controlError,
    count: controlStatus === "connected" ? (controlItems?.length ?? 0) : null,
  });
  if (controlStatus === "connected" && Array.isArray(controlItems)) {
    controlItems.forEach((r, i) => push(normalizeControlItem(r, i)));
  }

  sources.push({
    id: "missions.list",
    label: "Missions",
    status: missionsStatus,
    error: missionsError,
    count: missionsStatus === "connected" ? missions.length : null,
  });
  if (missionsStatus === "connected") {
    missions.forEach((m) => push(normalizeMissionAttention(m)));
  }

  sources.push({
    id: "connectors.approvals",
    label: "Connector approvals",
    status: approvalsStatus,
    error: approvalsError,
    count: approvalsStatus === "connected" ? approvals.length : null,
  });
  if (approvalsStatus === "connected") {
    approvals.forEach((a) => push(normalizeApprovalAsAttention({ ...a, _source: "connectors.approvals" })));
  }

  sources.push({
    id: "infrastructure.health",
    label: "Infrastructure",
    status: infraStatus,
    error: infraError,
    count: null,
  });
  if (infraStatus === "connected" && infra) {
    normalizeInfraDegraded(infra).forEach(push);
  }

  sources.push({
    id: "evidence.list",
    label: "Evidence",
    status: evidenceStatus,
    error: evidenceError,
    count: evidenceStatus === "connected" ? evidence.length : null,
  });
  if (evidenceStatus === "connected" && Array.isArray(evidence)) {
    evidence.slice(0, 5).forEach((e, i) => push(normalizeEvidenceAttention(e, i)));
  }

  items.sort((a, b) => severityRank(a.severity) - severityRank(b.severity));

  const partial =
    sources.some((s) => s.status === "unavailable" || s.status === "error") &&
    sources.some((s) => s.status === "connected");

  return {
    items,
    sources,
    partial,
    generatedAt: generatedAt || null,
    summary: summarizeAttention(items, sources),
  };
}

export function summarizeAttention(items, sources) {
  const by = (cat) => items.filter((i) => i.category === cat).length;
  const crit = items.filter((i) => i.severity === "critical").length;
  const high = items.filter((i) => i.severity === "high").length;
  const connected = sources.filter((s) => s.status === "connected");
  const failed = sources.filter((s) => s.status === "unavailable" || s.status === "error");

  const metric = (value, sourceOk) =>
    sourceOk ? { value, status: "ok" } : { value: null, status: "unavailable" };

  const approvalsSrc = sources.find((s) => s.id === "connectors.approvals");
  const missionsSrc = sources.find((s) => s.id === "missions.list");
  const infraSrc = sources.find((s) => s.id === "infrastructure.health");
  const evidenceSrc = sources.find((s) => s.id === "evidence.list");
  const controlSrc = sources.find((s) => s.id === "control.attention");

  return {
    critical: metric(crit + high, controlSrc?.status === "connected" || missionsSrc?.status === "connected"),
    pendingApprovals: metric(
      by("approval_required"),
      approvalsSrc?.status === "connected" || controlSrc?.status === "connected"
    ),
    blockedMissions: metric(by("blocked_mission"), missionsSrc?.status === "connected"),
    failedRuns: metric(by("failed_run"), controlSrc?.status === "connected" || missionsSrc?.status === "connected"),
    degradedSystems: metric(by("degraded_system"), infraSrc?.status === "connected" || controlSrc?.status === "connected"),
    recentEvidence: metric(by("evidence_ready"), evidenceSrc?.status === "connected"),
    sourcesConnected: connected.length,
    sourcesFailed: failed.length,
    totalItems: items.length,
  };
}

export function mapSeverityToStatus(sev) {
  if (sev === "critical") return "danger";
  if (sev === "high") return "warning";
  if (sev === "medium") return "pending";
  if (sev === "low") return "info";
  return "neutral";
}
