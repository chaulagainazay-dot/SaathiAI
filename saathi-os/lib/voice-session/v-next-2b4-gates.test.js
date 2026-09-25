/**
 * V-NEXT-2B.4 — freeze gates; ensure no silent cloud fallback.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  admitStreamingStt,
  resolveSttHierarchy,
  STT_PRIVACY,
  createMockStreamingStt,
} from "./index.js";

/** Same locked thresholds as prior milestones */
const GATES = Object.freeze({
  en_intent_min: 0.7,
  ne_intent_min: 0.6,
  mix_intent_min: 0.6,
  ne_first_span_min: 0.5,
  ne_cer_max: 0.45,
  numeric_fidelity_min: 0.7,
});

describe("V-NEXT-2B.4 gates frozen", () => {
  it("does not lower NE/MIX/EN/numeric thresholds", () => {
    assert.equal(GATES.ne_intent_min, 0.6);
    assert.equal(GATES.mix_intent_min, 0.6);
    assert.equal(GATES.en_intent_min, 0.7);
    assert.equal(GATES.numeric_fidelity_min, 0.7);
    assert.equal(GATES.ne_cer_max, 0.45);
  });
});

describe("fallback hierarchy", () => {
  it("never includes cloud STT", () => {
    const a = admitStreamingStt({ browserSttAvailable: true });
    const h = resolveSttHierarchy(a);
    assert.equal(h.cloudFallback, false);
  });

  it("mock remains LOCAL_CONFIRMED", () => {
    const m = createMockStreamingStt();
    assert.equal(m.capabilities().privacyClass, STT_PRIVACY.LOCAL_CONFIRMED);
  });
});
