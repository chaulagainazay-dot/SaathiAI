import test from "node:test";
import assert from "node:assert/strict";

import {
  TERMINAL_STATES,
  TERMINAL_LABEL,
  VERIFICATION,
  VERIFICATION_LABEL,
  TEST_STRATEGIES,
  HISTORY_LIMIT,
  TRIAD_HANDOFF,
  isTerminal,
  isTestStrategy,
  verificationFromEvents,
  buildHistoryItem,
  buildCommandHistory,
} from "./command-history.js";

const CID = "cmd-phase8b";

function run(id, over = {}) {
  return {
    id,
    objective: `objective ${id}`,
    strategy: "build",
    state: "completed",
    conversation_id: CID,
    created_at: 1000,
    updated_at: 2000,
    terminal_reason: "",
    ...over,
  };
}

// ── terminal lifecycle ─────────────────────────────────────────────────────

test("the terminal set mirrors the backend exactly", () => {
  assert.deepEqual([...TERMINAL_STATES].sort(), [
    "cancelled", "completed", "failed", "partially_completed", "rolled_back", "timed_out",
  ]);
});

test("every terminal state renders as itself and nothing else", () => {
  const expected = {
    completed: "Completed",
    failed: "Failed",
    cancelled: "Cancelled",
    timed_out: "Timed out",
    rolled_back: "Rolled back",
    partially_completed: "Partially completed",
  };
  for (const [state, label] of Object.entries(expected)) {
    const item = buildHistoryItem(run("r", { state }), { conversationId: CID });
    assert.equal(item.terminalLabel, label, `${state} must read as "${label}"`);
  }
  // The two that matter most: neither may be smoothed into "Completed".
  assert.notEqual(TERMINAL_LABEL.partially_completed, TERMINAL_LABEL.completed);
  assert.notEqual(TERMINAL_LABEL.rolled_back, TERMINAL_LABEL.completed);
});

test("non-terminal runs are never history", () => {
  for (const state of ["created", "planning", "awaiting_approval", "approved", "queued",
    "running", "delegated", "verifying", "reviewing", "paused", "blocked"]) {
    assert.equal(buildHistoryItem(run("r", { state }), { conversationId: CID }), null,
      `${state} still belongs to orchestration or attention`);
    assert.equal(isTerminal(state), false);
  }
});

test("active runs are excluded from the surface entirely", () => {
  const model = buildCommandHistory({
    runs: [run("a", { state: "running" }), run("b", { state: "blocked" }), run("c")],
    conversationId: CID,
  });
  assert.equal(model.items.length, 1);
  assert.equal(model.items[0].runId, "c");
});

// ── verification is its own axis ───────────────────────────────────────────

test("verification is never inferred from how a run ended", () => {
  const completed = buildHistoryItem(run("r1", { state: "completed" }), { conversationId: CID });
  assert.equal(completed.verificationState, VERIFICATION.UNAVAILABLE,
    "a completed run with no verification event is not verified");
  assert.equal(VERIFICATION_LABEL[VERIFICATION.UNAVAILABLE], null,
    "absence must render as nothing, never as quiet success");
});

test("real verification events decide verification", () => {
  assert.equal(verificationFromEvents([{ name: "agentrun.verification.passed" }]), VERIFICATION.PASSED);
  assert.equal(verificationFromEvents([{ name: "verification.failed" }]), VERIFICATION.FAILED);
  assert.equal(verificationFromEvents([{ name: "task.completed" }]), VERIFICATION.UNAVAILABLE);
  assert.equal(verificationFromEvents([]), VERIFICATION.UNAVAILABLE);
  assert.equal(verificationFromEvents(null), VERIFICATION.UNAVAILABLE);
});

test("one verification failure outweighs any number of passes", () => {
  assert.equal(verificationFromEvents([
    { name: "verification.passed" }, { name: "verification.failed" }, { name: "verification.passed" },
  ]), VERIFICATION.FAILED);
});

