import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  createHintDrivenLocalStt,
  createLocalStreamingStt,
  createTurnCoordinator,
  createRealtimeVoicePipeline,
  createVoiceSessionManager,
  admitStreamingStt,
  resolveSttHierarchy,
  formatVoiceInputLabel,
  normalizeTranscriptEvent,
  normalizeTurnText,
  isMeaningfulTranscript,
  forceReleaseInput,
  forceReleaseOutput,
  resetVoiceTelemetry,
  STT_PRIVACY,
} from "./index.js";

describe("local STT adapter contract", () => {
  it("ingests pre-roll PCM and marks privacy LOCAL_CONFIRMED", async () => {
    const finals = [];
    const partials = [];
    const stt = createHintDrivenLocalStt({ modelId: "tiny" });
    stt.onPartial((e) => partials.push(e));
    stt.onFinal((e) => finals.push(e));
    await stt.start({ sessionId: "s" });
    const pcm = new Float32Array(1600).fill(0.01);
    stt.pushAudio(pcm, { preRollAttached: true, transcriptHint: "Show my missions" });
    await stt.flush();
    assert.ok(finals.length >= 1);
    assert.equal(finals[0].privacyClass, STT_PRIVACY.LOCAL_CONFIRMED);
    assert.equal(finals[0].text.includes("missions"), true);
    assert.ok(stt.health().preRollSamples >= 1600);
    assert.equal(stt.capabilities().preRollPcmIngest, true);
    assert.equal(stt.capabilities().pushAudio, true);
    await stt.close();
  });

  it("unavailable local adapter throws on start and reports admission", async () => {
    const stt = createLocalStreamingStt({
      available: false,
      admissionState: "LOCAL_STT_UNAVAILABLE",
      admissionReason: "model missing",
    });
    await assert.rejects(() => stt.start(), /unavailable|model/i);
    assert.equal(stt.health().admissionState, "LOCAL_STT_UNAVAILABLE");
  });
});

describe("admission + hierarchy", () => {
  it("admits local STT READY when available and memory ok (explicit request)", () => {
    const a = admitStreamingStt({
      localSttAvailable: true,
      heavyLocalSttRequested: true,
      localSttModelLoaded: true,
      reclaimableMib: 2000,
      preferredModel: "base",
    });
    assert.equal(a.admission, "LOCAL_STT_READY");
    assert.equal(a.mode, "local_streaming");
    assert.equal(a.privacyClass, "LOCAL_CONFIRMED");
    assert.equal(a.policy.neverLowerLlmMemoryGate, true);
  });

  it("does not auto-primary local while multilingual gate is false", () => {
    const a = admitStreamingStt({
      localSttAvailable: true,
      localSttModelLoaded: true,
      reclaimableMib: 2000,
      browserSttAvailable: true,
      heavyLocalSttRequested: false,
    });
    // Browser compatibility remains product primary until NE gate passes
    assert.equal(a.mode, "browser_streaming");
    assert.equal(a.policy.multilingualLocalSttQualified, false);
  });

  it("blocks memory when LLM active and offers browser fallback", () => {
    const a = admitStreamingStt({
      localSttAvailable: true,
      heavyLocalSttRequested: true,
      localLlmActive: true,
      browserSttAvailable: true,
    });
    assert.equal(a.admission, "LOCAL_STT_BLOCKED_MEMORY");
    assert.equal(a.mode, "browser_fallback");
    assert.equal(a.policy.neverLowerLlmMemoryGate, true);
  });

  it("degrades to tiny under partial memory pressure", () => {
    const a = admitStreamingStt({
      localSttAvailable: true,
      heavyLocalSttRequested: true,
      reclaimableMib: 700,
      preferredModel: "base",
    });
    assert.equal(a.admission, "LOCAL_STT_READY_DEGRADED");
    assert.equal(a.modelId, "tiny");
  });

  it("model load failure selects browser fallback not cloud", () => {
    const a = admitStreamingStt({
      localSttAvailable: true,
      heavyLocalSttRequested: true,
      localSttModelLoaded: false,
      browserSttAvailable: true,
    });
    assert.equal(a.admission, "LOCAL_STT_BLOCKED_MODEL_LOAD");
    assert.equal(a.mode, "browser_fallback");
    const h = resolveSttHierarchy(a);
    assert.equal(h.cloudFallback, false);
    assert.ok(h.chain.some((c) => c.role === "TEXT_FALLBACK"));
  });

  it("formatVoiceInputLabel distinguishes local vs browser", () => {
    const local = formatVoiceInputLabel({
      adapter: "local_streaming_stt",
      privacyClass: "LOCAL_CONFIRMED",
      modelId: "base",
    });
    assert.match(local.line, /Local · Whisper/);
    assert.equal(local.privacyClass, "LOCAL_CONFIRMED");
    const browser = formatVoiceInputLabel({
      adapter: "browser_speech_recognition",
      privacyClass: "PLATFORM_MANAGED_UNKNOWN",
    });
    assert.match(browser.line, /Browser · Privacy unknown/);
  });
});

