// M71 presentation-only normalization for backend-authoritative mission runtime data.
// This module never derives permission, approval, execution success, or readiness.

const HEALTH_SIGNAL = {
  HEALTHY: "active",
  COMPLETE: "active",
  AT_RISK: "attention",
  CRITICAL: "danger",
  IDLE: "idle",
};

const number = (value, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const list = (value) => (Array.isArray(value) ? value : []);

export function missionRuntimeSignal(health) {
  return HEALTH_SIGNAL[String(health || "").toUpperCase()] || "unknown";
}

export function formatMissionEta(seconds) {
  const value = Math.max(0, number(seconds));
  if (value < 60) return `${Math.round(value)}s`;
  if (value < 3600) return `${Math.round(value / 60)}m`;
  return `${Math.round((value / 3600) * 10) / 10}h`;
}

export function normalizeMissionRuntimeSummary(raw) {
  if (!raw || typeof raw !== "object" || !raw.mission_id) return null;
  const progress = Math.max(0, Math.min(100, number(raw.progress_percent)));
  return {
    missionId: String(raw.mission_id),
    health: String(raw.health || "IDLE"),
    signal: missionRuntimeSignal(raw.health),
    state: String(raw.state || "UNKNOWN"),
    progress,
    activePhase: raw.active_phase ? String(raw.active_phase) : "",
    activePhaseTitle: raw.active_phase_title ? String(raw.active_phase_title) : "",
    activeTask: raw.active_task ? String(raw.active_task) : "",
    activeTaskTitle: raw.active_task_title ? String(raw.active_task_title) : "",
    currentAgent: raw.current_agent ? String(raw.current_agent) : "",
    taskCounts: raw.task_counts && typeof raw.task_counts === "object" ? raw.task_counts : {},
    warnings: list(raw.warnings).map(String),
    blockers: list(raw.blockers).map(String),
    etaSeconds: Math.max(0, number(raw.eta_seconds)),
    resourceUsage: raw.resource_usage && typeof raw.resource_usage === "object" ? raw.resource_usage : {},
    testStatus: String(raw.test_status || "NOT_RUN"),
    browserStatus: String(raw.browser_status || "NOT_RUN"),
    latestCommit: raw.latest_commit ? String(raw.latest_commit) : "",
    rollbackSha: raw.rollback_sha ? String(raw.rollback_sha) : "",
    lastCheckpointAt: raw.last_checkpoint_at ? number(raw.last_checkpoint_at) : 0,
  };
}

export function normalizeMissionRuntime(payload) {
  const summary = normalizeMissionRuntimeSummary(payload?.dashboard);
  if (!payload?.runtime || !summary) {
    return {
      planned: false,
      summary: null,
      tasks: [],
      dependencies: [],
      evidence: [],
      decisions: [],
      checkpoints: [],
      reviews: [],
      certifications: [],
      hierarchy: [],
    };
  }
  return {
    planned: true,
    summary,
    objective: String(payload.runtime.objective || ""),
    budget: payload.runtime.budget && typeof payload.runtime.budget === "object" ? payload.runtime.budget : {},
    usage: payload.runtime.usage && typeof payload.runtime.usage === "object" ? payload.runtime.usage : {},
    tasks: list(payload.tasks),
    dependencies: list(payload.dependencies),
    evidence: list(payload.evidence),
    decisions: list(payload.decisions),
    checkpoints: list(payload.checkpoints),
    reviews: list(payload.reviews),
    certifications: list(payload.certifications),
    hierarchy: list(payload.hierarchy),
  };
}
