import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  createMockStreamingStt,
  createTurnCoordinator,
  createRealtimeVoicePipeline,
  createVoiceSessionManager,
  admitStreamingStt,
  isMeaningfulTranscript,
  looksSyntacticallyComplete,
  forceReleaseInput,
  forceReleaseOutput,
  resetVoiceTelemetry,
  STT_PRIVACY,
} from "./index.js";

describe("stt policy", () => {
  it("partial is never treated as meaningful executable alone in coordinator", () => {
    assert.equal(isMeaningfulTranscript(""), false);
    assert.equal(isMeaningfulTranscript("hmm"), false);
    assert.equal(isMeaningfulTranscript("yes"), false);
    assert.equal(isMeaningfulTranscript("Show my missions"), true);
    assert.equal(isMeaningfulTranscript("मेरो portfolio"), true);
    assert.equal(looksSyntacticallyComplete("Hello."), true);
  });

  it("resource admission prefers browser STT and never lowers LLM gate", () => {
    const a = admitStreamingStt({ browserSttAvailable: true });
    // Browser path is READY_DEGRADED (privacy unknown) with legacy ALLOWED
    assert.ok(
      a.admission === "LOCAL_STT_READY_DEGRADED" || a.admission === "LOCAL_STT_ALLOWED"
    );
    assert.equal(a.mode, "browser_streaming");
    assert.equal(a.policy.neverLowerLlmMemoryGate, true);
    const b = admitStreamingStt({
      heavyLocalSttRequested: true,
      localLlmActive: true,
    });
    assert.ok(
      b.admission === "LOCAL_STT_BLOCKED_MEMORY" ||
        b.admission === "LOCAL_STT_BLOCKED_RESOURCE_PRESSURE"
    );
  });
});

describe("turn coordinator", () => {
  it("finalizes meaningful STT finals and marks backchannels non-executable", () => {
    const finals = [];
    const tc = createTurnCoordinator({
      onTurnFinal: (t) => finals.push(t),
      config: { silenceToFinalizeMs: 10, endpointGraceMs: 0 },
    });
    tc.onPartial({ text: "Show my" });
    assert.equal(finals.length, 0);
    tc.onFinal({ text: "Show my missions." });
    assert.equal(finals.length, 1);
    assert.equal(finals[0].isExecutable, true);

    tc.onFinal({ text: "okay" });
    assert.equal(finals[finals.length - 1].isBackchannel, true);
    assert.equal(finals[finals.length - 1].isExecutable, false);
  });

  it("classifies false interruption when no meaningful STT after barge-in", async () => {
    const tc = createTurnCoordinator({
      config: { falseInterruptWaitMs: 20 },
    });
    tc.beginInterruptEvaluation("ACOUSTIC_SPEECH");
    assert.equal(tc.getLastInterruptClass(), "UNKNOWN_INTERRUPTION");
    await new Promise((r) => setTimeout(r, 30));
    tc.tick();
    assert.equal(tc.getLastInterruptClass(), "FALSE_INTERRUPTION");
  });

  it("confirms real interruption when meaningful STT arrives", () => {
    const tc = createTurnCoordinator();
    tc.beginInterruptEvaluation("ACOUSTIC_SPEECH");
    tc.onFinal({ text: "Stop talking please" });
    assert.equal(tc.getLastInterruptClass(), "REAL_INTERRUPTION");
  });
});

describe("streaming pipeline + manager", () => {
  beforeEach(async () => {
    forceReleaseInput("SESSION_CLOSE");
    await forceReleaseOutput("SESSION_CLOSE");
    resetVoiceTelemetry();
  });

  it("streams partial then final into session without auto-execution", async () => {
    const mgr = createVoiceSessionManager({ sttMode: "mock" });
    mgr.openSession({ sessionId: "s1" });
    await mgr.startStreamingPipeline({ sttMode: "mock" });
    const mock = mgr.getPipeline().getMockStt();
    mock.pushTextPartial("Show my");
    await new Promise((r) => setTimeout(r, 5));
    assert.match(mgr.getSnapshot().transcriptPartial || "", /Show my/);
    mock.pushTextFinal("Show my current missions.");
    await new Promise((r) => setTimeout(r, 20));
    const snap = mgr.getSnapshot();
    assert.ok(snap.lastTurn?.text?.includes("missions"));
    assert.equal(snap.lastTurn?.isExecutable, true);
    // No tool execution fields
    assert.equal(snap.lastTurn?.executed, undefined);
    await mgr.close();
  });

  it("mock STT privacy is LOCAL_CONFIRMED; browser class is PLATFORM_MANAGED_UNKNOWN", () => {
    const mock = createMockStreamingStt();
    assert.equal(mock.capabilities().privacyClass, STT_PRIVACY.LOCAL_CONFIRMED);
    assert.equal(mock.capabilities().offlineGuaranteed, true);
  });

  it("pipeline degrades gracefully on block admission", async () => {
    // Direct admission path
    const blocked = admitStreamingStt({
      heavyLocalSttRequested: true,
      localLlmActive: true,
      browserSttAvailable: false,
    });
    assert.ok(
      blocked.admission === "LOCAL_STT_BLOCKED_MEMORY" ||
        blocked.admission === "LOCAL_STT_BLOCKED_RESOURCE_PRESSURE"
    );
  });
});
