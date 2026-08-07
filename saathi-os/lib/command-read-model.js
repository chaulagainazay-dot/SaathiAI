/**
 * UI-NEXT-3 — Production Hybrid Command read-model composition.
 *
 * Translates canonical backend/read contracts into presentation shapes.
 * Does NOT implement accounting, risk decisions, portfolio construction,
 * approval decisions, or execution rules.
 *
 * Provenance: LIVE | DERIVED | STALE | UNAVAILABLE | ERROR
 * Never invents DEMO financial values for production.
 */

import { PROVENANCE, mapUiIntent, yetiFromSystem, MODES, VOICE_SESSION_STATES } from "./design-lab/contracts.js";

export { MODES, VOICE_SESSION_STATES, mapUiIntent, yetiFromSystem };

/** Production provenance vocabulary (no DEMO in default production path). */
export const PROD_PROVENANCE = Object.freeze({
  LIVE: "LIVE",
  DERIVED: "DERIVED",
  STALE: "STALE",
  UNAVAILABLE: "UNAVAILABLE",
  ERROR: "ERROR",
  LOADING: "LOADING",
});

/** Reason codes → concise UI labels (deterministic; not LLM-only). */
export const REASON_CODE_LABELS = Object.freeze({
  TARGET_WEIGHT_RESTORE: "Restore target allocation",
  RISK_CONCENTRATION_REDUCTION: "Reduce concentration risk",
  CASH_BUFFER_RESTORE: "Restore minimum cash buffer",
  SIGNAL_STRENGTH_INCREASE: "Increase allocation from qualified signal",
  EQUAL_WEIGHT_BASELINE: "Equal-weight baseline allocation",
  FIXED_TARGET: "Fixed target weights",
  POSITION_ENTRY: "Open new position",
  POSITION_EXIT: "Exit position",
  NO_MATERIAL_DRIFT: "No material drift — hold",
  MIN_TRADE_THRESHOLD: "Below minimum trade size",
  TARGET_REDUCED_MAX_POSITION_LIMIT: "Capped at max position weight",
  TARGET_REDUCED_CASH_BUFFER: "Reduced to restore cash buffer",
  TARGET_REDUCED_GROSS_EXPOSURE: "Reduced for gross exposure limit",
  STALE_PRICE: "Stale or missing price",
  LEDGER_UNRECONCILED: "Ledger reconciliation required",
  INSUFFICIENT_CASH: "Insufficient cash for rebalance",
  RISK_BLOCKED: "Blocked by risk engine",
  SUPERSEDED: "Superseded by newer proposal",
  EXPIRED: "Proposal expired",
  STALE_PROPOSAL: "Proposal stale vs portfolio snapshot",
  SHORTS_DISABLED: "Shorts not permitted",
  LEVERAGE_DISABLED: "Leverage not permitted",
  SOFT_WARNING_NEAR_TOP3: "Near top-3 concentration soft limit",
});

export function reasonCodeLabel(code) {
  if (!code) return "—";
  return REASON_CODE_LABELS[code] || String(code).replace(/_/g, " ").toLowerCase();
}

export function formatFraction(v) {
  if (v == null || v === "" || v === "—") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  if (Math.abs(n) <= 1.0001) return `${(n * 100).toFixed(1)}%`;
  return String(v);
}

