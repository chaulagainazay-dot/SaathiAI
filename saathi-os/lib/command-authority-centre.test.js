import test from "node:test";
import assert from "node:assert/strict";

import {
  AUTHORITY_TYPE,
  AUTHORITY_PROVENANCE,
  AUTHORITY_TITLE,
  AUTHORITY_PRECEDENCE,
  AUTHORITY_INVALIDATING_EVENTS,
  PROVENANCE_LABEL,
  buildAuthorityItem,
  buildAuthorityCentre,
  shouldRefreshAuthority,
} from "./command-authority-centre.js";

const CID = "cmd-phase10";

function apiItem(over = {}) {
  return {
    id: "APPROVAL_REQUIRED:r1",
    type: "APPROVAL_REQUIRED",
    run_id: "r1",
    conversation_id: CID,
    objective: "Publish the research brief",
    strategy: "test_approval",
    state: "awaiting_approval",
    reason: "This action is waiting for your approval.",
    detail_code: "",
    created_at: 10,
    updated_at: 20,
    provenance: "AUTHORITATIVE_APPROVAL_STORE",
    approvals: [{ approval_id: "a1", agent: "executor", action: "publish", risk: 3 }],
    can_user_act: true,
    read_only: true,
    ...over,
  };
}

// ── types stay distinct ────────────────────────────────────────────────────

test("only real authority types exist here", () => {
  assert.deepEqual(Object.keys(AUTHORITY_TYPE).sort(), ["APPROVAL_REQUIRED", "BLOCKED"]);
  // Attention owns these; duplicating them would make this a second panel.
  for (const absent of ["DEGRADED", "FAILED"]) {
    assert.ok(!(absent in AUTHORITY_TYPE), `${absent} is not an authority refusal`);
  }
});

test("an unrecognised type is never rendered as authority", () => {
  for (const type of ["DEGRADED", "FAILED", "WARNING", "", undefined, "approval"]) {
    const item = buildAuthorityItem(apiItem({ type }), { conversationId: CID });
    if (type === "approval") assert.equal(item, null);
    else assert.equal(item, null, `${type} must not become an authority item`);
  }
});

test("approval and blocked read as themselves", () => {
  assert.equal(AUTHORITY_TITLE[AUTHORITY_TYPE.APPROVAL_REQUIRED], "Approval required");
  assert.equal(AUTHORITY_TITLE[AUTHORITY_TYPE.BLOCKED], "Blocked");
});

// ── provenance ─────────────────────────────────────────────────────────────

test("provenance is trusted only when the backend names a known source", () => {
  const known = buildAuthorityItem(apiItem(), { conversationId: CID });
  assert.equal(known.provenance, AUTHORITY_PROVENANCE.APPROVAL_STORE);

  // An unknown or absent provenance falls back to the weaker claim.
  for (const raw of ["SOMETHING_ELSE", "", undefined, "TRADING_GUARDIAN"]) {
    const item = buildAuthorityItem(apiItem({ provenance: raw }), { conversationId: CID });
    assert.equal(item.provenance, AUTHORITY_PROVENANCE.RUN_STATE,
      "an unrecognised source must not be presented as a stronger one");
  }
});

test("provenance is displayed, never inferred from wording", () => {
  assert.equal(PROVENANCE_LABEL[AUTHORITY_PROVENANCE.APPROVAL_STORE], "Approval store");
  assert.equal(PROVENANCE_LABEL[AUTHORITY_PROVENANCE.RUN_STATE], "Run authority state");
});

// ── copy ───────────────────────────────────────────────────────────────────

test("authority wording comes from the contract, never generated", () => {
  const item = buildAuthorityItem(apiItem(), { conversationId: CID });
  assert.equal(item.reason, "This action is waiting for your approval.");
  assert.equal(item.subject, "Publish the research brief", "the run's own text");

  // Absent stays absent rather than being filled in.
  const bare = buildAuthorityItem(apiItem({ reason: "", detail_code: "" }), { conversationId: CID });
  assert.equal(bare.reason, null);
  assert.equal(bare.detailCode, null);
});

// ── context ────────────────────────────────────────────────────────────────

test("authority classifies context without guessing", () => {
  assert.equal(buildAuthorityItem(apiItem(), { conversationId: CID }).contextClass, "IN_CONTEXT");
  assert.equal(buildAuthorityItem(apiItem({ conversation_id: "other" }),
    { conversationId: CID }).contextClass, "BACKGROUND");
  assert.equal(buildAuthorityItem(apiItem({ conversation_id: "" }),
    { conversationId: CID }).contextClass, "UNASSOCIATED");
});

// ── ordering ───────────────────────────────────────────────────────────────

test("a block outranks an approval", () => {
  // Approving cannot clear a block, so a block must never sit beneath one.
  assert.ok(AUTHORITY_PRECEDENCE[AUTHORITY_TYPE.BLOCKED]
    < AUTHORITY_PRECEDENCE[AUTHORITY_TYPE.APPROVAL_REQUIRED]);

  const model = buildAuthorityCentre({
    items: [
      apiItem({ id: "APPROVAL_REQUIRED:a", run_id: "a", updated_at: 999 }),
      apiItem({ id: "BLOCKED:b", run_id: "b", type: "BLOCKED",
        state: "blocked", approvals: [], updated_at: 1 }),
    ],
    conversationId: CID,
  });
  assert.deepEqual(model.items.map((i) => i.type),
    [AUTHORITY_TYPE.BLOCKED, AUTHORITY_TYPE.APPROVAL_REQUIRED]);
});

