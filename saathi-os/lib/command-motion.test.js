import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  voicePresentation,
  riskMotionTone,
  proposalMotionTone,
  allowVoiceLoop,
  relatedEvidenceEvents,
  MOTION_TECH,
  VOICE_SESSION_STATES,
  PROPOSAL_LIFECYCLE_STATES,
} from "./command-motion.js";

describe("command-motion UI-NEXT-3.1", () => {
  it("covers full VoiceSession vocabulary", () => {
    for (const s of VOICE_SESSION_STATES) {
      const p = voicePresentation(s);
      assert.equal(p.state, s);
      assert.ok(p.label);
    }
  });

  it("disables voice loops under reduced motion", () => {
    assert.equal(allowVoiceLoop("LISTENING", false), true);
    assert.equal(allowVoiceLoop("LISTENING", true), false);
    assert.equal(allowVoiceLoop("THINKING", true), false);
    assert.equal(allowVoiceLoop("SPEAKING", true), false);
    assert.equal(allowVoiceLoop("READY", false), false);
  });

  it("risk tones never invent status", () => {
    assert.equal(riskMotionTone("HEALTHY"), "ok");
    assert.equal(riskMotionTone("WARNING"), "warn");
    assert.equal(riskMotionTone("BREACHED"), "crit");
    assert.equal(riskMotionTone("RECONCILIATION_REQUIRED"), "crit");
    assert.equal(riskMotionTone(null), "muted");
  });

  it("proposal tones never imply execution success green", () => {
    assert.equal(proposalMotionTone("APPROVED"), "warn");
    assert.equal(proposalMotionTone("READY_FOR_APPROVAL"), "warn");
    assert.equal(proposalMotionTone("RISK_BLOCKED"), "crit");
    assert.ok(PROPOSAL_LIFECYCLE_STATES.includes("STALE_PROPOSAL"));
  });

  it("evidence linking only uses real ids", () => {
    const events = [
      { id: "ev1", type: "risk_breach", related_ids: ["pprop_1"] },
      { id: "ev2", type: "mission", mission_id: "m1" },
      { id: "ev3", type: "noise" },
    ];
    const hit = relatedEvidenceEvents(events, { id: "pprop_1" });
    assert.equal(hit.length, 1);
    assert.equal(hit[0].id, "ev1");
    const none = relatedEvidenceEvents(events, { id: "missing" });
    assert.equal(none.length, 0);
  });

  it("defers GSAP Lottie Three.js", () => {
    assert.equal(MOTION_TECH.gsap, "GSAP_RUNTIME_DEFERRED");
    assert.equal(MOTION_TECH.lottie, "LOTTIE_RUNTIME_DEFERRED");
    assert.equal(MOTION_TECH.three, "THREE_JS_DEFERRED");
    assert.equal(MOTION_TECH.primary, "CSS_SUFFICIENT");
  });
});
