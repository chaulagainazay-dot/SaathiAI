/**
 * V-NEXT-2B.1 — Local StreamingTranscriptionAdapter (Whisper family).
 *
 * Consumes PCM via pushAudio (including pre-roll). Does NOT open a microphone.
 * Engine execution is delegated to an optional local helper (Node worker path)
 * or a pluggable `transcribeFn` for tests/production helpers.
 *
 * Privacy: LOCAL_CONFIRMED when the helper runs entirely on-device.
 * Engine-specific types never leak past this adapter.
 */

import {
  STT_PRIVACY,
  nextUtteranceId,
  nextTranscriptSequence,
} from "./stt-contract.js";
import { recordVoiceTelemetry } from "./telemetry.js";

/** @typedef {"LOCAL_STT_READY"|"LOCAL_STT_READY_DEGRADED"|"LOCAL_STT_BLOCKED_MEMORY"|"LOCAL_STT_BLOCKED_MODEL_LOAD"|"LOCAL_STT_UNAVAILABLE"} LocalSttAdmissionState */

/**
 * @param {object} [opts]
 * @param {string} [opts.modelId] e.g. "base", "tiny"
 * @param {string} [opts.engineId] e.g. "faster-whisper", "whisper.cpp"
 * @param {() => string} [opts.getSessionId]
 * @param {(req: { pcm: Float32Array, sampleRate: number, language?: string|null, isFinal?: boolean }) => Promise<{ text: string, isFinal?: boolean, language?: string|null, confidence?: number|null }>| { text: string, isFinal?: boolean }} [opts.transcribeFn]
 * @param {number} [opts.sampleRate]
 * @param {number} [opts.partialEveryMs]
 * @param {number} [opts.minSamplesForPartial]
 * @param {LocalSttAdmissionState} [opts.admissionState]
 * @param {string} [opts.admissionReason]
 * @param {boolean} [opts.available]
 */
