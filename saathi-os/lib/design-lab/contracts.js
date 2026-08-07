/**
 * UI-NEXT-2.1 — Canonical read-contract shapes for Hybrid Command prototype.
 *
 * Fixtures match T-NEXT-1 ledger + T-NEXT-2 risk public keys.
 * Every value is tagged: REAL | DERIVED_FROM_REAL | DEMO | UNAVAILABLE
 *
 * No frontend accounting/risk recomputation.
 */

export const PROVENANCE = Object.freeze({
  REAL: "REAL",
  DERIVED_FROM_REAL: "DERIVED_FROM_REAL",
  DEMO: "DEMO",
  UNAVAILABLE: "UNAVAILABLE",
});

/** VoiceSession presentation vocabulary (UI-NEXT-2.1 mission + existing mapper). */
export const VOICE_SESSION_STATES = Object.freeze([
  "IDLE",
  "READY",
  "LISTENING",
  "TRANSCRIBING",
  "THINKING",
  "SPEAKING",
  "INTERRUPTING",
  "DEGRADED",
  "ERROR",
  "CLOSED",
]);

export const AGENT_NODE_STATES = Object.freeze([
  "IDLE",
  "ACTIVE",
  "WAITING",
  "BLOCKED",
  "COMPLETE",
  "FAILED",
  "VETOED",
  "APPROVAL_REQUIRED",
]);

export const MODES = Object.freeze([
  { id: "command", label: "Command" },
  { id: "agents", label: "Agents" },
  { id: "investments", label: "Investments" },
  { id: "evidence", label: "Evidence" },
]);

/**
 * Fixture scenarios for visual regression / interaction demos.
 * @typedef {'healthy'|'risk_warning'|'recon_required'|'voice_degraded'} ScenarioId
 */

