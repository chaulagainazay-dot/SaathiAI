import test from "node:test";
import assert from "node:assert/strict";

import {
  ATTENTION_TYPE,
  AUTHORITY_CLASS,
  TYPE_AUTHORITY,
  TYPE_PRECEDENCE,
  RUN_STATE_ATTENTION,
  FAILED_RETENTION_LIMIT,
  attentionTypeForRun,
  buildRunAttentionItem,
  buildDegradedAttentionItem,
  buildAttention,
} from "./command-attention.js";

const CID = "cmd-phase7";

function run(id, over = {}) {
  return {
    id,
    objective: `objective ${id}`,
    state: "failed",
    conversation_id: CID,
    created_at: 1000,
    ...over,
  };
}

const DEGRADED_SNAPSHOT = { degraded: true, degradedReasons: ["models"] };

// ── types and authority ────────────────────────────────────────────────────

test("only the three real run states become attention", () => {
  assert.equal(attentionTypeForRun(run("r", { state: "awaiting_approval" })), ATTENTION_TYPE.APPROVAL_REQUIRED);
  assert.equal(attentionTypeForRun(run("r", { state: "blocked" })), ATTENTION_TYPE.BLOCKED);
  assert.equal(attentionTypeForRun(run("r", { state: "failed" })), ATTENTION_TYPE.FAILED);

  // Everything else is activity or history, never attention.
  for (const state of ["created", "planning", "approved", "queued", "running", "delegated",
    "verifying", "reviewing", "completed", "paused", "cancelled", "timed_out",
    "rolled_back", "partially_completed"]) {
    assert.equal(attentionTypeForRun(run("r", { state })), null, `${state} must not need the owner`);
  }
});

test("the run-state map matches the backend vocabulary exactly", () => {
  assert.deepEqual(Object.keys(RUN_STATE_ATTENTION).sort(),
    ["awaiting_approval", "blocked", "failed"]);
});

test("authority is a property of the type, never of the row", () => {
  assert.equal(TYPE_AUTHORITY[ATTENTION_TYPE.APPROVAL_REQUIRED], AUTHORITY_CLASS.AUTHORITATIVE);
  assert.equal(TYPE_AUTHORITY[ATTENTION_TYPE.BLOCKED], AUTHORITY_CLASS.AUTHORITATIVE);
  assert.equal(TYPE_AUTHORITY[ATTENTION_TYPE.FAILED], AUTHORITY_CLASS.TRUSTED_RUNTIME);
  assert.equal(TYPE_AUTHORITY[ATTENTION_TYPE.DEGRADED], AUTHORITY_CLASS.ADVISORY);

  // A run record cannot talk its way into a stronger class.
  const item = buildRunAttentionItem(
    run("r1", { state: "failed", authorityClass: "AUTHORITATIVE", authority: "AUTHORITATIVE" }),
    { conversationId: CID });
  assert.equal(item.authorityClass, AUTHORITY_CLASS.TRUSTED_RUNTIME);
});

// ── context classification ─────────────────────────────────────────────────

test("attention classifies context, background and unassociated without guessing", () => {
  const inCtx = buildRunAttentionItem(run("r1"), { conversationId: CID });
  const bg = buildRunAttentionItem(run("r2", { conversation_id: "other" }), { conversationId: CID });
  const un = buildRunAttentionItem(run("r3", { conversation_id: "" }), { conversationId: CID });
  assert.equal(inCtx.contextClass, "IN_CONTEXT");
  assert.equal(bg.contextClass, "BACKGROUND");
  assert.equal(un.contextClass, "UNASSOCIATED");

  // With no active conversation nothing may claim to be in context.
  assert.equal(buildRunAttentionItem(run("r4"), { conversationId: "" }).contextClass, "BACKGROUND");
});

test("the degraded item is system-wide and claims no conversation", () => {
  const item = buildDegradedAttentionItem(DEGRADED_SNAPSHOT);
  assert.equal(item.contextClass, "UNASSOCIATED");
  assert.equal(item.conversationId, null);
  assert.equal(item.runId, null);
});

// ── degraded inclusion ─────────────────────────────────────────────────────

test("degraded appears only when the certified snapshot says so", () => {
  assert.equal(buildDegradedAttentionItem({ degraded: false, degradedReasons: [] }), null);
  assert.equal(buildDegradedAttentionItem(null), null);
  assert.equal(buildDegradedAttentionItem({ degradedReasons: ["models"] }), null,
    "a reason list without the degraded flag is not degradation");
  assert.ok(buildDegradedAttentionItem(DEGRADED_SNAPSHOT));
});

