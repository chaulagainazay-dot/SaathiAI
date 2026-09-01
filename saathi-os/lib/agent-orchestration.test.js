import test from "node:test";
import assert from "node:assert/strict";

import {
  buildAgentOrchestration, buildWorkItem, classifyRun, runLifecycle, agentDisplayName,
  isTerminalRunState, factsFromEvents, CONTEXT_CLASS, RUN_TERMINAL_STATES, WHAT_NEEDS_YOU_SOURCES,
} from "./agent-orchestration.js";

const CID = "cmd-abc";
const run = (id, over = {}) => ({ id, conversation_id: CID, state: "running", created_at: 100, ...over });
const ev = (name, at, payload = {}, run_id = "r1") => ({ id: `${name}-${at}`, name, created_at: at, payload, run_id });

test("classification: in-context, background, and never-guessed unassociated", () => {
  assert.equal(classifyRun(run("r1"), CID), CONTEXT_CLASS.IN_CONTEXT);
  assert.equal(classifyRun(run("r2", { conversation_id: "other" }), CID), CONTEXT_CLASS.BACKGROUND);
  assert.equal(classifyRun(run("r3", { conversation_id: "" }), CID), CONTEXT_CLASS.UNASSOCIATED);
  assert.equal(classifyRun(run("r4"), ""), CONTEXT_CLASS.BACKGROUND, "no active conversation means nothing is in context");
});

test("lifecycle labels come from the backend vocabulary, terminal set mirrors the runtime", () => {
  assert.equal(runLifecycle({ state: "running" }).label, "Working");
  assert.equal(runLifecycle({ state: "awaiting_approval" }).label, "Waiting for approval");
  assert.equal(runLifecycle({ state: "verifying" }).label, "Verifying");
  assert.equal(runLifecycle({}).label, "Unknown");
  assert.deepEqual([...RUN_TERMINAL_STATES].sort(),
    ["cancelled", "completed", "failed", "partially_completed", "rolled_back", "timed_out"]);
  for (const s of RUN_TERMINAL_STATES) assert.equal(isTerminalRunState(s), true);
  assert.equal(runLifecycle({ state: "paused" }).active, true, "paused is not terminal");
});

test("agent identity is a deterministic map and never invents an agent", () => {
  assert.equal(agentDisplayName("planner"), "Planner");
  assert.equal(agentDisplayName("researcher"), "Research");
  assert.equal(agentDisplayName("ceo"), "Business");
  assert.equal(agentDisplayName("some_new_role"), "some_new_role", "unknown roles are shown as-is, not renamed");
  assert.equal(agentDisplayName(""), "Agent");
});

test("events give the agent, verification and start, and never cross runs", () => {
  const facts = factsFromEvents([
    ev("agent.started", 10, { agent: "planner" }, "r1"),
    ev("verification.passed", 20, {}, "r1"),
    ev("agent.started", 30, { agent: "reviewer" }, "r-other"),
  ], "r1");
  assert.equal(facts.agentRole, "planner", "another run's agent must not leak in");
  assert.equal(facts.verification, "PASSED");
  assert.equal(facts.startedAt, 10);
});

test("the agentrun. fabric prefix is accepted", () => {
  assert.equal(factsFromEvents([ev("agentrun.agent.started", 5, { agent: "builder" })], "r1").agentRole, "builder");
});

test("liveness stays truthful: unknown, heartbeat, progress, and a real zero", () => {
  assert.equal(buildWorkItem(run("r1")).liveness.kind, "UNKNOWN");
  assert.equal(buildWorkItem(run("r1")).liveness.percent, null);
  assert.equal(buildWorkItem(run("r1", { last_heartbeat_at: 9 })).liveness.kind, "HEARTBEAT");
  assert.equal(buildWorkItem(run("r1", { last_heartbeat_at: 9 })).liveness.percent, null);
  assert.equal(buildWorkItem(run("r1", { progress_percent: 42 })).liveness.percent, 42);
  const zero = buildWorkItem(run("r1", { progress_percent: 0 }));
  assert.equal(zero.liveness.kind, "PROGRESS");
  assert.equal(zero.liveness.percent, 0, "a reported zero is real and distinct from absence");
});

test("verification is PASSED, FAILED or UNAVAILABLE — never assumed from completion", () => {
  assert.equal(buildWorkItem(run("r1", { state: "completed" })).verification, "UNAVAILABLE");
  assert.equal(buildWorkItem(run("r1"), { events: [ev("verification.passed", 5)] }).verification, "PASSED");
  assert.equal(buildWorkItem(run("r1"), { events: [ev("verification.failed", 5)] }).verification, "FAILED");
});

