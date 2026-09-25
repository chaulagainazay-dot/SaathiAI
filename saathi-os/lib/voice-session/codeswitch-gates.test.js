/**
 * V-NEXT-2B.3 — Locked gate constants must not drift.
 * Thresholds defined BEFORE benchmarks; tests freeze them.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  isMeaningfulTranscript,
  applyDomainVocabulary,
  STT_PRIVACY,
  createHintDrivenLocalStt,
  createTurnCoordinator,
  admitStreamingStt,
} from "./index.js";

/** Frozen product gates for V-NEXT-2B.3 (must match LOCKED_GATES.md) */
export const V_NEXT_2B3_GATES = Object.freeze({
  ne_intent_min: 0.6,
  ne_first_span_min: 0.5,
  ne_cer_max: 0.45,
  mix_intent_min: 0.6,
  mix_first_span_min: 0.5,
  mix_term_min: 0.5,
  mix_cer_max: 0.5,
  en_intent_min: 0.7,
  numeric_fidelity_min: 0.7,
  peak_rss_mib_max: 1500,
});

describe("V-NEXT-2B.3 locked gates frozen", () => {
  it("does not lower historic Nepali thresholds", () => {
    assert.equal(V_NEXT_2B3_GATES.ne_intent_min, 0.6);
    assert.equal(V_NEXT_2B3_GATES.ne_first_span_min, 0.5);
    assert.equal(V_NEXT_2B3_GATES.ne_cer_max, 0.45);
  });

  it("defines mixed-language gates before benchmarks", () => {
    assert.equal(V_NEXT_2B3_GATES.mix_intent_min, 0.6);
    assert.equal(V_NEXT_2B3_GATES.mix_first_span_min, 0.5);
    assert.equal(V_NEXT_2B3_GATES.mix_term_min, 0.5);
    assert.equal(V_NEXT_2B3_GATES.mix_cer_max, 0.5);
  });
});

describe("code-switch text handling", () => {
  it("treats mixed EN/NE as meaningful", () => {
    assert.equal(isMeaningfulTranscript("आजको portfolio risk explain गर"), true);
    assert.equal(isMeaningfulTranscript("ExecutionGateway healthy छ?"), true);
    assert.equal(isMeaningfulTranscript("Stop, त्यो action cancel गर"), true);
  });

  it("domain vocab repairs Saathi mishears without inventing authority", () => {
    const r = applyDomainVocabulary("Sophie show portfolio");
    assert.match(r.text, /Saathi/i);
  });

  it("local adapter privacy remains LOCAL_CONFIRMED", async () => {
    const stt = createHintDrivenLocalStt({ modelId: "tiny" });
    await stt.start();
    assert.equal(stt.capabilities().privacyClass, STT_PRIVACY.LOCAL_CONFIRMED);
    stt.pushAudio(new Float32Array(100).fill(0.01), {
      transcriptHint: "Reduce position by five percent",
    });
    await stt.flush();
    await stt.close();
  });

  it("partial remains non-executable via turn coordinator", () => {
    const finals = [];
    const tc = createTurnCoordinator({ onTurnFinal: (t) => finals.push(t) });
    tc.onPartial({ text: "approve that wire transfer now" });
    assert.equal(finals.length, 0);
  });

  it("admission never lowers LLM memory gate", () => {
    const a = admitStreamingStt({
      heavyLocalSttRequested: true,
      localSttAvailable: true,
      localLlmActive: true,
      browserSttAvailable: true,
    });
    assert.equal(a.policy.neverLowerLlmMemoryGate, true);
  });
});