test("same-type items order by the backend timestamp", () => {
  const model = buildAuthorityCentre({
    items: [
      apiItem({ id: "APPROVAL_REQUIRED:old", run_id: "old", updated_at: 5 }),
      apiItem({ id: "APPROVAL_REQUIRED:new", run_id: "new", updated_at: 50 }),
    ],
    conversationId: CID,
  });
  assert.deepEqual(model.items.map((i) => i.runId), ["new", "old"]);
});

// ── dedupe ─────────────────────────────────────────────────────────────────

test("one decision is one row however many events produced it", () => {
  const model = buildAuthorityCentre({
    items: [apiItem(), apiItem(), apiItem()], conversationId: CID });
  assert.equal(model.items.length, 1);
});

test("dedupe uses identifiers, never display text", () => {
  const model = buildAuthorityCentre({
    items: [
      apiItem({ id: "APPROVAL_REQUIRED:r1", run_id: "r1", objective: "same" }),
      apiItem({ id: "APPROVAL_REQUIRED:r2", run_id: "r2", objective: "same" }),
    ],
    conversationId: CID,
  });
  assert.equal(model.items.length, 2);
});

// ── the authority boundary ─────────────────────────────────────────────────

test("the surface grants nothing and offers no control", () => {
  const model = buildAuthorityCentre({
    items: [apiItem(), apiItem({ id: "BLOCKED:b", run_id: "b", type: "BLOCKED",
      state: "blocked", approvals: [] })],
    conversationId: CID,
  });
  assert.equal(model.readOnly, true);
  for (const item of model.items) {
    assert.equal(item.readOnly, true);
    assert.deepEqual(item.allowedActions, []);
    for (const key of ["approve", "deny", "retry", "override", "execute",
      "clearBlock", "unlock", "approvalToken", "token", "credential"]) {
      assert.ok(!(key in item), `${key} must not exist on an observational item`);
    }
  }
});

test("approval identifiers are carried, secrets are not", () => {
  const item = buildAuthorityItem(apiItem(), { conversationId: CID });
  assert.deepEqual(item.approvalIds, ["a1"]);
  assert.equal(item.approvalCount, 1);
  assert.ok(!JSON.stringify(item).toLowerCase().includes("token"));
});

test("canUserAct reports availability, never permission", () => {
  // A decision exists for the owner...
  assert.equal(buildAuthorityItem(apiItem(), { conversationId: CID }).canUserAct, true);
  // ...but an approval-held run with no approval record offers nothing.
  assert.equal(buildAuthorityItem(apiItem({ approvals: [] }),
    { conversationId: CID }).canUserAct, false);
  // A block is never the owner's to satisfy by deciding.
  assert.equal(buildAuthorityItem(apiItem({ type: "BLOCKED", state: "blocked", approvals: [] }),
    { conversationId: CID }).canUserAct, false);
});

test("execution readiness is never asserted", () => {
  // Nothing available here establishes it, so the surface makes no claim --
  // including when the authority list is empty.
  assert.equal(buildAuthorityCentre({ items: [], conversationId: CID }).executionReadiness, null);
  assert.equal(buildAuthorityCentre({ items: [apiItem()], conversationId: CID }).executionReadiness, null);
});

test("an approval-held run with no approval record falls back, not forward", () => {
  // Fail closed: report the weaker provenance rather than implying the approval
  // store asserted something it did not.
  const item = buildAuthorityItem(
    apiItem({ approvals: [], provenance: "AUTHORITATIVE_RUN_STATE" }),
    { conversationId: CID });
  assert.equal(item.provenance, AUTHORITY_PROVENANCE.RUN_STATE);
  assert.equal(item.canUserAct, false);
});

// ── refresh safety ─────────────────────────────────────────────────────────

test("authority refreshes only on events that can change a decision", () => {
  for (const name of AUTHORITY_INVALIDATING_EVENTS) {
    assert.equal(shouldRefreshAuthority(`agentrun.${name}`), true);
  }
  for (const name of ["task.started", "task.completed", "agent.started",
    "memory.retrieved", "verification.passed", "heartbeat"]) {
    assert.equal(shouldRefreshAuthority(`agentrun.${name}`), false, `${name} must not refetch`);
  }
  assert.equal(shouldRefreshAuthority("approval.resolved"), false, "unprefixed is not a run event");
  assert.equal(shouldRefreshAuthority(""), false);
});

test("the hook makes one bounded read and keys on the event object", async () => {
  const fs = await import("node:fs");
  const src = await fs.promises.readFile(
    new URL("./useCommandAuthorityCentre.js", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");

  assert.equal((code.match(/afetch\(/g) || []).length, 1, "exactly one request site");
  assert.match(code, /agents\/authority/);
  assert.ok(!/approvals\?|\/runs\/\$\{/.test(code), "no per-row approval fetch");
  for (const banned of ["setInterval", "setTimeout", "EventSource", "lastName"]) {
    assert.ok(!code.includes(banned), `${banned} must not drive authority`);
  }
  // The Phase 6 defect: keying on the name drops repeated events.
  assert.match(code, /\}, \[lastEvent, load\]\)/);
});

test("the panel renders no mutation control", async () => {
  const fs = await import("node:fs");
  const src = await fs.promises.readFile(
    new URL("../components/command/AuthorityCentre.jsx", import.meta.url), "utf8");
  for (const tag of ["<button", "<input", "<form", "onClick", "role=\"button\""]) {
    assert.ok(!src.includes(tag), `${tag} must not appear on a read-only authority surface`);
  }
});

test("empty means nothing is held, not that anything is cleared", () => {
  const model = buildAuthorityCentre({ items: [], conversationId: CID });
  assert.deepEqual(model.items, []);
  assert.equal(model.counts.total, 0);
  assert.equal(model.executionReadiness, null);
});