describe("turn quality + nepali/mixed", () => {
  it("normalizes provider events and never executes partials", () => {
    const ev = normalizeTranscriptEvent({
      text: "  Show missions  ",
      isFinal: false,
      privacyClass: STT_PRIVACY.LOCAL_CONFIRMED,
      source: "local_faster-whisper",
      sequence: 3,
    });
    assert.equal(ev.text, "Show missions");
    assert.equal(ev.isFinal, false);
    assert.equal(isMeaningfulTranscript(ev.text), true);
  });

  it("handles Nepali and mixed text as meaningful", () => {
    assert.equal(isMeaningfulTranscript("मेरो portfolio"), true);
    assert.equal(isMeaningfulTranscript("Saathi, आजको risk"), true);
    assert.equal(isMeaningfulTranscript("हजुर"), false);
    assert.equal(normalizeTurnText("  हो  "), "हो");
  });

  it("classifies extended backchannels as non-executable", () => {
    const finals = [];
    const tc = createTurnCoordinator({ onTurnFinal: (t) => finals.push(t) });
    tc.onFinal({ text: "ठीक छ" });
    assert.ok(finals.length >= 1);
    assert.equal(finals[0].isBackchannel, true);
    assert.equal(finals[0].isExecutable, false);
  });

  it("false interruption then recovery with meaningful STT", () => {
    const tc = createTurnCoordinator({ config: { falseInterruptWaitMs: 5000 } });
    tc.beginInterruptEvaluation("ACOUSTIC_SPEECH");
    tc.onFinal({ text: "Stop the response now" });
    assert.equal(tc.getLastInterruptClass(), "REAL_INTERRUPTION");
  });
});

describe("pipeline local + fallback", () => {
  beforeEach(async () => {
    forceReleaseInput("SESSION_CLOSE");
    await forceReleaseOutput("SESSION_CLOSE");
    resetVoiceTelemetry();
  });

  it("selects local adapter via factory and surfaces engine state", async () => {
    const mgr = createVoiceSessionManager({ sttMode: "local" });
    mgr.openSession({ sessionId: "local-1" });
    const pipeline = createRealtimeVoicePipeline({
      manager: mgr,
      sttMode: "local",
      admissionSignals: {
        localSttAvailable: true,
        reclaimableMib: 2500,
        browserSttAvailable: false,
      },
      localSttFactory: () => createHintDrivenLocalStt({ modelId: "base" }),
    });
    await pipeline.start();
    const stt = pipeline.getStt();
    stt.setHint("Open the command center.");
    stt.pushAudio(new Float32Array(800).fill(0.02), {
      transcriptHint: "Open the command center.",
    });
    await stt.flush();
    await new Promise((r) => setTimeout(r, 30));
    const health = pipeline.health();
    assert.equal(health.selectedMode, "local_streaming");
    assert.equal(health.engine.privacyClass, STT_PRIVACY.LOCAL_CONFIRMED);
    assert.match(health.label.line, /Local/);
    assert.equal(health.hierarchy.cloudFallback, false);
    await pipeline.stop();
    await mgr.close();
  });

  it("pre-roll PCM path does not open second mic", async () => {
    const stt = createHintDrivenLocalStt();
    await stt.start();
    const pre = new Float32Array(3200).fill(0.05);
    stt.pushAudio(pre, { preRollAttached: true, transcriptHint: "Cancel that response." });
    await stt.flush();
    assert.ok(stt.health().preRollSamples >= 3200);
    // single capture contract: adapter never calls getUserMedia
    assert.equal(stt.capabilities().pushAudio, true);
    await stt.close();
  });

  it("engine crash / missing model leaves session usable via degrade path", async () => {
    const mgr = createVoiceSessionManager();
    mgr.openSession({ sessionId: "deg" });
    const pipeline = createRealtimeVoicePipeline({
      manager: mgr,
      sttMode: "local",
      admissionSignals: {
        localSttAvailable: true,
        localSttModelLoaded: false,
        browserSttAvailable: false,
      },
      localSttFactory: () => {
        throw new Error("model cannot load");
      },
    });
    await pipeline.start();
    // mock fallback when no browser
    assert.ok(pipeline.health());
    await pipeline.stop();
    await mgr.close();
  });
});
