import test from "node:test";
import assert from "node:assert/strict";

import { buildCommandCoreSnapshot } from "./command-core-adapter.js";
import {
  operationalStatus,
  supervisingText,
  degradedText,
  verificationText,
  presencePresentation,
  presenceLabel,
  PRESENCE_SIZE_PX,
} from "./command-core-status.js";

const snap = (over = {}) => buildCommandCoreSnapshot(over);

test("capture stays quiet — LISTENING renders no status line", () => {
  assert.equal(operationalStatus(snap({ voiceSession: { state: "LISTENING" } })), null);
});

test("IDLE with nothing wrong renders no status line", () => {
  assert.equal(operationalStatus(snap()), null);
});

test("deterministic strings for the states this slice reaches", () => {
  assert.equal(operationalStatus(snap({ voiceSession: { state: "TRANSCRIBING" } })).text, "Understanding request…");
  assert.equal(operationalStatus(snap({ voiceSession: { state: "THINKING" } })).text, "Working on your request…");
  assert.equal(operationalStatus(snap({ voiceSession: { state: "SPEAKING" } })).text, "Saathi is speaking.");
});

test("SPEAKING does not shout into a live region", () => {
  assert.equal(operationalStatus(snap({ voiceSession: { state: "SPEAKING" } })).live, false);
});

test("SUPERVISING counts real missions and claims nothing more", () => {
  const one = snap({ missions: [{ missionId: "a", state: "ACTIVE" }] });
  assert.equal(operationalStatus(one).text, "1 agent is working.");

  const two = snap({ missions: [{ missionId: "a", state: "ACTIVE" }, { missionId: "b", state: "ACTIVE" }] });
  assert.equal(operationalStatus(two).text, "2 agents are working.");
});

test("a heartbeat says still running and never a percentage", () => {
  const s = snap({ missions: [{ missionId: "a", state: "ACTIVE", last_heartbeat_at: 123 }] });
  const text = supervisingText(s);
  assert.equal(text, "1 agent is working. Still running.");
  assert.ok(!/%/.test(text), "a heartbeat must not become progress");
});

test("unknown liveness produces no progress claim at all", () => {
  const s = snap({ missions: [{ missionId: "a", state: "ACTIVE" }] });
  assert.ok(!/%|progress|complete/i.test(supervisingText(s)));
});

test("server-reported progress is quoted, including a real zero", () => {
  const s = snap({ missions: [{ missionId: "a", state: "ACTIVE", progress_percent: 0 }] });
  assert.equal(supervisingText(s), "1 agent is working. 0% reported.");
});

test("degraded wording names only what actually degraded", () => {
  const s = snap({ system: { models: { status: "DEGRADED" } } });
  assert.equal(degradedText(s), "Reduced capability: model providers.");
  assert.equal(operationalStatus(s).text, "Reduced capability: model providers.");
});

test("degradation surfaces on an otherwise idle core", () => {
  const s = snap({ system: { gateway: { status: "DEGRADED" } } });
  assert.equal(operationalStatus(s).tone, "warn");
});

test("verification is never reported as passed without a real signal", () => {
  assert.equal(verificationText(snap()), null);
  assert.equal(
    verificationText(snap({ execution: { complete: true } })),
    "Execution complete — verification unavailable."
  );
  assert.equal(
    verificationText(snap({ runEvents: [{ id: "e1", name: "verification.passed", created_at: 1 }] })),
    "Result verified."
  );
});

test("no reachable state in this slice claims execution or a Guardian block", () => {
  for (const state of ["LISTENING", "TRANSCRIBING", "THINKING", "SPEAKING", "IDLE"]) {
    const line = operationalStatus(snap({ voiceSession: { state } }));
    if (!line) continue;
    assert.ok(!/execut|guardian|verified|blocked/i.test(line.text), `${state} must not claim authority truth`);
  }
});

test("presence keeps its compact intent and reads from core state", () => {
  const s = snap({ voiceSession: { state: "THINKING" } });
  const p = presencePresentation(s, {});
  assert.equal(p.state, "THINKING");
  assert.equal(p.animate, true);
  assert.equal(p.sizePx, PRESENCE_SIZE_PX);
});

test("reduced motion removes animation but keeps the state legible", () => {
  const s = snap({ voiceSession: { state: "LISTENING" }, microphoneEnergy: 0.04 });
  const p = presencePresentation(s, { reducedMotion: true });
  assert.equal(p.animate, false);
  assert.equal(p.energy, null, "no energy-driven motion under reduced motion");
  assert.equal(p.state, "LISTENING");
  assert.equal(p.label, "Saathi listening");
});

test("energy is consumed only while LISTENING and only when real", () => {
  assert.equal(presencePresentation(snap({ voiceSession: { state: "LISTENING" } }), {}).energy, null);
  assert.equal(
    presencePresentation(snap({ voiceSession: { state: "LISTENING" }, microphoneEnergy: 0.04 }), {}).energy,
    0.04
  );
  assert.equal(
    presencePresentation(snap({ voiceSession: { state: "THINKING" }, microphoneEnergy: 0.04 }), {}).energy,
    null
  );
});

test("supervising and degraded ride along as orthogonal conditions", () => {
  const s = snap({
    voiceSession: { state: "SPEAKING" },
    missions: [{ missionId: "a", state: "ACTIVE" }],
    system: { models: { status: "DEGRADED" } },
  });
  const p = presencePresentation(s, {});
  assert.equal(p.state, "SPEAKING");
  assert.equal(p.supervising, true);
  assert.equal(p.degraded, true);
});

test("every core state has an accessible name", () => {
  for (const state of ["IDLE", "LISTENING", "UNDERSTANDING", "THINKING", "SPEAKING",
    "DELEGATING", "SUPERVISING", "WAITING_APPROVAL", "EXECUTING", "VERIFYING", "BLOCKED", "DEGRADED"]) {
    assert.ok(presenceLabel(state).length > 0, `${state} needs a label`);
  }
});
