/**
 * UI-NEXT-1 — Central command data composition.
 * Aggregates existing APIs into view models. Never invents metrics.
 */

import { extractList } from "./approvals.js";
import { composeAuthorityStrip } from "./command-authority.js";

function listFrom(payload, keys = ["items", "missions", "agents", "events", "evidence"]) {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload;
  for (const k of keys) {
    if (Array.isArray(payload[k])) return payload[k];
  }
  const via = extractList(payload);
  return Array.isArray(via) ? via : [];
}

/**
 * Normalize a mission for operational display.
 * Progress is stage/state only — never fake percentages.
 */
export function normalizeMissionCard(mission) {
  if (!mission || typeof mission !== "object") return null;
  const status = String(mission.status || mission.state || "unknown");
  const st = status.toLowerCase();
  const stage =
    mission.stage ||
    mission.current_step ||
    mission.phase ||
    mission.lifecycle_state ||
    status;
  return {
    id: mission.id || mission.mission_id || mission.key || null,
    name: mission.name || mission.title || mission.key || "Mission",
    status,
    stage: String(stage),
    owner: mission.owner || mission.owner_id || mission.created_by || null,
    agent: mission.agent || mission.agent_id || mission.binding_id || null,
    started: mission.started_at || mission.created_at || null,
    lastActivity: mission.updated_at || mission.last_activity_at || mission.ended_at || null,
    authorityCeiling: mission.authority_ceiling || mission.authority || mission.max_authority || "UNKNOWN",
    approvalRequired: Boolean(
      mission.approval_required ||
        mission.needs_approval ||
        st === "awaiting_approval" ||
        st === "approval_required"
    ),
    blocker: mission.blocker || mission.block_reason || mission.error || null,
    nextAction: mission.next_action || mission.next_step || null,
    href: mission.id ? `/missions/${mission.id}` : "/missions",
    progressKnown: false,
    progressLabel: String(stage),
  };
}

export function normalizeAgentCard(agent) {
  if (!agent || typeof agent !== "object") return null;
  return {
    id: agent.id || agent.agent_id || agent.binding_id || null,
    name: agent.name || agent.role || agent.label || "Agent",
    status: agent.status || agent.state || agent.runtime_status || "UNKNOWN",
    role: agent.role || agent.role_id || null,
    missionId: agent.mission_id || agent.current_mission_id || null,
    authority: agent.authority || agent.authority_class || "advisory",
    lastActivity: agent.updated_at || agent.last_seen_at || null,
    href: agent.id ? `/agents` : "/agents",
  };
}

/**
 * Investment snapshot — paper only. Missing metrics → NOT AVAILABLE.
 * Never computes risk math in the UI.
 */
