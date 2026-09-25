/**
 * CENTRAL-COMMAND-TRADING-OPS — the presentation layer must not become a
 * second health authority, and must not let a frozen panel read as a live one.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  TRUTH_STATE_FOR_HEALTH,
  deterministicSummary,
  subsystemLabel,
  toSystemHealth,
  tradingOpsView,
  truthStateForHealth,
} from "./trading-ops-view.js";

const snapshot = (over = {}) => ({
  overall_health: "HEALTHY",
  mode: "SHADOW",
  live_trading_authorized: false,
  reconciliation_state: "HEALTHY",
  recovery_state: "NOT_REQUIRED",
  kill_switch_state: { engaged: false },
  subsystems: [
    { subsystem: "MARKET_DATA", health: "HEALTHY", detail: "feed fresh", authority: "a" },
    { subsystem: "GUARDIAN", health: "HEALTHY", detail: "policy loaded", authority: "b" },
  ],
  incidents: [],
  operator_actions_required: [],
  ...over,
});

const payload = (over = {}, snapOver = {}) => ({
  freshness: "FRESH",
  reflects_current_state: true,
  collected_at: "2026-09-06T12:00:00Z",
  served_at: "2026-09-06T12:00:10Z",
  age_seconds: 10,
  max_age_seconds: 180,
  snapshot: snapshot(snapOver),
  ...over,
});

// ── stale must never look healthy ──────────────────────────────────────────
test("a stale snapshot never displays as healthy, whatever it contains", () => {
  const stale = tradingOpsView(payload({
    freshness: "STALE", reflects_current_state: false, age_seconds: 3600,
  }));
  assert.equal(stale.overall, "HEALTHY");        // the recorded value survives
  assert.equal(stale.displayState, "STALE");     // but is not what is shown
  assert.notEqual(stale.displayState, "HEALTHY");
  for (const s of stale.subsystems) assert.equal(s.state, "STALE");
});

test("a payload missing the freshness verdict is treated as not current", () => {
  // An older server that does not send the flag must not read as fresh.
  const v = tradingOpsView(payload({ reflects_current_state: undefined }));
  assert.equal(v.stale, true);
  assert.equal(v.displayState, "STALE");
});

test("a fresh snapshot displays its real health", () => {
  const v = tradingOpsView(payload());
  assert.equal(v.stale, false);
  assert.equal(v.displayState, "HEALTHY");
  assert.equal(v.subsystems[0].state, "HEALTHY");
});

test("no payload at all is UNKNOWN, never healthy", () => {
  for (const bad of [null, undefined, "", 0, "nope"]) {
    const v = tradingOpsView(bad);
    assert.equal(v.displayState, "UNKNOWN");
    assert.equal(v.available, false);
    assert.equal(v.liveTradingAuthorized, false);
  }
});

// ── the UI computes no health ──────────────────────────────────────────────
test("health classes are mapped, never derived", () => {
  assert.equal(truthStateForHealth("HEALTHY"), "HEALTHY");
  assert.equal(truthStateForHealth("WARNING"), "DEGRADED");
  assert.equal(truthStateForHealth("DEGRADED"), "DEGRADED");
  assert.equal(truthStateForHealth("CRITICAL"), "BLOCKED");
  assert.equal(truthStateForHealth("FAILED_SAFE"), "BLOCKED");
  // An unrecognised health is UNKNOWN — the UI does not guess in the optimistic
  // direction, or in any direction.
  assert.equal(truthStateForHealth("SOMETHING_NEW"), "UNKNOWN");
  assert.equal(truthStateForHealth(null), "UNKNOWN");
  assert.equal(truthStateForHealth(""), "UNKNOWN");
});

test("the overall state is read from the snapshot, not recomputed from rows", () => {
  // Rows say HEALTHY; the snapshot says CRITICAL. The snapshot wins — otherwise
  // the UI would be a second aggregator with its own precedence rules.
  const v = tradingOpsView(payload({}, { overall_health: "CRITICAL" }));
  assert.equal(v.displayState, "BLOCKED");
  assert.deepEqual(v.subsystems.map((s) => s.state), ["HEALTHY", "HEALTHY"]);
});

test("the primary incident is the backend's first, not a UI ranking", () => {
  const v = tradingOpsView(payload({}, {
    incidents: [
      { incident_id: "i1", subsystem: "PROVIDER", severity: "MEDIUM",
        summary: "provider unavailable", authority: "x", state: "OPEN",
        symptoms: [{ subsystem: "MARKET_DATA", health: "DEGRADED" },
                   { subsystem: "STRATEGY", health: "DEGRADED" }] },
    ],
  }));
  assert.equal(v.primaryIncident.subsystem, "PROVIDER");
  assert.deepEqual(v.primaryIncident.symptoms.map((s) => s.id),
                   ["MARKET_DATA", "STRATEGY"]);
  // The strategy is a symptom, never presented as the cause.
  assert.notEqual(v.primaryIncident.subsystem, "STRATEGY");
});

// ── readiness vs health ────────────────────────────────────────────────────
test("a healthy shadow stack never implies live trading", () => {
  const v = tradingOpsView(payload());
  assert.equal(v.mode, "SHADOW");
  assert.equal(v.liveTradingAuthorized, false);
  assert.equal(v.displayState, "HEALTHY");
});

test("live authorisation is only true when the snapshot says so explicitly", () => {
  for (const val of [undefined, null, "true", 1, "yes"]) {
    const v = tradingOpsView(payload({}, { live_trading_authorized: val }));
    assert.equal(v.liveTradingAuthorized, false);
  }
});

// ── operator actions ───────────────────────────────────────────────────────
test("actions carry the authority that owns them", () => {
  const v = tradingOpsView(payload({}, {
    operator_actions_required: [{
      action: "REVIEW_RECONCILIATION", subsystem: "RECONCILIATION",
      authority: "saathi.platform.tg.reconciliation_v2",
      detail: "reconciliation required", automatable: false,
    }],
  }));
  assert.equal(v.actions[0].authority, "saathi.platform.tg.reconciliation_v2");
  assert.equal(v.actions[0].automatable, false);
});

test("no execution action can be rendered from a snapshot", () => {
  const v = tradingOpsView(payload({}, {
    operator_actions_required: [
      { action: "ACKNOWLEDGE_INCIDENT", subsystem: "MARKET_DATA", authority: "a" },
    ],
  }));
  const forbidden = ["BUY", "SELL", "EXECUTE", "RETRY_ORDER", "ENABLE_LIVE", "LIVE_TRADE"];
  for (const a of v.actions) assert.ok(!forbidden.includes(a.action), a.action);
});

// ── deterministic copy survives model failure ──────────────────────────────
test("deterministic copy states the safety-critical facts without a model", () => {
  const v = tradingOpsView(payload({}, {
    overall_health: "DEGRADED",
    reconciliation_state: "REQUIRED",
    kill_switch_state: { engaged: true, reason: "operator halt" },
    subsystems: [
      { subsystem: "MARKET_DATA", health: "DEGRADED", detail: "feed stale" },
      { subsystem: "GUARDIAN", health: "HEALTHY", detail: "policy loaded" },
    ],
  }));
  const copy = deterministicSummary(v);
  assert.match(copy, /Trading mode: SHADOW/);
  assert.match(copy, /Market data: DEGRADED/);
  assert.match(copy, /feed stale/);
  assert.match(copy, /Reconciliation: REQUIRED/);
  assert.match(copy, /Kill switch: ENGAGED/);
  assert.match(copy, /Live trading is not authorised/);
  // A healthy subsystem is not narrated as a problem.
  assert.ok(!/Guardian: /.test(copy));
});

test("deterministic copy leads with staleness rather than the stale values", () => {
  const v = tradingOpsView(payload({
    freshness: "STALE", reflects_current_state: false, age_seconds: 3600,
  }));
  const copy = deterministicSummary(v);
  assert.match(copy, /STALE/);
  assert.match(copy, /not now/);
  assert.match(copy, /Overall: STALE/);
});

test("deterministic copy handles a never-collected service", () => {
  const copy = deterministicSummary(tradingOpsView({
    freshness: "NEVER_COLLECTED", reflects_current_state: false, snapshot: null,
  }));
  assert.match(copy, /has not been collected/);
  assert.ok(!/HEALTHY/.test(copy));
});

test("deterministic copy needs no view at all", () => {
  assert.equal(deterministicSummary(null), "Trading status unavailable.");
});

// ── panel grammar reuse ────────────────────────────────────────────────────
test("the view folds into the existing system-health panel shape", () => {
  const sh = toSystemHealth(tradingOpsView(payload()));
  assert.equal(sh.overall, "HEALTHY");
  assert.deepEqual(Object.keys(sh.subsystems[0]).sort(),
                   ["detail", "id", "label", "state"]);
  assert.equal(sh.subsystems[0].label, "Market data");
});

test("a stale view folds into a stale panel", () => {
  const sh = toSystemHealth(tradingOpsView(payload({ reflects_current_state: false })));
  assert.equal(sh.overall, "STALE");
});

test("subsystem labels are readable text, not raw identifiers", () => {
  assert.equal(subsystemLabel("EXECUTION_GATEWAY"), "Execution gateway");
  assert.equal(subsystemLabel("KILL_SWITCH"), "Kill switch");
  // An unknown id degrades to readable text rather than throwing.
  assert.equal(subsystemLabel("SOME_NEW_THING"), "SOME NEW THING");
});

test("every canonical health class has a mapping", () => {
  for (const h of ["HEALTHY", "WARNING", "DEGRADED", "CRITICAL", "FAILED_SAFE"]) {
    assert.ok(TRUTH_STATE_FOR_HEALTH[h], h);
  }
});
