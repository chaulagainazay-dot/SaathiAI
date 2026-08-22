/**
 * RealtimeVoicePipelineCoordinator — SaathiOS-owned orchestration.
 * Pipecat/LiveKit would plug in as adapters later; this is the authority path.
 *
 * V-NEXT-2B.1: local STT primary when admitted; browser fallback; mock for tests.
 * Hierarchy never includes cloud STT.
 */

import { createBrowserStreamingStt, createMockStreamingStt } from "./browser-streaming-stt.js";
import { createLocalStreamingStt, createHintDrivenLocalStt } from "./local-streaming-stt.js";
import { createTurnCoordinator } from "./turn-coordinator.js";
import {
  admitStreamingStt,
  resolveSttHierarchy,
  formatVoiceInputLabel,
} from "./resource-budget.js";
import { getRecognitionCtor } from "./input-owner.js";
import { recordVoiceTelemetry } from "./telemetry.js";
import { STT_PRIVACY } from "./stt-contract.js";

/**
 * Normalize provider transcript events to engine-neutral shape.
 * @param {object} ev
 */
export function normalizeTranscriptEvent(ev = {}) {
  return {
    sessionId: String(ev.sessionId || ""),
    utteranceId: String(ev.utteranceId || ""),
    text: String(ev.text || "").trim(),
    isFinal: Boolean(ev.isFinal),
    confidence: ev.confidence == null ? null : Number(ev.confidence),
    language: ev.language || null,
    startedAt: ev.startedAt || null,
    endedAt: ev.endedAt || null,
    sequence: Number(ev.sequence) || 0,
    source: String(ev.source || "unknown"),
    privacyClass: ev.privacyClass || STT_PRIVACY.UNAVAILABLE,
    // strip engine-only fields from coordinator path (kept on raw if needed)
  };
}

/**
 * Observe a teardown tail without letting it reject.
 *
 * A rejected cleanup promise is still a fact worth recording, but an unhandled
 * one crashes the process under Node's default policy and is invisible to the
 * caller that deliberately did not await. So the rejection is attached to here,
 * classified, and surfaced as a resolved value.
 *
 * @param {object} opts
 * @param {Promise<any>|null|undefined} opts.tail
 * @param {unknown} opts.syncError error thrown before the first await, if any
 * @param {boolean} opts.wasActive
 * @param {string} opts.mode
 * @returns {Promise<{status: string, errorCode: string|null}>} never rejects
 */
function classifyTeardown({ tail, syncError, wasActive, mode }) {
  const report = (status, err) => {
    const errorCode = err == null ? null : String(err?.message || err).slice(0, 80);
    if (status !== "clean") {
      recordVoiceTelemetry("stt_teardown_failed", {
        reason: `${mode}:${status}`,
        errorCode: errorCode || status,
      });
    }
    return { status, errorCode };
  };

  if (syncError) return Promise.resolve(report("sync_error", syncError));
  const base = wasActive ? "clean" : "already_stopped";
  if (!tail || typeof tail.then !== "function") {
    return Promise.resolve(report(base, null));
  }
  return tail.then(
    () => report(base, null),
    (err) => report("async_error", err)
  );
}

/**
 * @param {object} opts
 * @param {object} opts.manager VoiceSessionManager
 * @param {"browser"|"mock"|"local"|"auto"} [opts.sttMode]
 * @param {object} [opts.sttAdapter] inject adapter
 * @param {object} [opts.admissionSignals]
 * @param {object} [opts.localSttFactory] () => adapter
 * @param {boolean} [opts.browserFallbackEnabled] opt in to Chrome Web Speech
 *   when the local engine is unavailable. Off by default: Chrome's recognizer
 *   sends audio to a Google service and is unreachable on the owner's host, so
 *   silently routing there would be both a privacy change and a dead end.
 */
