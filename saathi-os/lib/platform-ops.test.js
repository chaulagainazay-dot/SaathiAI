import assert from "node:assert/strict";
import test from "node:test";

import {
  canCancelExecution,
  requiresDestructiveConfirmation,
  runtimeTone,
  safeAuthorityOptions,
} from "./platform-ops.js";

test("runtime operations UI treats terminal executions as immutable", () => {
  assert.equal(canCancelExecution({ state: "PAUSED" }), true);
  assert.equal(canCancelExecution({ state: "COMPLETED" }), false);
  assert.equal(canCancelExecution({ state: "TIMED_OUT" }), false);
});

test("binding authority choices cannot exceed the displayed role ceiling", () => {
  assert.deepEqual(safeAuthorityOptions("viewer"), ["READ_ONLY"]);
  assert.deepEqual(safeAuthorityOptions("operator"), ["READ_ONLY", "LOCAL_MUTATION"]);
  assert.equal(safeAuthorityOptions("owner").includes("SECURITY_SENSITIVE"), false);
  assert.equal(safeAuthorityOptions("admin").includes("FINANCIAL_EXECUTION"), false);
});

test("irreversible administration actions require confirmation", () => {
  assert.equal(requiresDestructiveConfirmation("REVOKE_BINDING"), true);
  assert.equal(requiresDestructiveConfirmation("RESOLVE_FAILED"), true);
  assert.equal(requiresDestructiveConfirmation("MARK_REVIEWED"), false);
  assert.equal(runtimeTone("REVOKED"), "error");
});
