/**
 * VoiceSessionManager — single orchestrator for input/output ownership,
 * interrupt policy, and published session snapshot.
 */

import {
  INITIAL_VOICE_SESSION,
  detectVoiceCapabilities,
  deriveSessionState,
  INTERRUPT_REASONS,
} from "./contract.js";
import {
  acquireInputClaim,
  forceReleaseInput,
  getInputOwnerSnapshot,
  openMicrophoneForClaim,
  subscribeInputOwner,
} from "./input-owner.js";
import {
  acquireOutputClaim,
  forceReleaseOutput,
  getOutputOwnerSnapshot,
  subscribeOutputOwner,
  cancelBrowserSpeechSynthesis,
} from "./output-owner.js";
import { recordVoiceTelemetry } from "./telemetry.js";
import { createBargeInController } from "./barge-in-controller.js";

/**
 * @typedef {object} VoiceSessionManager
 */

/**
 * Create a manager instance (one per app shell).
 * @param {object} [hooks]
 * @param {(reason: string) => void|Promise<void>} [hooks.onStopOutput]
 * @param {(reason: string) => void|Promise<void>} [hooks.onStopInput]
 */
export function createVoiceSessionManager(hooks = {}) {
  let snapshot = {
    ...INITIAL_VOICE_SESSION,
    capabilities: detectVoiceCapabilities(),
    speechDetected: false,
    lastBargeInLatencyMs: null,
    vadHealth: null,
  };
  const subscribers = new Set();
  let inputClaim = null;
  let outputClaim = null;
  let closed = false;
  let listening = false;
  let speaking = false;
  let thinking = false;
  let interrupting = false;
  let speechDetected = false;
  let error = "";
  let startedAt = null;

  function getMediaStream() {
    return inputClaim?.mediaStream || null;
  }

  const bargeIn = createBargeInController({
    manager: null,
    getStream: getMediaStream,
  });

  function publish(partial = {}) {
    const now = new Date().toISOString();
    const caps = snapshot.capabilities || detectVoiceCapabilities();
    // If VAD failed, degrade capability flags honestly
    const vadOk = !bargeIn.isVadFailed() && caps.vadAvailable;
    snapshot = {
      ...snapshot,
      ...partial,
      lastActivityAt: now,
      speechDetected,
      state: deriveSessionState({
        closed,
        error: error || partial.error,
        listening,
        speaking,
        thinking,
        interrupting,
        speechDetected,
        degraded: snapshot.degraded || bargeIn.isVadFailed(),
        ready: Boolean(caps.microphoneAvailable || caps.speechRecognitionAvailable),
      }),
      capabilities: {
        ...caps,
        vadAvailable: vadOk,
        acousticBargeInAvailable: vadOk && !bargeIn.isVadFailed(),
        manualInterruptAvailable: true,
        fullDuplexAvailable: false,
        wakeWordAvailable: false,
        streamingSttAvailable: false,
        streamingTtsAvailable: false,
      },
      inputClaimId: inputClaim?.id || null,
      outputClaimId: outputClaim?.id || null,
      inputState: listening ? "listening" : inputClaim ? "held" : "idle",
      outputState: speaking ? "speaking" : outputClaim ? "held" : "idle",
      vadHealth: bargeIn.health(),
    };
    for (const fn of subscribers) {
      try {
        fn(snapshot);
      } catch {
        /* ignore */
      }
    }
    return snapshot;
  }

  function refreshCapabilities() {
    publish({ capabilities: detectVoiceCapabilities() });
  }

  const unsubIn = subscribeInputOwner(() => {
    if (!getInputOwnerSnapshot().claimId && inputClaim) {
      inputClaim = null;
      listening = false;
      publish();
    }
  });
  const unsubOut = subscribeOutputOwner(() => {
    if (!getOutputOwnerSnapshot().claimId && outputClaim) {
      outputClaim = null;
      speaking = false;
      publish();
    }
  });

  const api = {
    getSnapshot() {
      return snapshot;
    },
    subscribe(fn) {
      subscribers.add(fn);
      try {
        fn(snapshot);
      } catch {
        /* ignore */
      }
      return () => subscribers.delete(fn);
    },
    refreshCapabilities,

    notifySpeechDetected(on, _ev) {
      speechDetected = Boolean(on);
      publish();
    },
    notifyBargeInLatency(ms) {
      publish({ lastBargeInLatencyMs: ms });
    },
    notifyVadFailed(message) {
      error = "";
      publish({
        degraded: true,
        capabilities: {
          ...detectVoiceCapabilities(),
          vadAvailable: false,
          acousticBargeInAvailable: false,
          manualInterruptAvailable: true,
        },
      });
      recordVoiceTelemetry("vad_failed", { errorCode: String(message || "").slice(0, 80) });
    },

    /**
     * Ensure session id exists for UI/telemetry.
     */
    openSession({ sessionId = "", inputProvider = "browser", outputProvider = "platform" } = {}) {
      if (closed) closed = false;
      if (!startedAt) startedAt = new Date().toISOString();
      const sid = sessionId || snapshot.sessionId || `vs-${Date.now()}`;
      recordVoiceTelemetry("session_created", { sessionId: sid });
      return publish({
        sessionId: sid,
        startedAt,
        error: "",
        inputProvider,
        outputProvider,
        capabilities: detectVoiceCapabilities(),
      });
    },

    /**
     * Claim input; policy: stop output first (manual interrupt) unless acoustic path.
     */
    async beginInput({ label = "voice-input", stopOutputFirst = true } = {}) {
      if (closed) throw new Error("Voice session is closed");
      if (stopOutputFirst) {
        await api.interrupt("USER_MIC_REQUEST");
      }
      inputClaim = acquireInputClaim({
        label,
        onPreempt: () => {
          listening = false;
        },
      });
      listening = true;
      error = "";
      recordVoiceTelemetry("input_started", {
        sessionId: snapshot.sessionId,
        claimId: inputClaim.id,
      });
      // Arm VAD on same physical capture when stream is attached later
      return publish({ error: "" });
    },

    getInputClaim() {
      return inputClaim;
    },

    /**
     * Attach VAD to the current claim's MediaStream (same getUserMedia).
     */
    async armVad({ bargeInMode = false, config = {} } = {}) {
      try {
        if (inputClaim && !inputClaim.mediaStream) {
          // open mic with AEC when available; synthetic/tests may skip
          try {
            await openMicrophoneForClaim(inputClaim);
          } catch {
            /* headless / no mic — VAD still accepts processVadFrame */
          }
        }
        await bargeIn.arm({ bargeInMode, config });
        if (bargeInMode) {
          bargeIn.markSpeakingStart();
          if (config.echoSuppressionMs === 0) bargeIn.clearEchoWindow();
        }
        publish();
      } catch (err) {
        api.notifyVadFailed(String(err?.message || err));
      }
      return bargeIn.health();
    },

    /** Test/synthetic frames into VAD + pre-roll */
    processVadFrame(frame, meta) {
      bargeIn.processFrame(frame, meta);
    },

    getPreRollSamples() {
      return bargeIn.getPreRoll();
    },

    getBargeInHealth() {
      return bargeIn.health();
    },

    endInput(reason = "USER_CANCEL") {
      bargeIn.disarm();
      if (inputClaim) {
        inputClaim.release();
        inputClaim = null;
      } else {
        forceReleaseInput(reason);
      }
      listening = false;
      speechDetected = false;
      recordVoiceTelemetry("input_stopped", {
        sessionId: snapshot.sessionId,
        reason,
      });
      return publish();
    },

    async beginOutput({ label = "voice-output", stop, armBargeIn = true } = {}) {
      if (closed) throw new Error("Voice session is closed");
      // New assistant response interrupts prior speech
      if (outputClaim) {
        await api.interrupt("NEW_ASSISTANT_RESPONSE");
      }
      outputClaim = acquireOutputClaim({
        label,
        stop: async () => {
          try {
            await stop?.();
          } catch {
            /* ignore */
          }
          try {
            await hooks.onStopOutput?.("CLAIM_RELEASE");
          } catch {
            /* ignore */
          }
          cancelBrowserSpeechSynthesis();
          bargeIn.markSpeakingEnd();
        },
      });
      speaking = true;
      error = "";
      recordVoiceTelemetry("output_started", {
        sessionId: snapshot.sessionId,
        claimId: outputClaim.id,
      });
      publish({ error: "" });

      // Acoustic barge-in: keep/reuse single input capture for VAD monitor
      if (armBargeIn) {
        try {
          if (!inputClaim) {
            inputClaim = acquireInputClaim({ label: "vad-monitor" });
          }
          if (!inputClaim.mediaStream) {
            await openMicrophoneForClaim(inputClaim);
          }
          await bargeIn.arm({ bargeInMode: true });
          bargeIn.markSpeakingStart();
        } catch (err) {
          // VAD failure must not block playback — manual interrupt remains
          api.notifyVadFailed(String(err?.message || err));
        }
      }
      return snapshot;
    },

    getOutputClaim() {
      return outputClaim;
    },

    async endOutput(reason = "USER_CANCEL") {
      bargeIn.markSpeakingEnd();
      if (outputClaim) {
        await outputClaim.release();
        outputClaim = null;
      } else {
        await forceReleaseOutput(reason);
      }
      speaking = false;
      recordVoiceTelemetry("output_stopped", {
        sessionId: snapshot.sessionId,
        reason,
      });
      return publish();
    },

    setThinking(on) {
      thinking = Boolean(on);
      return publish();
    },

    setTranscript({ partial = "", final = "", assistant = "" } = {}) {
      return publish({
        transcriptPartial: partial,
        transcriptFinal: final || snapshot.transcriptFinal,
        assistantText: assistant || snapshot.assistantText,
      });
    },

    setError(message) {
      error = String(message || "");
      recordVoiceTelemetry("error", {
        sessionId: snapshot.sessionId,
        errorCode: error.slice(0, 80),
      });
      return publish({ error });
    },

    /**
     * Canonical interrupt — manual or ACOUSTIC_SPEECH (VAD).
     * @param {string} reason
     */
    async interrupt(reason = "USER_CANCEL") {
      if (!INTERRUPT_REASONS.includes(reason) && reason) {
        // allow extension strings
      }
      interrupting = true;
      publish();
      recordVoiceTelemetry("interruption", {
        sessionId: snapshot.sessionId,
        reason,
      });
      try {
        await hooks.onStopOutput?.(reason);
      } catch {
        /* ignore */
      }
      cancelBrowserSpeechSynthesis();
      bargeIn.markSpeakingEnd();
      if (outputClaim) {
        try {
          await outputClaim.release();
        } catch {
          /* ignore */
        }
        outputClaim = null;
      } else {
        await forceReleaseOutput(reason);
      }
      speaking = false;

      // Input: only release on session close / logout / route — keep for acoustic continue
      if (
        reason === "ROUTE_CHANGE" ||
        reason === "SESSION_CLOSE" ||
        reason === "LOGOUT" ||
        reason === "ERROR"
      ) {
        await bargeIn.disarm();
        if (inputClaim) {
          inputClaim.release();
          inputClaim = null;
        } else {
          forceReleaseInput(reason);
        }
        listening = false;
        speechDetected = false;
        try {
          await hooks.onStopInput?.(reason);
        } catch {
          /* ignore */
        }
      } else if (reason === "ACOUSTIC_SPEECH") {
        // Preserve input ownership so utterance continues after barge-in
        listening = true;
        speechDetected = true;
      }

      interrupting = false;
      return publish();
    },

    async close(reason = "SESSION_CLOSE") {
      await bargeIn.disarm();
      await api.interrupt(reason);
      if (inputClaim) {
        inputClaim.release();
        inputClaim = null;
      }
      forceReleaseInput(reason);
      listening = false;
      speaking = false;
      thinking = false;
      speechDetected = false;
      closed = true;
      recordVoiceTelemetry("cleanup", {
        sessionId: snapshot.sessionId,
        reason,
      });
      return publish({ sessionId: snapshot.sessionId });
    },

    dispose() {
      unsubIn();
      unsubOut();
      bargeIn.disarm();
      api.close("SESSION_CLOSE");
      subscribers.clear();
    },
  };

  // Wire circular barge-in → manager (mutable)
  bargeIn.manager = api;

  // initial capability detect
  refreshCapabilities();
  return api;
}

/** Process-wide default manager for browser shell */
let defaultManager = null;

export function getDefaultVoiceSessionManager() {
  if (!defaultManager) {
    defaultManager = createVoiceSessionManager();
  }
  return defaultManager;
}

export function resetDefaultVoiceSessionManager() {
  if (defaultManager) {
    defaultManager.dispose();
    defaultManager = null;
  }
}
