/**
 * UI-NEXT-2 design-lab DEMO contracts.
 * Field names mirror T-NEXT-1 / 1.1 / 2 — values are MOCK only.
 */

export const DEMO_BANNER = "DEMO / MOCK — not live portfolio or risk authority";

/** @typedef {'IDLE'|'READY'|'LISTENING'|'TRANSCRIBING'|'THINKING'|'SPEAKING'|'INTERRUPTING'|'DEGRADED'|'ERROR'} VoiceState */

export const VOICE_STATES = [
  "IDLE",
  "READY",
  "LISTENING",
  "TRANSCRIBING",
  "THINKING",
  "SPEAKING",
  "INTERRUPTING",
  "DEGRADED",
  "ERROR",
];

export const MODES = [
  { id: "command", label: "Command" },
  { id: "agents", label: "Agents" },
  { id: "investments", label: "Investments" },
  { id: "evidence", label: "Evidence" },
];

export const CONCEPTS = [
  { id: "A", label: "A · Institutional", blurb: "Tables, risk, precision" },
  { id: "B", label: "B · AI Spatial", blurb: "Saathi + topology focus" },
  { id: "C", label: "C · Hybrid", blurb: "Selected architecture" },
];

/** Representative T-NEXT ledger + risk snapshot (DEMO). */
export const demoPortfolio = {
  mode: "PAPER",
  live_execution: "UNAVAILABLE",
  source: "DEMO_MOCK",
  books_authority: "canonical_fund_ledger",
  paper_nav: "1,248,500.00",
  cash: "312,400.00",
  realized_pnl: "+18,220.00",
  unrealized_pnl: "+6,140.00",
  daily_pnl: "+2,410.00",
  weekly_pnl: "+9,880.00",
  drawdown: "3.2%",
  gross_exposure: "936,100.00",
  net_exposure: "936,100.00",
  cash_pct: "25%",
  largest_position: "12%",
  portfolio_status: "HEALTHY",
  reconciliation: "HEALTHY",
  positions: [
    { symbol: "AAA", quantity: "1,200", weight: "12%", market_value: "149,800" },
    { symbol: "BBB", quantity: "800", weight: "9%", market_value: "112,400" },
    { symbol: "CCC", quantity: "2,000", weight: "8%", market_value: "99,900" },
  ],
};

export const demoRisk = {
  label: "PAPER RISK",
  mode: "PAPER",
  live_execution: "UNAVAILABLE",
  risk_status: "WARNING",
  budget_version: "paper-risk-budget/v1",
  drawdown: "3.2%",
  max_drawdown: "15%",
  gross_exposure_pct: "75%",
  cash_pct: "25%",
  largest_position: "12%",
  stress_loss: "−62,400 (mkt −5% DEMO)",
  reason_codes: ["SOFT: top3 approaching limit"],
  risk_budget_consumed: [
    { name: "position_concentration", used: "12%", limit: "15%", status: "OK" },
    { name: "gross_exposure", used: "75%", limit: "100%", status: "OK" },
    { name: "drawdown", used: "3.2%", limit: "15%", status: "OK" },
    { name: "cash_buffer", used: "25% cash", limit: "≥5%", status: "OK" },
  ],
};

export const demoAgents = [
  { id: "cio", label: "CIO / Manager", status: "ACTIVE", owner: "system" },
  { id: "research", label: "Research", status: "WAITING", owner: "agent" },
  { id: "quant", label: "Quant", status: "ACTIVE", owner: "agent" },
  { id: "macro", label: "Macro", status: "IDLE", owner: "agent" },
  { id: "proposal", label: "Portfolio Proposal", status: "APPROVAL_REQUIRED", owner: "system" },
  { id: "risk", label: "Risk Engine", status: "COMPLETE", owner: "risk" },
  { id: "tg", label: "Trading Guardian", status: "COMPLETE", owner: "tg" },
  { id: "approval", label: "Approval", status: "BLOCKED", owner: "human" },
];

export const demoAttention = [
  { id: "a1", severity: "high", title: "Approve rebalance proposal", kind: "approval" },
  { id: "a2", severity: "medium", title: "Risk soft warning: top3 concentration", kind: "risk" },
  { id: "a3", severity: "low", title: "Research mission waiting on data", kind: "mission" },
];

export const demoEvidence = [
  { t: "09:12", stage: "research", detail: "Macro brief complete", id: "ev_demo_1" },
  { t: "09:18", stage: "proposal", detail: "Rebalance DRAFT", id: "ev_demo_2" },
  { t: "09:19", stage: "risk", detail: "evaluate_proposed_trade → WARN", id: "ev_demo_3" },
  { t: "09:19", stage: "tg", detail: "Guardian ALLOW (paper)", id: "ev_demo_4" },
  { t: "09:20", stage: "approval", detail: "Awaiting operator", id: "ev_demo_5" },
  { t: "—", stage: "order", detail: "Not submitted", id: "ev_demo_6" },
  { t: "—", stage: "fill", detail: "—", id: "ev_demo_7" },
  { t: "—", stage: "ledger", detail: "No new post", id: "ev_demo_8" },
  { t: "09:00", stage: "recon", detail: "HEALTHY", id: "ev_demo_9" },
];

export const demoSystem = {
  tg: "SAFE",
  gateway: "READY",
  models: "LOCAL/BOUND",
  health: "HEALTHY",
  paper: "PAPER",
  live: "UNAVAILABLE",
};

/**
 * Simple voice navigation demo mapping (UI only).
 * @param {string} text
 */
export function mapVoiceCommand(text) {
  const t = (text || "").toLowerCase();
  if (t.includes("stop")) return { mode: null, voice: "INTERRUPTING", focus: "composer", reply: "Stopped." };
  if (t.includes("evidence")) return { mode: "evidence", voice: "SPEAKING", focus: "evidence", reply: "Opening evidence timeline." };
  if (t.includes("mission") || t.includes("agent")) return { mode: "agents", voice: "SPEAKING", focus: "agents", reply: "Showing active missions." };
  if (t.includes("approval")) return { mode: "command", voice: "SPEAKING", focus: "attention", reply: "You have items needing approval." };
  if (t.includes("stress") || t.includes("risk") || t.includes("portfolio"))
    return { mode: "investments", voice: "SPEAKING", focus: "risk", reply: "Portfolio risk surface focused. DEMO metrics only." };
  if (t.includes("command") || t.includes("go back")) return { mode: "command", voice: "READY", focus: "saathi", reply: "Back to Command." };
  return { mode: "command", voice: "THINKING", focus: "saathi", reply: "I can show risk, missions, approvals, or evidence. (DEMO)" };
}
