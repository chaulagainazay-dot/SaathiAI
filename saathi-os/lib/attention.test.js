import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  normalizeControlItem,
  normalizeMissionAttention,
  aggregateAttention,
  summarizeAttention,
  mapSeverityToStatus,
} from "./attention.js";

describe("attention normalization", () => {
  it("maps control items with stable ids", () => {
    const n = normalizeControlItem({ severity: "critical", kind: "execution_failed", message: "3 failed", link: "/control/execution" });
    assert.equal(n.category, "failed_run");
    assert.equal(n.severity, "critical");
    assert.equal(n.href, "/monitoring");
    assert.ok(n.id.includes("ctrl"));
  });

  it("maps approval kinds to approval_required", () => {
    const n = normalizeControlItem({ severity: "medium", kind: "browser_approval", message: "1 waiting", link: "/control" });
    assert.equal(n.category, "approval_required");
    assert.equal(n.actionRoute, "/approvals");
  });

  it("only emits mission attention for blocked/failed statuses", () => {
    assert.equal(normalizeMissionAttention({ id: "1", name: "A", status: "active" }), null);
    const b = normalizeMissionAttention({ id: "2", name: "B", status: "blocked" });
    assert.equal(b.category, "blocked_mission");
  });
});

describe("aggregateAttention partial failure", () => {
  it("keeps successful sources when others fail", () => {
    const r = aggregateAttention({
      controlItems: [{ severity: "high", kind: "registry_health", message: "RED" }],
      controlStatus: "connected",
      missions: [],
      missionsStatus: "unavailable",
      missionsError: "network",
      approvals: [{ id: "a1", title: "Send email" }],
      approvalsStatus: "connected",
      infraStatus: "unavailable",
      evidenceStatus: "unavailable",
    });
    assert.equal(r.partial, true);
    assert.ok(r.items.some((i) => i.category === "degraded_system" || i.rawKind === "registry_health"));
    assert.ok(r.items.some((i) => i.category === "approval_required"));
    assert.ok(r.sources.find((s) => s.id === "missions.list").status === "unavailable");
  });

  it("summary never invents zero for unavailable metrics", () => {
    const r = aggregateAttention({
      controlStatus: "unavailable",
      missionsStatus: "unavailable",
      approvalsStatus: "unavailable",
      infraStatus: "unavailable",
      evidenceStatus: "unavailable",
    });
    assert.equal(r.summary.pendingApprovals.status, "unavailable");
    assert.equal(r.summary.pendingApprovals.value, null);
  });

  it("empty connected list can be zero", () => {
    const r = aggregateAttention({
      controlItems: [],
      controlStatus: "connected",
      approvals: [],
      approvalsStatus: "connected",
      missions: [],
      missionsStatus: "connected",
      infraStatus: "connected",
      infra: { status: "ok" },
      evidence: [],
      evidenceStatus: "connected",
    });
    assert.equal(r.summary.pendingApprovals.status, "ok");
    assert.equal(r.summary.pendingApprovals.value, 0);
  });
});

describe("mapSeverityToStatus", () => {
  it("maps critical to danger", () => {
    assert.equal(mapSeverityToStatus("critical"), "danger");
  });
});

describe("summarizeAttention export", () => {
  it("exists", () => {
    assert.equal(typeof summarizeAttention, "function");
  });
});
