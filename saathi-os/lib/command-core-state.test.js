import test from "node:test";
import assert from "node:assert/strict";

import {
  COMMAND_CORE_STATES,
  MOTION_PRIMITIVE,
  STATE_TIMING,
  TIMING_CLASS,
  SAFETY_STATES,
  missionLiveness,
  hasLiveDelegatedWork,
  deriveCommandCoreState,
  assertTransition,
  reducedMotionPresentation,
} from "./command-core-state.js";

const activeMission = { mission_id: "m1", state: "ACTIVE" };

test("the contract exposes twelve states, each with a motion primitive and timing", () => {
  assert.equal(COMMAND_CORE_STATES.length, 12);
  for (const state of COMMAND_CORE_STATES) {
    assert.ok(MOTION_PRIMITIVE[state], `${state} needs a motion primitive`);
    assert.ok(TIMING_CLASS[STATE_TIMING[state]], `${state} needs a valid timing class`);
  }
});

test("safety states enter on INSTANT timing and never on a cinematic class", () => {
  for (const state of SAFETY_STATES) {
    assert.equal(STATE_TIMING[state], "INSTANT", `${state} must be INSTANT`);
  }
  assert.notEqual(STATE_TIMING.BLOCKED, "EXPRESSIVE");
});

test("missing progress is UNKNOWN, not zero percent", () => {
  const live = missionLiveness({ mission_id: "m1" });
  assert.equal(live.kind, "UNKNOWN");
  assert.equal(live.percent, null);
});

test("a heartbeat alone never becomes a progress percentage", () => {
  const live = missionLiveness({ last_heartbeat_at: 1_700_000_000 });
  assert.equal(live.kind, "HEARTBEAT");
  assert.equal(live.percent, null);
  assert.equal(live.lastHeartbeatAt, 1_700_000_000);
});

test("progress is reported only when the server reported it", () => {
  const live = missionLiveness({ progress_percent: 42, last_heartbeat_at: 5 });
  assert.equal(live.kind, "PROGRESS");
  assert.equal(live.percent, 42);
});

test("a server-reported zero is preserved and is distinguishable from absence", () => {
  assert.equal(missionLiveness({ progress_percent: 0 }).kind, "PROGRESS");
  assert.equal(missionLiveness({ progress_percent: 0 }).percent, 0);
  assert.equal(missionLiveness({}).percent, null);
});

test("SUPERVISING is derived from real mission state and differs from IDLE", () => {
  const idle = deriveCommandCoreState({});
  assert.equal(idle.state, "IDLE");
  assert.equal(idle.supervising, false);

  const supervising = deriveCommandCoreState({ missions: [activeMission] });
  assert.equal(supervising.state, "SUPERVISING");
  assert.equal(supervising.supervising, true);
  assert.notEqual(supervising.motion, MOTION_PRIMITIVE.IDLE);
});

test("SUPERVISING yields to Saathi's own turn but the flag stays true", () => {
  const thinking = deriveCommandCoreState({
    missions: [activeMission],
    assistant: { processing: true },
  });
  assert.equal(thinking.state, "THINKING");
  assert.equal(thinking.supervising, true);
});

test("no live mission means no SUPERVISING, whatever the panel shows", () => {
  assert.equal(hasLiveDelegatedWork([{ state: "COMPLETE" }]), false);
  assert.equal(hasLiveDelegatedWork([]), false);
  assert.equal(deriveCommandCoreState({ missions: [{ state: "COMPLETE" }] }).state, "IDLE");
});

test("a Guardian block outranks every other signal", () => {
  const blocked = deriveCommandCoreState({
    guardian: { blocked: true },
    approval: { pending: true },
    execution: { active: true },
    assistant: { speaking: true },
    voice: { state: "LISTENING" },
    missions: [activeMission],
  });
  assert.equal(blocked.state, "BLOCKED");
  assert.equal(blocked.timing, "INSTANT");
});