/** @returns {import('./contracts.js').CommandReadModel} */
export function buildDemoCommandModel(scenario = "healthy") {
  if (scenario === "empty_states") {
    return {
      scenario: "empty_states",
      global_provenance: PROVENANCE.DEMO,
      banner: "DEMO · empty-state fixture",
      portfolio: {
        provenance: PROVENANCE.DEMO,
        authority: "PortfolioLedgerService",
        mode: "PAPER",
        live_execution: "UNAVAILABLE",
        paper_nav: "100000.00",
        cash: "100000.00",
        realized_pnl: "0.00",
        unrealized_pnl: "0.00",
        gross_exposure: "0.00",
        net_exposure: "0.00",
        positions: [],
        portfolio_status: "HEALTHY",
        reconciliation: { ok: true, portfolio_status: "HEALTHY", pending_ledger_posts: 0 },
      },
      risk: {
        provenance: PROVENANCE.DEMO,
        authority: "PortfolioRiskEngine",
        label: "PAPER RISK",
        mode: "PAPER",
        live_execution: "UNAVAILABLE",
        risk_status: "HEALTHY",
        result: "ALLOW",
        drawdown: "0",
        daily_pnl: "0",
        weekly_pnl: "0",
        cash_pct: "1",
        largest_position: "0",
        budget_version: "paper-risk-budget/v1",
        risk_budget_consumed: [],
        stress: [],
        reason_codes: [],
        active_breaches: [],
      },
      agents: { provenance: PROVENANCE.DEMO, authority: "fixture", nodes: [] },
      mission: { provenance: PROVENANCE.DEMO, id: "none", name: "No active mission", stages: [] },
      approvals: { provenance: PROVENANCE.DEMO, items: [] },
      evidence: { provenance: PROVENANCE.DEMO, events: [] },
      system: {
        provenance: PROVENANCE.DEMO,
        paper: { value: "PAPER", status: "HEALTHY" },
        trading_guardian: { value: "SAFE", status: "HEALTHY" },
        ledger_reconciliation: { value: "HEALTHY", status: "HEALTHY" },
        risk: { value: "HEALTHY", status: "HEALTHY" },
        voice: { value: "READY", status: "HEALTHY" },
        models: { value: "LOCAL/BOUND", status: "HEALTHY" },
        gateway: { value: "READY", status: "HEALTHY" },
        runtime_health: { value: "HEALTHY", status: "HEALTHY" },
      },
      attention: { provenance: PROVENANCE.DERIVED_FROM_REAL, items: [] },
      voice_session_state: "READY",
    };
  }
  if (scenario === "service_error") {
    const base = buildDemoCommandModel("healthy");
    return {
      ...base,
      scenario: "service_error",
      banner: "DEMO · partial service failure",
      portfolio: { ...base.portfolio, error: "portfolio read failed", paper_nav: null, cash: null, positions: [] },
      risk: { ...base.risk, risk_status: "UNAVAILABLE", error: "risk unavailable", risk_budget_consumed: [], stress: [] },
      agents: { ...base.agents, error: "mission service unavailable", nodes: [] },
      system: {
        ...base.system,
        risk: { value: "UNAVAILABLE", status: "UNAVAILABLE" },
        voice: { value: "UNAVAILABLE", status: "UNAVAILABLE" },
      },
      attention: {
        provenance: PROVENANCE.DERIVED_FROM_REAL,
        items: [
          { id: "att-err-p", severity: "high", kind: "provider_degraded", title: "Portfolio read failed", urgency: 90, ref: "portfolio" },
          { id: "att-err-r", severity: "high", kind: "provider_degraded", title: "Risk unavailable", urgency: 85, ref: "risk" },
        ],
      },
    };
  }

  const reconOk = scenario !== "recon_required";
  const riskWarn = scenario === "risk_warning" || scenario === "recon_required";
  const voiceDegraded = scenario === "voice_degraded";

  /** Matches PortfolioLedgerService.command_center_summary + get_state fields */
  const portfolio = {
    provenance: PROVENANCE.DEMO,
    authority: "PortfolioLedgerService",
    mode: "PAPER",
    live_execution: "UNAVAILABLE",
    source: reconOk ? "canonical_fund_ledger" : "canonical_fund_ledger",
    fund_id: "fund_demo_ui21",
    paper_nav: "1248500.00",
    equity: "1248500.00",
    cash: "312400.00",
    realized_pnl: "18220.00",
    unrealized_pnl: "6140.00",
    pnl: "24360.00",
    total_pnl: "24360.00",
    gross_exposure: "936100.00",
    net_exposure: "936100.00",
    positions_value: "936100.00",
    invariants_ok: reconOk,
    portfolio_status: reconOk ? "HEALTHY" : "RECONCILIATION_REQUIRED",
    reconciliation: reconOk
      ? { ok: true, portfolio_status: "HEALTHY", pending_ledger_posts: 0 }
      : {
          ok: false,
          portfolio_status: "RECONCILIATION_REQUIRED",
          pending_ledger_posts: 2,
          issues: [{ code: "LEDGER_POST_PENDING", detail: "2 fill(s) pending ledger post" }],
        },
    positions: [
      {
        security_id: "sec_AAA_PAPER",
        symbol: "AAA",
        quantity: "1200.000000",
        avg_cost: "118.000000",
        cost_basis: "141600.00",
        market_value: "149800.00",
        unrealized_pnl: "8200.00",
        realized_pnl: "1200.00",
        weight: "0.12",
        mark_stale: false,
        mark: { price: "124.833333", source: "DEMO", stale: false },
      },
      {
        security_id: "sec_BBB_PAPER",
        symbol: "BBB",
        quantity: "800.000000",
        avg_cost: "135.000000",
        cost_basis: "108000.00",
        market_value: "112400.00",
        unrealized_pnl: "4400.00",
        realized_pnl: "800.00",
        weight: "0.09",
        mark_stale: false,
        mark: { price: "140.500000", source: "DEMO", stale: false },
      },
      {
        security_id: "sec_CCC_PAPER",
        symbol: "CCC",
        quantity: "2000.000000",
        avg_cost: "48.000000",
        cost_basis: "96000.00",
        market_value: "99900.00",
        unrealized_pnl: "3900.00",
        realized_pnl: "400.00",
        weight: "0.08",
        mark_stale: false,
        mark: { price: "49.950000", source: "DEMO", stale: false },
      },
    ],
  };

  /** Matches PortfolioRiskEngine.command_risk_contract */
  const risk = {
    provenance: PROVENANCE.DEMO,
    authority: "PortfolioRiskEngine",
    label: "PAPER RISK",
    mode: "PAPER",
    live_execution: "UNAVAILABLE",
    risk_status: reconOk ? (riskWarn ? "WARNING" : "HEALTHY") : "RECONCILIATION_REQUIRED",
    result: reconOk ? (riskWarn ? "WARN" : "ALLOW") : "BLOCK",
    nav: portfolio.paper_nav,
    drawdown: "0.032",
    max_drawdown: "0.032",
    daily_pnl: "2410.00",
    daily_pnl_pct: "0.0019",
    weekly_pnl: "9880.00",
    weekly_pnl_pct: "0.008",
    gross_exposure: portfolio.gross_exposure,
    gross_exposure_pct: "0.75",
    cash_pct: "0.25",
    largest_position: "0.12",
    budget_version: "paper-risk-budget/v1",
    source: "portfolio_risk_engine",
    stress_loss: "-62400.00",
    reason_codes: reconOk
      ? riskWarn
        ? ["SOFT_WARNING_NEAR_TOP3"]
        : []
      : ["LEDGER_UNRECONCILED"],
    active_breaches: reconOk
      ? []
      : [{ reason_code: "LEDGER_UNRECONCILED", detail: "pending ledger posts" }],
    risk_budget_consumed: [
      {
        name: "position_concentration",
        used: "0.12",
        remaining: "0.03",
        limit: "0.15",
        unit: "fraction",
        status: riskWarn ? "WARNING" : "OK",
        soft_threshold: "0.1275",
        hard_threshold: "0.15",
      },
      {
        name: "gross_exposure",
        used: "0.75",
        remaining: "0.25",
        limit: "1.00",
        unit: "fraction",
        status: "OK",
        soft_threshold: "0.85",
        hard_threshold: "1.00",
      },
      {
        name: "drawdown",
        used: "0.032",
        remaining: "0.118",
        limit: "0.15",
        unit: "fraction",
        status: "OK",
        soft_threshold: "0.1275",
        hard_threshold: "0.15",
      },
      {
        name: "cash_buffer",
        used: "0.25",
        remaining: "—",
        limit: "0.05 min",
        unit: "fraction_cash",
        status: "OK",
        soft_threshold: "0.0575",
        hard_threshold: "0.05",
      },
    ],
    stress: [
      {
        scenario: { scenario_id: "mkt_m5", name: "market -5%" },
        projected_nav: "1186075.00",
        loss: "-62425.00",
        status: "OK",
        breaches: [],
      },
      {
        scenario: { scenario_id: "mkt_m10", name: "market -10%" },
        projected_nav: "1123650.00",
        loss: "-124850.00",
        status: "WARNING",
        breaches: [],
      },
      {
        scenario: { scenario_id: "largest_m15", name: "largest position -15%" },
        projected_nav: "1226030.00",
        loss: "-22470.00",
        status: "OK",
        breaches: [],
      },
      {
        scenario: { scenario_id: "top3_m10", name: "top 3 positions -10%" },
        projected_nav: "1212280.00",
        loss: "-36220.00",
        status: "OK",
        breaches: [],
      },
    ],
  };

  const agents = {
    provenance: PROVENANCE.DEMO,
    authority: "mission/agent read models (fixture shape)",
    nodes: [
      {
        id: "cio",
        name: "CIO / Manager",
        role: "orchestrator",
        status: "ACTIVE",
        task: "Coordinate rebalance review",
        inputs: ["research brief", "risk snapshot"],
        outputs: ["mission plan"],
        dependencies: ["research", "quant"],
        evidence: ["ev_demo_1"],
      },
      {
        id: "research",
        name: "Research",
        role: "research",
        status: "WAITING",
        task: "Await macro data",
        inputs: ["market observation"],
        outputs: [],
        dependencies: [],
        evidence: ["ev_demo_1"],
      },
      {
        id: "quant",
        name: "Quant",
        role: "quant",
        status: "ACTIVE",
        task: "Allocation draft",
        inputs: ["positions"],
        outputs: ["proposal draft"],
        dependencies: ["research"],
        evidence: ["ev_demo_2"],
      },
      {
        id: "macro",
        name: "Macro",
        role: "macro",
        status: "IDLE",
        task: "—",
        inputs: [],
        outputs: [],
        dependencies: [],
        evidence: [],
      },
      {
        id: "proposal",
        name: "Portfolio Proposal",
        role: "proposal",
        status: "APPROVAL_REQUIRED",
        task: "Rebalance DRAFT",
        inputs: ["quant output"],
        outputs: ["proposal_id"],
        dependencies: ["quant", "risk"],
        evidence: ["ev_demo_2"],
      },
      {
        id: "risk",
        name: "Risk Engine",
        role: "risk",
        status: "COMPLETE",
        task: "evaluate_proposed_trade",
        inputs: ["proposal"],
        outputs: ["WARN"],
        dependencies: ["proposal"],
        evidence: ["ev_demo_3"],
      },
      {
        id: "tg",
        name: "Trading Guardian",
        role: "guardian",
        status: "COMPLETE",
        task: "paper ALLOW",
        inputs: ["risk decision"],
        outputs: ["allowed=true"],
        dependencies: ["risk"],
        evidence: ["ev_demo_4"],
      },
      {
        id: "approval",
        name: "Approval",
        role: "approval",
        status: "BLOCKED",
        task: "Operator decision",
        inputs: ["proposal", "tg"],
        outputs: [],
        dependencies: ["tg"],
        evidence: ["ev_demo_5"],
      },
    ],
  };

  const mission = {
    provenance: PROVENANCE.DEMO,
    authority: "mission runtime (fixture vocabulary)",
    id: "msn_demo_rebalance",
    name: "Paper rebalance review",
    stages: [
      { id: "created", label: "created", status: "COMPLETE" },
      { id: "researching", label: "researching", status: "COMPLETE" },
      { id: "analysis", label: "analysis", status: "ACTIVE" },
      { id: "risk_review", label: "risk review", status: "COMPLETE" },
      { id: "approval", label: "approval", status: "BLOCKED" },
      { id: "paper_execution", label: "paper execution", status: "IDLE" },
      { id: "completed", label: "completed", status: "IDLE" },
    ],
  };

  const approvals = {
    provenance: PROVENANCE.DEMO,
    authority: "approvals read surface (fixture)",
    items: [
      {
        id: "appr_demo_1",
        requested_action: "paper.order.submit rebalance",
        requester: "quant-agent",
        risk_summary: riskWarn ? "WARN · soft concentration" : "ALLOW",
        scope: "PAPER only",
        expiry: "2026-08-07T18:00:00Z",
        status: "APPROVAL_REQUIRED",
      },
    ],
  };

  const evidence = {
    provenance: PROVENANCE.DEMO,
    authority: "audit/evidence (fixture causal chain)",
    events: [
      {
        id: "ev_demo_1",
        timestamp: "2026-08-07T09:12:00Z",
        type: "research",
        actor: "macro-agent",
        status: "COMPLETE",
        reason: "brief complete",
        related_ids: ["msn_demo_rebalance"],
      },
      {
        id: "ev_demo_2",
        timestamp: "2026-08-07T09:18:00Z",
        type: "proposal",
        actor: "quant-agent",
        status: "DRAFT",
        reason: "rebalance draft",
        related_ids: ["msn_demo_rebalance", "appr_demo_1"],
      },
      {
        id: "ev_demo_3",
        timestamp: "2026-08-07T09:19:00Z",
        type: "risk_evaluation",
        actor: "PortfolioRiskEngine",
        status: riskWarn ? "WARN" : "ALLOW",
        reason: risk.reason_codes[0] || "within limits",
        related_ids: ["ev_demo_2"],
      },
      {
        id: "ev_demo_4",
        timestamp: "2026-08-07T09:19:10Z",
        type: "tg_decision",
        actor: "TradingGuardian",
        status: "ALLOW",
        reason: "paper environment",
        related_ids: ["ev_demo_3"],
      },
      {
        id: "ev_demo_5",
        timestamp: "2026-08-07T09:20:00Z",
        type: "approval",
        actor: "operator",
        status: "PENDING",
        reason: "awaiting decision",
        related_ids: ["appr_demo_1"],
      },
      {
        id: "ev_demo_6",
        timestamp: null,
        type: "paper_order",
        actor: null,
        status: "UNAVAILABLE",
        reason: "not submitted",
        related_ids: [],
      },
      {
        id: "ev_demo_7",
        timestamp: null,
        type: "fill",
        actor: null,
        status: "UNAVAILABLE",
        reason: "no order",
        related_ids: [],
      },
      {
        id: "ev_demo_8",
        timestamp: null,
        type: "ledger_event",
        actor: "PortfolioLedgerService",
        status: reconOk ? "IDLE" : "PENDING",
        reason: reconOk ? "no new post" : "pending posts",
        related_ids: [],
      },
      {
        id: "ev_demo_9",
        timestamp: "2026-08-07T09:00:00Z",
        type: "reconciliation",
        actor: "system",
        status: reconOk ? "HEALTHY" : "RECONCILIATION_REQUIRED",
        reason: reconOk ? "clean" : "ledger post pending",
        related_ids: [],
      },
    ],
  };

  const system = {
    provenance: PROVENANCE.DEMO,
    paper: { value: "PAPER", status: "HEALTHY" },
    trading_guardian: { value: "SAFE", status: "HEALTHY" },
    ledger_reconciliation: {
      value: reconOk ? "HEALTHY" : "RECONCILIATION_REQUIRED",
      status: reconOk ? "HEALTHY" : "BLOCKED",
    },
    risk: {
      value: risk.risk_status,
      status: reconOk ? (riskWarn ? "WARNING" : "HEALTHY") : "BLOCKED",
    },
    voice: {
      value: voiceDegraded ? "DEGRADED" : "READY",
      status: voiceDegraded ? "DEGRADED" : "HEALTHY",
    },
    models: { value: "LOCAL/BOUND", status: "HEALTHY" },
    gateway: { value: "READY", status: "HEALTHY" },
    runtime_health: { value: "HEALTHY", status: "HEALTHY" },
  };

  const attention = buildAttention({ portfolio, risk, agents, approvals, system, mission });

  return {
    scenario,
    global_provenance: PROVENANCE.DEMO,
    banner: "DEMO / MOCK fixtures — exact T-NEXT field names; not live authority",
    portfolio,
    risk,
    agents,
    mission,
    approvals,
    evidence,
    system,
    attention,
    voice_session_state: voiceDegraded ? "DEGRADED" : "READY",
  };
}

