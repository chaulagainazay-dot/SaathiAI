/**
 * R2.1 — local speech recognition transport + provider selection policy.
 *
 * Selection has to be truthful, because every untruthful branch is a product
 * lie: silently reaching Chrome's recognizer is an unannounced privacy change,
 * and silently reaching the mock publishes invented speech.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  encodeWav,
  createWhisperCppTranscriber,
  createLocalWhisperStt,
  probeLocalSttHealth,
  LocalSttTransportError,
  MAX_UTTERANCE_SECONDS,
} from "./local-whisper-stt.js";
import { createRealtimeVoicePipeline } from "./pipeline-coordinator.js";

function tone(seconds = 0.5, rate = 16000) {
  const pcm = new Float32Array(Math.round(seconds * rate));
  for (let i = 0; i < pcm.length; i += 1) pcm[i] = Math.sin((2 * Math.PI * 440 * i) / rate) * 0.3;
  return pcm;
}

function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => body };
}

// ── WAV container ───────────────────────────────────────────────────────────

describe("local speech recognition transport — audio container", () => {
  it("encodes mono 16-bit PCM WAV the server can parse", () => {
    const wav = encodeWav(tone(1.0), 16000);
    const ascii = (from, to) => String.fromCharCode(...wav.slice(from, to));
    assert.equal(ascii(0, 4), "RIFF");
    assert.equal(ascii(8, 12), "WAVE");
    const view = new DataView(wav.buffer);
    assert.equal(view.getUint16(20, true), 1, "PCM format tag");
    assert.equal(view.getUint16(22, true), 1, "mono");
    assert.equal(view.getUint32(24, true), 16000, "sample rate");
    assert.equal(view.getUint16(34, true), 16, "16-bit samples");
    assert.equal(wav.byteLength, 44 + 16000 * 2);
  });

  it("clamps out-of-range samples instead of wrapping them", () => {
    const wav = encodeWav(Float32Array.from([2, -2]), 16000);
    const view = new DataView(wav.buffer);
    assert.equal(view.getInt16(44, true), 32767);
    assert.equal(view.getInt16(46, true), -32768);
  });
});

// ── the transcriber sends only bounded, settled utterances ──────────────────

describe("local speech recognition transport — request contract", () => {
  it("never sends a partial: this engine has no partial mode", async () => {
    let called = false;
    const transcribe = createWhisperCppTranscriber({
      fetchImpl: async () => { called = true; return jsonResponse({ text: "x" }); },
    });
    const out = await transcribe({ pcm: tone(), sampleRate: 16000, isFinal: false });
    assert.equal(called, false, "no request for a partial");
    assert.deepEqual(out, { text: "", isFinal: false });
  });

  it("refuses an utterance longer than the bounded duration before sending", async () => {
    const transcribe = createWhisperCppTranscriber({
      fetchImpl: async () => assert.fail("oversized audio was sent"),
    });
    await assert.rejects(
      () => transcribe({ pcm: tone(MAX_UTTERANCE_SECONDS + 1), sampleRate: 16000, isFinal: true }),
      (err) => err instanceof LocalSttTransportError && err.category === "resource"
    );
  });

  it("carries the session credential and posts a wav blob", async () => {
    let seen = null;
    const transcribe = createWhisperCppTranscriber({
      fetchImpl: async (url, init) => { seen = { url, init }; return jsonResponse({ text: "hello" }); },
      readToken: () => "tok-123",
      apiBase: "http://127.0.0.1:8765",
    });
    const out = await transcribe({ pcm: tone(), sampleRate: 16000, isFinal: true });
    assert.equal(out.text, "hello");
    assert.equal(seen.url, "http://127.0.0.1:8765/api/v1/voice/stt/transcribe");
    assert.equal(seen.init.method, "POST");
    assert.equal(seen.init.headers["X-Platform-Token"], "tok-123");
    assert.equal(seen.init.credentials, "include");
  });

  it("passes a language hint only when one was chosen", async () => {
    const forms = [];
    const transcribe = createWhisperCppTranscriber({
      fetchImpl: async (_u, init) => { forms.push(init.body.get("language")); return jsonResponse({ text: "" }); },
    });
    await transcribe({ pcm: tone(), sampleRate: 16000, isFinal: true });
    await transcribe({ pcm: tone(), sampleRate: 16000, isFinal: true, language: "ne" });
    assert.deepEqual(forms, [null, "ne"]);
  });
});

// ── failures stay bounded and categorized ───────────────────────────────────

describe("local speech recognition transport — bounded failures", () => {
  const cases = [
    [401, "authentication"],
    [413, "resource"],
    [415, "unsupported"],
    [503, "backend"],
  ];
  for (const [status, category] of cases) {
    it(`maps HTTP ${status} to the ${category} category`, async () => {
      const transcribe = createWhisperCppTranscriber({
        fetchImpl: async () => jsonResponse({ message: "no" }, { ok: false, status }),
      });
      await assert.rejects(
        () => transcribe({ pcm: tone(), sampleRate: 16000, isFinal: true }),
        (err) => err.category === category
      );
    });
  }

  it("classifies an unreachable service as network, never as a transcript", async () => {
    const transcribe = createWhisperCppTranscriber({
      fetchImpl: async () => { throw new TypeError("Failed to fetch"); },
    });
    await assert.rejects(
      () => transcribe({ pcm: tone(), sampleRate: 16000, isFinal: true }),
      (err) => err.category === "network"
    );
  });

  it("cancellation yields no transcript and is synchronous", async () => {
    let abortSignal = null;
    const transcribe = createWhisperCppTranscriber({
      fetchImpl: (_u, init) => {
        abortSignal = init.signal;
        return new Promise((_res, rej) => {
          init.signal?.addEventListener("abort", () => {
            const e = new Error("aborted"); e.name = "AbortError"; rej(e);
          });
        });
      },
    });
    const pending = transcribe({ pcm: tone(), sampleRate: 16000, isFinal: true });
    transcribe.cancelSync();
    assert.equal(abortSignal.aborted, true, "abort happened without awaiting");
    assert.deepEqual(await pending, { text: "", isFinal: false });
  });
});

// ── health probe is read-only ───────────────────────────────────────────────

describe("local speech recognition health probe", () => {
  it("reports readiness without opening a microphone", async () => {
    const health = await probeLocalSttHealth({
      fetchImpl: async () => jsonResponse({
        available: true, state: "READY", engine: "whisper.cpp/ggml",
        model: "ggml-base.bin", privacy_class: "LOCAL_CONFIRMED", languages: ["en", "ne"],
      }),
    });
    assert.equal(health.available, true);
    assert.equal(health.privacyClass, "LOCAL_CONFIRMED");
    assert.deepEqual(health.languages, ["en", "ne"]);
  });

  it("a signed-out probe is unavailable and says why", async () => {
    const health = await probeLocalSttHealth({
      fetchImpl: async () => jsonResponse({}, { ok: false, status: 401 }),
    });
    assert.equal(health.available, false);
    assert.equal(health.category, "authentication");
    assert.match(health.reason, /sign-in/i);
  });

  it("an unreachable service is unavailable, never assumed ready", async () => {
    const health = await probeLocalSttHealth({
      fetchImpl: async () => { throw new TypeError("Failed to fetch"); },
    });
    assert.equal(health.available, false);
    assert.equal(health.category, "network");
  });
});

// ── adapter integration ─────────────────────────────────────────────────────

describe("local whisper adapter", () => {
  it("declares local-confirmed privacy and reaches the final listeners", async () => {
    const adapter = createLocalWhisperStt({
      transcribeFn: async () => ({ text: "show my missions", isFinal: true, language: "en" }),
      getSessionId: () => "s-1",
    });
    const finals = [];
    adapter.onFinal((ev) => finals.push(ev));
    await adapter.start({ sessionId: "s-1" });
    adapter.pushAudio(tone(1.0));
    await adapter.flush?.();
    await adapter.close();
    assert.equal(finals.length, 1);
    assert.equal(finals[0].text, "show my missions");
    assert.equal(finals[0].privacyClass, "LOCAL_CONFIRMED");
    assert.equal(finals[0].isFinal, true);
  });

  it("cancelSync closes the in-flight request without awaiting", async () => {
    let aborted = false;
    const transcribeFn = async () => ({ text: "", isFinal: true });
    transcribeFn.cancelSync = () => { aborted = true; };
    const adapter = createLocalWhisperStt({ transcribeFn });
    await adapter.start({ sessionId: "s-2" });
    adapter.cancelSync();
    assert.equal(aborted, true);
    await adapter.close();
  });
});

// ── selection policy ────────────────────────────────────────────────────────
//
// These run against a stubbed browser so the coordinator takes the product
// branch rather than the Node branch, and every pipeline is stopped in a
// `finally` so a failed assertion cannot leak its tick timer into the runner.

function installBrowserEnv({ withSpeechRecognition = true } = {}) {
  const intervals = new Set();
  class FakeSpeechRecognition {
    start() { this.running = true; }
    stop() { this.running = false; }
    abort() { this.running = false; }
  }
  const navigatorStub = {
    mediaDevices: {
      async getUserMedia() {
        const tracks = [{ kind: "audio", readyState: "live", stop() { this.readyState = "ended"; } }];
        return { getTracks: () => tracks };
      },
    },
  };
  const windowStub = { navigator: navigatorStub };
  if (withSpeechRecognition) windowStub.SpeechRecognition = FakeSpeechRecognition;

  const realWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const realNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const realSetInterval = globalThis.setInterval;
  const realClearInterval = globalThis.clearInterval;
  Object.defineProperty(globalThis, "window", { value: windowStub, configurable: true, writable: true });
  Object.defineProperty(globalThis, "navigator", { value: navigatorStub, configurable: true, writable: true });
  globalThis.setInterval = (...args) => { const h = realSetInterval(...args); intervals.add(h); return h; };
  globalThis.clearInterval = (h) => { intervals.delete(h); return realClearInterval(h); };

  return {
    restore() {
      globalThis.setInterval = realSetInterval;
      globalThis.clearInterval = realClearInterval;
      for (const h of intervals) realClearInterval(h);
      intervals.clear();
      if (realWindow) Object.defineProperty(globalThis, "window", realWindow);
      else delete globalThis.window;
      if (realNavigator) Object.defineProperty(globalThis, "navigator", realNavigator);
      else delete globalThis.navigator;
    },
  };
}

async function withPipeline(options, assertions) {
  const env = installBrowserEnv(options.browserEnv ?? {});
  const pipeline = createRealtimeVoicePipeline({ manager: null, ...options.pipeline });
  try {
    await pipeline.start();
    await assertions(pipeline);
  } finally {
    await pipeline.stop();
    env.restore();
  }
}

describe("provider selection is truthful", () => {
  it("uses the local engine when one is explicitly wired", async () => {
    await withPipeline(
      {
        pipeline: {
          sttMode: "auto",
          localSttFactory: () =>
            createLocalWhisperStt({ transcribeFn: async () => ({ text: "", isFinal: true }) }),
        },
      },
      (pipeline) => {
        assert.equal(pipeline.health().selectedMode, "local_streaming");
      }
    );
  });

  it("prefers the local engine even when Chrome's recognizer exists", async () => {
    await withPipeline(
      {
        browserEnv: { withSpeechRecognition: true },
        pipeline: {
          sttMode: "auto",
          localSttFactory: () =>
            createLocalWhisperStt({ transcribeFn: async () => ({ text: "", isFinal: true }) }),
        },
      },
      (pipeline) => {
        assert.equal(pipeline.health().selectedMode, "local_streaming");
      }
    );
  });

  it("without a local engine and without an opt-in, voice is unavailable — never silently browser", async () => {
    await withPipeline(
      { browserEnv: { withSpeechRecognition: true }, pipeline: { sttMode: "auto" } },
      (pipeline) => {
        const health = pipeline.health();
        assert.equal(health.selectedMode, "unavailable");
        assert.notEqual(health.selectedMode, "mock", "the mock is never a product surface");
      }
    );
  });

  it("the browser fallback is reachable only after an explicit opt-in", async () => {
    await withPipeline(
      {
        browserEnv: { withSpeechRecognition: true },
        pipeline: { sttMode: "auto", browserFallbackEnabled: true },
      },
      (pipeline) => {
        assert.equal(pipeline.health().selectedMode, "browser_streaming");
      }
    );
  });

  it("an explicit browser request is still honoured", async () => {
    await withPipeline(
      { browserEnv: { withSpeechRecognition: true }, pipeline: { sttMode: "browser" } },
      (pipeline) => {
        assert.equal(pipeline.health().selectedMode, "browser_streaming");
      }
    );
  });

  it("a browser with no recognizer and no local engine reports unavailable, not mock", async () => {
    await withPipeline(
      {
        browserEnv: { withSpeechRecognition: false },
        pipeline: { sttMode: "auto", browserFallbackEnabled: true },
      },
      (pipeline) => {
        assert.equal(pipeline.health().selectedMode, "unavailable");
      }
    );
  });
});
