import test from "node:test";
import assert from "node:assert/strict";

import { selectContextualRun, eventsForContext, isRunActive, RUN_CONTEXT_SOURCE } from "./command-run-context.js";
import { buildCommandCoreSnapshot } from "./command-core-adapter.js";

const CID = "conv-central";
const run = (id, over = {}) => ({ id, conversation_id: CID, state: "running", created_at: 100, ...over });

test("no conversation and no runs means no contextual run", () => {
  assert.equal(selectContextualRun(), null);
  assert.equal(selectContextualRun({ conversationId: CID, conversationRuns: [] }), null);
});

test("an existing run on this conversation becomes contextual", () => {
  const ctx = selectContextualRun({ conversationId: CID, conversationRuns: [run("r1")] });
  assert.equal(ctx.runId, "r1");
  assert.equal(ctx.source, RUN_CONTEXT_SOURCE.CONVERSATION);
  assert.equal(ctx.conversationId, CID);
});

test("the newest run on the conversation wins", () => {
  const ctx = selectContextualRun({
    conversationId: CID,
    conversationRuns: [run("old", { created_at: 100 }), run("new", { created_at: 900 })],
  });
  assert.equal(ctx.runId, "new");
});

test("a run belonging to another conversation is never adopted", () => {
  const other = run("elsewhere", { conversation_id: "conv-other" });
  assert.equal(selectContextualRun({ conversationId: CID, conversationRuns: [other] }), null,
    "a globally active run must not hijack the centre");
});

test("an unrelated active run does not become context even when it is the only run", () => {
  const only = { id: "bg", conversation_id: "conv-background", state: "running", created_at: 999 };
  assert.equal(selectContextualRun({ conversationId: CID, conversationRuns: [only] }), null);
});

test("the run just submitted here takes priority over an older conversation run", () => {
  const ctx = selectContextualRun({
    conversationId: CID,
    submittedRunId: "r2",
    conversationRuns: [run("r1", { created_at: 100 }), run("r2", { created_at: 50 })],
  });
  assert.equal(ctx.runId, "r2");
  assert.equal(ctx.source, RUN_CONTEXT_SOURCE.SUBMITTED);
});

test("a submitted run stands before the server list catches up", () => {
  const ctx = selectContextualRun({ conversationId: CID, submittedRunId: "fresh", conversationRuns: [] });
  assert.equal(ctx.runId, "fresh");
  assert.equal(ctx.source, RUN_CONTEXT_SOURCE.SUBMITTED);
});

test("a submitted run without a conversation identity is refused", () => {
  assert.equal(selectContextualRun({ submittedRunId: "orphan", conversationRuns: [] }), null);
});

test("an explicit pin is honoured only when the server correlates it here", () => {
  const pinned = selectContextualRun({
    conversationId: CID, explicitRunId: "r1", conversationRuns: [run("r1"), run("r2", { created_at: 900 })],
  });
  assert.equal(pinned.runId, "r1");
  assert.equal(pinned.source, RUN_CONTEXT_SOURCE.EXPLICIT);

  const foreign = selectContextualRun({
    conversationId: CID, explicitRunId: "elsewhere",
    conversationRuns: [run("elsewhere", { conversation_id: "conv-other" })],
  });
  assert.equal(foreign, null, "pinning must not adopt another conversation's run");
});

test("run activity uses the runtime's own vocabulary", () => {
  assert.equal(isRunActive({ state: "running" }), true);
  assert.equal(isRunActive({ state: "queued" }), true);
  assert.equal(isRunActive({ status: "completed" }), false);
  assert.equal(isRunActive({}), false);
});

test("only the contextual run's events pass the gate", () => {
  const ctx = selectContextualRun({ conversationId: CID, conversationRuns: [run("r1")] });
  const kept = eventsForContext([
    { id: "e1", name: "agent.started", run_id: "r1", created_at: 1 },
    { id: "e2", name: "agent.started", run_id: "r-other", created_at: 2 },
  ], ctx);
  assert.equal(kept.length, 1);
  assert.equal(kept[0].id, "e1");
});

test("with no context, no events pass", () => {
  assert.deepEqual(eventsForContext([{ id: "e1", run_id: "r1" }], null), []);
});

test("a background run's agent.started cannot produce SUPERVISING", () => {
  const ctx = selectContextualRun({ conversationId: CID, conversationRuns: [run("r1")] });
  const background = [{ id: "b1", name: "agent.started", run_id: "r-background", created_at: 10 }];
  const snap = buildCommandCoreSnapshot({
    runEvents: eventsForContext(background, ctx), runId: ctx.runId,
  });
  assert.notEqual(snap.coreState, "SUPERVISING");
  assert.equal(snap.supervising, false);
});

test("the contextual run's agent.started does produce SUPERVISING", () => {
  const ctx = selectContextualRun({ conversationId: CID, conversationRuns: [run("r1")] });
  const events = [{ id: "e1", name: "agent.started", run_id: "r1", created_at: 10 }];
  const snap = buildCommandCoreSnapshot({
    runEvents: eventsForContext(events, ctx), runId: ctx.runId,
    missions: [{ missionId: "r1", state: "ACTIVE" }],
  });
  assert.equal(snap.coreState, "SUPERVISING");
  assert.equal(snap.supervising, true);
});

test("degradation stays orthogonal to a contextual run", () => {
  const ctx = selectContextualRun({ conversationId: CID, conversationRuns: [run("r1")] });
  const snap = buildCommandCoreSnapshot({
    runEvents: eventsForContext([{ id: "e1", name: "agent.started", run_id: "r1", created_at: 10 }], ctx),
    runId: ctx.runId,
    missions: [{ missionId: "r1", state: "ACTIVE" }],
    system: { models: { status: "DEGRADED" } },
  });
  assert.equal(snap.coreState, "SUPERVISING");
  assert.equal(snap.degraded, true);
});

test("a contextual run reports no progress the server never sent", () => {
  const ctx = selectContextualRun({ conversationId: CID, conversationRuns: [run("r1")] });
  const snap = buildCommandCoreSnapshot({
    runEvents: eventsForContext([{ id: "e1", name: "agent.started", run_id: "r1", created_at: 10 }], ctx),
    runId: ctx.runId, missions: [{ missionId: "r1", state: "ACTIVE" }],
  });
  assert.equal(snap.missionLiveness[0].kind, "UNKNOWN");
  assert.equal(snap.missionLiveness[0].percent, null);
});
