/**
 * RealtimeVoicePipelineCoordinator — SaathiOS-owned orchestration.
 * Pipecat/LiveKit would plug in as adapters later; this is the authority path.
 */

import { createBrowserStreamingStt, createMockStreamingStt } from "./browser-streaming-stt.js";
import { createTurnCoordinator } from "./turn-coordinator.js";
import { admitStreamingStt } from "./resource-budget.js";
import { getRecognitionCtor } from "./input-owner.js";
import { recordVoiceTelemetry } from "./telemetry.js";

/**
 * @param {object} opts
 * @param {object} opts.manager VoiceSessionManager
 * @param {"browser"|"mock"|"auto"} [opts.sttMode]
 * @param {object} [opts.sttAdapter] inject adapter
 */
export function createRealtimeVoicePipeline({
  manager: managerIn = null,
  sttMode = "auto",
  sttAdapter = null,
} = {}) {
  const self = { manager: managerIn };
  const browserAvailable = Boolean(getRecognitionCtor());
  const admission = admitStreamingStt({
    browserSttAvailable: browserAvailable || sttMode === "mock",
    heavyLocalSttRequested: false,
    localLlmActive: false,
  });

  let stt =
    sttAdapter ||
    (sttMode === "mock" || (sttMode === "auto" && !browserAvailable)
      ? createMockStreamingStt()
      : createBrowserStreamingStt({
          getSessionId: () => self.manager?.getSnapshot?.()?.sessionId || "",
        }));

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
  let degraded = admission.admission !== "LOCAL_STT_ALLOWED";

  return {
    get manager() {
      return self.manager;
    },
    set manager(m) {
      self.manager = m;
    },
    admission,
    stt,
    turns,

    async start() {
      if (active) return;
      if (admission.admission === "LOCAL_STT_BLOCKED_RESOURCE_PRESSURE") {
        degraded = true;
        self.manager?.notifySttDegraded?.(admission.reason);
        return;
      }
      try {
        await stt.start({ sessionId: self.manager?.getSnapshot?.()?.sessionId });
        unsubPartial = stt.onPartial((ev) => {
          // PARTIAL ≠ executable
          turns.onPartial(ev);
          self.manager?.setTranscript?.({ partial: ev.text });
          self.manager?.notifyPipelineEvent?.({ type: "stt.partial", text: ev.text });
        });
        unsubFinal = stt.onFinal((ev) => {
          turns.onFinal(ev);
          self.manager?.setTranscript?.({ final: ev.text, partial: "" });
          self.manager?.notifyPipelineEvent?.({ type: "stt.final", text: ev.text });
        });
        tickTimer = setInterval(() => turns.tick(), 120);
        active = true;
        degraded = false;
        recordVoiceTelemetry("pipeline_started", {
          reason: admission.mode,
        });
      } catch (err) {
        degraded = true;
        self.manager?.notifySttDegraded?.(String(err?.message || err));
        recordVoiceTelemetry("pipeline_failed", {
          errorCode: String(err?.message || err).slice(0, 80),
        });
      }
    },

    /** Notify VAD speech for turn coordination */
    onVadSpeechStart() {
      turns.onVadSpeechStart();
    },
    onVadSpeechEnd() {
      turns.onVadSpeechEnd();
    },

    onAcousticInterrupt() {
      turns.beginInterruptEvaluation("ACOUSTIC_SPEECH");
    },

    /** Feed pre-roll metadata (browser STT cannot ingest PCM) */
    attachPreRoll(samples) {
      stt.pushAudio?.(samples, {
        preRollAttached: true,
        sampleCount: samples?.length || 0,
      });
    },

    /** Test helpers for mock STT */
    getMockStt() {
      return stt;
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
      return {
        active,
        degraded,
        admission,
        stt: stt.health?.() || null,
        turns: turns.health(),
      };
    },
  };
}
