import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  detectVoiceCapabilities,
  deriveSessionState,
  toCommandVoiceLabel,
  createVoiceSessionManager,
  acquireInputClaim,
  forceReleaseInput,
  getInputOwnerSnapshot,
  acquireOutputClaim,
  forceReleaseOutput,
  getOutputOwnerSnapshot,
  resetVoiceTelemetry,
  getVoiceTelemetrySnapshot,
  CAPABILITY_DEFAULTS,
} from "./index.js";

describe("voice-session contract", () => {
  it("defaults capabilities without inventing full-duplex or wake word", () => {
    const caps = detectVoiceCapabilities(null);
    // Energy VAD adapter is available in-process; acoustic barge-in needs mic.
    assert.equal(caps.vadAvailable, true);
    assert.equal(caps.acousticBargeInAvailable, false);
    assert.equal(caps.wakeWordAvailable, false);
    assert.equal(caps.fullDuplexAvailable, false);
    assert.equal(caps.manualInterruptAvailable, true);
  });

  it("derives truthful states only", () => {
    assert.equal(deriveSessionState({ listening: true }), "LISTENING");
    assert.equal(deriveSessionState({ speaking: true }), "SPEAKING");
    assert.equal(deriveSessionState({ thinking: true }), "THINKING");
    assert.equal(deriveSessionState({ interrupting: true }), "INTERRUPTING");
    assert.equal(deriveSessionState({ speechDetected: true }), "SPEECH_DETECTED");
    assert.equal(deriveSessionState({ error: "x" }), "ERROR");
    assert.equal(deriveSessionState({ closed: true }), "CLOSED");
    assert.equal(toCommandVoiceLabel("LISTENING"), "LISTENING");
    assert.equal(toCommandVoiceLabel("SPEECH_DETECTED"), "SPEECH_DETECTED");
    assert.equal(toCommandVoiceLabel("IDLE"), "OFF");
  });
});

describe("single ownership invariants", () => {
  beforeEach(() => {
    forceReleaseInput("SESSION_CLOSE");
    forceReleaseOutput("SESSION_CLOSE");
    resetVoiceTelemetry();
  });

  it("allows only one active input claim", () => {
    const a = acquireInputClaim({ label: "a" });
    assert.equal(getInputOwnerSnapshot().claimId, a.id);
    const b = acquireInputClaim({ label: "b" });
    assert.equal(a.isActive(), false);
    assert.equal(b.isActive(), true);
    assert.equal(getInputOwnerSnapshot().claimId, b.id);
    b.release();
    assert.equal(getInputOwnerSnapshot().claimId, null);
  });

  it("allows only one active output claim", async () => {
    let stopped = 0;
    const a = acquireOutputClaim({
      label: "a",
      stop: async () => {
        stopped += 1;
      },
    });
    const b = acquireOutputClaim({
      label: "b",
      stop: async () => {},
    });
    assert.equal(a.isActive(), false);
    assert.equal(b.isActive(), true);
    assert.ok(stopped >= 1);
    await b.release();
    assert.equal(getOutputOwnerSnapshot().claimId, null);
  });

  it("manager interrupt stops output and mic request stops output first", async () => {
    const mgr = createVoiceSessionManager();
    mgr.openSession({ sessionId: "t1" });
    await mgr.beginOutput({ label: "out" });
    assert.equal(mgr.getSnapshot().state, "SPEAKING");
    await mgr.interrupt("USER_MIC_REQUEST");
    // output released; input not forced on mic request
    assert.notEqual(mgr.getSnapshot().state, "SPEAKING");
    await mgr.beginInput({ label: "in", stopOutputFirst: true });
    assert.equal(mgr.getSnapshot().state, "LISTENING");
    await mgr.close("SESSION_CLOSE");
    assert.equal(mgr.getSnapshot().state, "CLOSED");
    const tel = getVoiceTelemetrySnapshot();
    assert.ok((tel.counts.interruption || 0) >= 1);
    assert.ok((tel.counts.session_created || 0) >= 1);
  });

  it("double beginInput preempts prior input", async () => {
    const mgr = createVoiceSessionManager();
    await mgr.beginInput({ label: "one" });
    const first = mgr.getInputClaim()?.id;
    await mgr.beginInput({ label: "two" });
    const second = mgr.getInputClaim()?.id;
    assert.ok(first);
    assert.ok(second);
    assert.notEqual(first, second);
    await mgr.close();
  });

  it("capability defaults export is frozen shape", () => {
    assert.equal(CAPABILITY_DEFAULTS.vadAvailable, false);
    assert.equal(CAPABILITY_DEFAULTS.manualInterruptAvailable, true);
  });
});