function buildAttention({ portfolio, risk, agents, approvals, system, mission }) {
  const items = [];
  for (const a of approvals.items || []) {
    if (a.status === "APPROVAL_REQUIRED" || a.status === "PENDING") {
      items.push({
        id: `att-${a.id}`,
        severity: "high",
        kind: "approval_required",
        title: a.requested_action,
        urgency: 100,
        ref: a.id,
      });
    }
  }
  if (portfolio.portfolio_status === "RECONCILIATION_REQUIRED") {
    items.push({
      id: "att-recon",
      severity: "critical",
      kind: "reconciliation_required",
      title: "RECONCILIATION REQUIRED",
      urgency: 120,
      ref: "reconciliation",
    });
  }
  if (risk.risk_status === "BREACHED" || risk.result === "BLOCK") {
    items.push({
      id: "att-risk-breach",
      severity: "critical",
      kind: "risk_breach",
      title: `Risk blocked: ${(risk.reason_codes || []).join(", ") || "breach"}`,
      urgency: 110,
      ref: "risk",
    });
  } else if (risk.risk_status === "WARNING" || risk.result === "WARN") {
    items.push({
      id: "att-risk-warn",
      severity: "medium",
      kind: "risk_warning",
      title: `Risk warning: ${(risk.reason_codes || []).join(", ") || "soft limit"}`,
      urgency: 70,
      ref: "risk",
    });
  }
  for (const n of agents.nodes || []) {
    if (n.status === "BLOCKED" || n.status === "FAILED") {
      items.push({
        id: `att-agent-${n.id}`,
        severity: n.status === "FAILED" ? "high" : "medium",
        kind: n.status === "FAILED" ? "failed_agent_task" : "mission_blocked",
        title: `${n.name}: ${n.status}`,
        urgency: n.status === "FAILED" ? 90 : 60,
        ref: n.id,
      });
    }
  }
  if (system.voice.status === "DEGRADED") {
    items.push({
      id: "att-voice",
      severity: "medium",
      kind: "voice_degraded",
      title: "Voice degraded",
      urgency: 50,
      ref: "voice",
    });
  }
  if (mission.stages?.some((s) => s.status === "BLOCKED")) {
    items.push({
      id: "att-mission",
      severity: "medium",
      kind: "mission_blocked",
      title: `${mission.name} blocked at approval`,
      urgency: 65,
      ref: mission.id,
    });
  }
  items.sort((a, b) => b.urgency - a.urgency);
  return { provenance: PROVENANCE.DERIVED_FROM_REAL, items };
}

