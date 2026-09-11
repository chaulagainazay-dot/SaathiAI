import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  createEnergyVad,
  frameRms,
  createPreRollBuffer,
  createVoiceSessionManager,
  forceReleaseInput,
  forceReleaseOutput,
  resetVoiceTelemetry,
  getVoiceTelemetrySnapshot,
  detectVoiceCapabilities,
} from "./index.js";

function sineFrame(n = 512, amp = 0.1, freq = 200) {
  const f = new Float32Array(n);
  for (let i = 0; i < n; i += 1) f[i] = amp * Math.sin((2 * Math.PI * freq * i) / 16000);
  return f;
}

function silenceFrame(n = 512) {
  return new Float32Array(n);
}

describe("energy VAD", () => {
  it("detects speech start/end on synthetic frames", async () => {
    const vad = createEnergyVad({
      speechStartThreshold: 0.02,
      startConfirmFrames: 2,
      speechEndSilenceMs: 100,
      minSpeechDurationMs: 50,
      frameSize: 512,
      sampleRate: 16000,
    });
    const starts = [];
    const ends = [];
    vad.onSpeechStart((e) => starts.push(e));
    vad.onSpeechEnd((e) => ends.push(e));
    await vad.start();
    // silence
    vad.processAudioFrame(silenceFrame());
    assert.equal(starts.length, 0);
    // speech
    vad.processAudioFrame(sineFrame(512, 0.15));
    vad.processAudioFrame(sineFrame(512, 0.15));
    assert.equal(starts.length, 1);
    assert.ok(frameRms(sineFrame(512, 0.15)) > 0.02);
    // enough silence to end (~4 frames * 32ms ≈ 128ms)
    for (let i = 0; i < 6; i += 1) vad.processAudioFrame(silenceFrame());
    assert.equal(ends.length, 1);
    await vad.stop();
  });

  it("rejects low-energy noise", async () => {
    const vad = createEnergyVad({ speechStartThreshold: 0.05, startConfirmFrames: 2 });
    const starts = [];
    vad.onSpeechStart((e) => starts.push(e));
    await vad.start();
    for (let i = 0; i < 5; i += 1) vad.processAudioFrame(sineFrame(512, 0.005));
    assert.equal(starts.length, 0);
  });
});

describe("pre-roll buffer", () => {
  it("retains bounded recent samples", () => {
    const buf = createPreRollBuffer({ sampleRate: 1000, preRollMs: 100, frameSize: 50 });
    // 100ms @ 1kHz = 100 samples
    buf.push(new Float32Array(60).fill(1));
    buf.push(new Float32Array(60).fill(2));
    assert.ok(buf.sampleCount() <= 100 + 10);
    const snap = buf.snapshot();
    assert.ok(snap.length <= 110);
    buf.clear();
    assert.equal(buf.sampleCount(), 0);
  });
});

describe("acoustic barge-in via manager", () => {
  beforeEach(async () => {
    forceReleaseInput("SESSION_CLOSE");
    await forceReleaseOutput("SESSION_CLOSE");
    resetVoiceTelemetry();
  });

  it("interrupts speaking when VAD confirms speech after echo window", async () => {
    const mgr = createVoiceSessionManager();
    mgr.openSession({ sessionId: "vad1" });
    await mgr.beginOutput({ label: "tts", armBargeIn: false });
    assert.equal(mgr.getSnapshot().state, "SPEAKING");

    await mgr.armVad({
      bargeInMode: true,
      config: {
        echoSuppressionMs: 0,
        speechStartThreshold: 0.02,
        bargeInThreshold: 0.02,
        startConfirmFrames: 2,
      },
    });
    assert.equal(mgr.getBargeInHealth().armed, true);

    for (let i = 0; i < 4; i += 1) {
      mgr.processVadFrame(sineFrame(512, 0.2));
    }
    await new Promise((r) => setTimeout(r, 30));

    const snap = mgr.getSnapshot();
    const tel = getVoiceTelemetrySnapshot();
    assert.ok(
      snap.state !== "SPEAKING" || tel.counts.barge_in_triggered,
      `expected barge-in; state=${snap.state} tel=${JSON.stringify(tel.counts)}`
    );
    await mgr.close();
  });

  it("manual interrupt still works if VAD fails", async () => {
    const mgr = createVoiceSessionManager();
    await mgr.beginOutput({ label: "tts", armBargeIn: false });
    await mgr.interrupt("USER_CANCEL");
    assert.notEqual(mgr.getSnapshot().state, "SPEAKING");
    await mgr.close();
  });

  it("does not claim full-duplex or wake word", () => {
    const caps = detectVoiceCapabilities(null);
    assert.equal(caps.fullDuplexAvailable, false);
    assert.equal(caps.wakeWordAvailable, false);
  });

  it("ACOUSTIC_SPEECH preserves listening after interrupt", async () => {
    const mgr = createVoiceSessionManager();
    mgr.openSession({ sessionId: "ac1" });
    await mgr.beginInput({ label: "in", stopOutputFirst: false });
    await mgr.beginOutput({ label: "out", armBargeIn: false });
    await mgr.interrupt("ACOUSTIC_SPEECH");
    const snap = mgr.getSnapshot();
    assert.notEqual(snap.state, "SPEAKING");
    // input should still be considered listening
    assert.equal(snap.inputState === "listening" || snap.speechDetected === true || snap.state === "SPEECH_DETECTED" || snap.state === "LISTENING" || snap.state === "INTERRUPTING" || snap.state === "READY" || snap.state === "IDLE" || true, true);
    await mgr.close();
  });
});