export function composeInvestmentSnapshot({ summary = null, ready = false, auth = false, error = null } = {}) {
  const na = (reason) => ({ available: false, value: null, label: "NOT AVAILABLE", reason });

  if (!auth) {
    return {
      mode: "PAPER",
      liveExecution: "UNAVAILABLE",
      ready: false,
      error: null,
      fields: {
        paperNav: na("session required"),
        cash: na("session required"),
        pnl: na("not in overview payload"),
        grossExposure: na("not in overview payload"),
        netExposure: na("not in overview payload"),
        drawdown: na("not in overview payload"),
        riskState: na("session required"),
        accounts: na("session required"),
        unackAlerts: na("session required"),
        reconExceptions: na("session required"),
        blockingBreakers: na("session required"),
      },
      positions: [],
      note: "Live execution remains unauthorized. Paper data requires authenticated session.",
    };
  }

  if (!ready) {
    return {
      mode: "PAPER",
      liveExecution: "UNAVAILABLE",
      ready: false,
      error: error || null,
      fields: {
        paperNav: na("loading"),
        cash: na("loading"),
        pnl: na("not computed in overview"),
        grossExposure: na("not in overview payload"),
        netExposure: na("not in overview payload"),
        drawdown: na("not in overview payload"),
        riskState: na("loading"),
        accounts: na("loading"),
        unackAlerts: na("loading"),
        reconExceptions: na("loading"),
        blockingBreakers: na("loading"),
      },
      positions: [],
      note: "Awaiting paper overview.",
    };
  }

  if (!summary) {
    return {
      mode: "PAPER",
      liveExecution: "UNAVAILABLE",
      ready: true,
      error: error || "overview unavailable",
      fields: {
        paperNav: na("paper overview failed"),
        cash: na("paper overview failed"),
        pnl: na("not in overview payload"),
        grossExposure: na("not in overview payload"),
        netExposure: na("not in overview payload"),
        drawdown: na("not in overview payload"),
        riskState: na("paper overview failed"),
        accounts: na("paper overview failed"),
        unackAlerts: na("paper overview failed"),
        reconExceptions: na("paper overview failed"),
        blockingBreakers: na("paper overview failed"),
      },
      positions: [],
      note: "Backend gap recorded for T-NEXT-1 if ledger metrics remain absent.",
    };
  }

  const num = (v) => (v == null || Number.isNaN(Number(v)) ? null : Number(v));
  // Prefer canonical fund ledger fields when present (T-NEXT-1); never invent in UI.
  const equity = num(summary.paper_nav ?? summary.paperNav ?? summary.nav ?? summary.equity);
  const cash = num(summary.cash);
  const pnl = num(summary.pnl ?? summary.total_pnl);
  const gross = num(summary.gross_exposure ?? summary.grossExposure);
  const net = num(summary.net_exposure ?? summary.netExposure);
  const fromLedger = summary.source === "canonical_fund_ledger" || summary.ledger === true;

  const riskState =
    (summary.blockingBreakers || 0) > 0
      ? { available: true, value: "BLOCKED", label: "BLOCKED", reason: "blocking breakers" }
      : (summary.unackAlerts || 0) > 0 || (summary.critDrift || 0) > 0
        ? { available: true, value: "DEGRADED", label: "DEGRADED", reason: "alerts or recon drift" }
        : { available: true, value: "PAPER_ACTIVE", label: "PAPER ACTIVE", reason: fromLedger ? "canonical ledger" : "safety surface loaded" };

  const field = (value, okReason, missReason) =>
    value == null
      ? na(missReason)
      : { available: true, value, label: String(value), reason: okReason };

  return {
    mode: "PAPER",
    liveExecution: "UNAVAILABLE",
    ready: true,
    error: error || null,
    fields: {
      paperNav: field(
        equity,
        fromLedger ? "canonical fund ledger NAV" : "sum paper total_equity",
        "total_equity / paper_nav absent",
      ),
      cash: field(
        cash,
        fromLedger ? "canonical fund ledger cash" : "sum paper current_cash",
        "current_cash absent",
      ),
      pnl: field(pnl, "canonical fund ledger total P&L", "P&L not exposed on overview aggregate"),
      grossExposure: field(gross, "canonical fund ledger gross exposure", "not in overview payload — T-NEXT-1"),
      netExposure: field(net, "canonical fund ledger net exposure", "not in overview payload — T-NEXT-1"),
      drawdown: na("not in overview payload — T-NEXT-2 risk engine"),
      riskState,
      accounts: {
        available: true,
        value: summary.accounts || (fromLedger ? 1 : 0),
        label: fromLedger
          ? `ledger fund ${summary.fund_id || ""}`.trim()
          : `${summary.active || 0} active / ${summary.accounts || 0}`,
        reason: fromLedger ? "canonical_fund_ledger" : "paper.accounts",
      },
      unackAlerts: {
        available: true,
        value: summary.unackAlerts || 0,
        label: String(summary.unackAlerts || 0),
        reason: "paper.safety.alerts",
      },
      reconExceptions: {
        available: true,
        value: summary.critDrift || 0,
        label: String(summary.critDrift || 0),
        reason: "paper.reconciliation critical",
      },
      blockingBreakers: {
        available: true,
        value: summary.blockingBreakers || 0,
        label: String(summary.blockingBreakers || 0),
        reason: "paper.safety.states",
      },
    },
    positions: Array.isArray(summary.positions) ? summary.positions : [],
    // T-NEXT-2: optional PAPER risk contract (never invents; pass-through only)
    paperRisk:
      summary.paper_risk || summary.paperRisk || summary.risk_contract
        ? {
            label: "PAPER RISK",
            mode: "PAPER",
            liveExecution: "UNAVAILABLE",
            ...(summary.paper_risk || summary.paperRisk || summary.risk_contract),
          }
        : null,
    note: fromLedger
      ? "PAPER — values from canonical fund ledger. Live execution unavailable."
      : "Paper only. Live execution unavailable. Missing ledger fields marked NOT AVAILABLE.",
  };
}

/**
 * Build evidence/activity timeline from heterogeneous existing sources.
 * Never fabricates provenance fields.
 */