test("verification never implies execution", () => {
  const item = buildHistoryItem(run("r1"), {
    conversationId: CID, events: [{ name: "verification.passed" }] });
  assert.equal(item.verificationState, VERIFICATION.PASSED);
  assert.equal(VERIFICATION_LABEL[VERIFICATION.PASSED], "Verified");
  for (const key of ["executed", "execution", "executionGranted", "authority", "approved"]) {
    assert.ok(!(key in item), `${key} must not exist on a history record`);
  }
});

// ── context correlation ────────────────────────────────────────────────────

test("history classifies context without guessing", () => {
  assert.equal(buildHistoryItem(run("a"), { conversationId: CID }).contextClass, "IN_CONTEXT");
  assert.equal(buildHistoryItem(run("b", { conversation_id: "other" }),
    { conversationId: CID }).contextClass, "BACKGROUND");
  assert.equal(buildHistoryItem(run("c", { conversation_id: "" }),
    { conversationId: CID }).contextClass, "UNASSOCIATED");
  assert.equal(buildHistoryItem(run("d"), { conversationId: "" }).contextClass, "BACKGROUND");
});

// ── ordering ───────────────────────────────────────────────────────────────

test("history orders by when runs ended, not when they started", () => {
  const model = buildCommandHistory({
    runs: [
      run("early-start-late-end", { created_at: 1, updated_at: 900 }),
      run("late-start-early-end", { created_at: 500, updated_at: 600 }),
    ],
    conversationId: CID,
  });
  assert.deepEqual(model.items.map((i) => i.runId),
    ["early-start-late-end", "late-start-early-end"]);
});

test("records that ended in the same instant keep a stable order", () => {
  // Wall-clock stamps give only a partial order; the tie-break must at least
  // be deterministic so the list does not appear to shuffle between renders.
  const runs = [run("aaa", { updated_at: 5 }), run("bbb", { updated_at: 5 }), run("ccc", { updated_at: 5 })];
  const first = buildCommandHistory({ runs, conversationId: CID }).items.map((i) => i.runId);
  const second = buildCommandHistory({ runs: [...runs].reverse(), conversationId: CID }).items.map((i) => i.runId);
  assert.deepEqual(first, second);
});

test("a run with no end timestamp falls back to its start", () => {
  const model = buildCommandHistory({
    runs: [run("no-end", { updated_at: null, created_at: 50 }), run("ended", { updated_at: 10 })],
    conversationId: CID,
  });
  assert.deepEqual(model.items.map((i) => i.runId), ["no-end", "ended"]);
});

// ── dedupe ─────────────────────────────────────────────────────────────────

test("one run is one record however many events it emitted", () => {
  const model = buildCommandHistory({
    runs: [run("r1"), run("r1"), run("r1")], conversationId: CID });
  assert.equal(model.items.length, 1);
});

test("dedupe uses identifiers, never display text", () => {
  const model = buildCommandHistory({
    runs: [run("r1", { objective: "same" }), run("r2", { objective: "same" })],
    conversationId: CID,
  });
  assert.equal(model.items.length, 2);
  assert.deepEqual(model.items.map((i) => i.id).sort(), ["HISTORY:r1", "HISTORY:r2"]);
});

// ── failure history ────────────────────────────────────────────────────────

test("a failure reason is shown only when the backend wrote one", () => {
  assert.equal(buildHistoryItem(run("r1", { state: "failed" }), { conversationId: CID }).failureReason, null);
  assert.equal(buildHistoryItem(run("r2", { state: "failed", terminal_reason: "provider unavailable" }),
    { conversationId: CID }).failureReason, "provider unavailable");
});

test("a failed run is history without being an instruction", () => {
  const item = buildHistoryItem(run("r1", { state: "failed" }), { conversationId: CID });
  assert.equal(item.terminalLabel, "Failed");
  assert.deepEqual(item.allowedActions, [], "history offers no retry");
  assert.equal(item.readOnly, true);
});

// ── certification fixtures ─────────────────────────────────────────────────

test("certification strategies are excluded from history by default", () => {
  const runs = [
    run("real", { strategy: "build" }),
    run("hold", { strategy: "test_hold" }),
    run("fail", { strategy: "test_fail", state: "failed" }),
  ];
  const model = buildCommandHistory({ runs, conversationId: CID });
  assert.deepEqual(model.items.map((i) => i.runId), ["real"]);
  assert.equal(model.testStrategyRecords, 2, "the count is reported, not hidden");
});

