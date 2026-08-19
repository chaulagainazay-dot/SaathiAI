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
import { createRealtimeVoicePipeline } from "./pipeline-coordinator.js";

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
    lastTurn: null,
    lastPipelineEvent: null,
    sttDegraded: false,
    sttDegradedReason: "",
    interruptClass: null,
    sttEngine: null,
    voiceInputLabel: null,
    sttUnsupported: false,
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

  /** @type {ReturnType<typeof createRealtimeVoicePipeline>|null} */
  let pipeline = null;

  /**
   * Monotonic input generation. `beginInput()` opens a new one; anything
   * stamped with an older generation belongs to a session the user already
   * ended, and a consumer that pinned its generation can reject it.
   */
  let inputEpoch = 0;
  let turnSeq = 0;
  /** @type {Set<(turn: object) => void>} */
  const finalTurnListeners = new Set();
  /** @type {Set<(partial: object) => void>} */
  const partialTranscriptListeners = new Set();
  /** Last error code published, so one engine fault is reported once. */
  let lastPublishedErrorCode = "";

  function fanOut(listeners, payload) {
    for (const fn of listeners) {
      try {
        fn(payload);
      } catch {
        /* a consumer's failure must not break the others */
      }
    }
  }

  /**
   * Observe an unawaited cleanup promise.
   *
   * Teardown entry points are synchronous by contract, so the async parts of
   * cleanup are started and not awaited. Dropping those promises on the floor
   * would turn any failure into an unhandled rejection — invisible here, fatal
   * to the process. Attaching this instead records the failure and resolves.
   *
   * @param {unknown} tail
   * @param {string} stage
   * @param {string} reason
   * @returns {Promise<{status: string, errorCode: string|null}>} never rejects
   */
  function observeCleanupTail(tail, stage, reason) {
    if (!tail || typeof tail.then !== "function") {
      return Promise.resolve({ status: "clean", errorCode: null });
    }
    return tail.then(
      () => ({ status: "clean", errorCode: null }),
      (err) => {
        const errorCode = String(err?.message || err).slice(0, 80);
        recordVoiceTelemetry("cleanup_failed", {
          sessionId: snapshot.sessionId,
          reason: `${stage}:${reason}`,
          errorCode,
        });
        return { status: "async_error", errorCode };
      }
    );
  }

  /**
   * The last teardown tail, so callers and tests can observe how cleanup
   * finished without any teardown path having to become async.
   * @type {Promise<{status: string, errorCode: string|null}>}
   */
  let inputPipelineTeardown = Promise.resolve({ status: "idle", errorCode: null });

  /**
   * Detach and stop the streaming input pipeline.
   *
   * The browser STT adapter restarts its own recognizer from `onend`, so the
   * only thing that ends capture is the adapter's cancelled flag. `endInput()`
   * is synchronous by contract, and awaiting an async stop would leave a window
   * where that self-restart could win the race. `beginStop()` exists for
   * exactly this: it closes the whole restart window — tick timer, transcript
   * subscriptions, cancelled flag, recognizer abort — before it returns, and
   * hands back the asynchronous remainder separately.
   *
   * That remainder is kept, not discarded. It never rejects (the coordinator
   * classifies it first), so nothing here suppresses a failure: a failed
   * teardown lands in telemetry and in `whenInputPipelineStopped()`.
   *
   * Idempotent: a second call finds no pipeline and does nothing.
   *
   * @returns {Promise<{status: string, errorCode: string|null}>|null}
   */
  function stopInputPipeline(reason = "SESSION_CLOSE") {
    const stopping = pipeline;
    if (!stopping) return null;
    pipeline = null;
    let tail;
    try {
      ({ tail } = stopping.beginStop());
    } catch (err) {
      // beginStop is written not to throw; if it ever does, the failure is
      // recorded rather than swallowed, and teardown still continues.
      const errorCode = String(err?.message || err).slice(0, 80);
      recordVoiceTelemetry("stt_teardown_failed", { reason, errorCode });
      tail = Promise.resolve({ status: "begin_stop_threw", errorCode });
    }
    inputPipelineTeardown = tail;
    recordVoiceTelemetry("stt_pipeline_stopped", {
      sessionId: snapshot.sessionId,
      reason,
    });
    return tail;
  }

  function publish(partial = {}) {
    const now = new Date().toISOString();
    const caps = snapshot.capabilities || detectVoiceCapabilities();
    const vadOk = !bargeIn.isVadFailed() && caps.vadAvailable;
    const sttOk = caps.streamingSttAvailable && !snapshot.sttDegraded;
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
        degraded: snapshot.degraded || bargeIn.isVadFailed() || snapshot.sttDegraded,
        ready: Boolean(caps.microphoneAvailable || caps.speechRecognitionAvailable),
      }),
      capabilities: {
        ...caps,
        vadAvailable: vadOk,
        acousticBargeInAvailable: vadOk && !bargeIn.isVadFailed(),
        streamingSttAvailable: sttOk || Boolean(pipeline && !pipeline.health?.()?.degraded),
        partialTranscriptAvailable: sttOk || Boolean(pipeline),
        turnCoordinationAvailable: true,
        manualInterruptAvailable: true,
        fullDuplexAvailable: false,
        wakeWordAvailable: false,
        streamingTtsAvailable: false,
      },
      inputClaimId: inputClaim?.id || null,
      outputClaimId: outputClaim?.id || null,
      inputState: listening ? "listening" : inputClaim ? "held" : "idle",
      outputState: speaking ? "speaking" : outputClaim ? "held" : "idle",
      vadHealth: bargeIn.health(),
      pipelineHealth: pipeline?.health?.() || null,
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
    if (!inputClaim) return;
    // Ownership can be taken away as well as given up: another surface
    // acquiring the microphone preempts this claim. The streaming pipeline's
    // recognizer is created inside the adapter rather than registered on the
    // claim, so releasing the claim does not stop it — without this, a chat
    // voice surface taking the microphone would leave the shell's recognizer
    // running against a claim it no longer holds.
    const lost = !getInputOwnerSnapshot().claimId || inputClaim.isActive?.() === false;
    if (!lost) return;
    stopInputPipeline("CLAIM_PREEMPTED");
    inputClaim = null;
    listening = false;
    publish();
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
      if (on) pipeline?.onVadSpeechStart?.();
      else pipeline?.onVadSpeechEnd?.();
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
     * The authoritative finalized turn.
     *
     * Reached only from the streaming pipeline's own turn coordinator — there
     * is one recognizer and one path to a final. Each turn carries a
     * `turnId`, so a consumer that submits work can be exactly-once without
     * inspecting text, and an `epoch`, so a consumer can reject a turn that
     * belongs to a session it no longer owns.
     *
     * `isExecutable` stays informational: Command must not auto-execute tools.
     */
    notifyTurnFinal(turn) {
      publish({ lastTurn: turn });
      const text = String(turn?.text || "").trim();
      // Empty finals carry nothing to submit. A turn with no live pipeline
      // behind it is a late event from a session already torn down.
      if (!text || !pipeline) return;
      // Identity comes from the turn's own sequence when it has one, so
      // redelivering the same turn object is recognisably the same turn.
      const sequence = Number(turn?.sequence) || (turnSeq += 1);
      fanOut(finalTurnListeners, {
        ...turn,
        text,
        sessionId: snapshot.sessionId,
        epoch: inputEpoch,
        turnId: `${snapshot.sessionId || "vs"}:${inputEpoch}:${sequence}`,
      });
    },

    /**
     * A partial transcript. Published for display; never executable, never a
     * finalized turn, and dropped once the pipeline behind it is gone.
     */
    notifyPartialTranscript(ev) {
      const text = String(ev?.text || "").trim();
      if (!text || !pipeline) return;
      fanOut(partialTranscriptListeners, {
        text,
        sessionId: snapshot.sessionId,
        epoch: inputEpoch,
        privacyClass: ev?.privacyClass || null,
        isFinal: false,
        isExecutable: false,
      });
    },

    /** Subscribe to authoritative finalized turns. */
    onFinalTurn(cb) {
      finalTurnListeners.add(cb);
      return () => finalTurnListeners.delete(cb);
    },

    /** Subscribe to authoritative partial transcripts. */
    onPartialTranscript(cb) {
      partialTranscriptListeners.add(cb);
      return () => partialTranscriptListeners.delete(cb);
    },

    getInputEpoch() {
      return inputEpoch;
    },

    /**
     * An engine fault from the one authoritative recognizer. Published once:
     * a recognizer can repeat the same error every restart attempt, and the
     * user needs one truthful message, not a stream of them.
     */
    notifySttError(err) {
      const code = String(err?.code || err?.message || err || "speech_recognition_error");
      if (code === lastPublishedErrorCode) return snapshot;
      lastPublishedErrorCode = code;
      return api.setError(code);
    },

    /**
     * No engine can transcribe in this runtime. Truthful unavailability, not
     * a silent downgrade to a deterministic stand-in.
     */
    notifySttUnsupported(reason) {
      const message = String(
        reason || "Speech recognition is unavailable in this browser."
      );
      error = message;
      lastPublishedErrorCode = message;
      recordVoiceTelemetry("stt_unsupported", {
        sessionId: snapshot.sessionId,
        errorCode: message.slice(0, 80),
      });
      return publish({
        sttUnsupported: true,
        sttDegraded: true,
        sttDegradedReason: message,
        degraded: true,
        error: message,
      });
    },
    notifyPipelineEvent(ev) {
      publish({ lastPipelineEvent: ev });
    },
    notifySttDegraded(reason) {
      publish({ sttDegraded: true, sttDegradedReason: String(reason || ""), degraded: true });
    },
    notifySttEngineState(engine) {
      publish({
        sttEngine: engine || null,
        voiceInputLabel: engine?.label || null,
      });
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
      inputEpoch += 1;
      turnSeq = 0;
      lastPublishedErrorCode = "";
      listening = true;
      error = "";
      recordVoiceTelemetry("input_started", {
        sessionId: snapshot.sessionId,
        claimId: inputClaim.id,
      });
      // Start streaming STT + turn coordinator (browser or mock)
      try {
        await api.startStreamingPipeline({ sttMode: hooks.sttMode || "auto" });
      } catch (err) {
        api.notifySttDegraded(String(err?.message || err));
      }
      // `error` is blank unless starting the pipeline reported a real fault —
      // an unsupported engine, for instance. Blanking it here unconditionally
      // would erase the one truthful thing the runtime just learned.
      return publish({ error });
    },

    /**
     * Attach streaming STT pipeline (tests may inject mock mode).
     */
    async startStreamingPipeline({ sttMode = "auto" } = {}) {
      // One recognizer per session: any prior pipeline is torn down first.
      stopInputPipeline("PIPELINE_RESTART");
      pipeline = createRealtimeVoicePipeline({ manager: api, sttMode });
      await pipeline.start();
      return pipeline.health();
    },

    getPipeline() {
      return pipeline;
    },

    /**
     * Resolve once the last input-pipeline teardown has fully settled.
     * Resolves to its classification; never rejects.
     */
    whenInputPipelineStopped() {
      return inputPipelineTeardown;
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
      // disarm() is async and endInput is not; observe rather than drop it.
      observeCleanupTail(bargeIn.disarm(), "vad_disarm", reason);
      // Stop the recognizer before the ownership guard below. A consumer whose
      // cleanup releases the input claim first arrives here with nothing owned,
      // and an early return there used to leave the pipeline's self-restarting
      // recognizer holding the microphone after the user stopped voice.
      stopInputPipeline(reason);
      // Idempotent teardown. Every publish() allocates a new snapshot with a
      // fresh lastActivityAt, so publishing when nothing was owned hands every
      // React subscriber a changed value for a state change that did not
      // happen. A consumer whose cleanup calls endInput then re-runs forever.
      const foreignClaim = !inputClaim && Boolean(getInputOwnerSnapshot().claimId);
      const owned = Boolean(inputClaim) || listening || speechDetected || foreignClaim;
      if (inputClaim) {
        inputClaim.release();
        inputClaim = null;
      } else if (foreignClaim) {
        forceReleaseInput(reason);
      }
      if (!owned) return snapshot;
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
      // Idempotent for the same reason as endInput.
      const foreignClaim = !outputClaim && Boolean(getOutputOwnerSnapshot().claimId);
      const owned = Boolean(outputClaim) || speaking || foreignClaim;
      if (outputClaim) {
        await outputClaim.release();
        outputClaim = null;
      } else if (foreignClaim) {
        await forceReleaseOutput(reason);
      }
      if (!owned) return snapshot;
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
        // Navigation and logout end capture, so the recognizer goes with it.
        stopInputPipeline(reason);
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
        pipeline?.onAcousticInterrupt?.();
        // Attach pre-roll PCM to STT (local ingests; browser metadata-only)
        try {
          const pre = bargeIn.getPreRoll?.();
          if (pre?.length) {
            pipeline?.attachPreRoll?.(pre);
            pipeline?.pushLivePcm?.(pre, { preRollAttached: true });
          }
        } catch {
          /* ignore */
        }
      }

      interrupting = false;
      return publish({
        interruptClass: pipeline?.turns?.getLastInterruptClass?.() || null,
      });
    },

    async close(reason = "SESSION_CLOSE") {
      stopInputPipeline(reason);
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
      observeCleanupTail(bargeIn.disarm(), "vad_disarm", "DISPOSE");
      observeCleanupTail(api.close("SESSION_CLOSE"), "close", "DISPOSE");
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