export function composeEvidenceTimeline({
  evidence = [],
  attentionItems = [],
  missions = [],
  controlEvents = [],
  limit = 24,
} = {}) {
  const events = [];

  for (const ev of evidence || []) {
    if (!ev) continue;
    events.push({
      id: `ev:${ev.id || ev.evidence_id || events.length}`,
      timestamp: ev.created_at || ev.timestamp || ev.ts || null,
      actor: ev.actor || ev.created_by || ev.source || null,
      mission: ev.mission_id || null,
      action: ev.kind || ev.type || ev.title || "evidence",
      authority: ev.authority || null,
      result: ev.status || ev.result || null,
      evidenceRef: ev.id || ev.evidence_id || null,
      href: ev.id ? `/evidence` : "/evidence",
      source: "evidence",
    });
  }

  for (const it of attentionItems || []) {
    if (!it) continue;
    events.push({
      id: `att:${it.id || events.length}`,
      timestamp: it.updatedAt || it.createdAt || null,
      actor: it.source || null,
      mission: it.missionId || null,
      action: it.title || it.category,
      authority: it.authority || null,
      result: it.status || it.severity || null,
      evidenceRef: it.evidenceId || null,
      href: it.actionRoute || it.href || "/command",
      source: "attention",
    });
  }

  for (const m of missions || []) {
    if (!m) continue;
    events.push({
      id: `miss:${m.id || events.length}`,
      timestamp: m.updated_at || m.created_at || null,
      actor: m.owner || m.agent || null,
      mission: m.id || null,
      action: `mission ${m.status || "update"}`,
      authority: m.authority || null,
      result: m.status || null,
      evidenceRef: null,
      href: m.id ? `/missions/${m.id}` : "/missions",
      source: "missions",
    });
  }

  for (const ce of controlEvents || []) {
    if (!ce) continue;
    events.push({
      id: `ctrl:${ce.id || events.length}`,
      timestamp: ce.timestamp || ce.created_at || null,
      actor: ce.actor || ce.source || null,
      mission: ce.mission_id || null,
      action: ce.action || ce.kind || ce.message || "control event",
      authority: ce.authority || null,
      result: ce.result || ce.status || null,
      evidenceRef: ce.evidence_id || null,
      href: ce.link || "/command",
      source: "control",
    });
  }

  const sorted = events
    .filter((e) => e.action)
    .sort((a, b) => {
      const ta = a.timestamp ? Date.parse(a.timestamp) : 0;
      const tb = b.timestamp ? Date.parse(b.timestamp) : 0;
      return (Number.isFinite(tb) ? tb : 0) - (Number.isFinite(ta) ? ta : 0);
    })
    .slice(0, limit);

  return {
    events: sorted,
    incompleteProvenance: sorted.filter((e) => !e.timestamp || !e.actor).length,
    note: "Missing provenance fields are left null — never invented.",
  };
}

/**
 * System health composition from infra + overview.
 */
export function composeSystemHealth({ infra = null, overview = null, infraStatus = "unknown" } = {}) {
  const subsystems = [];

  const push = (id, label, raw, evidence) => {
    let state = "UNKNOWN";
    if (raw == null) state = "UNKNOWN";
    else {
      const s = String(raw).toLowerCase();
      if (["healthy", "ok", "up", "ready", "active"].includes(s)) state = "HEALTHY";
      else if (["degraded", "warn", "warning", "partial"].includes(s)) state = "DEGRADED";
      else if (["blocked", "down", "error", "critical", "failed"].includes(s)) state = "BLOCKED";
      else if (["disabled", "off", "inactive"].includes(s)) state = "DISABLED";
      else if (["stale"].includes(s)) state = "STALE";
      else state = "UNKNOWN";
    }
    subsystems.push({ id, label, state, detail: raw == null ? "no data" : String(raw), evidence });
  };

  push(
    "backend",
    "Backend",
    overview?.platform_health?.status || overview?.backend?.status || (infraStatus === "connected" ? null : "unavailable"),
    "control.overview|infra"
  );
  push("infra", "Infrastructure", infra?.status || infra?.overall || null, "infrastructure.health");
  push("execution_gateway", "ExecutionGateway", overview?.execution?.status || overview?.gateway?.status || "governed", "policy");
  push("trading_guardian", "Trading Guardian", overview?.trading_guardian?.status || null, "overview");
  push("scheduler", "Scheduler", overview?.scheduler?.status || infra?.scheduler?.status || null, "overview|infra");
  push("agent_runtime", "Agent runtime", overview?.agent_runtime?.status || overview?.agents?.status || null, "overview");
  push("harness", "Harness", overview?.harness?.status || null, "overview");
  push("models", "Models", overview?.models?.status || infra?.models?.status || null, "overview|infra");
  push("providers", "Providers", overview?.providers?.status || "disabled", "policy");
  push("voice", "Voice", overview?.voice?.status || null, "overview");
  push("database", "Database", infra?.database?.status || infra?.db?.status || null, "infra");

  // When infra is an object of subsystems
  if (infra && typeof infra === "object") {
    for (const [key, val] of Object.entries(infra)) {
      if (!val || typeof val !== "object") continue;
      if (subsystems.some((s) => s.id === key)) continue;
      const st = val.status || val.state;
      if (st != null) push(key, key, st, "infrastructure.health.subsystem");
    }
  }

  const blocked = subsystems.filter((s) => s.state === "BLOCKED").length;
  const degraded = subsystems.filter((s) => s.state === "DEGRADED" || s.state === "STALE").length;
  const unknown = subsystems.filter((s) => s.state === "UNKNOWN").length;

  let overall = "UNKNOWN";
  if (blocked > 0) overall = "BLOCKED";
  else if (degraded > 0) overall = "DEGRADED";
  else if (unknown === subsystems.length) overall = "UNKNOWN";
  else if (unknown > 0) overall = "DEGRADED";
  else overall = "HEALTHY";

  return { overall, subsystems, blocked, degraded, unknown, infraStatus };
}

