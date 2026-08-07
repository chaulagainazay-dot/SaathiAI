import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  normalizeMissionCard,
  composeInvestmentSnapshot,
  composeEvidenceTimeline,
  composeSystemHealth,
  composeCommandCenterViewModel,
} from "./command-composition.js";

describe("command-composition", () => {
  it("mission cards use stage not fake progress percent", () => {
    const m = normalizeMissionCard({
      id: "m1",
      name: "Alpha",
      status: "active",
      stage: "research",
      approval_required: true,
    });
    assert.equal(m.progressKnown, false);
    assert.equal(m.progressLabel, "research");
    assert.equal(m.approvalRequired, true);
    assert.ok(!String(m.progressLabel).includes("%"));
  });

  it("investment marks missing metrics NOT AVAILABLE and live unavailable", () => {
    const snap = composeInvestmentSnapshot({
      auth: true,
      ready: true,
      summary: { accounts: 2, active: 1, cash: 100, equity: 150, blockingBreakers: 0, unackAlerts: 0, critDrift: 0 },
    });
    assert.equal(snap.mode, "PAPER");
    assert.equal(snap.liveExecution, "UNAVAILABLE");
    assert.equal(snap.fields.paperNav.available, true);
    assert.equal(snap.fields.pnl.available, false);
    assert.equal(snap.fields.pnl.label, "NOT AVAILABLE");
    assert.equal(snap.fields.drawdown.available, false);
  });

  it("investment reads canonical fund ledger fields when provided", () => {
    const snap = composeInvestmentSnapshot({
      auth: true,
      ready: true,
      summary: {
        source: "canonical_fund_ledger",
        fund_id: "fund_demo",
        paper_nav: "100000.00",
        cash: "90000.00",
        pnl: "123.45",
        gross_exposure: "10000.00",
        net_exposure: "10000.00",
        positions: [{ symbol: "AAA", quantity: "10" }],
        blockingBreakers: 0,
        unackAlerts: 0,
        critDrift: 0,
      },
    });
    assert.equal(snap.mode, "PAPER");
    assert.equal(snap.liveExecution, "UNAVAILABLE");
    assert.equal(snap.fields.paperNav.available, true);
    assert.equal(snap.fields.paperNav.value, 100000);
    assert.equal(snap.fields.pnl.available, true);
    assert.equal(snap.fields.grossExposure.available, true);
    assert.equal(snap.fields.netExposure.available, true);
    assert.equal(snap.positions.length, 1);
    assert.ok(String(snap.note).includes("canonical fund ledger"));
  });

  it("investment without session does not invent zeros", () => {
    const snap = composeInvestmentSnapshot({ auth: false });
    assert.equal(snap.fields.paperNav.available, false);
    assert.equal(snap.fields.cash.available, false);
  });

  it("timeline never invents timestamps or actors", () => {
    const tl = composeEvidenceTimeline({
      evidence: [{ id: "e1", kind: "research_completed" }],
      missions: [{ id: "m1", status: "active", name: "M" }],
    });
    assert.ok(tl.events.length >= 1);
    const bare = tl.events.find((e) => e.evidenceRef === "e1");
    assert.equal(bare.timestamp, null);
    assert.ok(tl.incompleteProvenance >= 1);
  });

  it("system health uses small vocabulary", () => {
    const h = composeSystemHealth({
      infra: { status: "degraded", database: { status: "ok" } },
      overview: { platform_health: { status: "ok" } },
      infraStatus: "connected",
    });
    assert.equal(h.overall, "DEGRADED");
    assert.ok(h.subsystems.some((s) => s.id === "database"));
  });

  it("full view model sets liveTrading false and composes attention", () => {
    const vm = composeCommandCenterViewModel({
      attention: {
        items: [
          {
            id: "a1",
            category: "approval_required",
            severity: "high",
            title: "Approve tool",
            authority: "approval-required",
            actionable: true,
            actionRoute: "/approvals",
            source: "test",
          },
        ],
        partial: false,
        sources: [],
      },
      missions: [{ id: "m1", status: "blocked", name: "B", blocker: "approval" }],
      tradingAuth: true,
      tradingReady: true,
      tradingSummary: { accounts: 1, equity: 10, cash: 5, blockingBreakers: 0, unackAlerts: 0, critDrift: 0 },
      apiBase: "http://localhost:8765",
    });
    assert.equal(vm.meta.liveTrading, false);
    assert.equal(vm.meta.inventsMetrics, false);
    assert.equal(vm.attention.items.length, 1);
    assert.equal(vm.activity.blockedMissions.length, 1);
    assert.equal(vm.investment.liveExecution, "UNAVAILABLE");
    assert.ok(vm.authority.chips.find((c) => c.id === "live_orders").state === "DISABLED");
  });
});