test("contextual and background work are separated, and counted separately", () => {
  const model = buildAgentOrchestration({
    conversationId: CID,
    runs: [
      run("ctx", { created_at: 200 }),
      run("bg", { conversation_id: "other", created_at: 150 }),
      run("orphan", { conversation_id: "", created_at: 120 }),
    ],
  });
  assert.deepEqual(model.inContext.map((i) => i.runId), ["ctx"]);
  assert.deepEqual(model.background.map((i) => i.runId), ["bg"]);
  assert.deepEqual(model.unassociated.map((i) => i.runId), ["orphan"]);
  assert.equal(model.counts.inContextActive, 1);
  assert.equal(model.counts.backgroundActive, 1);
});

test("two background runs stay separate rows with their own agents", () => {
  const model = buildAgentOrchestration({
    conversationId: CID,
    runs: [run("b1", { conversation_id: "c1" }), run("b2", { conversation_id: "c2" })],
    eventsByRunId: {
      b1: [ev("agent.started", 10, { agent: "planner" }, "b1")],
      b2: [ev("agent.started", 11, { agent: "researcher" }, "b2")],
    },
  });
  assert.equal(model.background.length, 2);
  const agents = model.background.map((i) => i.agent).sort();
  assert.deepEqual(agents, ["Planner", "Research"]);
});

test("an event from one run never updates another row", () => {
  const model = buildAgentOrchestration({
    conversationId: CID,
    runs: [run("a"), run("b", { conversation_id: "other" })],
    eventsByRunId: { a: [ev("verification.passed", 10, {}, "b")] },
  });
  assert.equal(model.inContext[0].verification, "UNAVAILABLE", "run b's verification must not land on run a");
});

test("a contextual run finishing leaves background work untouched", () => {
  const model = buildAgentOrchestration({
    conversationId: CID,
    runs: [run("ctx", { state: "completed" }), run("bg", { conversation_id: "other", state: "running" })],
  });
  assert.equal(model.inContext[0].lifecycle.terminal, true);
  assert.equal(model.counts.inContextActive, 0);
  assert.equal(model.background[0].lifecycle.active, true);
  assert.equal(model.counts.backgroundActive, 1);
});

test("no row ever fabricates progress", () => {
  const model = buildAgentOrchestration({
    conversationId: CID,
    runs: [run("r1", { created_at: 1 })],
    eventsByRunId: { r1: Array.from({ length: 40 }, (_, i) => ev("task.completed", i)) },
  });
  const row = model.inContext[0];
  assert.equal(row.liveness.kind, "UNKNOWN", "event volume is not progress");
  assert.equal(row.liveness.percent, null);
});

test("failure is legible and carries a real reason when one exists", () => {
  const row = buildWorkItem(run("r1", { state: "failed" }), {
    conversationId: CID, events: [ev("task.failed", 9, { error: "provider unavailable" })],
  });
  assert.equal(row.lifecycle.label, "Failed");
  assert.equal(row.failureReason, "provider unavailable");
  assert.equal(row.needsYou, "failure");
});

test("needsYou is raised only by real backend states", () => {
  assert.equal(buildWorkItem(run("r1", { state: "awaiting_approval" })).needsYou, "approval");
  assert.equal(buildWorkItem(run("r1", { state: "blocked" })).needsYou, "blocked");
  assert.equal(buildWorkItem(run("r1", { state: "running" })).needsYou, null);
  assert.equal(buildWorkItem(run("r1", { state: "completed" })).needsYou, null);
});

test("the panel is observational and grants nothing", () => {
  const model = buildAgentOrchestration({ conversationId: CID, runs: [run("r1")] });
  assert.equal(model.readOnly, true);
  const row = model.inContext[0];
  for (const key of ["approve", "approved", "execute", "authority", "approvalToken", "executionGranted"]) {
    assert.ok(!(key in row), `${key} must not exist on an observational row`);
  }
});

test("the What-needs-you contract names only real backend sources", () => {
  assert.deepEqual(WHAT_NEEDS_YOU_SOURCES.map((s) => s.key), ["approval", "failure", "blocked", "degraded"]);
  for (const s of WHAT_NEEDS_YOU_SOURCES) assert.ok(s.source && s.authority);
});

test("the read model uses no frontend clock", async () => {
  const fs = await import("node:fs");
  const src = await fs.promises.readFile(new URL("./agent-orchestration.js", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
  for (const banned of ["Date.now", "setTimeout", "setInterval", "performance.now"]) {
    assert.ok(!code.includes(banned), `${banned} must not be system truth`);
  }
});
