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

  // Phase 11 adds a second site: one bounded read, and one mutation. Nothing
  // per-row, and nothing that polls.
  assert.equal((code.match(/afetch\(/g) || []).length, 2,
    "one authority read and one approval mutation");
  assert.match(code, /agents\/authority/);
  assert.match(code, /\/approve/);
  assert.ok(!/approvals\?limit|per-row/.test(code), "no per-row approval fetch");
  for (const banned of ["setInterval", "setTimeout", "EventSource", "lastName"]) {
    assert.ok(!code.includes(banned), `${banned} must not drive authority`);
  }
  // The Phase 6 defect: keying on the name drops repeated events.
  assert.match(code, /\}, \[lastEvent, load\]\)/);
});

test("the panel renders only the two approval decisions", async () => {
  // Supersedes the Phase 10 rule that no control existed at all. Phase 11 adds
  // approve and deny and nothing else: the forbidden verbs stay forbidden.
  const fs = await import("node:fs");
  const src = await fs.promises.readFile(
    new URL("../components/command/AuthorityCentre.jsx", import.meta.url), "utf8");

  assert.match(src, /data-testid="ac-approve"/);
  assert.match(src, /data-testid="ac-deny"/);
  for (const forbidden of ["ac-retry", "ac-override", "ac-unblock", "ac-execute",
    "Execute", "Override", "Unblock", "Continue", "Clear block"]) {
    assert.ok(!src.includes(forbidden), `${forbidden} must not appear`);
  }
  assert.ok(!src.includes("<form"), "no form submission path");
});

test("empty means nothing is held, not that anything is cleared", () => {
  const model = buildAuthorityCentre({ items: [], conversationId: CID });
  assert.deepEqual(model.items, []);
  assert.equal(model.counts.total, 0);
  assert.equal(model.executionReadiness, null);
});

// ── Phase 11: the approval mutation contract ───────────────────────────────

test("a control binds to one specific approval record", async () => {
  const { buildAuthorityItem: b } = await import("./command-authority-centre.js");
  const one = b(apiItem(), { conversationId: CID });
  assert.equal(one.actionableApprovalId, "a1", "the record's own id, never an index");
  assert.equal(one.actionSummary, "publish");

  // Several pending approvals: the surface must not choose one for the owner.
  const many = b(apiItem({ approvals: [
    { approval_id: "a1", action: "x" }, { approval_id: "a2", action: "y" }] }),
    { conversationId: CID });
  assert.equal(many.actionableApprovalId, null);
  assert.equal(many.approvalCount, 2);
});

test("nothing is actionable without a pending approval", async () => {
  const { buildAuthorityItem: b } = await import("./command-authority-centre.js");
  const none = b(apiItem({ approvals: [] }), { conversationId: CID });
  assert.equal(none.actionableApprovalId, null);
  assert.equal(none.canUserAct, false);
});

test("a blocked item is never actionable", async () => {
  const { buildAuthorityItem: b } = await import("./command-authority-centre.js");
  const blocked = b(apiItem({ type: "BLOCKED", state: "blocked", approvals: [] }),
    { conversationId: CID });
  assert.equal(blocked.canUserAct, false);
  assert.equal(blocked.actionableApprovalId, null, "BLOCKED recovery stays out of scope");
});

test("confirmation copy is deterministic and promises no execution", async () => {
  const { CONFIRM_COPY } = await import("./command-authority-centre.js");
  assert.equal(CONFIRM_COPY.approve.title, "Approve this action?");
  assert.equal(CONFIRM_COPY.approve.confirm, "Approve");
  assert.equal(CONFIRM_COPY.deny.confirm, "Deny");
  assert.equal(CONFIRM_COPY.approve.cancel, "Cancel");

  assert.match(CONFIRM_COPY.approve.body, /does not guarantee execution/);
  for (const copy of Object.values(CONFIRM_COPY)) {
    for (const banned of ["execution ready", "safe to execute", "approved for execution",
      "will execute", "executed"]) {
      assert.ok(!copy.body.toLowerCase().includes(banned), `${banned} must not be promised`);
    }
  }
});