test("a pending approval outranks conversation and execution", () => {
  const waiting = deriveCommandCoreState({
    approval: { pending: true },
    execution: { active: true },
    assistant: { speaking: true },
  });
  assert.equal(waiting.state, "WAITING_APPROVAL");
});

test("voice states map to listening, understanding and speaking", () => {
  assert.equal(deriveCommandCoreState({ voice: { state: "LISTENING" } }).state, "LISTENING");
  assert.equal(deriveCommandCoreState({ voice: { state: "SPEECH_DETECTED" } }).state, "LISTENING");
  assert.equal(deriveCommandCoreState({ voice: { state: "TRANSCRIBING" } }).state, "UNDERSTANDING");
  assert.equal(deriveCommandCoreState({ voice: { state: "SPEAKING" } }).state, "SPEAKING");
});

test("verification is a distinct state and does not read as execution", () => {
  const verifying = deriveCommandCoreState({ execution: { active: true, verifying: true } });
  assert.equal(verifying.state, "VERIFYING");
});

test("degradation never masks a more specific state, but the flag survives", () => {
  const degradedIdle = deriveCommandCoreState({ system: { degraded: true } });
  assert.equal(degradedIdle.state, "DEGRADED");

  const degradedListening = deriveCommandCoreState({
    system: { degraded: true },
    voice: { state: "LISTENING" },
  });
  assert.equal(degradedListening.state, "LISTENING");
  assert.equal(degradedListening.degraded, true);
});

test("WAITING_APPROVAL cannot reach EXECUTING without an approval grant", () => {
  const denied = assertTransition("WAITING_APPROVAL", "EXECUTING", { executionGranted: true });
  assert.equal(denied.allowed, false);
  assert.equal(denied.reason, "execution-requires-approval");

  const allowed = assertTransition("WAITING_APPROVAL", "EXECUTING", {
    executionGranted: true,
    approvalGranted: true,
  });
  assert.equal(allowed.allowed, true);
});

test("execution always requires a backend grant, from any state", () => {
  for (const from of ["IDLE", "THINKING", "SUPERVISING", "VERIFYING"]) {
    const result = assertTransition(from, "EXECUTING", {});
    assert.equal(result.allowed, false, `${from} must not self-authorise`);
    assert.equal(result.reason, "execution-requires-backend-grant");
  }
});

test("BLOCKED cannot reach EXECUTING without a newer Guardian clearance", () => {
  const stale = assertTransition("BLOCKED", "EXECUTING", {
    executionGranted: true,
    approvalGranted: true,
    guardianBlockedAt: 200,
    guardianClearedAt: 100,
  });
  assert.equal(stale.allowed, false);
  assert.equal(stale.reason, "execution-requires-new-guardian-clearance");

  const missing = assertTransition("BLOCKED", "EXECUTING", { executionGranted: true });
  assert.equal(missing.allowed, false);

  const fresh = assertTransition("BLOCKED", "EXECUTING", {
    executionGranted: true,
    guardianBlockedAt: 100,
    guardianClearedAt: 200,
  });
  assert.equal(fresh.allowed, true);
});

test("verification only follows execution", () => {
  assert.equal(assertTransition("IDLE", "VERIFYING", {}).allowed, false);
  assert.equal(assertTransition("EXECUTING", "VERIFYING", {}).allowed, true);
});

test("an unknown target state is refused", () => {
  assert.equal(assertTransition("IDLE", "TELEPORTING", {}).allowed, false);
});

test("reduced motion keeps safety meaning without animation", () => {
  const blocked = reducedMotionPresentation("BLOCKED");
  assert.equal(blocked.animate, false);
  assert.equal(blocked.requiresTextAffordance, true);

  const idle = reducedMotionPresentation("IDLE");
  assert.equal(idle.animate, false);
  assert.equal(idle.requiresTextAffordance, false);
});
