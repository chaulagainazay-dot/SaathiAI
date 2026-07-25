import assert from "node:assert/strict";
import test from "node:test";

import {
  attentionSeverity,
  canCancelExecution,
  canExportEvidence,
  canPreviewRetention,
  EVIDENCE_EXPORT_KINDS,
  isProductionAuthorized,
  requiresDestructiveConfirmation,
  runtimeTone,
  safeAuthorityOptions,
  safetyBadges,
  uiStateDescriptor,
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

test("M54 retention preview is owner/admin only", () => {
  assert.equal(canPreviewRetention("viewer"), false);
  assert.equal(canPreviewRetention("operator"), false);
  assert.equal(canPreviewRetention("owner"), true);
  assert.equal(canPreviewRetention("admin"), true);
});

test("M54 evidence export is available to any authenticated platform role", () => {
  assert.equal(canExportEvidence("viewer"), true);
  assert.equal(canExportEvidence("stranger"), false);
  assert.ok(EVIDENCE_EXPORT_KINDS.includes("certification_manifest"));
  assert.ok(!EVIDENCE_EXPORT_KINDS.includes("raw_arguments"));
});

test("M54 production authorization is never honored client-side", () => {
  assert.equal(isProductionAuthorized({ environment: { production_authorized: true } }), false);
  assert.equal(isProductionAuthorized(null), false);
});

test("M54 attention severity ranks uncertain dispatch as critical", () => {
  assert.equal(attentionSeverity("DISPATCH_OUTCOME_UNCERTAIN"), "critical");
  assert.equal(attentionSeverity("APPROVAL_REQUIRED"), "info");
  assert.equal(attentionSeverity("BINDING_SUSPENDED"), "warn");
});

test("M54 UI state descriptors cover all required operator states", () => {
  for (const key of [
    "loading", "empty", "denied", "SUSPENDED", "REVOKED", "WAITING_APPROVAL",
    "PAUSED", "UNCERTAIN", "FAILED", "CANCELLED", "TIMED_OUT", "COMPLETED",
  ]) {
    assert.ok(uiStateDescriptor(key).label, `${key} has a label`);
  }
  assert.equal(uiStateDescriptor("COMPLETED").tone, "ok");
});

test("M54 safety badges always assert disabled execution surfaces", () => {
  const badges = safetyBadges({ safety: {} }).map((b) => b.label).join(" ");
  assert.ok(badges.includes("DISABLED"));
  assert.ok(badges.includes("DRY_RUN_ONLY"));
  assert.ok(badges.includes("UNENGAGED_ADVISORY_ONLY"));
});
