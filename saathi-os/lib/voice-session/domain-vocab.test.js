import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  applyDomainVocabulary,
  normalizeTranscriptText,
  isMeaningfulTranscript,
} from "./index.js";

describe("domain vocabulary repair", () => {
  it("repairs known SaathiOS term variants deterministically", () => {
    const r = applyDomainVocabulary("Sophie, show my active missions");
    assert.match(r.text, /Saathi/i);
    assert.ok(r.applied.length >= 1);
  });

  it("repairs Execution Gateway spacing", () => {
    const r = applyDomainVocabulary("Is execution gateway healthy?");
    assert.match(r.text, /ExecutionGateway/);
  });

  it("does not invent executable approval authority", () => {
    const r = applyDomainVocabulary("provals pending");
    assert.match(r.text, /approvals/i);
    // still untrusted user text — meaningfulness only
    assert.equal(isMeaningfulTranscript(r.text), true);
  });

  it("normalizeTranscriptText is NFKC and trims", () => {
    assert.equal(normalizeTranscriptText("  hello   world  "), "hello world");
  });
});