test("degradation is one item, never one per subsystem", () => {
  const model = buildAttention({
    runs: [], conversationId: CID,
    snapshot: { degraded: true, degradedReasons: ["models", "gateway", "voice"] },
  });
  assert.equal(model.items.filter((i) => i.type === ATTENTION_TYPE.DEGRADED).length, 1);
});

test("degraded copy is the certified deterministic wording", () => {
  assert.equal(buildDegradedAttentionItem(DEGRADED_SNAPSHOT).subject,
    "Reduced capability: model providers.");
});

// ── ordering ───────────────────────────────────────────────────────────────

test("ordering is deterministic precedence, then backend recency", () => {
  assert.deepEqual(
    Object.entries(TYPE_PRECEDENCE).sort((a, b) => a[1] - b[1]).map(([k]) => k),
    [ATTENTION_TYPE.BLOCKED, ATTENTION_TYPE.APPROVAL_REQUIRED,
     ATTENTION_TYPE.FAILED, ATTENTION_TYPE.DEGRADED]);

  const model = buildAttention({
    runs: [
      run("f", { state: "failed", created_at: 50 }),
      run("a", { state: "awaiting_approval", created_at: 10 }),
      run("b", { state: "blocked", created_at: 1 }),
    ],
    conversationId: CID,
    snapshot: DEGRADED_SNAPSHOT,
  });
  assert.deepEqual(model.items.map((i) => i.type), [
    ATTENTION_TYPE.BLOCKED, ATTENTION_TYPE.APPROVAL_REQUIRED,
    ATTENTION_TYPE.FAILED, ATTENTION_TYPE.DEGRADED,
  ]);
});

test("same-type items order by the backend timestamp, newest first", () => {
  const model = buildAttention({
    runs: [run("old", { created_at: 10 }), run("new", { created_at: 99 })],
    conversationId: CID,
  });
  assert.deepEqual(model.items.map((i) => i.runId), ["new", "old"]);
});

// ── duplicates and collapse ────────────────────────────────────────────────

test("one run in one state is one item, however many events produced it", () => {
  // task.failed and run.state=failed describe one underlying failure.
  const model = buildAttention({
    runs: [run("r1"), run("r1"), run("r1")],
    conversationId: CID,
  });
  assert.equal(model.items.length, 1);
});

test("dedupe keys come from backend identifiers, not display text", () => {
  const model = buildAttention({
    runs: [run("r1", { objective: "same text" }), run("r2", { objective: "same text" })],
    conversationId: CID,
  });
  assert.equal(model.items.length, 2, "two real runs are two items even with identical text");
  assert.deepEqual(model.items.map((i) => i.id).sort(), ["FAILED:r1", "FAILED:r2"]);
});

test("a run cannot occupy two attention types at once", () => {
  const model = buildAttention({ runs: [run("r1", { state: "blocked" })], conversationId: CID });
  assert.equal(model.items.length, 1);
  assert.equal(model.items[0].type, ATTENTION_TYPE.BLOCKED);
});

// ── resolution ─────────────────────────────────────────────────────────────

test("an item disappears only when backend state stops justifying it", () => {
  const unresolved = buildAttention({
    runs: [run("r1", { state: "awaiting_approval" })], conversationId: CID });
  assert.equal(unresolved.items.length, 1);

  // approval resolved -> the run moves on -> the item is simply not produced
  for (const after of ["approved", "running", "completed", "cancelled"]) {
    const resolved = buildAttention({ runs: [run("r1", { state: after })], conversationId: CID });
    assert.equal(resolved.items.length, 0, `${after} must clear the approval item`);
  }
});

test("resolving one item leaves the others standing", () => {
  const before = buildAttention({
    runs: [run("a", { state: "awaiting_approval" }), run("b", { state: "blocked" })],
    conversationId: CID,
  });
  assert.equal(before.items.length, 2);

  const after = buildAttention({
    runs: [run("a", { state: "approved" }), run("b", { state: "blocked" })],
    conversationId: CID,
  });
  assert.deepEqual(after.items.map((i) => i.type), [ATTENTION_TYPE.BLOCKED]);
});

test("degraded clears when the condition clears", () => {
  assert.equal(buildAttention({ runs: [], conversationId: CID, snapshot: DEGRADED_SNAPSHOT }).items.length, 1);
  assert.equal(buildAttention({ runs: [], conversationId: CID,
    snapshot: { degraded: false, degradedReasons: [] } }).items.length, 0);
});

