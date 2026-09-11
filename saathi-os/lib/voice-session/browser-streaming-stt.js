/**
 * Browser SpeechRecognition as StreamingTranscriptionAdapter.
 * Privacy: PLATFORM_MANAGED_UNKNOWN (browser may process off-device).
 * Does not open a second microphone — uses SpeechRecognition's own capture
 * while respecting AudioInputOwner claim lifecycle for exclusive ownership.
 */

import {
  STT_PRIVACY,
  nextUtteranceId,
  nextTranscriptSequence,
} from "./stt-contract.js";
import { getRecognitionCtor } from "./input-owner.js";
import { recordVoiceTelemetry } from "./telemetry.js";

/**
 * @param {object} [opts]
 * @param {string} [opts.lang]
 * @param {() => string} [opts.getSessionId]
 * @returns {import('./stt-contract.js').StreamingTranscriptionAdapter}
 */
export function createBrowserStreamingStt(opts = {}) {
  const lang = opts.lang || "en-US";
  const getSessionId = opts.getSessionId || (() => "");
  /** @type {Set<Function>} */
  const partialListeners = new Set();
  /** @type {Set<Function>} */
  const finalListeners = new Set();

  let recognition = null;
  let running = false;
  let cancelled = false;
  let utteranceId = "";
  let utteranceStartedAt = null;
  let lastPartial = "";
  let error = "";
  let finals = 0;
  let partials = 0;

  function emitPartial(text) {
    partials += 1;
    lastPartial = text;
    const ev = {
      sessionId: getSessionId(),
      utteranceId,
      text,
      isFinal: false,
      confidence: null,
      language: lang,
      startedAt: utteranceStartedAt,
      endedAt: null,
      sequence: nextTranscriptSequence(),
      source: "browser_speech_recognition",
      privacyClass: STT_PRIVACY.PLATFORM_MANAGED_UNKNOWN,
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
    finals += 1;
    const ev = {
      sessionId: getSessionId(),
      utteranceId,
      text,
      isFinal: true,
      confidence: null,
      language: lang,
      startedAt: utteranceStartedAt,
      endedAt: new Date().toISOString(),
      sequence: nextTranscriptSequence(),
      source: "browser_speech_recognition",
      privacyClass: STT_PRIVACY.PLATFORM_MANAGED_UNKNOWN,
    };
    for (const fn of finalListeners) {
      try {
        fn(ev);
      } catch {
        /* ignore */
      }
    }
    // prepare next utterance id
    utteranceId = nextUtteranceId();
    utteranceStartedAt = new Date().toISOString();
    lastPartial = "";
  }

  return {
    async start(session = {}) {
      cancelled = false;
      error = "";
      const Ctor = getRecognitionCtor();
      if (!Ctor) {
        error = "SpeechRecognition unavailable";
        throw new Error(error);
      }
      utteranceId = nextUtteranceId();
      utteranceStartedAt = new Date().toISOString();
      recognition = new Ctor();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = session.lang || lang;

      recognition.onresult = (event) => {
        if (cancelled) return;
        let interim = "";
        let finalText = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const piece = event.results[i][0]?.transcript || "";
          if (event.results[i].isFinal) finalText += piece;
          else interim += piece;
        }
        if (interim) emitPartial(interim);
        if (finalText.trim()) emitFinal(finalText.trim());
      };
      recognition.onerror = (ev) => {
        error = String(ev?.error || "speech_recognition_error");
        recordVoiceTelemetry("stt_error", { errorCode: error.slice(0, 80) });
      };
      recognition.onend = () => {
        running = false;
        if (!cancelled && recognition) {
          try {
            recognition.start();
            running = true;
          } catch {
            /* already stopped */
          }
        }
      };

      recognition.start();
      running = true;
      recordVoiceTelemetry("stt_started", {
        sessionId: getSessionId(),
        reason: "browser",
      });
    },

    // Browser STT does not accept raw PCM push; pre-roll is metadata-only for this adapter.
    pushAudio(_frame, meta = {}) {
      if (meta?.preRollAttached) {
        recordVoiceTelemetry("stt_preroll_note", {
          sessionId: getSessionId(),
          reason: "browser_stt_cannot_ingest_pcm_preroll",
        });
      }
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
      /* browser finalizes on isFinal results */
    },

    async cancel() {
      cancelled = true;
      try {
        recognition?.stop?.();
        recognition?.abort?.();
      } catch {
        /* ignore */
      }
      recognition = null;
      running = false;
      recordVoiceTelemetry("stt_cancelled", { sessionId: getSessionId() });
    },

    async close() {
      await this.cancel();
    },

    health() {
      return {
        adapter: "browser_speech_recognition",
        running,
        error,
        partials,
        finals,
        lastPartial,
        utteranceId,
        privacyClass: STT_PRIVACY.PLATFORM_MANAGED_UNKNOWN,
      };
    },

    capabilities() {
      return {
        streaming: true,
        partials: true,
        pushAudio: false,
        preRollPcmIngest: false,
        languages: [lang, "ne-NP", "hi-IN"],
        privacyClass: STT_PRIVACY.PLATFORM_MANAGED_UNKNOWN,
        offlineGuaranteed: false,
      };
    },
  };
}

/**
 * Deterministic mock STT for unit tests — no browser APIs.
 * pushTextPartial / pushTextFinal simulate streaming.
 */
export function createMockStreamingStt() {
  /** @type {Set<Function>} */
  const partialListeners = new Set();
  /** @type {Set<Function>} */
  const finalListeners = new Set();
  let utteranceId = nextUtteranceId();
  let running = false;
  let seqBase = 0;

  function emit(text, isFinal) {
    seqBase += 1;
    const ev = {
      sessionId: "mock",
      utteranceId,
      text,
      isFinal,
      confidence: isFinal ? 0.9 : 0.5,
      language: "en-US",
      startedAt: new Date().toISOString(),
      endedAt: isFinal ? new Date().toISOString() : null,
      sequence: seqBase,
      source: "mock_streaming_stt",
      privacyClass: STT_PRIVACY.LOCAL_CONFIRMED,
    };
    const set = isFinal ? finalListeners : partialListeners;
    for (const fn of set) fn(ev);
    if (isFinal) utteranceId = nextUtteranceId();
  }

  return {
    async start() {
      running = true;
    },
    pushAudio() {},
    onPartial(cb) {
      partialListeners.add(cb);
      return () => partialListeners.delete(cb);
    },
    onFinal(cb) {
      finalListeners.add(cb);
      return () => finalListeners.delete(cb);
    },
    async flush() {},
    async cancel() {
      running = false;
    },
    async close() {
      running = false;
    },
    health() {
      return { adapter: "mock", running, privacyClass: STT_PRIVACY.LOCAL_CONFIRMED };
    },
    capabilities() {
      return {
        streaming: true,
        partials: true,
        pushAudio: true,
        preRollPcmIngest: true,
        privacyClass: STT_PRIVACY.LOCAL_CONFIRMED,
        offlineGuaranteed: true,
      };
    },
    // test helpers
    pushTextPartial(text) {
      emit(text, false);
    },
    pushTextFinal(text) {
      emit(text, true);
    },
  };
}