export function createRealtimeVoicePipeline({
  manager: managerIn = null,
  sttMode = "auto",
  sttAdapter = null,
  admissionSignals = {},
  localSttFactory = null,
  browserFallbackEnabled = false,
} = {}) {
  const self = { manager: managerIn };
  const inBrowser = typeof window !== "undefined";
  const browserAvailable = Boolean(getRecognitionCtor());
  /** Set when no adapter can serve this runtime truthfully. */
  let unsupportedReason = "";

  const signals = {
    browserSttAvailable: browserAvailable || sttMode === "mock",
    // Supplying a local factory IS the explicit request. The locked
    // multilingual gate in VOICE_RESOURCE_POLICY stays false — the R2.1
    // re-measurement confirmed Nepali still fails it — so local is admitted
    // as the explicitly-chosen English-optimized path, never as a silent
    // multilingual primary. Do not flip that gate to shortcut this.
    heavyLocalSttRequested: sttMode === "local" || Boolean(localSttFactory),
    localSttAvailable: Boolean(localSttFactory) || sttMode === "local",
    localLlmActive: false,
    ...admissionSignals,
  };

  // auto: prefer local when factory provided, else browser, else mock
  if (sttMode === "auto" && localSttFactory) {
    signals.localSttAvailable = true;
  }

  const admission = admitStreamingStt(signals);
  const hierarchy = resolveSttHierarchy(admission);

  /** @type {import('./stt-contract.js').StreamingTranscriptionAdapter} */
  let stt = sttAdapter;
  let selectedMode = admission.mode;

  if (!stt) {
    if (sttMode === "mock") {
      stt = createMockStreamingStt();
      selectedMode = "mock";
    } else if (
      sttMode === "local" ||
      (sttMode === "auto" && admission.mode === "local_streaming" && localSttFactory)
    ) {
      try {
        stt =
          typeof localSttFactory === "function"
            ? localSttFactory({ modelId: admission.modelId || "base" })
            : createLocalStreamingStt({
                modelId: admission.modelId || "base",
                available: false,
                admissionState: "LOCAL_STT_UNAVAILABLE",
                admissionReason: "No local STT factory",
              });
        selectedMode = "local_streaming";
      } catch (err) {
        // fall through to browser
        stt = null;
        recordVoiceTelemetry("stt_local_factory_failed", {
          errorCode: String(err?.message || err).slice(0, 80),
        });
      }
    }

    if (!stt) {
      // Chrome Web Speech is a fallback, never a default. Reaching it requires
      // either an explicit `browser` request or an explicit opt-in, because it
      // ships the owner's audio to a Google service (PLATFORM_MANAGED_UNKNOWN)
      // and, on this host, answers `network` without ever producing a
      // transcript. Falling back silently would trade a truthful "unavailable"
      // for an unannounced privacy change that still cannot transcribe.
      const browserFallbackAllowed =
        sttMode === "browser" ||
        (browserFallbackEnabled &&
          (browserAvailable ||
            admission.mode === "browser_streaming" ||
            admission.mode === "browser_fallback"));
      if (browserFallbackAllowed) {
        stt = createBrowserStreamingStt({
          getSessionId: () => self.manager?.getSnapshot?.()?.sessionId || "",
        });
        selectedMode = "browser_streaming";
      } else if (!inBrowser) {
        // No browser speech engine exists in this runtime at all — Node, the
        // test harness. Deterministic adapter, never a product surface.
        stt = createMockStreamingStt();
        selectedMode = "mock";
      } else {
        // A browser with no SpeechRecognition and no local engine has no way
        // to transcribe. Saying so is the only truthful answer: substituting
        // the mock here would publish invented transcripts as if they were
        // speech, and would open a microphone that can produce no STT.
        stt = null;
        selectedMode = "unavailable";
        unsupportedReason = browserAvailable
          ? "Local speech recognition is unavailable, and the browser speech fallback is turned off."
          : "Speech recognition is unavailable in this browser and no local STT engine is installed.";
      }
    }
  }

  const turns = createTurnCoordinator({
    onTurnFinal: (turn) => {
      self.manager?.notifyTurnFinal?.(turn);
    },
    onEvent: (ev) => {
      self.manager?.notifyPipelineEvent?.(ev);
    },
  });

  let unsubPartial = null;
  let unsubFinal = null;
  let unsubError = null;
  let tickTimer = null;
  let active = false;
  let degraded =
    admission.admission !== "LOCAL_STT_READY" &&
    admission.legacyAdmission !== "LOCAL_STT_ALLOWED";
  let fallbackUsed = false;

  async function startAdapter(adapter) {
    await adapter.start({ sessionId: self.manager?.getSnapshot?.()?.sessionId });
    unsubPartial = adapter.onPartial((raw) => {
      const ev = normalizeTranscriptEvent(raw);
      // PARTIAL ≠ executable
      turns.onPartial(ev);
      self.manager?.setTranscript?.({ partial: ev.text });
      self.manager?.notifyPartialTranscript?.(ev);
      self.manager?.notifyPipelineEvent?.({ type: "stt.partial", text: ev.text, privacyClass: ev.privacyClass });
      self.manager?.notifySttEngineState?.(buildEngineState());
    });
    unsubFinal = adapter.onFinal((raw) => {
      const ev = normalizeTranscriptEvent(raw);
      turns.onFinal(ev);
      self.manager?.setTranscript?.({ final: ev.text, partial: "" });
      self.manager?.notifyPipelineEvent?.({ type: "stt.final", text: ev.text, privacyClass: ev.privacyClass });
      self.manager?.notifySttEngineState?.(buildEngineState());
    });
    // Engine errors are the authoritative error source for input; they must
    // reach published runtime state rather than dying in adapter telemetry.
    unsubError =
      adapter.onError?.((err) => {
        self.manager?.notifySttError?.(err);
      }) || null;
    tickTimer = setInterval(() => turns.tick(), 120);
    active = true;
  }

  function buildEngineState() {
    const h = stt?.health?.() || {};
    const label = formatVoiceInputLabel({
      ...h,
      adapter: h.adapter || selectedMode,
      privacyClass: h.privacyClass || admission.privacyClass,
      modelId: h.modelId || admission.modelId,
      engineId: h.engineId,
      degraded,
      admission: admission.admission,
      admissionState: h.admissionState || admission.admission,
    });
    return {
      mode: selectedMode,
      admission: admission.admission,
      privacyClass: h.privacyClass || admission.privacyClass || STT_PRIVACY.UNAVAILABLE,
      modelId: h.modelId || admission.modelId || null,
      engineId: h.engineId || null,
      language: h.language || null,
      degraded,
      fallbackUsed,
      hierarchy,
      label,
      supported: Boolean(stt),
      unsupportedReason,
    };
  }

  /**
   * Synchronous cancellation boundary.
   *
   * Everything that can still produce a transcript, a timer tick, or a
   * recognizer restart is closed before this function returns:
   *
   *   - `active` cleared, so `start()` cannot no-op its way back in;
   *   - the turn tick interval cleared;
   *   - partial/final subscriptions detached, so late adapter events reach
   *     no manager;
   *   - the adapter cancelled synchronously (`cancelSync`, or the
   *     synchronous prefix of `cancel()` for adapters without it);
   *   - the turn coordinator reset.
   *
   * Callers that must not await — `endInput()` is synchronous by contract —
   * call this directly. The returned `tail` is the adapter's asynchronous
   * remainder, already wrapped so it settles to a classification instead of
   * rejecting; awaiting it is optional, ignoring it cannot go unhandled.
   *
   * Idempotent: a second call finds nothing live and reports `already_stopped`.
   *
   * @returns {{ closed: boolean, tail: Promise<{status: string, errorCode: string|null}> }}
   */
  function beginStop() {
    const wasActive = active;
    active = false;
    if (tickTimer) {
      clearInterval(tickTimer);
      tickTimer = null;
    }
    if (unsubPartial) unsubPartial();
    if (unsubFinal) unsubFinal();
    if (unsubError) unsubError();
    unsubPartial = unsubFinal = unsubError = null;

    let tail = null;
    let syncError = null;
    try {
      if (typeof stt?.cancelSync === "function") {
        stt.cancelSync();
      } else {
        // Contract: cancel()'s synchronous prefix must close the window too.
        tail = stt?.cancel?.();
      }
    } catch (err) {
      syncError = err;
    }
    turns.reset();

    const classified = classifyTeardown({
      tail,
      syncError,
      wasActive,
      mode: selectedMode,
    });
    return { closed: true, tail: classified };
  }

  return {
    get manager() {
      return self.manager;
    },
    set manager(m) {
      self.manager = m;
    },
    admission,
    hierarchy,
    stt,
    turns,

    async start() {
      if (active) return;
      if (!stt) {
        degraded = true;
        self.manager?.notifySttUnsupported?.(unsupportedReason);
        self.manager?.notifySttEngineState?.(buildEngineState());
        recordVoiceTelemetry("stt_unsupported", {
          errorCode: unsupportedReason.slice(0, 80),
        });
        return;
      }
      if (
        admission.admission === "LOCAL_STT_BLOCKED_MEMORY" &&
        admission.mode === "text_or_manual"
      ) {
        degraded = true;
        self.manager?.notifySttDegraded?.(admission.reason);
        self.manager?.notifySttEngineState?.(buildEngineState());
        return;
      }
      try {
        await startAdapter(stt);
        degraded =
          selectedMode === "browser_streaming" ||
          admission.admission === "LOCAL_STT_READY_DEGRADED";
        recordVoiceTelemetry("pipeline_started", {
          reason: selectedMode,
        });
        self.manager?.notifySttEngineState?.(buildEngineState());
      } catch (err) {
        // Fallback: browser if local failed
        if (selectedMode === "local_streaming" && browserAvailable) {
          try {
            stt = createBrowserStreamingStt({
              getSessionId: () => self.manager?.getSnapshot?.()?.sessionId || "",
            });
            selectedMode = "browser_streaming";
            fallbackUsed = true;
            await startAdapter(stt);
            degraded = true;
            self.manager?.notifySttDegraded?.(
              `Local STT failed (${String(err?.message || err).slice(0, 80)}); browser fallback`
            );
            self.manager?.notifySttEngineState?.(buildEngineState());
            return;
          } catch (err2) {
            degraded = true;
            self.manager?.notifySttDegraded?.(String(err2?.message || err2));
            recordVoiceTelemetry("pipeline_failed", {
              errorCode: String(err2?.message || err2).slice(0, 80),
            });
            return;
          }
        }
        degraded = true;
        self.manager?.notifySttDegraded?.(String(err?.message || err));
        recordVoiceTelemetry("pipeline_failed", {
          errorCode: String(err?.message || err).slice(0, 80),
        });
        self.manager?.notifySttEngineState?.(buildEngineState());
      }
    },

    /** Notify VAD speech for turn coordination */
    onVadSpeechStart() {
      turns.onVadSpeechStart();
    },
    onVadSpeechEnd() {
      turns.onVadSpeechEnd();
      // Local STT: silence end → flush final decode
      if (stt?.capabilities?.()?.pushAudio) {
        void stt.flush?.();
      }
    },

    onAcousticInterrupt() {
      turns.beginInterruptEvaluation("ACOUSTIC_SPEECH");
    },

    /**
     * Feed pre-roll PCM to local adapters; browser only records metadata.
     * @param {Float32Array|number[]} samples
     */
    attachPreRoll(samples) {
      stt?.pushAudio?.(samples, {
        preRollAttached: true,
        sampleCount: samples?.length || 0,
      });
    },

    /**
     * Live PCM from AudioFrameTap / VAD path — local only.
     */
    pushLivePcm(frame, meta = {}) {
      if (stt?.capabilities?.()?.pushAudio) {
        stt.pushAudio?.(frame, meta);
      }
    },

    /** Test helpers for mock STT */
    getMockStt() {
      return stt;
    },

    getStt() {
      return stt;
    },

    getEngineState() {
      return buildEngineState();
    },

    beginStop,

    async stop() {
      const { tail } = beginStop();
      return tail;
    },

    health() {
      const engine = buildEngineState();
      return {
        active,
        degraded,
        admission,
        hierarchy,
        selectedMode,
        fallbackUsed,
        stt: stt?.health?.() || null,
        turns: turns.health(),
        engine,
        label: engine.label,
      };
    },
  };
}

export { createHintDrivenLocalStt };