test("nothing resolves by elapsed time", async () => {
  const fs = await import("node:fs");
  const src = await fs.promises.readFile(new URL("./command-attention.js", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
  for (const banned of ["Date.now", "setTimeout", "setInterval", "performance.now", "new Date"]) {
    assert.ok(!code.includes(banned), `${banned} must never decide attention`);
  }
});

// ── retention (presentation only) ──────────────────────────────────────────

test("failure retention limits display without touching lifecycle truth", () => {
  const runs = Array.from({ length: 6 }, (_, i) =>
    run(`f${i}`, { state: "failed", created_at: i }));
  const model = buildAttention({ runs, conversationId: CID });

  const failed = model.items.filter((i) => i.type === ATTENTION_TYPE.FAILED);
  assert.equal(failed.length, FAILED_RETENTION_LIMIT);
  // the newest survive, by the backend's own timestamps
  assert.deepEqual(failed.map((i) => i.runId), ["f5", "f4", "f3"]);
  // and every retained item is still, in truth, unresolved
  for (const i of failed) assert.equal(i.resolutionState, "UNRESOLVED");
});

test("withheld failures are disclosed, never silently dropped", () => {
  const runs = Array.from({ length: 6 }, (_, i) => run(`f${i}`, { created_at: i }));
  assert.equal(buildAttention({ runs, conversationId: CID }).withheldFailed, 3);
  assert.equal(buildAttention({ runs: [run("f0")], conversationId: CID }).withheldFailed, 0);
});

test("retention never caps authoritative attention", () => {
  const runs = Array.from({ length: 6 }, (_, i) =>
    run(`b${i}`, { state: "blocked", created_at: i }));
  const model = buildAttention({ runs, conversationId: CID });
  assert.equal(model.items.length, 6, "blocks are never withheld");
  assert.equal(model.withheldFailed, 0);
});

// ── copy and authority boundary ────────────────────────────────────────────

test("a reason is shown only when the backend wrote one", () => {
  const without = buildRunAttentionItem(run("r1"), { conversationId: CID });
  assert.equal(without.reason, null, "absence must stay absence");

  const withReason = buildRunAttentionItem(run("r2"), {
    conversationId: CID, detail: { terminal_reason: "provider unavailable" } });
  assert.equal(withReason.reason, "provider unavailable");
});

test("approval copy is never generated", () => {
  const item = buildRunAttentionItem(run("r1", {
    state: "awaiting_approval", objective: "Publish research brief" }), { conversationId: CID });
  // The title is a fixed label and the subject is the run's own text.
  assert.equal(item.title, "Approval required");
  assert.equal(item.subject, "Publish research brief");
  assert.equal(item.reason, null);
});

test("the surface grants nothing and offers no recovery action", () => {
  const model = buildAttention({
    runs: [run("a", { state: "awaiting_approval" }), run("b", { state: "blocked" }), run("c")],
    conversationId: CID,
    snapshot: DEGRADED_SNAPSHOT,
  });
  assert.equal(model.readOnly, true);
  for (const item of model.items) {
    assert.equal(item.readOnly, true);
    assert.deepEqual(item.allowedActions, [], "no action may be offered");
    for (const key of ["approve", "approved", "deny", "execute", "retry", "clear",
      "approvalToken", "executionGranted", "authority"]) {
      assert.ok(!(key in item), `${key} must not exist on an observational item`);
    }
  }
});

test("every item carries provenance", () => {
  const model = buildAttention({
    runs: [run("a", { state: "blocked" })], conversationId: CID, snapshot: DEGRADED_SNAPSHOT });
  for (const item of model.items) {
    assert.equal(item.provenance, "REAL");
    assert.ok(item.source, "each item names the truth it came from");
  }
});

test("the panel stays empty when nothing is unresolved", () => {
  const model = buildAttention({
    runs: [run("a", { state: "completed" }), run("b", { state: "running" })],
    conversationId: CID,
    snapshot: { degraded: false, degradedReasons: [] },
  });
  assert.deepEqual(model.items, []);
  assert.equal(model.counts.total, 0);
});

// ── the hook adds no traffic and cannot repeat the Phase 6 defect ──────────

test("the attention hook fetches nothing and keys on no event name", async () => {
  const fs = await import("node:fs");
  const src = await fs.promises.readFile(new URL("./useCommandAttention.js", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
  for (const banned of ["afetch", "fetch(", "EventSource", "setInterval", "setTimeout",
    "useEffect", "last?.name", "lastName"]) {
    assert.ok(!code.includes(banned), `${banned} must not appear on the attention path`);
  }
});