/**
 * Bounded UI intents from final transcripts only (non-executing).
 */
export function mapUiIntent(text) {
  const t = String(text || "").toLowerCase().trim();
  if (!t) return { type: "noop" };
  if (/\bstop\b/.test(t)) return { type: "stop", mode: null, focus: "saathi", voice: "INTERRUPTING", reply: "Stopped." };
  if (/evidence|timeline|what happened/.test(t))
    return { type: "nav", mode: "evidence", focus: "evidence", voice: "SPEAKING", reply: "Opening evidence timeline." };
  if (/mission|agent|topology/.test(t))
    return { type: "nav", mode: "agents", focus: "agents", voice: "SPEAKING", reply: "Showing active missions and agents." };
  if (/approval|needs me|what needs/.test(t))
    return { type: "nav", mode: "command", focus: "attention", voice: "SPEAKING", reply: "Focusing on items that need you." };
  if (/invest|portfolio|position|nav|cash|stress|risk/.test(t))
    return {
      type: "nav",
      mode: "investments",
      focus: "risk",
      voice: "SPEAKING",
      reply: "Opening Investments · PAPER RISK. Values follow ledger/risk contracts.",
    };
  if (/command|go back|home cockpit/.test(t))
    return { type: "nav", mode: "command", focus: "saathi", voice: "READY", reply: "Back to Command." };
  return {
    type: "chat",
    mode: null,
    focus: "saathi",
    voice: "SPEAKING",
    reply: "I can open risk, missions, approvals, or evidence. I cannot authorize trades. (read-only prototype)",
  };
}

export function yetiFromSystem({ voice, attention, risk }) {
  if (voice === "LISTENING" || voice === "TRANSCRIBING") return "listening";
  if (voice === "THINKING") return "thinking";
  if (voice === "SPEAKING") return "speaking";
  if (voice === "DEGRADED" || voice === "ERROR") return "degraded";
  if (risk?.risk_status === "BREACHED" || risk?.result === "BLOCK") return "warning";
  if ((attention?.items || []).some((i) => i.kind === "approval_required")) return "approval_waiting";
  if (risk?.risk_status === "HEALTHY" && voice === "READY") return "success";
  return "idle";
}
