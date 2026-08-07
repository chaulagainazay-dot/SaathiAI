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
  };
  const subscribers = new Set();
  let inputClaim = null;
  let outputClaim = null;
  let closed = false;
  let listening = false;
  let speaking = false;
  let thinking = false;
  let interrupting = false;
  let error = "";
  let startedAt = null;

  function publish(partial = {}) {
    const now = new Date().toISOString();
    snapshot = {
      ...snapshot,
      ...partial,
      lastActivityAt: now,
      state: deriveSessionState({
        closed,
        error: error || partial.error,
        listening,
        speaking,
        thinking,
        interrupting,
        degraded: snapshot.degraded,
        ready: Boolean(snapshot.capabilities?.microphoneAvailable || snapshot.capabilities?.speechRecognitionAvailable),
      }),
      inputClaimId: inputClaim?.id || null,
      outputClaimId: outputClaim?.id || null,
      inputState: listening ? "listening" : inputClaim ? "held" : "idle",
      outputState: speaking ? "speaking" : outputClaim ? "held" : "idle",
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
     * Claim input; policy: stop output first (manual interrupt).
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
      return publish({ error: "" });
    },

    getInputClaim() {
      return inputClaim;
    },

    endInput(reason = "USER_CANCEL") {
      if (inputClaim) {
        inputClaim.release();
        inputClaim = null;
      } else {
        forceReleaseInput(reason);
      }
      listening = false;
      recordVoiceTelemetry("input_stopped", {
        sessionId: snapshot.sessionId,
        reason,
      });
      return publish();
    },

    async beginOutput({ label = "voice-output", stop } = {}) {
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
        },
      });
      speaking = true;
      error = "";
      recordVoiceTelemetry("output_started", {
        sessionId: snapshot.sessionId,
        claimId: outputClaim.id,
      });
      return publish({ error: "" });
    },

    getOutputClaim() {
      return outputClaim;
    },

    async endOutput(reason = "USER_CANCEL") {
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
     * Canonical interrupt — manual/input-request interruption (not acoustic VAD).
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

      // Input: only release on session close / logout / route — not on mic request
      if (
        reason === "ROUTE_CHANGE" ||
        reason === "SESSION_CLOSE" ||
        reason === "LOGOUT" ||
        reason === "ERROR"
      ) {
        if (inputClaim) {
          inputClaim.release();
          inputClaim = null;
        } else {
          forceReleaseInput(reason);
        }
        listening = false;
        try {
          await hooks.onStopInput?.(reason);
        } catch {
          /* ignore */
        }
      }

      interrupting = false;
      return publish();
    },

    async close(reason = "SESSION_CLOSE") {
      await api.interrupt(reason);
      if (inputClaim) {
        inputClaim.release();
        inputClaim = null;
      }
      forceReleaseInput(reason);
      listening = false;
      speaking = false;
      thinking = false;
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
      api.close("SESSION_CLOSE");
      subscribers.clear();
    },
  };

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
