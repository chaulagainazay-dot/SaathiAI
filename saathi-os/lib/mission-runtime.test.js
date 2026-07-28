import test from "node:test";
import assert from "node:assert/strict";

import {
  formatMissionEta,
  missionRuntimeSignal,
  normalizeMissionRuntime,
  normalizeMissionRuntimeSummary,
} from "./mission-runtime.js";

test("mission runtime summary renders only backend state", () => {
  const summary = normalizeMissionRuntimeSummary({
    mission_id: "mis_1",
    health: "AT_RISK",
    state: "WAITING",
    progress_percent: 42.25,
    active_phase: "phase_1",
    active_task: "task_2",
    current_agent: "ReviewerAgent",
    task_counts: { total: 4, completed: 1, blocked: 1 },
    warnings: ["budget nearing limit"],
    blockers: ["approval"],
    eta_seconds: 3600,
    resource_usage: { cycles: 3 },
    test_status: "PASS",
    browser_status: "NOT_RUN",
  });
  assert.equal(summary.signal, "attention");
  assert.equal(summary.progress, 42.25);
  assert.equal(summary.currentAgent, "ReviewerAgent");
  assert.deepEqual(summary.blockers, ["approval"]);
  assert.equal(formatMissionEta(summary.etaSeconds), "1h");
});

test("mission runtime fails closed for absent or malformed data", () => {
  assert.equal(normalizeMissionRuntimeSummary(null), null);
  assert.equal(normalizeMissionRuntimeSummary({ health: "HEALTHY" }), null);
  const runtime = normalizeMissionRuntime({ runtime: null, dashboard: null });
  assert.equal(runtime.planned, false);
  assert.deepEqual(runtime.tasks, []);
  assert.equal(missionRuntimeSignal("invented"), "unknown");
});

test("mission runtime clamps presentation values and preserves evidence arrays", () => {
  const runtime = normalizeMissionRuntime({
    runtime: { objective: "Bounded mission", budget: { max_cycles: 5 }, usage: { cycles: 1 } },
    dashboard: {
      mission_id: "mis_2",
      health: "COMPLETE",
      state: "COMPLETED",
      progress_percent: 140,
      eta_seconds: -8,
    },
    tasks: [{ node_id: "task_1", status: "COMPLETED" }],
    evidence: [{ evidence_id: "ev_1", status: "PASS" }],
    certifications: [{ certification_id: "mcert_1", verdict: "MISSION_COMPLETE" }],
  });
  assert.equal(runtime.planned, true);
  assert.equal(runtime.summary.progress, 100);
  assert.equal(runtime.summary.etaSeconds, 0);
  assert.equal(runtime.summary.signal, "active");
  assert.equal(runtime.tasks.length, 1);
  assert.equal(runtime.evidence.length, 1);
  assert.equal(runtime.certifications[0].verdict, "MISSION_COMPLETE");
});
