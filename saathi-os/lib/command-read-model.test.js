import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  composeHybridCommandModel,
  composePortfolioPanel,
  composeRiskPanel,
  composeProposalPanel,
  composePerformancePanel,
  composeAttention,
  composeSystemStrip,
  reasonCodeLabel,
  mapProductionUiIntent,
  formatFraction,
  formatMoney,
} from "./command-read-model.js";

describe("command-read-model production", () => {
  it("formats fractions and money without inventing", () => {
    assert.equal(formatFraction("0.15"), "15.0%");
    assert.equal(formatMoney("1000.5"), "1,000.50");
    assert.equal(formatMoney(null), "—");
  });

  it("maps reason codes deterministically", () => {
    assert.match(reasonCodeLabel("TARGET_WEIGHT_RESTORE"), /Restore target/i);
    assert.ok(reasonCodeLabel("UNKNOWN_CODE"));
  });

  it("portfolio panel never fabricates NAV", () => {
    const empty = composePortfolioPanel(null);
    assert.equal(empty.provenance, "UNAVAILABLE");
    assert.equal(empty.paper_nav, undefined);
    const live = composePortfolioPanel({
      source: "canonical_fund_ledger",
      paper_nav: "100000",
      cash: "50000",
      positions: [],
      portfolio_status: "HEALTHY",
    });
    assert.equal(live.provenance, "LIVE");
    assert.equal(live.paper_nav, "100000");
    assert.equal(live.live_execution, "UNAVAILABLE");
  });

  it("risk panel pass-through", () => {
    const r = composeRiskPanel({
      source: "portfolio_risk_engine",
      risk_status: "WARNING",
      result: "WARN",
      drawdown: "0.03",
      reason_codes: ["SOFT_WARNING_NEAR_TOP3"],
      risk_budget_consumed: [{ name: "drawdown", used: "0.03", limit: "0.15", status: "OK" }],
    });
    assert.equal(r.provenance, "LIVE");
    assert.equal(r.risk_status, "WARNING");
    assert.equal(r.live_execution, "UNAVAILABLE");
  });

  it("proposal panel enforces zero execution", () => {
    const p = composeProposalPanel({
      active: {
        id: "pprop_1",
        status: "READY_FOR_APPROVAL",
        reason_codes: ["TARGET_WEIGHT_RESTORE"],
        trades: [],
      },
    });
    assert.equal(p.portfolio_proposal.authorizes_execution, false);
    assert.equal(p.portfolio_proposal.mode, "PAPER");
    assert.equal(p.portfolio_proposal.reason_labels[0].code, "TARGET_WEIGHT_RESTORE");
  });

  it("attention ranks recon and proposal", () => {
    const att = composeAttention({
      portfolio: { portfolio_status: "RECONCILIATION_REQUIRED" },
      risk: { risk_status: "WARNING", result: "WARN", reason_codes: ["X"] },
      proposal: { portfolio_proposal: { id: "p1", status: "READY_FOR_APPROVAL" } },
      approvals: [{ id: "a1", status: "PENDING", requested_action: "paper order" }],
    });
    assert.ok(att.items.some((i) => i.kind === "reconciliation_required"));
    assert.ok(att.items.some((i) => i.kind === "portfolio_proposal_ready"));
    assert.ok(att.items[0].urgency >= att.items[att.items.length - 1].urgency);
  });

  it("full hybrid model meta authority flags", () => {
    const m = composeHybridCommandModel({
      portfolioSnap: { source: "canonical_fund_ledger", paper_nav: "1", cash: "1", positions: [] },
      riskSnap: { source: "portfolio_risk_engine", risk_status: "HEALTHY" },
    });
    assert.equal(m.meta.inventsMetrics, false);
    assert.equal(m.meta.liveTrading, false);
    assert.equal(m.meta.authorizesExecution, false);
    assert.equal(m.meta.frontendRiskAuthority, false);
    assert.ok(m.evidence.causal_chain.some((c) => c.type === "ledger"));
  });

  it("keeps infrastructure model status scalar for React rendering", () => {
    const strip = composeSystemStrip({
      infra: { models: [{ id: "local", available: true, light: "🟢" }] },
    });
    assert.equal(strip.models.value, "1 bound");
    assert.equal(typeof strip.models.value, "string");
  });

  it("voice intents never authorize finance", () => {
    const i = mapProductionUiIntent("show the proposal");
    assert.equal(i.focus, "proposal");
    assert.match(i.reply, /cannot approve|cannot authorize/i);
    const s = mapProductionUiIntent("stop");
    assert.equal(s.type, "stop");
  });

  it("performance panel pass-through no invent", () => {
    const empty = composePerformancePanel(null);
    assert.equal(empty.provenance, "UNAVAILABLE");
    const live = composePerformancePanel({
      paper_performance: {
        nav: "100000",
        return_pct: "0.01",
        source: "portfolio_performance_engine",
        mode: "PAPER",
        live_execution: "UNAVAILABLE",
        provenance: "DERIVED",
      },
    });
    assert.equal(live.paper_performance.live_execution, "UNAVAILABLE");
    assert.equal(live.paper_performance.nav, "100000");
  });

  it("loading shows LOADING not zero", () => {
    const p = composePortfolioPanel(null, { loading: true });
    assert.equal(p.provenance, "LOADING");
    assert.equal(p.paper_nav, null);
  });
});
