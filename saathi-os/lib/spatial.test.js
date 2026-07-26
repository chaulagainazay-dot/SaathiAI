import test from "node:test";
import assert from "node:assert/strict";
import {
  SIGNAL,
  CONNECTION,
  MODULES,
  coreSignal,
  coreMetrics,
  moduleState,
  ringLayout,
  curvePath,
  connectionSignal,
  round2,
  pct,
  pathD,
} from "./spatial.js";

test("module registry is stable, unique, and route-bound", () => {
  assert.equal(MODULES.length, 12);
  const ids = MODULES.map((m) => m.id);
  assert.equal(new Set(ids).size, ids.length, "ids unique");
  for (const m of MODULES) {
    assert.ok(m.route && m.route.startsWith("/"), `${m.id} has route`);
    assert.ok(m.label && m.icon && m.flow, `${m.id} complete`);
  }
});

test("coreSignal: gateway down dominates as danger", () => {
  const s = coreSignal({ health: { identity: "ACTIVE", runtime: { gateway: "DOWN" } } });
  assert.equal(s, SIGNAL.DANGER);
});

test("coreSignal: pending approvals/attention -> attention (amber)", () => {
  assert.equal(coreSignal({ metrics: { waiting_approvals: 3, active_executions: 1 } }), SIGNAL.ATTENTION);
  assert.equal(coreSignal({ diagnostics: { runtime: { attention_count: 2 } } }), SIGNAL.ATTENTION);
});

test("coreSignal: enforced gateway is healthy, NOT blocked", () => {
  const s = coreSignal({
    health: { identity: "ACTIVE", runtime: { gateway: "TOOL_GATEWAY_ENFORCED" } },
    metrics: { waiting_approvals: 0, executions_requiring_attention: 0, failed_executions: 0 },
  });
  assert.equal(s, SIGNAL.ACTIVE);
});

test("coreSignal: healthy identity with nothing pending -> active (cyan)", () => {
  const s = coreSignal({ health: { identity: "ACTIVE", runtime: { gateway: "ACTIVE" } }, metrics: { waiting_approvals: 0, executions_requiring_attention: 0, failed_executions: 0 } });
  assert.equal(s, SIGNAL.ACTIVE);
});

test("coreSignal: no data at all -> unknown, never invented", () => {
  assert.equal(coreSignal({}), SIGNAL.UNKNOWN);
});

test("coreSignal: idle when health present but not active and nothing pending", () => {
  const s = coreSignal({ health: { identity: "PROVISIONING", runtime: { gateway: "ACTIVE" } }, metrics: { waiting_approvals: 0, executions_requiring_attention: 0, active_executions: 0, failed_executions: 0 } });
  assert.equal(s, SIGNAL.IDLE);
});

test("coreMetrics: null when absent, number when present — no fabrication", () => {
  const m = coreMetrics({ metrics: { active_executions: 2, waiting_approvals: 1, executions_requiring_attention: 0, total_executions: 9, failed_executions: 0 } });
  assert.equal(m.runningExecutions, 2);
  assert.equal(m.pendingApprovals, 1);
  assert.equal(m.total, 9);
  const empty = coreMetrics({});
  assert.equal(empty.runningExecutions, null);
  assert.equal(empty.pendingApprovals, null);
});

test("moduleState approvals: pending -> attention with count", () => {
  const s = moduleState("approvals", { metrics: { waiting_approvals: 3 } });
  assert.equal(s.signal, SIGNAL.ATTENTION);
  assert.equal(s.count, 3);
  assert.match(s.detail, /3 pending/);
});

test("moduleState approvals: none -> idle", () => {
  const s = moduleState("approvals", { approvals: [] });
  assert.equal(s.signal, SIGNAL.IDLE);
  assert.equal(s.count, 0);
});

test("moduleState runtime: failed executions raise attention", () => {
  const s = moduleState("runtime", { metrics: { active_executions: 1, failed_executions: 2 } });
  assert.equal(s.signal, SIGNAL.ATTENTION);
});

test("moduleState bindings: unavailable when no data -> unknown, not zero", () => {
  const s = moduleState("bindings", {});
  assert.equal(s.signal, SIGNAL.UNKNOWN);
  assert.equal(s.count, null);
});

test("moduleState bindings: counts active", () => {
  const s = moduleState("bindings", { bindings: [{ state: "ACTIVE" }, { state: "SUSPENDED" }] });
  assert.equal(s.count, 2);
  assert.match(s.detail, /1\/2 active/);
});

test("ringLayout: deterministic, starts at top, correct count", () => {
  const pts = ringLayout(4, { cx: 0.5, cy: 0.5, rx: 0.4, ry: 0.4 });
  assert.equal(pts.length, 4);
  // First point at top: x≈0.5, y≈0.1
  assert.ok(Math.abs(pts[0].x - 0.5) < 1e-9);
  assert.ok(Math.abs(pts[0].y - 0.1) < 1e-9);
  // Deterministic: same inputs -> same outputs
  const again = ringLayout(4, { cx: 0.5, cy: 0.5, rx: 0.4, ry: 0.4 });
  assert.deepEqual(pts, again);
});

test("ringLayout: empty for non-positive count", () => {
  assert.deepEqual(ringLayout(0), []);
  assert.deepEqual(ringLayout(-3), []);
});

test("curvePath: returns from/control/to with a real bow offset", () => {
  const p = curvePath({ x: 0.5, y: 0.5 }, { x: 0.9, y: 0.5 }, 0.2);
  assert.ok(p.from && p.c1 && p.to);
  // horizontal edge -> control point offset vertically
  assert.notEqual(p.c1.y, 0.5);
});

test("connectionSignal: authority modules always route amber", () => {
  const mod = MODULES.find((m) => m.id === "approvals");
  assert.equal(connectionSignal(mod, { signal: SIGNAL.ACTIVE }), CONNECTION.AUTHORITY);
});

test("connectionSignal: danger state -> blocked regardless of module", () => {
  const mod = MODULES.find((m) => m.id === "runtime");
  assert.equal(connectionSignal(mod, { signal: SIGNAL.DANGER }), CONNECTION.BLOCKED);
});

test("round2/pct: emit hydration-stable values (no float tail, no trailing zeros)", () => {
  assert.equal(round2(28.499999999999982), 28.5);
  assert.equal(pct(0.28499999999999982), "28.5%");
  assert.equal(pct(0.15358983848622465), "15.36%");
  // no trailing zeros that a browser would strip
  assert.equal(pct(0.5), "50%");
});

test("pathD: rounded, deterministic SVG path", () => {
  const d = pathD(curvePath({ x: 0.5, y: 0.5 }, { x: 0.285, y: 0.1536 }, 0.16));
  assert.match(d, /^M 50 50 Q [\d.]+ [\d.]+ 28\.5 15\.36$/);
  // no long float tails
  assert.ok(!/\d{6,}/.test(d), "no 6+ digit runs");
});

test("connectionSignal: idle/unknown -> inactive", () => {
  const mod = MODULES.find((m) => m.id === "memory");
  assert.equal(connectionSignal(mod, { signal: SIGNAL.IDLE }), CONNECTION.INACTIVE);
  assert.equal(connectionSignal(mod, null), CONNECTION.INACTIVE);
});