test("fixture records are labelled and can be included for certification", () => {
  assert.deepEqual([...TEST_STRATEGIES].sort(), ["test_fail", "test_hold"]);
  assert.equal(isTestStrategy("test_hold"), true);
  assert.equal(isTestStrategy("build"), false);

  const runs = [run("real"), run("hold", { strategy: "test_hold" })];
  const included = buildCommandHistory({ runs, conversationId: CID, includeTestStrategies: true });
  assert.equal(included.items.length, 2);
  assert.equal(included.items.find((i) => i.runId === "hold").isTestStrategy, true);
});

// ── retention ──────────────────────────────────────────────────────────────

test("history is bounded and discloses what it withholds", () => {
  const runs = Array.from({ length: 14 }, (_, i) => run(`r${i}`, { updated_at: i }));
  const model = buildCommandHistory({ runs, conversationId: CID });
  assert.equal(model.items.length, HISTORY_LIMIT);
  assert.equal(model.withheld, 4);
  assert.equal(model.counts.total, 14);
  // the newest survive
  assert.equal(model.items[0].runId, "r13");
});

test("bounding is presentation only and uses no clock", async () => {
  const fs = await import("node:fs");
  const src = await fs.promises.readFile(new URL("./command-history.js", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
  for (const banned of ["Date.now", "setTimeout", "setInterval", "performance.now", "new Date"]) {
    assert.ok(!code.includes(banned), `${banned} must never decide what is history`);
  }
});

// ── authority boundary ─────────────────────────────────────────────────────

test("the surface grants nothing", () => {
  const model = buildCommandHistory({
    runs: [run("a"), run("b", { state: "failed" })], conversationId: CID });
  assert.equal(model.readOnly, true);
  for (const item of model.items) {
    assert.equal(item.readOnly, true);
    assert.deepEqual(item.allowedActions, []);
    for (const key of ["retry", "rerun", "approve", "delete", "clear", "restore", "execute"]) {
      assert.ok(!(key in item), `${key} must not exist on a history record`);
    }
  }
});

test("every record carries provenance and names its source", () => {
  const item = buildHistoryItem(run("r1"), { conversationId: CID });
  assert.equal(item.provenance, "REAL");
  assert.equal(item.source, "agent-runtime.orchestration_run");
});

test("history reports empty as empty", () => {
  const model = buildCommandHistory({ runs: [], conversationId: CID });
  assert.deepEqual(model.items, []);
  assert.equal(model.counts.total, 0);
  assert.equal(model.withheld, 0);
});

// ── the hook adds no traffic and cannot repeat the Phase 6 defect ──────────

test("the history hook fetches nothing and keys on no event name", async () => {
  const fs = await import("node:fs");
  const src = await fs.promises.readFile(new URL("./useCommandHistory.js", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
  for (const banned of ["afetch", "fetch(", "EventSource", "setInterval", "setTimeout",
    "useEffect", "lastName", "last?.name"]) {
    assert.ok(!code.includes(banned), `${banned} must not appear on the history path`);
  }
});

test("history does not read the other surfaces' retained rows", async () => {
  // The read model must take durable run records, not what Phase 6/7 dropped.
  const fs = await import("node:fs");
  const src = await fs.promises.readFile(new URL("./command-history.js", import.meta.url), "utf8");
  for (const banned of ["TERMINAL_RETENTION_LIMIT", "FAILED_RETENTION_LIMIT",
    "buildAgentOrchestration", "buildAttention", "withheldTerminal"]) {
    assert.ok(!src.includes(banned), `history must not derive from ${banned}`);
  }
});

test("the triad handoff is documented and disjoint", () => {
  assert.deepEqual(TRIAD_HANDOFF.map((t) => t.surface),
    ["WHO_IVE_GOT_WORKING", "WHAT_NEEDS_YOU", "WHAT_IVE_BEEN_DOING"]);
  for (const t of TRIAD_HANDOFF) assert.ok(t.holds && t.question);
});
