import test from "node:test";
import assert from "node:assert/strict";

import { reduceRunEvents, buildCommandCoreSnapshot, PROVENANCE } from "./command-core-adapter.js";

const ev = (id, name, created_at, payload = {}, run_id = "run-1") => ({ id, name, created_at, payload, run_id });
const snap = (over = {}) => buildCommandCoreSnapshot({ runId: "run-1", ...over });
const activeMission = { missionId: "m1", state: "ACTIVE" };

test("IDLE when nothing is happening", () => {
  const s = snap();
  assert.equal(s.coreState, "IDLE");
  assert.equal(s.supervising, false);
  assert.equal(s.degraded, false);
});

test("voice states drive LISTENING, UNDERSTANDING, THINKING and SPEAKING", () => {
  assert.equal(snap({ voiceSession: { state: "LISTENING" } }).coreState, "LISTENING");
  assert.equal(snap({ voiceSession: { state: "TRANSCRIBING" } }).coreState, "UNDERSTANDING");
  assert.equal(snap({ voiceSession: { state: "THINKING" } }).coreState, "THINKING");
  assert.equal(snap({ voiceSession: { state: "SPEAKING" } }).coreState, "SPEAKING");
});

test("transcripts and energy pass through without invention", () => {
  const s = snap({
    voiceSession: { state: "LISTENING", transcriptPartial: "what is my", transcriptFinal: "" },
    microphoneEnergy: 0.031,
  });
  assert.equal(s.transcriptPartial, "what is my");
  assert.equal(s.transcriptFinal, "");
  assert.equal(s.microphoneEnergy, 0.031);
  assert.equal(snap({ voiceSession: { state: "LISTENING" } }).microphoneEnergy, null);
});

test("DELEGATING on delegation.created, before the agent has started", () => {
  const s = snap({ runEvents: [ev("e1", "delegation.created", 10)] });
  assert.equal(s.coreState, "DELEGATING");
  assert.equal(s.provenance.delegation, PROVENANCE.TRUSTED_RUNTIME);
});

test("SUPERVISING once the agent is running and Saathi is quiet", () => {
  const s = snap({
    runEvents: [ev("e1", "delegation.created", 10), ev("e2", "agent.started", 11)],
    missions: [activeMission],
  });
  assert.equal(s.coreState, "SUPERVISING");
  assert.equal(s.supervising, true);
  assert.deepEqual(s.activeMissionIds, ["m1"]);
});

test("mission truth survives when Saathi speaks over a running agent", () => {
  const s = snap({
    runEvents: [ev("e1", "agent.started", 11)],
    missions: [activeMission],
    voiceSession: { state: "SPEAKING" },
  });
  assert.equal(s.coreState, "SPEAKING");
  assert.equal(s.supervising, true, "SUPERVISING must not be the only home of mission truth");
  assert.deepEqual(s.activeMissionIds, ["m1"]);
});

test("an approval request outranks a running agent", () => {
  const s = snap({
    runEvents: [ev("e1", "agent.started", 11), ev("e2", "approval.requested", 12, { approval_id: "ap-9" })],
    missions: [activeMission],
  });
  assert.equal(s.coreState, "WAITING_APPROVAL");
  assert.equal(s.approvalPending, true);
  assert.equal(s.approvalId, "ap-9");
  assert.equal(s.provenance.approval, PROVENANCE.AUTHORITATIVE);
});

test("a Guardian block preempts every other signal", () => {
  const s = snap({
    runEvents: [ev("e1", "approval.requested", 12)],
    missions: [activeMission],
    voiceSession: { state: "SPEAKING" },
    execution: { active: true },
    guardian: { blocked: true, blockedAt: 50, decisionId: "g-7" },
  });
  assert.equal(s.coreState, "BLOCKED");
  assert.equal(s.guardianDecisionId, "g-7");
  assert.equal(s.timing, "INSTANT");
});

test("without a Guardian verdict the Command Core never asserts BLOCKED", () => {
  const s = snap({ runEvents: [ev("e1", "task.failed", 12)] });
  assert.notEqual(s.coreState, "BLOCKED");
  assert.equal(s.guardianBlocked, false);
  assert.equal(s.provenance.guardian, PROVENANCE.UNAVAILABLE);
});

test("degradation is orthogonal: it never erases a more specific state", () => {
  const speaking = snap({
    voiceSession: { state: "SPEAKING" },
    system: { models: { status: "DEGRADED" } },
  });
  assert.equal(speaking.coreState, "SPEAKING");
  assert.equal(speaking.degraded, true);
  assert.deepEqual(speaking.degradedReasons, ["models"]);

  const quiet = snap({ system: { gateway: { status: "DEGRADED" } } });
  assert.equal(quiet.coreState, "DEGRADED");
});

test("tool.requested is a request and never becomes EXECUTING", () => {
  const s = snap({ runEvents: [ev("e1", "tool.requested", 20)] });
  assert.equal(s.executionState, "REQUESTED");
  assert.notEqual(s.coreState, "EXECUTING");
  assert.equal(s.provenance.execution, PROVENANCE.UNAVAILABLE);
});

test("EXECUTING and VERIFYING come only from supplied execution truth", () => {
  assert.equal(snap({ execution: { active: true } }).coreState, "EXECUTING");
  assert.equal(snap({ execution: { active: true, verifying: true } }).coreState, "VERIFYING");
});