export function formatMoney(v) {
  if (v == null || v === "" || v === "—") return "—";
  const n = Number(String(v).replace(/,/g, ""));
  if (Number.isNaN(n)) return String(v);
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function naPanel(authority, reason = "UNAVAILABLE", extra = {}) {
  return {
    provenance: PROD_PROVENANCE.UNAVAILABLE,
    authority,
    mode: "PAPER",
    live_execution: "UNAVAILABLE",
    error: reason,
    ...extra,
  };
}

/**
 * Compose portfolio panel from command-snapshot or summary payload.
 * Pass-through only — no NAV/P&L math.
 */
export function composePortfolioPanel(snapshot, { error = null, loading = false } = {}) {
  if (loading) {
    return {
      provenance: PROD_PROVENANCE.LOADING,
      authority: "PortfolioLedgerService",
      mode: "PAPER",
      live_execution: "UNAVAILABLE",
      paper_nav: null,
      cash: null,
      positions: [],
      portfolio_status: "LOADING",
    };
  }
  if (error) {
    return { ...naPanel("PortfolioLedgerService", error), portfolio_status: "ERROR", positions: [] };
  }
  if (!snapshot) {
    return { ...naPanel("PortfolioLedgerService", "no snapshot"), portfolio_status: "UNAVAILABLE", positions: [] };
  }
  const recon = snapshot.reconciliation || {};
  const status =
    snapshot.portfolio_status ||
    recon.portfolio_status ||
    (recon.ok === false ? "RECONCILIATION_REQUIRED" : "HEALTHY");
  const fromLedger =
    snapshot.source === "canonical_fund_ledger" ||
    snapshot.books_authority === "canonical_fund_ledger" ||
    snapshot.ledger === true;

  return {
    provenance: fromLedger ? PROD_PROVENANCE.LIVE : PROD_PROVENANCE.DERIVED,
    authority: "PortfolioLedgerService",
    mode: "PAPER",
    live_execution: "UNAVAILABLE",
    source: snapshot.source || (fromLedger ? "canonical_fund_ledger" : "paper_overview"),
    fund_id: snapshot.fund_id || null,
    account_id: snapshot.account_id || null,
    paper_nav: snapshot.paper_nav ?? snapshot.nav ?? snapshot.equity ?? null,
    cash: snapshot.cash ?? snapshot.current_cash ?? null,
    realized_pnl: snapshot.realized_pnl ?? null,
    unrealized_pnl: snapshot.unrealized_pnl ?? null,
    pnl: snapshot.pnl ?? snapshot.total_pnl ?? null,
    gross_exposure:
      snapshot.gross_exposure ??
      snapshot.exposure?.gross ??
      snapshot.positions_value ??
      null,
    net_exposure: snapshot.net_exposure ?? snapshot.exposure?.net ?? null,
    positions: Array.isArray(snapshot.positions) ? snapshot.positions : [],
    portfolio_status: status,
    reconciliation: recon.ok != null || recon.portfolio_status ? recon : { portfolio_status: status },
    invariants_ok: snapshot.invariants_ok,
    error: snapshot.error || null,
  };
}

/**
 * Compose risk panel from paper_risk_snapshot / command_risk_contract.
 */
export function composeRiskPanel(risk, { error = null, loading = false } = {}) {
  if (loading) {
    return {
      provenance: PROD_PROVENANCE.LOADING,
      authority: "PortfolioRiskEngine",
      label: "PAPER RISK",
      mode: "PAPER",
      live_execution: "UNAVAILABLE",
      risk_status: "LOADING",
      risk_budget_consumed: [],
      stress: [],
    };
  }
  if (error) {
    return {
      ...naPanel("PortfolioRiskEngine", error),
      label: "PAPER RISK",
      risk_status: "ERROR",
      risk_budget_consumed: [],
      stress: [],
      reason_codes: [],
      active_breaches: [],
    };
  }
  if (!risk) {
    return {
      ...naPanel("PortfolioRiskEngine", "risk unavailable"),
      label: "PAPER RISK",
      risk_status: "UNAVAILABLE",
      risk_budget_consumed: [],
      stress: [],
      reason_codes: [],
      active_breaches: [],
    };
  }
  return {
    provenance: risk.source === "portfolio_risk_engine" ? PROD_PROVENANCE.LIVE : PROD_PROVENANCE.DERIVED,
    authority: "PortfolioRiskEngine",
    label: risk.label || "PAPER RISK",
    mode: "PAPER",
    live_execution: "UNAVAILABLE",
    risk_status: risk.risk_status || risk.risk_state || "UNAVAILABLE",
    result: risk.result || null,
    nav: risk.nav ?? null,
    drawdown: risk.drawdown ?? null,
    max_drawdown: risk.max_drawdown ?? null,
    daily_pnl: risk.daily_pnl ?? null,
    daily_pnl_pct: risk.daily_pnl_pct ?? null,
    weekly_pnl: risk.weekly_pnl ?? null,
    weekly_pnl_pct: risk.weekly_pnl_pct ?? null,
    gross_exposure: risk.gross_exposure ?? null,
    gross_exposure_pct: risk.gross_exposure_pct ?? null,
    cash_pct: risk.cash_pct ?? null,
    largest_position: risk.largest_position ?? risk.largest_position_pct ?? null,
    budget_version: risk.budget_version ?? null,
    risk_budget_consumed: risk.risk_budget_consumed || risk.risk_budget_bars || [],
    stress: risk.stress || [],
    stress_loss: risk.stress_loss ?? null,
    reason_codes: risk.reason_codes || [],
    active_breaches: risk.active_breaches || risk.breaches || [],
    source: risk.source || "portfolio_risk_engine",
    error: risk.error || null,
  };
}

/**
 * Compose proposal panel from T-NEXT-3 command_proposal_contract.
 */
export function composePerformancePanel(payload, { error = null, loading = false } = {}) {
  if (loading) {
    return { provenance: PROD_PROVENANCE.LOADING, paper_performance: null };
  }
  if (error) {
    return { provenance: PROD_PROVENANCE.ERROR, error, paper_performance: null };
  }
  const perf = payload?.paper_performance || payload?.performance || null;
  if (!perf) {
    return {
      provenance: PROD_PROVENANCE.UNAVAILABLE,
      paper_performance: null,
      note: "performance unavailable",
    };
  }
  return {
    provenance: perf.provenance === "DERIVED" || perf.source === "portfolio_performance_engine" ? PROD_PROVENANCE.LIVE : PROD_PROVENANCE.DERIVED,
    paper_performance: {
      ...perf,
      mode: "PAPER",
      live_execution: "UNAVAILABLE",
    },
  };
}

export function composeProposalPanel(payload, { error = null, loading = false } = {}) {
  if (loading) {
    return { provenance: PROD_PROVENANCE.LOADING, portfolio_proposal: null };
  }
  if (error) {
    return { provenance: PROD_PROVENANCE.ERROR, error, portfolio_proposal: null };
  }
  const active = payload?.active || payload?.portfolio_proposal || null;
  if (!active) {
    return {
      provenance: PROD_PROVENANCE.UNAVAILABLE,
      portfolio_proposal: null,
      proposals: payload?.proposals || [],
      fund_id: payload?.fund_id || null,
      authorizes_execution: false,
      mode: "PAPER",
    };
  }
  return {
    provenance: PROD_PROVENANCE.LIVE,
    portfolio_proposal: {
      ...active,
      authorizes_execution: false,
      mode: "PAPER",
      reason_labels: (active.reason_codes || []).map((c) => ({
        code: c,
        label: reasonCodeLabel(c),
      })),
    },
    proposals: payload?.proposals || [],
    fund_id: payload?.fund_id || null,
    authorizes_execution: false,
    mode: "PAPER",
  };
}

/**
 * Unified attention ranking for production Command.
 */
export function composeAttention({
  portfolio,
  risk,
  proposal,
  approvals = [],
  agents = [],
  missions = [],
  voiceState = "READY",
  system = {},
} = {}) {
  const items = [];
  const push = (item) => {
    if (!item?.id) return;
    items.push(item);
  };

  const recon =
    portfolio?.portfolio_status === "RECONCILIATION_REQUIRED" ||
    portfolio?.reconciliation?.portfolio_status === "RECONCILIATION_REQUIRED" ||
    risk?.risk_status === "RECONCILIATION_REQUIRED";
  if (recon) {
    push({
      id: "att-recon",
      severity: "CRITICAL",
      rank: "CRITICAL",
      kind: "reconciliation_required",
      title: "Reconciliation required",
      urgency: 120,
      ref: "reconciliation",
      focus: "portfolio",
    });
  }

  const pp = proposal?.portfolio_proposal;
  if (pp?.status === "RISK_BLOCKED") {
    push({
      id: `att-prop-block-${pp.id}`,
      severity: "CRITICAL",
      rank: "CRITICAL",
      kind: "risk_blocked_proposal",
      title: `Proposal blocked by risk: ${(pp.reason_codes || []).slice(0, 2).join(", ") || "RISK_BLOCKED"}`,
      urgency: 115,
      ref: pp.id,
      focus: "proposal",
    });
  } else if (pp?.status === "READY_FOR_APPROVAL") {
    push({
      id: `att-prop-ready-${pp.id}`,
      severity: "ACTION_REQUIRED",
      rank: "ACTION_REQUIRED",
      kind: "portfolio_proposal_ready",
      title: `Portfolio proposal ready for approval`,
      urgency: 105,
      ref: pp.id,
      focus: "proposal",
    });
  } else if (pp?.status === "STALE_PROPOSAL" || pp?.status === "EXPIRED") {
    push({
      id: `att-prop-stale-${pp.id}`,
      severity: "WARNING",
      rank: "WARNING",
      kind: pp.status === "EXPIRED" ? "expired_proposal" : "stale_proposal",
      title: `Proposal ${pp.status}`,
      urgency: 80,
      ref: pp.id,
      focus: "proposal",
    });
  } else if (pp?.status === "DATA_INSUFFICIENT") {
    push({
      id: `att-prop-data-${pp.id}`,
      severity: "WARNING",
      rank: "WARNING",
      kind: "data_insufficient",
      title: "Proposal data insufficient",
      urgency: 75,
      ref: pp.id,
      focus: "proposal",
    });
  }

  if (risk?.risk_status === "BREACHED" || risk?.result === "BLOCK") {
    push({
      id: "att-risk-breach",
      severity: "CRITICAL",
      rank: "CRITICAL",
      kind: "risk_breach",
      title: `Risk blocked: ${(risk.reason_codes || []).slice(0, 2).join(", ") || "breach"}`,
      urgency: 110,
      ref: "risk",
      focus: "risk",
    });
  } else if (risk?.risk_status === "WARNING" || risk?.result === "WARN") {
    push({
      id: "att-risk-warn",
      severity: "WARNING",
      rank: "WARNING",
      kind: "risk_warning",
      title: `Risk warning: ${(risk.reason_codes || []).slice(0, 2).join(", ") || "soft limit"}`,
      urgency: 70,
      ref: "risk",
      focus: "risk",
    });
  }

  for (const a of approvals || []) {
    const st = String(a.status || a.state || "").toUpperCase();
    if (st.includes("PENDING") || st.includes("REQUIRED") || st.includes("APPROVAL")) {
      push({
        id: `att-appr-${a.id || a.approval_id || items.length}`,
        severity: "ACTION_REQUIRED",
        rank: "ACTION_REQUIRED",
        kind: "approval_required",
        title: a.requested_action || a.title || a.action || "Approval required",
        urgency: 100,
        ref: a.id || a.approval_id,
        focus: "attention",
      });
    }
  }

  for (const n of agents || []) {
    const st = String(n.status || "").toUpperCase();
    if (st === "FAILED" || st === "BLOCKED") {
      push({
        id: `att-agent-${n.id || n.name}`,
        severity: st === "FAILED" ? "ACTION_REQUIRED" : "WARNING",
        rank: st === "FAILED" ? "ACTION_REQUIRED" : "WARNING",
        kind: st === "FAILED" ? "agent_failed" : "mission_blocked",
        title: `${n.name || n.id}: ${st}`,
        urgency: st === "FAILED" ? 90 : 60,
        ref: n.id,
        focus: "agents",
      });
    }
  }

  for (const m of missions || []) {
    const st = String(m.status || m.state || "").toLowerCase();
    if (st.includes("block") || st.includes("fail")) {
      push({
        id: `att-miss-${m.id || items.length}`,
        severity: "WARNING",
        rank: "WARNING",
        kind: "mission_blocked",
        title: `${m.name || m.title || "Mission"}: ${m.status || m.state}`,
        urgency: 65,
        ref: m.id,
        focus: "agents",
      });
    }
  }

  if (voiceState === "DEGRADED" || voiceState === "ERROR") {
    push({
      id: "att-voice",
      severity: "WARNING",
      rank: "WARNING",
      kind: "voice_degraded",
      title: `Voice ${voiceState}`,
      urgency: 50,
      ref: "voice",
      focus: "saathi",
    });
  }

  if (system?.models?.status === "DEGRADED" || system?.gateway?.status === "DEGRADED") {
    push({
      id: "att-provider",
      severity: "WARNING",
      rank: "WARNING",
      kind: "provider_degraded",
      title: "Provider / runtime degraded",
      urgency: 55,
      ref: "system",
      focus: "system",
    });
  }

  // Dedupe by kind+ref
  const seen = new Set();
  const deduped = [];
  for (const it of items.sort((a, b) => b.urgency - a.urgency)) {
    const k = `${it.kind}:${it.ref || it.id}`;
    if (seen.has(k)) continue;
    seen.add(k);
    deduped.push(it);
  }
  return { provenance: PROD_PROVENANCE.DERIVED, items: deduped };
}

export function composeSystemStrip({ portfolio, risk, voiceState, infra = null, tg = null } = {}) {
  const recon =
    portfolio?.portfolio_status === "RECONCILIATION_REQUIRED" ||
    portfolio?.reconciliation?.portfolio_status === "RECONCILIATION_REQUIRED";
  const riskSt = risk?.risk_status || "UNAVAILABLE";
  const riskTone =
    riskSt === "BREACHED" || risk?.result === "BLOCK" || recon
      ? "BLOCKED"
      : riskSt === "WARNING" || risk?.result === "WARN"
        ? "WARNING"
        : riskSt === "UNAVAILABLE" || riskSt === "ERROR" || riskSt === "LOADING"
          ? "UNAVAILABLE"
          : "HEALTHY";

  return {
    provenance: PROD_PROVENANCE.DERIVED,
    paper: { value: "PAPER", status: "HEALTHY" },
    trading_guardian: {
      value: tg?.status || tg?.value || "SAFE",
      status: tg?.status === "BLOCKED" ? "BLOCKED" : "HEALTHY",
    },
    recon: {
      value: recon ? "RECONCILIATION_REQUIRED" : portfolio?.portfolio_status || "HEALTHY",
      status: recon ? "BLOCKED" : portfolio?.provenance === "ERROR" ? "UNAVAILABLE" : "HEALTHY",
    },
    risk: { value: riskSt, status: riskTone },
    voice: {
      value: voiceState || "UNAVAILABLE",
      status:
        voiceState === "DEGRADED" || voiceState === "ERROR"
          ? "DEGRADED"
          : voiceState
            ? "HEALTHY"
            : "UNAVAILABLE",
    },
    models: {
      value: infra?.models || "BOUND",
      status: infra?.ok === false ? "DEGRADED" : "HEALTHY",
    },
    gateway: {
      value: "EG",
      status: infra?.gateway === "down" ? "DEGRADED" : "HEALTHY",
    },
  };
}

/**
 * Build full production Hybrid Command model from source slices.
 * Partial failures isolate to their panels.
 */
export function composeHybridCommandModel({
  portfolioSnap = null,
  portfolioError = null,
  portfolioLoading = false,
  riskSnap = null,
  riskError = null,
  riskLoading = false,
  proposalPayload = null,
  proposalError = null,
  proposalLoading = false,
  performancePayload = null,
  performanceError = null,
  performanceLoading = false,
  agents = [],
  missions = [],
  approvals = [],
  evidence = [],
  voiceState = "READY",
  voiceTranscript = "",
  voiceReply = "",
  focusEntity = null,
  infra = null,
  tg = null,
  banner = null,
} = {}) {
  const portfolio = composePortfolioPanel(portfolioSnap, {
    error: portfolioError,
    loading: portfolioLoading,
  });
  const risk = composeRiskPanel(riskSnap, { error: riskError, loading: riskLoading });
  const proposal = composeProposalPanel(proposalPayload, {
    error: proposalError,
    loading: proposalLoading,
  });
  const performance = composePerformancePanel(performancePayload, {
    error: performanceError,
    loading: performanceLoading,
  });
  const attention = composeAttention({
    portfolio,
    risk,
    proposal,
    approvals,
    agents,
    missions,
    voiceState,
  });
  const system = composeSystemStrip({ portfolio, risk, voiceState, infra, tg });

  const agentNodes = (agents || []).map((a) => ({
    id: a.id || a.agent_id || a.binding_id,
    name: a.name || a.role || a.label || "Agent",
    role: a.role || a.role_id || null,
    status: a.status || a.state || a.runtime_status || "UNKNOWN",
    task: a.task || a.current_task || a.next_action || "—",
    mission: a.mission_id || a.current_mission_id || null,
    evidence: a.evidence || a.evidence_ids || [],
    dependencies: a.dependencies || [],
    latest_output: a.latest_output || a.output || null,
  }));

  const missionCards = (missions || []).map((m) => ({
    id: m.id || m.mission_id,
    name: m.name || m.title || "Mission",
    status: m.status || m.state || "unknown",
    stage: m.stage || m.phase || m.lifecycle_state || m.status,
    owner: m.owner || m.owner_id || null,
  }));

  const evidenceEvents = (evidence || []).map((e, i) => ({
    id: e.id || e.evidence_id || `ev-${i}`,
    timestamp: e.created_at || e.timestamp || e.ts || null,
    type: e.kind || e.type || e.title || "event",
    actor: e.actor || e.created_by || e.source || null,
    status: e.status || e.result || null,
    reason: e.reason || e.detail || null,
    related_ids: e.related_ids || e.links || [],
    evidence_ref: e.id || e.evidence_id || null,
  }));

  // Causal chain skeleton — only mark present steps when evidence exists
  const chainTypes = [
    "research",
    "signal",
    "portfolio_construction",
    "proposal",
    "risk",
    "trading_guardian",
    "approval",
    "paper_order",
    "fill",
    "ledger",
    "reconciliation",
  ];
  const causalChain = chainTypes.map((type) => {
    const hit = evidenceEvents.find((e) => String(e.type).toLowerCase().includes(type.replace("_", "")));
    if (type === "proposal" && proposal.portfolio_proposal) {
      return {
        type,
        status: proposal.portfolio_proposal.status,
        id: proposal.portfolio_proposal.id,
        provenance: PROD_PROVENANCE.LIVE,
      };
    }
    if (type === "risk" && risk.provenance === PROD_PROVENANCE.LIVE) {
      return { type, status: risk.risk_status, provenance: PROD_PROVENANCE.LIVE };
    }
    if (type === "ledger" && portfolio.provenance === PROD_PROVENANCE.LIVE) {
      return { type, status: portfolio.portfolio_status, provenance: PROD_PROVENANCE.LIVE };
    }
    if (type === "reconciliation" && portfolio.reconciliation) {
      return {
        type,
        status: portfolio.reconciliation.portfolio_status || (portfolio.reconciliation.ok ? "HEALTHY" : "REQUIRED"),
        provenance: PROD_PROVENANCE.DERIVED,
      };
    }
    if (hit) {
      return { type, status: hit.status, id: hit.id, provenance: PROD_PROVENANCE.LIVE };
    }
    return { type, status: "UNAVAILABLE", provenance: PROD_PROVENANCE.UNAVAILABLE };
  });

  return {
    global_provenance: PROD_PROVENANCE.LIVE,
    banner:
      banner ||
      "PRODUCTION Hybrid Command · PAPER only · LIVE/UNAVAILABLE provenance · no DEMO defaults",
    mode_labels: MODES,
    portfolio,
    risk,
    proposal,
    performance,
    attention,
    system,
    agents: { provenance: agentNodes.length ? PROD_PROVENANCE.LIVE : PROD_PROVENANCE.UNAVAILABLE, nodes: agentNodes },
    missions: {
      provenance: missionCards.length ? PROD_PROVENANCE.LIVE : PROD_PROVENANCE.UNAVAILABLE,
      items: missionCards,
    },
    approvals: {
      provenance: approvals?.length ? PROD_PROVENANCE.LIVE : PROD_PROVENANCE.UNAVAILABLE,
      items: approvals || [],
    },
    evidence: {
      provenance: evidenceEvents.length ? PROD_PROVENANCE.LIVE : PROD_PROVENANCE.UNAVAILABLE,
      events: evidenceEvents,
      causal_chain: causalChain,
    },
    saathi: {
      voice_session_state: voiceState || "READY",
      transcript: voiceTranscript || "",
      reply: voiceReply || "",
      focus: focusEntity || null,
      authority: "VoiceSession consumer — no second mic owner",
    },
    meta: {
      inventsMetrics: false,
      liveTrading: false,
      authorizesExecution: false,
      authorizesApproval: false,
      frontendRiskAuthority: false,
      frontendLedgerAuthority: false,
      frontendConstructionAuthority: false,
    },
  };
}

/**
 * Extend mapUiIntent with proposal-aware navigation for production.
 */
export function mapProductionUiIntent(text) {
  const t = String(text || "").toLowerCase().trim();
  if (!t) return { type: "noop" };
  if (/\bstop\b/.test(t)) {
    return { type: "stop", mode: null, focus: "saathi", voice: "INTERRUPTING", reply: "Stopped." };
  }
  if (/proposal|rebalance|what.*(propos|suggest)|why.*(block|propos)/.test(t)) {
    return {
      type: "nav",
      mode: "investments",
      focus: "proposal",
      voice: "SPEAKING",
      reply: "Opening the portfolio proposal. Deterministic reason codes first; I cannot approve or execute.",
    };
  }
  if (/evidence|timeline|what happened/.test(t)) {
    return { type: "nav", mode: "evidence", focus: "evidence", voice: "SPEAKING", reply: "Opening evidence." };
  }
  if (/mission|agent/.test(t)) {
    return { type: "nav", mode: "agents", focus: "agents", voice: "SPEAKING", reply: "Showing agents and missions." };
  }
  if (/approval|needs me|what needs/.test(t)) {
    return {
      type: "nav",
      mode: "command",
      focus: "attention",
      voice: "SPEAKING",
      reply: "Focusing on items that need your attention.",
    };
  }
  if (/invest|portfolio|position|nav|cash|stress|risk/.test(t)) {
    return {
      type: "nav",
      mode: "investments",
      focus: /risk|stress|drawdown/.test(t) ? "risk" : "portfolio",
      voice: "SPEAKING",
      reply: "Opening Investments · PAPER. Values follow ledger and risk contracts.",
    };
  }
  if (/command|go back|home/.test(t)) {
    return { type: "nav", mode: "command", focus: "saathi", voice: "READY", reply: "Back to Command." };
  }
  return {
    type: "chat",
    mode: null,
    focus: "saathi",
    voice: "SPEAKING",
    reply: "I can open portfolio, risk, proposal, agents, approvals, or evidence. I cannot authorize trades.",
  };
}

// Keep design-lab PROVENANCE for fixture tests only
export { PROVENANCE };
