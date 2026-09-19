import test from "node:test";
import assert from "node:assert/strict";
import {
  STATUS_META, statusMeta, statusLabel, motionFor, agentAriaLabel, indexCompany, officeSummary,
  headerMetrics, activeRoles, flattenTree, activePath, treeRoleIds, formatAgo, isRelevantEvent,
  systemTone, refreshInterval, activityText, operationsLine, formatIn,
} from "./organization.js";

const BACKEND_STATUSES = ["OFFLINE", "UNAVAILABLE", "UNKNOWN", "IDLE", "ASSIGNED", "RESEARCHING",
  "ANALYZING", "WORKING", "WAITING", "REVIEWING", "CHALLENGING", "AWAITING_EVIDENCE",
  "AWAITING_APPROVAL", "BLOCKED", "COMPLETE", "ERROR"];

test("every backend status has a label and a non-colour glyph", () => {
  for (const s of BACKEND_STATUSES) {
    assert.ok(STATUS_META[s], s);
    assert.ok(STATUS_META[s].glyph && STATUS_META[s].glyph.length <= 2, s);
  }
  const glyphs = BACKEND_STATUSES.map((s) => STATUS_META[s].glyph);
  assert.equal(new Set(glyphs).size, glyphs.length, "glyphs distinguish states without colour");
});

test("unknown status never renders as idle or ok", () => {
  assert.equal(statusMeta("WHATEVER").label, "Unknown");
  assert.equal(statusMeta(undefined).label, "Unknown");
  assert.notEqual(systemTone("UNKNOWN"), "success");
});

test("not-connected availability is surfaced", () => {
  assert.equal(statusLabel({ status: "UNAVAILABLE", availability: "NOT_CONNECTED" }), "Not connected");
  assert.equal(statusLabel({ status: "UNAVAILABLE", availability: "UNAVAILABLE" }), "Unavailable");
});

test("reduced motion disables all worker animation", () => {
  for (const s of BACKEND_STATUSES) assert.equal(motionFor(s, true), "none");
  assert.equal(motionFor("IDLE", false), "none");
  assert.equal(motionFor("RESEARCHING", false), "scan");
});

test("aria label carries status and reason", () => {
  const l = agentAriaLabel({ name: "Email Agent", title: "Email", status: "UNAVAILABLE",
    availability: "NOT_CONNECTED", reason: "Gmail: not connected" });
  assert.match(l, /Not connected/);
  assert.match(l, /Gmail/);
});

const SNAP = {
  roles: [
    { role_id: "a", name: "A", status: "WORKING" },
    { role_id: "b", name: "B", status: "IDLE" },
    { role_id: "c", name: "C", status: "ERROR", reason: "boom" },
  ],
  offices: [{ office_id: "o1", members: ["a", "b"] }, { office_id: "o2", members: ["c", "missing"] }],
  floors: [{ floor_id: "f1", offices: ["o1", "o2"] }],
  metrics: { total: 3, active: 1, idle: 1, in_review: 0, blocked: 0, errors: 1 },
};

test("indexCompany preserves order and drops unknown members", () => {
  const idx = indexCompany(SNAP);
  assert.deepEqual(idx.floors[0].offices.map((o) => o.office_id), ["o1", "o2"]);
  assert.deepEqual(idx.offices.o2.roles.map((r) => r.role_id), ["c"]);
  assert.equal(indexCompany(null), null);
});

test("office summary counts busy and attention", () => {
  const idx = indexCompany(SNAP);
  assert.equal(officeSummary(idx.offices.o1).busy, 1);
  assert.equal(officeSummary(idx.offices.o2).attention, 1);
});

test("header metrics come from backend, never invented", () => {
  assert.equal(headerMetrics(SNAP), SNAP.metrics);
  const m = headerMetrics({ roles: SNAP.roles });
  assert.equal(m.total, 3);
  assert.equal(m.active, 1);
  assert.equal(activeRoles(SNAP).length, 1);
});

const TREE = {
  role_id: "owner", status: "WAITING", children: [{
    role_id: "exec.saathi", status: "WAITING", children: [
      { role_id: "inv.fund_manager", status: "WAITING", children: [
        { role_id: "crypto.technical", status: "ANALYZING", children: [] }] },
      { role_id: "ic.chair", status: "ASSIGNED", children: [] }],
  }],
};

test("delegation tree flattens with connectors", () => {
  const flat = flattenTree(TREE);
  assert.deepEqual(flat.map((n) => n.role_id),
    ["owner", "exec.saathi", "inv.fund_manager", "crypto.technical", "ic.chair"]);
  assert.equal(flat[4].connector.trim().startsWith("└──"), true);
  assert.equal(flat[2].connector.includes("├──"), true);
});

test("active path follows the busiest leaf from the owner", () => {
  assert.deepEqual(activePath(TREE), ["owner", "exec.saathi", "inv.fund_manager", "crypto.technical"]);
  assert.deepEqual(activePath(null), []);
  assert.equal(treeRoleIds(TREE).size, 5);
});

test("event relevance and time formatting", () => {
  assert.ok(isRelevantEvent("org.agent.started"));
  assert.ok(isRelevantEvent("agentrun.run.state"));
  assert.ok(!isRelevantEvent("trade.fill"));
  assert.ok(!isRelevantEvent(undefined));
  assert.equal(formatAgo(100, 130), "30s ago");
  assert.equal(formatAgo(0, 130), "—");
});

test("refresh interval is lazy when idle and never polls hidden tabs", () => {
  assert.equal(refreshInterval({ visible: false, missionActive: true, liveConnected: false }), null);
  assert.equal(refreshInterval({ visible: true, missionActive: false, liveConnected: true }), 60000);
  assert.equal(refreshInterval({ visible: true, missionActive: true, liveConnected: false }), 2000);
});

test("duty activity and operations line are truthful", () => {
  assert.equal(activityText({ name: "duty.completed", role_name: "Risk", status: "AWAITING_EVIDENCE" }),
    "Risk — finished duty · awaiting data");
  assert.equal(operationsLine(null).state, "unknown");
  assert.equal(operationsLine({ running: false, owner_setting: "paused" }).state, "paused");
  const run = operationsLine({ running: true, duties_runnable: 97, duties_total: 103, completed_since_start: 4,
    current: { title: "Scan backend error log" } });
  assert.equal(run.state, "running");
  assert.match(run.text, /97 of 103/);
  assert.match(run.text, /Scan backend error log/);
  assert.equal(formatIn(130, 100), "in 30s");
});
