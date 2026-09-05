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
 * @param {object} opts
 * @param {object} opts.manager VoiceSessionManager
 * @param {"browser"|"mock"|"local"|"auto"} [opts.sttMode]
 * @param {object} [opts.sttAdapter] inject adapter
 * @param {object} [opts.admissionSignals]
 * @param {object} [opts.localSttFactory] () => adapter
 */
export function createRealtimeVoicePipeline({
  manager: managerIn = null,
  sttMode = "auto",
  sttAdapter = null,
  admissionSignals = {},
  localSttFactory = null,
} = {}) {
  const self = { manager: managerIn };
  const browserAvailable = Boolean(getRecognitionCtor());

  const signals = {
    browserSttAvailable: browserAvailable || sttMode === "mock",
    heavyLocalSttRequested: sttMode === "local",
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
      if (sttMode === "browser" || browserAvailable || admission.mode === "browser_streaming" || admission.mode === "browser_fallback") {
        stt = createBrowserStreamingStt({
          getSessionId: () => self.manager?.getSnapshot?.()?.sessionId || "",
        });
        selectedMode = "browser_streaming";
      } else {
        stt = createMockStreamingStt();
        selectedMode = "mock";
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
    tickTimer = setInterval(() => turns.tick(), 120);
    active = true;
  }

  function buildEngineState() {
    const h = stt.health?.() || {};
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
    };
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
      stt.pushAudio?.(samples, {
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

    async stop() {
      active = false;
      if (tickTimer) {
        clearInterval(tickTimer);
        tickTimer = null;
      }
      if (unsubPartial) unsubPartial();
      if (unsubFinal) unsubFinal();
      unsubPartial = unsubFinal = null;
      try {
        await stt.cancel();
      } catch {
        /* ignore */
      }
      turns.reset();
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
        stt: stt.health?.() || null,
        turns: turns.health(),
        engine,
        label: engine.label,
      };
    },
  };
}

export { createHintDrivenLocalStt };