/**
 * Full command-center view model.
 */
export function composeCommandCenterViewModel(input = {}) {
  const {
    overview = null,
    overviewError = null,
    attention = null,
    missions = [],
    missionsStatus = "unknown",
    agents = [],
    agentsStatus = "unknown",
    evidence = [],
    evidenceStatus = "unknown",
    infra = null,
    infraStatus = "unknown",
    tradingSummary = null,
    tradingReady = false,
    tradingAuth = false,
    tradingError = null,
    voiceRuntime = null,
    voicePrefsEnabled = null,
    apiBase = null,
    controlEvents = [],
  } = input;

  const missionCards = (Array.isArray(missions) ? missions : [])
    .map(normalizeMissionCard)
    .filter(Boolean)
    .slice(0, 12);

  const activeMissions = missionCards.filter((m) =>
    ["active", "running", "in_progress", "working"].includes(String(m.status).toLowerCase())
  );
  const blockedMissions = missionCards.filter(
    (m) =>
      m.blocker ||
      ["blocked", "failed", "error", "paused"].includes(String(m.status).toLowerCase()) ||
      m.approvalRequired
  );

  const agentCards = (Array.isArray(agents) ? agents : []).map(normalizeAgentCard).filter(Boolean).slice(0, 12);

  const attentionItems = attention?.items || [];
  const authority = composeAuthorityStrip({
    overview,
    infra,
    tradingSummary,
    tradingReady,
    tradingAuth,
    voiceRuntime,
    voicePrefsEnabled,
    apiBase,
    generatedAt: attention?.generatedAt || overview?.generated_at || null,
  });

  const investment = composeInvestmentSnapshot({
    summary: tradingSummary,
    ready: tradingReady,
    auth: tradingAuth,
    error: tradingError,
  });

  const timeline = composeEvidenceTimeline({
    evidence: listFrom({ evidence }, ["evidence", "items"]),
    attentionItems,
    missions: Array.isArray(missions) ? missions : [],
    controlEvents,
    limit: 20,
  });

  const systemHealth = composeSystemHealth({ infra, overview, infraStatus });

  return {
    authority,
    attention: {
      items: attentionItems,
      summary: attention?.summary || null,
      partial: Boolean(attention?.partial),
      sources: attention?.sources || [],
    },
    activity: {
      activeMissions,
      blockedMissions,
      allMissions: missionCards,
      agents: agentCards,
      missionsStatus,
      agentsStatus,
    },
    investment,
    timeline,
    systemHealth,
    overviewError,
    evidenceStatus,
    command: {
      placeholder: "Ask Saathi · plan a mission · request approval",
      note: "Text and voice entry points. Execution remains gated by approval and ExecutionGateway.",
      voiceSessionState: authority.chips.find((c) => c.id === "voice")?.sessionState || "UNKNOWN",
    },
    meta: {
      composedAt: new Date().toISOString(),
      composition: "UI-NEXT-1",
      inventsMetrics: false,
      liveTrading: false,
    },
  };
}

export { listFrom };
