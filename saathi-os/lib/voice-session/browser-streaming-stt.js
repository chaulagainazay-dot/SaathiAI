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
  /** @type {Set<Function>} */
  const errorListeners = new Set();

  let recognition = null;
  let running = false;
  let cancelled = false;
  let utteranceId = "";
  let utteranceStartedAt = null;
  let lastPartial = "";
  let error = "";
  let finals = 0;
  let partials = 0;
  /**
   * A finalized utterance keeps its id until the next one actually starts.
   * Rotating on the final instead would make a redelivered result look like a
   * brand-new utterance, and downstream duplicate detection would have nothing
   * to key on.
   */
  let awaitingNewUtterance = false;

  function emitPartial(text) {
    if (awaitingNewUtterance) {
      utteranceId = nextUtteranceId();
      utteranceStartedAt = new Date().toISOString();
      awaitingNewUtterance = false;
    }
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
    // The next partial opens the next utterance.
    awaitingNewUtterance = true;
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
      awaitingNewUtterance = false;
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
        if (cancelled) return;
        const payload = {
          code: error,
          message: error,
          source: "browser_speech_recognition",
          fatal: error === "not-allowed" || error === "service-not-allowed",
        };
        for (const fn of errorListeners) {
          try {
            fn(payload);
          } catch {
            /* ignore */
          }
        }
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
    onError(cb) {
      errorListeners.add(cb);
      return () => errorListeners.delete(cb);
    },

    async flush() {
      /* browser finalizes on isFinal results */
    },

    /**
     * Close the restart window. Fully synchronous by contract.
     *
     * `onend` restarts the recognizer, so cancellation is only real once the
     * handlers are detached and `cancelled` is set. Both happen here, before
     * `abort()` — a browser that dispatches `onend` synchronously from
     * `abort()` must not find a live restart path. Callers that need a
     * guaranteed-closed window call this instead of awaiting `cancel()`.
     */
    cancelSync() {
      cancelled = true;
      const rec = recognition;
      recognition = null;
      running = false;
      if (rec) {
        // Neutralize first: detached handlers cannot schedule a restart.
        try {
          rec.onresult = null;
          rec.onerror = null;
          rec.onend = null;
        } catch {
          /* ignore */
        }
        try {
          rec.stop?.();
        } catch {
          /* ignore */
        }
        try {
          rec.abort?.();
        } catch {
          /* ignore */
        }
      }
      recordVoiceTelemetry("stt_cancelled", { sessionId: getSessionId() });
    },

    async cancel() {
      this.cancelSync();
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
    cancelSync() {
      running = false;
    },
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
