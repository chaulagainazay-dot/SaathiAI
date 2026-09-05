import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  PROVENANCE,
  VOICE_SESSION_STATES,
  AGENT_NODE_STATES,
  buildDemoCommandModel,
  mapUiIntent,
  yetiFromSystem,
} from "./contracts.js";
import { formatFraction, formatMoney, loadCommandReadModel } from "./read-adapter.js";

describe("ui-next-2.1 contracts", () => {
  it("tags global provenance DEMO and ledger authority name", () => {
    const m = buildDemoCommandModel("healthy");
    assert.equal(m.global_provenance, PROVENANCE.DEMO);
    assert.equal(m.portfolio.authority, "PortfolioLedgerService");
    assert.equal(m.risk.authority, "PortfolioRiskEngine");
    assert.equal(m.risk.label, "PAPER RISK");
    assert.equal(m.portfolio.live_execution, "UNAVAILABLE");
  });

  it("matches T-NEXT ledger field keys", () => {
    const p = buildDemoCommandModel().portfolio;
    for (const k of [
      "paper_nav",
      "cash",
      "realized_pnl",
      "unrealized_pnl",
      "gross_exposure",
      "net_exposure",
      "positions",
      "portfolio_status",
    ]) {
      assert.ok(k in p, k);
    }
    const pos = p.positions[0];
    for (const k of ["security_id", "symbol", "quantity", "cost_basis", "market_value", "weight"]) {
      assert.ok(k in pos, k);
    }
  });

  it("matches T-NEXT risk field keys and budget bars", () => {
    const r = buildDemoCommandModel("risk_warning").risk;
    for (const k of [
      "risk_status",
      "drawdown",
      "daily_pnl",
      "weekly_pnl",
      "largest_position",
      "risk_budget_consumed",
      "stress",
      "reason_codes",
    ]) {
      assert.ok(k in r, k);
    }
    const bar = r.risk_budget_consumed[0];
    assert.ok("soft_threshold" in bar && "hard_threshold" in bar && "status" in bar);
    assert.equal(r.risk_status, "WARNING");
  });

  it("surfaces reconciliation required prominently in model", () => {
    const m = buildDemoCommandModel("recon_required");
    assert.equal(m.portfolio.portfolio_status, "RECONCILIATION_REQUIRED");
    assert.ok(m.attention.items.some((i) => i.kind === "reconciliation_required"));
    assert.equal(m.risk.risk_status, "RECONCILIATION_REQUIRED");
  });

  it("includes CLOSED in voice vocabulary", () => {
    assert.ok(VOICE_SESSION_STATES.includes("CLOSED"));
    assert.ok(VOICE_SESSION_STATES.includes("LISTENING"));
  });

  it("agent states cover required set", () => {
    for (const s of ["IDLE", "ACTIVE", "WAITING", "BLOCKED", "COMPLETE", "FAILED", "VETOED", "APPROVAL_REQUIRED"]) {
      assert.ok(AGENT_NODE_STATES.includes(s));
    }
  });

  it("maps final-transcript UI intents without financial authorization", () => {
    assert.equal(mapUiIntent("show portfolio risk").mode, "investments");
    assert.equal(mapUiIntent("Stop").type, "stop");
    assert.equal(mapUiIntent("what needs my approval").focus, "attention");
    assert.match(mapUiIntent("buy 100 shares").reply, /cannot authorize/i);
  });

  it("yeti presentation maps from system without authority", () => {
    assert.equal(yetiFromSystem({ voice: "LISTENING", attention: { items: [] }, risk: {} }), "listening");
    assert.equal(
      yetiFromSystem({
        voice: "READY",
        attention: { items: [{ kind: "approval_required" }] },
        risk: { risk_status: "HEALTHY" },
      }),
      "approval_waiting",
    );
  });

  it("format helpers do not invent risk math", () => {
    assert.equal(formatFraction("0.12"), "12.0%");
    assert.ok(formatMoney("1248500.00").includes("1"));
  });

  it("loadCommandReadModel returns demo when live unavailable", async () => {
    const m = await loadCommandReadModel({ scenario: "healthy", preferLive: true });
    assert.equal(m.global_provenance, "DEMO");
  });
});
