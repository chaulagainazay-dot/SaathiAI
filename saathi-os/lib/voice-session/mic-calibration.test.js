/**
 * R2.1-D18 — the calibration measurement, and the contract of the surface that
 * collects it.
 *
 * The failed physical attempt proved only that `speechDetected` never latched.
 * Classifying *why* needs distributions for silence and speech, evaluated by the
 * same rule the live VAD uses. These tests pin both halves: the arithmetic, and
 * the promises the panel makes about what it does to the microphone.
 *
 * The panel itself is checked against its source. There is no DOM renderer in
 * this suite, and the properties that matter — no capture on mount, claim before
 * getUserMedia, production constraints, no recognizer, no upload, teardown on
 * every exit — are all statements about which code exists and in what order.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  CALIBRATION_PHASES,
  CALIBRATION_SENTENCE,
  CALIBRATION_TOTAL_SECONDS,
  phaseAtElapsed,
  quantile,
  median,
  summarisePhase,
  summariseCalibration,
  describeTrackSettings,
} from "./mic-calibration.js";
import { DEFAULT_VAD_CONFIG } from "./vad-contract.js";
import { isSpeechLikeFrame, SPEECH_ZCR_MIN, SPEECH_ZCR_MAX } from "./energy-vad.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const PANEL_SRC = readFileSync(
  join(HERE, "..", "..", "components", "voice", "MicCalibrationPanel.jsx"), "utf8");
const PANEL = PANEL_SRC.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
const THR = DEFAULT_VAD_CONFIG.speechStartThreshold;

const frame = (rms, zcr = 0.1) => ({ rms, zcr });

describe("the guided sequence", () => {
  it("is three five-second phases in a fixed order", () => {
    assert.deepEqual(CALIBRATION_PHASES.map((p) => p.id), ["silence", "normal", "clear"]);
    assert.deepEqual(CALIBRATION_PHASES.map((p) => p.seconds), [5, 5, 5]);
    assert.equal(CALIBRATION_TOTAL_SECONDS, 15);
  });

  it("prompts the sentence for both speech phases and not for silence", () => {
    assert.equal(CALIBRATION_PHASES[0].speak, false);
    assert.equal(CALIBRATION_PHASES[1].speak, true);
    assert.equal(CALIBRATION_PHASES[2].speak, true);
    assert.match(CALIBRATION_SENTENCE, /Hello Saathi, this is Ajay testing the microphone\./);
  });

  it("attributes samples to phases on half-open boundaries", () => {
    assert.equal(phaseAtElapsed(0), "silence");
    assert.equal(phaseAtElapsed(4999), "silence");
    assert.equal(phaseAtElapsed(5000), "normal");   // first sample of phase two
    assert.equal(phaseAtElapsed(9999), "normal");
    assert.equal(phaseAtElapsed(10000), "clear");
    assert.equal(phaseAtElapsed(14999), "clear");
  });

  it("drops samples past the end rather than crediting the last phase", () => {
    assert.equal(phaseAtElapsed(15000), null);
    assert.equal(phaseAtElapsed(60000), null);
    assert.equal(phaseAtElapsed(-1), null);
  });
});

describe("quantiles", () => {
  it("median handles odd and even lengths", () => {
    assert.equal(median([1, 2, 3]), 2);
    assert.equal(median([1, 2, 3, 4]), 2.5);
    assert.equal(median([]), 0);
  });

  it("quantile clamps at both ends", () => {
    const s = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    assert.equal(quantile(s, 0), 1);
    assert.equal(quantile(s, 1), 10);
    assert.equal(quantile(s, 0.95), 10);
    assert.equal(quantile(s, 0.5), 6);
    assert.equal(quantile([], 0.95), 0);
  });
});

describe("the speech-start decision", () => {
  it("counts the longest consecutive run, not the total", () => {
    // Six qualifying frames, but never three in a row.
    const samples = [
      frame(0.05), frame(0.05), frame(0.001),
      frame(0.05), frame(0.05), frame(0.001),
      frame(0.05), frame(0.05),
    ];
    const r = summarisePhase(samples);
    assert.equal(r.framesAboveThreshold, 6);
    assert.equal(r.maxConsecutiveSpeechLike, 2);
    assert.equal(r.wouldTrigger, false, "three consecutive frames are required");
  });

  it("triggers once the run reaches startConfirmFrames", () => {
    const r = summarisePhase([frame(0.05), frame(0.05), frame(0.05)]);
    assert.equal(r.maxConsecutiveSpeechLike, 3);
    assert.equal(r.wouldTrigger, true);
  });

  it("loud broadband noise does not trigger — ZCR is out of range", () => {
    const noisy = Array.from({ length: 20 }, () => frame(0.9, 0.8));
    const r = summarisePhase(noisy);
    assert.equal(r.framesAboveThreshold, 20, "energy alone is present");
    assert.equal(r.maxConsecutiveSpeechLike, 0, "but it is not speech-like");
    assert.equal(r.wouldTrigger, false);
  });

  it("a DC-ish frame with ample energy does not trigger either", () => {
    const r = summarisePhase(Array.from({ length: 20 }, () => frame(0.9, 0.001)));
    assert.equal(r.wouldTrigger, false);
  });

  it("valid energy with invalid ZCR never counts, at either bound", () => {
    assert.equal(isSpeechLikeFrame(0.9, SPEECH_ZCR_MIN, THR), false);
    assert.equal(isSpeechLikeFrame(0.9, SPEECH_ZCR_MAX, THR), false);
    assert.equal(isSpeechLikeFrame(0.9, SPEECH_ZCR_MIN + 0.001, THR), true);
  });

  it("uses the live VAD rule rather than a copy of it", () => {
    const src = readFileSync(join(HERE, "mic-calibration.js"), "utf8");
    assert.ok(src.includes('from "./energy-vad.js"'));
    assert.ok(src.includes("isSpeechLikeFrame"));
    assert.ok(!/zcr\s*>\s*0\.01/.test(src), "the ZCR bounds must not be re-stated here");
    assert.ok(!/rms\s*>=\s*0\.018/.test(src), "the threshold must not be hardcoded here");
  });
});

describe("the run summary", () => {
  const run = () => summariseCalibration({
    silence: Array.from({ length: 100 }, () => frame(0.002, 0.2)),
    normal: Array.from({ length: 100 }, () => frame(0.05, 0.2)),
    clear: Array.from({ length: 100 }, () => frame(0.09, 0.2)),
  });

  it("takes the noise floor from the silent phase's p95, not its maximum", () => {
    const r = summariseCalibration({
      silence: [...Array.from({ length: 99 }, () => frame(0.002, 0.2)), frame(0.5, 0.2)],
      normal: [], clear: [],
    });
    assert.equal(r.noiseFloor, 0.002, "a single outlier must not define the floor");
  });

  it("reports speech-to-noise ratios against that floor", () => {
    const r = run();
    assert.equal(r.noiseFloor, 0.002);
    assert.ok(Math.abs(r.normalSpeechToNoise - 25) < 0.001);
    assert.ok(Math.abs(r.clearSpeechToNoise - 45) < 0.001);
  });

  it("states plainly whether production conditions would have triggered", () => {
    const r = run();
    assert.equal(r.wouldTriggerNormal, true);
    assert.equal(r.wouldTriggerClear, true);
    assert.equal(r.falseTriggerInSilence, false);
  });

  it("surfaces a silent phase that would have false-triggered", () => {
    const r = summariseCalibration({
      silence: Array.from({ length: 10 }, () => frame(0.05, 0.2)), normal: [], clear: [],
    });
    assert.equal(r.falseTriggerInSilence, true);
  });

  it("survives empty phases without inventing numbers", () => {
    const r = summariseCalibration({ silence: [], normal: [], clear: [] });
    assert.equal(r.phases.silence.frames, 0);
    assert.equal(r.noiseFloor, 0);
    assert.equal(r.normalSpeechToNoise, null, "no floor means no ratio, not Infinity");
  });

  it("recommends nothing — it reports only", () => {
    const r = run();
    const keys = JSON.stringify(Object.keys(r));
    assert.ok(!/recommend|suggested|newThreshold|apply/i.test(keys));
    const src = readFileSync(join(HERE, "mic-calibration.js"), "utf8");
    assert.ok(!/recommendedThreshold|applyThreshold/.test(src));
  });
});

describe("device reporting", () => {
  it("reports applied settings and never a stable device id", () => {
    const d = describeTrackSettings({
      label: "MacBook Pro Microphone (Built-in)",
      getSettings: () => ({
        deviceId: "STABLE-ID-THAT-MUST-NOT-LEAK", groupId: "GROUP-ID",
        sampleRate: 48000, channelCount: 1,
        echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      }),
    });
    assert.equal(d.label, "MacBook Pro Microphone (Built-in)");
    assert.equal(d.sampleRate, 48000);
    assert.equal(d.autoGainControl, true);
    const dumped = JSON.stringify(d);
    assert.ok(!dumped.includes("STABLE-ID-THAT-MUST-NOT-LEAK"));
    assert.ok(!dumped.includes("GROUP-ID"));
    assert.ok(!("deviceId" in d) && !("groupId" in d));
  });

  it("tolerates a track that reports nothing", () => {
    const d = describeTrackSettings(null);
    assert.equal(d.sampleRate, null);
  });
});

describe("the calibration surface contract", () => {
  it("never opens the microphone on mount", () => {
    // Capture is delegated to the capture manager, which arms its deadline
    // before opening anything. The panel supplies openMicrophone as a dependency
    // and never calls it itself outside that wiring.
    const mountEffect = PANEL.slice(PANEL.indexOf("useEffect(() =>"), PANEL.indexOf("const start ="));
    assert.ok(!mountEffect.includes("openMicrophoneForClaim"), "no capture from mount");
    assert.ok(!mountEffect.includes("cap.start"), "no capture from mount");
    assert.equal(PANEL.split("openMicrophoneForClaim(").length - 1, 1,
                 "exactly one place the device is opened");
    const capAt = PANEL.indexOf("cap.start(");
    const startAt = PANEL.indexOf("const start =");
    const stopAt = PANEL.indexOf("const stop =");
    assert.ok(capAt > startAt && capAt < stopAt,
              "capture may only begin from the explicit start callback");
    // Capture lives behind an explicit control.
    assert.ok(PANEL.includes('data-testid="calibration-start"'));
    assert.ok(PANEL.includes("onClick={start}"));
  });

  it("acquires the shared claim before opening the device", () => {
    const claimAt = PANEL.indexOf("acquireInputClaim(");
    const openAt = PANEL.indexOf("openMicrophoneForClaim(");
    assert.ok(claimAt > -1 && openAt > -1);
    assert.ok(claimAt < openAt, "ownership must precede capture");
    assert.ok(PANEL.includes("diagnostics.mic-calibration"), "claim carries its own identity");
  });

  it("uses the production constraints rather than its own", () => {
    assert.ok(!/getUserMedia\(/.test(PANEL), "must not call getUserMedia directly");
    assert.ok(!/audio:\s*true/.test(PANEL), "must not pass raw constraints");
    // openMicrophoneForClaim(claim) with no second argument = the contract default.
    assert.match(PANEL, /openMicrophoneForClaim\(claim\)/);
  });

  it("reuses the production tap and frame maths", () => {
    assert.ok(PANEL.includes("createAudioFrameTap"));
    assert.ok(PANEL.includes("frameRms") && PANEL.includes("frameZcr"));
  });

  it("constructs no recognizer and no MediaRecorder", () => {
    for (const banned of ["SpeechRecognition", "webkitSpeechRecognition",
                          "MediaRecorder", "getRecognitionCtor"]) {
      assert.ok(!PANEL.includes(banned), banned);
    }
  });

  it("issues no network request of any kind", () => {
    for (const banned of ["fetch(", "afetch", "XMLHttpRequest", "WebSocket",
                          "createSession", "voiceRuntimeActions", "/api/"]) {
      assert.ok(!PANEL.includes(banned), banned);
    }
  });

  it("keeps only derived numbers, never frames or streams", () => {
    assert.match(PANEL, /rms: frameRms\(frame\), zcr: frameZcr\(frame\)/);
    assert.ok(!/samplesRef\.current\[id\]\.push\(frame\)/.test(PANEL),
              "the frame itself must never be retained");
    assert.ok(!/localStorage|sessionStorage|indexedDB/.test(PANEL),
              "derived data must not be persisted");
  });

  it("routes every terminal reason through one handler", () => {
    // Teardown itself belongs to the capture manager, which guarantees it runs
    // exactly once per generation; see calibration-capture.test.js. What the
    // panel owes is a truthful reaction to each reason, and disposal on unmount.
    const handler = PANEL.slice(PANEL.indexOf("const onTerminal"), PANEL.indexOf("function capture()"));
    for (const reason of ["COMPLETED", "DEADLINE", "PREEMPTED", "ERROR", "STOPPED"]) {
      assert.ok(handler.includes(reason), reason);
    }
    assert.ok(PANEL.includes("onPreempt"), "preemption is wired to the manager");
    assert.match(PANEL, /useEffect\(\(\) => \(\) => \{ captureRef\.current\?\.stop\?\./);
  });

  it("delegates track/claim cleanup to the capture manager", () => {
    // The panel must not hold its own stream, tap or claim references: two
    // owners of the same teardown is how a resource survives one of them.
    for (const ref of ["streamRef", "tapRef", "claimRef", "timerRef"]) {
      assert.ok(!PANEL.includes(ref), ref + " must live in the capture manager");
    }
    assert.ok(PANEL.includes("createCalibrationCapture"));
    const mgr = readFileSync(join(HERE, "calibration-capture.js"), "utf8");
    assert.ok(mgr.includes("t.stop()") && mgr.includes("release?.()"));
  });

  it("clears derived results on demand", () => {
    assert.ok(PANEL.includes('data-testid="calibration-clear"'));
    assert.match(PANEL, /const clear = useCallback\(\(\) => \{[\s\S]*?setResults\(null\)/);
  });

  it("grants no authority and claims no stronger privacy than it proves", () => {
    for (const banned of ["authority", "executable", "backchannel", "approval"]) {
      assert.ok(!new RegExp(`${banned}\\s*[:=]`).test(PANEL), banned);
    }
    assert.match(PANEL_SRC, /analysed in memory/);
    assert.match(PANEL_SRC, /not recorded, stored or\s+uploaded/);
    assert.match(PANEL_SRC, /creates no voice session/);
  });

  it("cannot own the microphone alongside Live Voice", () => {
    // One registry, one active claim: acquiring preempts the incumbent, and the
    // incumbent's onPreempt tears it down. Both surfaces use the same module.
    const owner = readFileSync(join(HERE, "input-owner.js"), "utf8");
    assert.match(owner, /activeClaim\.release\(\)/);
    assert.ok(PANEL.includes("acquireInputClaim"));
    assert.ok(PANEL.includes("onPreempt"));
  });
});