test("every mutation failure is mapped deterministically", async () => {
  const { mutationErrorFor, MUTATION_ERROR } = await import("./command-authority-centre.js");
  assert.equal(mutationErrorFor(401), MUTATION_ERROR[401]);
  assert.equal(mutationErrorFor(403), MUTATION_ERROR[403]);
  assert.equal(mutationErrorFor(404), MUTATION_ERROR[404]);
  assert.equal(mutationErrorFor(409), MUTATION_ERROR[409]);
  assert.equal(mutationErrorFor(410), MUTATION_ERROR[410]);
  assert.equal(mutationErrorFor(null), MUTATION_ERROR.NETWORK);
  assert.equal(mutationErrorFor(500), MUTATION_ERROR.SERVER);
  // None of them claims a decision was made.
  for (const msg of Object.values(MUTATION_ERROR)) {
    assert.ok(!/approved|denied/i.test(msg), `"${msg}" must not imply an outcome`);
  }
});

test("the mutation requests authority and never grants it", async () => {
  const fs = await import("node:fs");
  const src = await fs.promises.readFile(
    new URL("./useCommandAuthorityCentre.js", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");

  assert.match(code, /\/approve/, "it calls the existing approval route");
  assert.match(code, /method: "POST"/);
  assert.match(code, /approval_id: approvalId/, "bound to the approval record");
  assert.match(code, /runs\/\$\{encodeURIComponent\(runId\)\}/, "and to its run");

  // No local authority: the model is never rewritten on success.
  for (const banned of ["setItems(items.filter", "resolutionState:", "status: \"approved\"",
    "optimistic"]) {
    assert.ok(!code.includes(banned), `${banned} would be optimistic authority`);
  }
  // Success and failure both re-read the server.
  assert.ok((code.match(/await load\(\)/g) || []).length >= 2,
    "authority is re-read rather than assumed");
});

test("the row does not remove itself on success", async () => {
  const fs = await import("node:fs");
  const src = await fs.promises.readFile(
    new URL("../components/command/AuthorityCentre.jsx", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\/|\{\/\*[\s\S]*?\*\/\}/g, "");
  for (const banned of ["setResolved", "filter((r) =>", "hidden = true", "setRemoved"]) {
    assert.ok(!code.includes(banned), "a row disappears only when the server says so");
  }
  // A submit in flight cannot be submitted again.
  assert.match(code, /if \(busy\) return;/);
  assert.match(code, /disabled=\{busy\}/);
});

test("the confirmation is a real dialog", async () => {
  const fs = await import("node:fs");
  const src = await fs.promises.readFile(
    new URL("../components/command/AuthorityCentre.jsx", import.meta.url), "utf8");
  assert.match(src, /role="dialog"/);
  assert.match(src, /aria-modal="true"/);
  assert.match(src, /aria-labelledby=/);
  assert.match(src, /confirmRef\.current\?\.focus\(\)/, "focus moves into the dialog");
  assert.match(src, /e\.key === "Escape"/, "Escape cancels");
  assert.match(src, /role="alert"/, "errors are announced");
  // Buttons are named, never icon-only.
  assert.match(src, /copy\.confirm/);
  assert.match(src, /\{copy\.cancel\}/);
});

test("no execution-readiness claim survives anywhere on the surface", async () => {
  const fs = await import("node:fs");
  for (const rel of ["../components/command/AuthorityCentre.jsx",
    "./command-authority-centre.js", "./useCommandAuthorityCentre.js"]) {
    const src = await fs.promises.readFile(new URL(rel, import.meta.url), "utf8");
    const code = src.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
    for (const banned of ["EXECUTION READY", "Approved for execution", "Safe to execute"]) {
      assert.ok(!code.includes(banned), `${banned} must never be shown (${rel})`);
    }
  }
});

test("the dialog's buttons are styled by the component that renders them", async () => {
  // Regression of a known class: styled-jsx only scopes markup rendered by the
  // component declaring the block, so button rules living in AuthorityRow never
  // reached the confirmation's buttons and they rendered as bare 23px text.
  const fs = await import("node:fs");
  const src = await fs.promises.readFile(
    new URL("../components/command/AuthorityCentre.jsx", import.meta.url), "utf8");
  const dialog = src.slice(src.indexOf("function ConfirmDialog"), src.indexOf("function AuthorityRow"));
  assert.match(dialog, /<style jsx>/, "the dialog declares its own block");
  assert.match(dialog, /\.ac-btn\s*\{[^}]*min-height:\s*36px/s,
    "its buttons need a real touch target");
});
