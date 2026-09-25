/**
 * CENTRAL-COMMAND-TRADING-OPS — presentation of the canonical ops snapshot.
 *
 * PURE. Every value here is READ from the snapshot the backend already
 * classified. This file computes no health, merges no subsystem states, and
 * decides no severity — doing any of that would make the UI a second health
 * authority, which is exactly what the trading program spent four milestones
 * making impossible.
 *
 * The one judgement it does make is about FRESHNESS, and it makes it in the
 * safe direction: a snapshot that no longer describes now is never rendered as
 * confident health, however green its contents.
 */

/** Canonical backend health → the existing UI truth vocabulary. */
export const TRUTH_STATE_FOR_HEALTH = Object.freeze({
  HEALTHY: "HEALTHY",
  WARNING: "DEGRADED",
  DEGRADED: "DEGRADED",
  CRITICAL: "BLOCKED",
  // Contained on purpose, not chaotic — but still "do not proceed", so it
  // renders BLOCKED. The distinction survives in the detail line and in
  // `failedSafe`, because "safely halted" and "unsafely ambiguous" are
  // different things to tell an operator.
  FAILED_SAFE: "BLOCKED",
});

/** Unknown health never becomes HEALTHY. */
export function truthStateForHealth(health) {
  if (!health) return "UNKNOWN";
  return TRUTH_STATE_FOR_HEALTH[String(health).toUpperCase()] || "UNKNOWN";
}

export const SUBSYSTEM_LABELS = Object.freeze({
  MARKET_DATA: "Market data",
  PROVIDER: "Provider",
  STRATEGY: "Strategy",
  PORTFOLIO: "Portfolio",
  RISK: "Risk",
  GUARDIAN: "Guardian",
  EXECUTION_GATEWAY: "Execution gateway",
  SHADOW: "Shadow",
  PAPER: "Paper",
  RECONCILIATION: "Reconciliation",
  APPROVAL: "Approval",
  KILL_SWITCH: "Kill switch",
});

export function subsystemLabel(id) {
  return SUBSYSTEM_LABELS[id] || String(id || "").replace(/_/g, " ");
}

/**
 * Deterministic status copy. NOT generated, NOT narrated.
 *
 * This is what an operator reads when the model is unavailable, wrong, or slow,
 * so it carries the safety-critical meaning on its own. Narration may sit
 * alongside it; it may never replace it.
 */
export function deterministicSummary(view) {
  if (!view) return "Trading status unavailable.";
  const lines = [];
  if (view.freshness === "NEVER_COLLECTED") {
    return "Trading status has not been collected yet. No health is being reported.";
  }
  if (view.stale) {
    lines.push(
      `Trading status is STALE — last collected ${view.ageSeconds}s ago. ` +
        "The values below describe that moment, not now.",
    );
  }
  lines.push(`Trading mode: ${view.mode}.`);
  lines.push(`Overall: ${view.stale ? "STALE" : view.overall}.`);
  for (const s of view.subsystems || []) {
    if (s.health && s.health !== "HEALTHY") {
      lines.push(`${s.label}: ${s.health}${s.detail ? ` — ${s.detail}` : ""}.`);
    }
  }
  if (view.reconciliation && view.reconciliation !== "HEALTHY") {
    lines.push(`Reconciliation: ${view.reconciliation}.`);
  }
  if (view.killSwitch?.engaged) lines.push("Kill switch: ENGAGED.");
  if (view.primaryIncident) {
    lines.push(`Primary incident: ${view.primaryIncident.subsystem} — ${view.primaryIncident.summary}.`);
  }
  if (!view.liveTradingAuthorized) lines.push("Live trading is not authorised.");
  return lines.join(" ");
}

/**
 * Build the render model from a `/tg/operations/trading-ops` payload.
 *
 * Missing payload is UNKNOWN, never HEALTHY — the same rule the backend keeps.
 */
export function tradingOpsView(payload) {
  if (!payload || typeof payload !== "object") {
    return {
      available: false,
      freshness: "NEVER_COLLECTED",
      stale: true,
      overall: "UNKNOWN",
      displayState: "UNKNOWN",
      mode: "UNKNOWN",
      subsystems: [],
      incidents: [],
      actions: [],
      liveTradingAuthorized: false,
    };
  }

  const snap = payload.snapshot || null;
  const freshness = payload.freshness || "NEVER_COLLECTED";
  // `reflects_current_state` is the backend's own verdict; absence is treated as
  // "not current" so a payload from an older server cannot read as fresh.
  const stale = payload.reflects_current_state !== true;

  const subsystems = (snap?.subsystems || []).map((s) => ({
    id: s.subsystem,
    label: subsystemLabel(s.subsystem),
    health: s.health,
    // Stale readings are shown as STALE rather than as their last value, so a
    // frozen panel cannot read as a live one.
    state: stale ? "STALE" : truthStateForHealth(s.health),
    detail: s.detail || "",
    authority: s.authority || null,
    causedBy: s.caused_by || null,
  }));

  const incidents = (snap?.incidents || []).map((i) => ({
    id: i.incident_id,
    subsystem: i.subsystem,
    severity: i.severity,
    state: i.state,
    summary: i.summary,
    authority: i.authority,
    runbookRef: i.runbook_ref || null,
    acknowledged: !!i.acknowledged,
    // The root-cause claim comes from the backend's convergence, not from any
    // ranking done here.
    symptoms: (i.symptoms || []).map((s) => ({
      id: s.subsystem,
      label: subsystemLabel(s.subsystem),
      health: s.health,
    })),
  }));

  const actions = (snap?.operator_actions_required || []).map((a) => ({
    action: a.action,
    subsystem: a.subsystem,
    // Every action names the authority that owns it. An action without one is
    // not rendered as actionable: a button with no owner is a button that lies.
    authority: a.authority,
    detail: a.detail,
    incidentId: a.incident_id || null,
    automatable: !!a.automatable,
  }));

  const overall = snap?.overall_health || "UNKNOWN";
  return {
    available: !!snap,
    freshness,
    stale,
    collectedAt: payload.collected_at || null,
    servedAt: payload.served_at || null,
    ageSeconds: payload.age_seconds ?? null,
    maxAgeSeconds: payload.max_age_seconds ?? null,
    overall,
    // NO_STALE_SNAPSHOT_AS_CURRENT_HEALTH, enforced at the one place the badge
    // reads from. A stale snapshot cannot display HEALTHY under any contents.
    displayState: stale ? "STALE" : truthStateForHealth(overall),
    mode: snap?.mode || "UNKNOWN",
    liveTradingAuthorized: snap?.live_trading_authorized === true,
    subsystems,
    incidents,
    primaryIncident: incidents[0] || null,
    actions,
    reconciliation: snap?.reconciliation_state || null,
    recovery: snap?.recovery_state || null,
    killSwitch: {
      engaged: !!snap?.kill_switch_state?.engaged,
      reason: snap?.kill_switch_state?.reason || null,
      scope: snap?.kill_switch_state?.scope || null,
    },
  };
}

/**
 * Fold into the shape `SystemHealthPanel` already renders, so the trading rows
 * reuse the existing panel grammar rather than introducing a rival one.
 */
export function toSystemHealth(view) {
  return {
    overall: view?.displayState || "UNKNOWN",
    subsystems: (view?.subsystems || []).map((s) => ({
      id: s.id,
      label: s.label,
      state: s.state,
      detail: s.detail,
    })),
  };
}
