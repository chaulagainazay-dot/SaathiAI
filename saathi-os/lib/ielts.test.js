import { describe, it } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { IELTS_NOTICE, ieltsActions, ieltsFeedbackSpeech } from "./ielts.js";

describe("IELTSAlert frontend contract", () => {
  it("labels bounded limitations explicitly", () => {
    assert.match(IELTS_NOTICE.scoring, /never official/i);
    assert.match(IELTS_NOTICE.availability, /not live/i);
    assert.match(IELTS_NOTICE.payment, /no payment settlement/i);
  });

  it("mutations use the authenticated platform IELTS namespace", async () => {
    const seen = [];
    const original = globalThis.fetch;
    globalThis.fetch = async (url, options) => {
      seen.push({ url: String(url), options });
      return new Response(JSON.stringify({ ok: true }), {
        status: 200, headers: { "content-type": "application/json" },
      });
    };
    try {
      await ieltsActions.goal({
        exam_type: "academic", target_band: 7, planned_test_date: "2030-01-01",
      }, "test-token");
      assert.match(seen[0].url, /\/api\/v1\/platform\/ielts\/goals$/);
      assert.equal(seen[0].options.method, "POST");
      assert.equal(seen[0].options.headers["X-Platform-Token"], "test-token");
    } finally {
      globalThis.fetch = original;
    }
  });

  it("workspace exposes required semantic states and bounded journeys", () => {
    const source = fs.readFileSync(
      new URL("../components/ielts/IELTSWorkspace.jsx", import.meta.url), "utf8"
    );
    for (const text of [
      "Sign in required", "Permission restricted", "Retry", "No exam goal yet",
      "Structured practice", "pronunciation will not be assessed",
      "Fixture alerts evaluated", "manual payment", "evidence timeline",
      "Read aloud", "Read IELTS feedback aloud", 'profileId: "yeti_teacher"',
    ]) assert.ok(source.includes(text), text);
    assert.ok(source.includes('aria-label="IELTSAlert workspace"'));
    assert.ok(source.includes('aria-live="polite"'));
    assert.ok(source.includes("p.owner_id !== userId"), "self-review controls must stay hidden");
    assert.ok(source.includes("pathname.endsWith(`/practice/${skill}`)"));
    assert.ok(source.includes("voiceOutput.speak(ieltsFeedbackSpeech(r)"));
    assert.equal(source.includes("speechSynthesis"), false);
  });

  it("turns only bounded backend feedback into transparent speech text", () => {
    assert.equal(ieltsFeedbackSpeech({ body: { response: "private answer" } }), "");
    const text = ieltsFeedbackSpeech({
      body: {
        response: "private answer must not be repeated",
        feedback: {
          label: "practice estimate",
          official: false,
          overall_level: "developing",
          criteria: {
            task_response: {
              level: "developing",
              feedback: "Connect each claim to the prompt.",
            },
          },
          limitations: ["Manual review is still required."],
        },
      },
    });
    assert.match(text, /practice estimate/i);
    assert.match(text, /task response/i);
    assert.match(text, /never an official IELTS score/i);
    assert.equal(text.includes("private answer"), false);
    assert.ok(text.length <= 4_000);
  });

  it("global sign out clears the centralized platform context", () => {
    const source = fs.readFileSync(
      new URL("../app/security/page.jsx", import.meta.url), "utf8"
    );
    assert.ok(source.includes('plat("/auth/logout"'));
    assert.ok(source.includes('setToken("")'));
  });
});