test("execution complete without a verification signal is reported, not celebrated", () => {
  const s = snap({ execution: { complete: true } });
  assert.equal(s.verificationState, "EXECUTION_COMPLETE_VERIFICATION_UNAVAILABLE");
  assert.equal(s.provenance.verification, PROVENANCE.UNAVAILABLE);
});

test("a real verification event is honoured", () => {
  const passed = snap({ runEvents: [ev("e1", "verification.passed", 30)], execution: { complete: true } });
  assert.equal(passed.verificationState, "PASSED");
  assert.equal(passed.provenance.verification, PROVENANCE.AUTHORITATIVE);

  const failed = snap({ runEvents: [ev("e1", "verification.failed", 30)] });
  assert.equal(failed.verificationState, "FAILED");
});

test("a fabricated frontend event cannot authorize execution", () => {
  const s = snap({
    runEvents: [
      ev("x1", "execution.started", 40),
      ev("x2", "approval.granted", 41),
      ev("x3", "guardian.cleared", 42),
    ],
  });
  assert.equal(s.executionState, "NONE");
  assert.equal(s.approvalGranted, false);
  assert.notEqual(s.coreState, "EXECUTING");
});

test("an unlabelled approval.resolved is not a grant", () => {
  const s = snap({
    runEvents: [ev("e1", "approval.requested", 10), ev("e2", "approval.resolved", 11, {})],
  });
  assert.equal(s.approvalPending, true);
  assert.equal(s.approvalDecision, null);
  assert.equal(s.approvalGranted, false);
});

test("approval outcomes are read from the payload", () => {
  const granted = snap({
    runEvents: [ev("e1", "approval.requested", 10), ev("e2", "approval.resolved", 11, { approved: true })],
  });
  assert.equal(granted.approvalDecision, "APPROVED");
  assert.equal(granted.approvalGranted, true);

  const denied = snap({
    runEvents: [ev("e1", "approval.requested", 10), ev("e2", "approval.resolved", 11, { approved: false })],
  });
  assert.equal(denied.approvalDecision, "DENIED");
  assert.equal(denied.approvalGranted, false);
});

test("a grant older than a Guardian block does not survive the block", () => {
  const s = snap({
    runEvents: [ev("e1", "approval.requested", 10), ev("e2", "approval.resolved", 11, { approved: true })],
    guardian: { blocked: true, blockedAt: 50 },
  });
  assert.equal(s.coreState, "BLOCKED");
  assert.equal(s.approvalGranted, false, "stale grant must not outlive a newer block");
});

test("out-of-order delivery folds in backend timestamp order", () => {
  const inOrder = reduceRunEvents([
    ev("e1", "approval.requested", 10),
    ev("e2", "approval.resolved", 11, { approved: true }),
  ]);
  const shuffled = reduceRunEvents([
    ev("e2", "approval.resolved", 11, { approved: true }),
    ev("e1", "approval.requested", 10),
  ]);
  assert.deepEqual(shuffled, inOrder);
  assert.equal(shuffled.approvalPending, false);
});

test("a stale resolution arriving after a newer request does not clear it", () => {
  const fold = reduceRunEvents([
    ev("e1", "approval.resolved", 5, { approved: true }),
    ev("e2", "approval.requested", 20),
  ]);
  assert.equal(fold.approvalPending, true, "the newer request wins");
  assert.equal(fold.approvalDecision, null);
});

test("duplicate rows are idempotent", () => {
  const once = reduceRunEvents([ev("e1", "agent.started", 10)]);
  const twice = reduceRunEvents([ev("e1", "agent.started", 10), ev("e1", "agent.started", 10)]);
  assert.deepEqual(twice, once);
});

test("events from another run cannot move this run", () => {
  const fold = reduceRunEvents(
    [ev("e1", "agent.started", 10, {}, "run-1"), ev("e2", "approval.requested", 11, {}, "run-2")],
    { runId: "run-1" }
  );
  assert.equal(fold.approvalPending, false, "mission B must not raise an approval on mission A");
  assert.equal(fold.agentStartedAt, 10);
});

test("the fabric's agentrun. prefix is accepted", () => {
  const fold = reduceRunEvents([ev("e1", "agentrun.agent.started", 10)]);
  assert.equal(fold.agentStartedAt, 10);
});

test("mission liveness keeps absence, heartbeat and progress distinct", () => {
  const s = snap({
    missions: [
      { missionId: "a", state: "ACTIVE" },
      { missionId: "b", state: "ACTIVE", last_heartbeat_at: 99 },
      { missionId: "c", state: "ACTIVE", progress_percent: 0 },
    ],
  });
  assert.equal(s.missionLiveness[0].kind, "UNKNOWN");
  assert.equal(s.missionLiveness[0].percent, null);
  assert.equal(s.missionLiveness[1].kind, "HEARTBEAT");
  assert.equal(s.missionLiveness[1].percent, null);
  assert.equal(s.missionLiveness[2].kind, "PROGRESS");
  assert.equal(s.missionLiveness[2].percent, 0);
});

test("the adapter reads no frontend clock", async () => {
  const src = await import("node:fs").then((fs) =>
    fs.promises.readFile(new URL("./command-core-adapter.js", import.meta.url), "utf8")
  );
  const code = src.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
  for (const banned of ["Date.now", "setTimeout", "setInterval", "performance.now"]) {
    assert.ok(!code.includes(banned), `${banned} must not be system truth`);
  }
});
