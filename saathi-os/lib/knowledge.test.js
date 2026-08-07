import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { claimKindLabel, freshnessLabel } from "./knowledge.js";

describe("knowledge UI helpers", () => {
  it("labels freshness states", () => {
    assert.equal(freshnessLabel("fresh").label, "Fresh");
    assert.equal(freshnessLabel("stale").tone, "warn");
    assert.equal(freshnessLabel("expired").tone, "bad");
    assert.equal(freshnessLabel("conflicting").label, "Conflict");
    assert.equal(freshnessLabel("").label, "Unknown");
  });

  it("labels claim kinds", () => {
    assert.equal(claimKindLabel("grounded_fact"), "Grounded fact");
    assert.equal(claimKindLabel("inference"), "Inference");
    assert.equal(claimKindLabel("recommendation"), "Recommendation");
    assert.equal(claimKindLabel("unresolved_conflict"), "Unresolved conflict");
    assert.equal(claimKindLabel("unavailable_evidence"), "No evidence");
  });

  it("does not invent grounded status from empty labels", () => {
    assert.equal(claimKindLabel(undefined), "Answer");
    assert.equal(freshnessLabel(null).tone, "muted");
  });
});