export function createLocalStreamingStt(opts = {}) {
  const modelId = opts.modelId || "base";
  const engineId = opts.engineId || "faster-whisper";
  const getSessionId = opts.getSessionId || (() => "");
  const sampleRate = opts.sampleRate || 16000;
  const partialEveryMs = opts.partialEveryMs ?? 450;
  const minSamplesForPartial = opts.minSamplesForPartial ?? sampleRate * 0.6;
  const transcribeFn = opts.transcribeFn || null;
  let admissionState = opts.admissionState || (opts.available === false ? "LOCAL_STT_UNAVAILABLE" : "LOCAL_STT_READY");
  let admissionReason = opts.admissionReason || "";
  let available = opts.available !== false && Boolean(transcribeFn);

  /** @type {Set<Function>} */
  const partialListeners = new Set();
  /** @type {Set<Function>} */
  const finalListeners = new Set();

  let running = false;
  let cancelled = false;
  let utteranceId = "";
  let utteranceStartedAt = null;
  let lastPartial = "";
  let error = "";
  let finals = 0;
  let partials = 0;
  let preRollSamples = 0;
  let pcmChunks = [];
  let pcmLength = 0;
  let lastPartialAt = 0;
  let inflight = false;
  let language = opts.language || null;

  function concatPcm() {
    if (!pcmChunks.length) return new Float32Array(0);
    const out = new Float32Array(pcmLength);
    let off = 0;
    for (const c of pcmChunks) {
      out.set(c, off);
      off += c.length;
    }
    return out;
  }

  function emitPartial(text) {
    const t = String(text || "").trim();
    if (!t || t === lastPartial) return;
    partials += 1;
    lastPartial = t;
    const ev = {
      sessionId: getSessionId(),
      utteranceId,
      text: t,
      isFinal: false,
      confidence: null,
      language,
      startedAt: utteranceStartedAt,
      endedAt: null,
      sequence: nextTranscriptSequence(),
      source: `local_${engineId}`,
      privacyClass: STT_PRIVACY.LOCAL_CONFIRMED,
      modelId,
      engineId,
    };
    for (const fn of partialListeners) {
      try {
        fn(ev);
      } catch {
        /* ignore */
      }
    }
  }

  function emitFinal(text) {
    const t = String(text || "").trim();
    finals += 1;
    const ev = {
      sessionId: getSessionId(),
      utteranceId,
      text: t,
      isFinal: true,
      confidence: null,
      language,
      startedAt: utteranceStartedAt,
      endedAt: new Date().toISOString(),
      sequence: nextTranscriptSequence(),
      source: `local_${engineId}`,
      privacyClass: STT_PRIVACY.LOCAL_CONFIRMED,
      modelId,
      engineId,
    };
    for (const fn of finalListeners) {
      try {
        fn(ev);
      } catch {
        /* ignore */
      }
    }
    utteranceId = nextUtteranceId();
    utteranceStartedAt = new Date().toISOString();
    lastPartial = "";
    pcmChunks = [];
    pcmLength = 0;
    // keep cumulative preRollSamples for health diagnostics across finals
  }

  /** @type {Promise<void>|null} */
  let inflightPromise = null;

  async function maybeTranscribe({ forceFinal = false } = {}) {
    if (!available || !transcribeFn || cancelled) return;
    if (pcmLength < minSamplesForPartial && !forceFinal) return;
    const now =
      typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
    if (!forceFinal && now - lastPartialAt < partialEveryMs) return;

    // Serialize: wait for prior decode so flush cannot race partials
    if (inflightPromise) {
      try {
        await inflightPromise;
      } catch {
        /* ignore */
      }
      if (cancelled) return;
      if (!forceFinal) return; // prior partial already covered
    }

    inflight = true;
    lastPartialAt = now;
    const pcm = concatPcm();
    inflightPromise = (async () => {
      try {
        const result = await transcribeFn({
          pcm,
          sampleRate,
          language,
          isFinal: forceFinal,
        });
        if (cancelled) return;
        const text = String(result?.text || "").trim();
        if (result?.language) language = result.language;
        if (forceFinal || result?.isFinal) {
          emitFinal(text);
        } else if (text) {
          emitPartial(text);
        }
      } catch (err) {
        error = String(err?.message || err);
        admissionState = "LOCAL_STT_BLOCKED_MODEL_LOAD";
        admissionReason = error.slice(0, 160);
        recordVoiceTelemetry("stt_error", { errorCode: error.slice(0, 80), reason: engineId });
      } finally {
        inflight = false;
        inflightPromise = null;
      }
    })();
    await inflightPromise;
  }

  return {
    async start(session = {}) {
      if (!available) {
        error = admissionReason || "Local STT unavailable";
        throw new Error(error);
      }
      cancelled = false;
      error = "";
      running = true;
      utteranceId = nextUtteranceId();
      utteranceStartedAt = new Date().toISOString();
      language = session.lang || session.language || language;
      pcmChunks = [];
      pcmLength = 0;
      recordVoiceTelemetry("stt_started", {
        sessionId: getSessionId(),
        reason: `local_${engineId}_${modelId}`,
      });
    },

    /**
     * Accept Float32 PCM frames. meta.preRollAttached marks pre-roll delivery.
     */
    pushAudio(frame, meta = {}) {
      if (!running || cancelled) return;
      let samples = frame;
      if (!(samples instanceof Float32Array)) {
        samples = new Float32Array(samples || []);
      }
      if (!samples.length) return;
      // copy to detach from caller buffers
      const copy = new Float32Array(samples.length);
      copy.set(samples);
      pcmChunks.push(copy);
      pcmLength += copy.length;
      if (meta?.preRollAttached) {
        preRollSamples += copy.length;
        recordVoiceTelemetry("stt_preroll_pcm", {
          sessionId: getSessionId(),
          reason: `samples=${copy.length}`,
        });
      }
      // fire-and-forget partial decode
      void maybeTranscribe({ forceFinal: Boolean(meta?.forceFinal) });
    },

    onPartial(cb) {
      partialListeners.add(cb);
      return () => partialListeners.delete(cb);
    },
    onFinal(cb) {
      finalListeners.add(cb);
      return () => finalListeners.delete(cb);
    },

    async flush() {
      await maybeTranscribe({ forceFinal: true });
    },

    async cancel() {
      cancelled = true;
      running = false;
      pcmChunks = [];
      pcmLength = 0;
      recordVoiceTelemetry("stt_cancelled", { sessionId: getSessionId() });
    },

    async close() {
      await this.cancel();
    },

    health() {
      return {
        adapter: "local_streaming_stt",
        engineId,
        modelId,
        running,
        error,
        partials,
        finals,
        lastPartial,
        utteranceId,
        preRollSamples,
        pcmBufferedSamples: pcmLength,
        privacyClass: STT_PRIVACY.LOCAL_CONFIRMED,
        admissionState,
        admissionReason,
        available,
      };
    },

    capabilities() {
      return {
        streaming: true,
        partials: true,
        pushAudio: true,
        preRollPcmIngest: true,
        languages: ["en", "ne", "mixed", "auto"],
        privacyClass: STT_PRIVACY.LOCAL_CONFIRMED,
        offlineGuaranteed: true,
        engineId,
        modelId,
        admissionState,
      };
    },

    /** Test / diagnostics */
    getAdmissionState() {
      return { admissionState, admissionReason, available };
    },
    setAdmission(state, reason = "") {
      admissionState = state;
      admissionReason = reason;
      if (
        state === "LOCAL_STT_BLOCKED_MEMORY" ||
        state === "LOCAL_STT_BLOCKED_MODEL_LOAD" ||
        state === "LOCAL_STT_UNAVAILABLE"
      ) {
        available = false;
      }
    },
  };
}

/**
 * Build a deterministic local STT for unit tests: echoes normalized energy-gated text from meta.label
 * or decodes a simple injected text via pushAudio meta.transcriptHint.
 */
export function createLocalStreamingSttForTests(opts = {}) {
  let lastHint = "";
  return createLocalStreamingStt({
    ...opts,
    available: true,
    admissionState: "LOCAL_STT_READY",
    engineId: opts.engineId || "test-local-whisper",
    modelId: opts.modelId || "tiny",
    minSamplesForPartial: opts.minSamplesForPartial ?? 1,
    partialEveryMs: opts.partialEveryMs ?? 0,
    async transcribeFn({ isFinal }) {
      const text = lastHint || opts.fixedText || "";
      return { text, isFinal: Boolean(isFinal), language: "en" };
    },
    // wrap pushAudio via proxy — attach helper
  });
}

/**
 * Helper: create test local STT that reads transcript hints from pushAudio meta.
 */
export function createHintDrivenLocalStt(opts = {}) {
  let hint = opts.fixedText || "";
  const adapter = createLocalStreamingStt({
    ...opts,
    available: true,
    admissionState: "LOCAL_STT_READY",
    engineId: "test-local-whisper",
    modelId: opts.modelId || "tiny",
    minSamplesForPartial: 1,
    partialEveryMs: 0,
    transcribeFn: async ({ isFinal }) => ({
      text: hint,
      isFinal: Boolean(isFinal),
      language: opts.language || "en",
    }),
  });
  const origPush = adapter.pushAudio.bind(adapter);
  adapter.pushAudio = (frame, meta = {}) => {
    if (meta?.transcriptHint != null) hint = String(meta.transcriptHint);
    return origPush(frame, meta);
  };
  adapter.setHint = (t) => {
    hint = String(t || "");
  };
  return adapter;
}
