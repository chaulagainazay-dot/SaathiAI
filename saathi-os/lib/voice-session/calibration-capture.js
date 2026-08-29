/**
 * The microphone-safety half of calibration: a hard deadline that does not
 * depend on anything asynchronous succeeding.
 *
 * The first version armed its 15-second timer *after* `await tap.start()`. The
 * device was therefore already open while the only thing that would ever close
 * it was still being constructed. A `tap.start()` that hung — an AudioContext
 * that never resumes, a device that stalls — would have left the microphone
 * live with no timer to stop it, indefinitely. Nothing in that design bounded
 * capture; the countdown was doing double duty as both presentation and safety,
 * and it only existed once the risky await had already returned.
 *
 * So safety is separated from presentation here:
 *
 *   - a generation is marked before anything is opened, and every async step
 *     re-checks it. A result belonging to a superseded or terminated run is
 *     discarded rather than applied;
 *   - the deadline is armed *first*, before the claim, before `getUserMedia`,
 *     before the tap. It fires on wall-clock time alone and terminalizes the
 *     generation whatever else is or is not happening;
 *   - termination is idempotent per generation and always performs the same
 *     teardown: stop tracks, close the tap, release the claim, clear timers;
 *   - a late `tap.start()` resolution finds its generation terminal, tears down
 *     the resources it just finished creating, and returns without restarting
 *     phases or overwriting the terminal outcome.
 *
 * The phase countdown is presentation only. If it never runs, the microphone
 * still closes.
 */
import { CALIBRATION_TOTAL_SECONDS } from "./mic-calibration.js";

/**
 * Cleanup margin beyond the measurement window.
 *
 * The deadline is a backstop, not the normal path: a healthy run completes on
 * its own at exactly 15 s. The margin exists so an ordinary completion that
 * happens to land a few milliseconds late is not reported as a timeout, while
 * still bounding a hung start to well under two seconds of extra capture.
 */
export const CALIBRATION_CLEANUP_MARGIN_MS = 1500;

export const CALIBRATION_DEADLINE_MS =
  CALIBRATION_TOTAL_SECONDS * 1000 + CALIBRATION_CLEANUP_MARGIN_MS;

export const TERMINAL_REASONS = Object.freeze({
  COMPLETED: "COMPLETED",
  STOPPED: "STOPPED",
  DEADLINE: "DEADLINE",
  ERROR: "ERROR",
  PREEMPTED: "PREEMPTED",
  DISPOSED: "DISPOSED",
});

export const CALIBRATION_STARTUP_STAGES = Object.freeze([
  "idle", "claim_acquired", "capture_requested", "capture_opened",
  "track_selected", "frame_source_constructing", "processor_constructed",
  "reader_acquired", "processing_loop_started", "first_frame_received",
  "measuring", "cleanup_started", "cleanup_confirmed", "cleanup_failed",
]);

const ERROR_NAMES = new Set(["Error", "NotAllowedError", "NotFoundError", "NotReadableError", "OverconstrainedError", "AbortError", "InvalidStateError", "TypeError"]);
const stageCode = (stage) => ({
  idle: "CLAIM_ACQUISITION_FAILED",
  claim_acquired: "CLAIM_ACQUISITION_FAILED",
  capture_requested: "CAPTURE_REQUEST_FAILED",
  capture_opened: "NO_AUDIO_TRACK",
  track_selected: "NO_AUDIO_TRACK",
  frame_source_constructing: "FRAME_SOURCE_CONSTRUCTION_FAILED",
  processor_constructed: "TRACK_PROCESSOR_CONSTRUCTION_FAILED",
  reader_acquired: "READER_ACQUISITION_FAILED",
  processing_loop_started: "PROCESSING_LOOP_FAILED",
  first_frame_received: "PROCESSING_LOOP_FAILED",
}[stage] || "CALIBRATION_START_FAILED");

/**
 * @param {object} deps injected so the whole lifecycle is testable without a
 *   browser: a hung start, a late resolve and a rejection are all just promises.
 */
export function createCalibrationCapture({
  acquireClaim,
  openMicrophone,
  createTap,
  onTerminal = () => {},
  onCleanupPending = () => {},
  setTimeoutImpl = setTimeout,
  clearTimeoutImpl = clearTimeout,
  deadlineMs = CALIBRATION_DEADLINE_MS,
  cleanupTimeoutMs = 2000,
  onStage = () => {},
  onCaptureReleased = () => {},
  onPipelineCleanup = () => {},
  onPipelineDiagnostics = () => {},
} = {}) {
  let generation = 0;
  let run = null;
  let lastRun = null;
  let snapshot = Object.freeze({
    phase: "idle", startupStage: "idle", startupErrorCode: "", cleanupState: "cleanup_confirmed",
    captureReleaseState: "idle", trackCount: 0, endedTrackCount: 0, claimState: "idle",
    pipelineState: "idle", outstandingFrames: 0, readerCancelState: "idle", processingLoopState: "idle",
    phaseBTimeoutArmed: false, phaseBTimeoutFired: false, controllerPipelineState: "idle",
    pipelineCallbackCount: 0, pipelineCallbackLastState: "none", terminalCallbackCount: 0,
    cleanupPromiseState: "idle", phaseAFunctionReturned: false, phaseBEntered: false,
    hasDrainAfterRelease: false, hasTapCleanup: false,
    controllerImplementationId: "calibration-capture-v2-split-drain",
  });
  const subscribers = new Set();
  const publish = (patch) => {
    snapshot = Object.freeze({ ...snapshot, ...patch });
    for (const listener of subscribers) { try { listener(); } catch { /* observers must not throw */ } }
  };

  async function teardown(state) {
    // Stop timers and tracks synchronously first; then close the graph and hand
    // ownership back. Each step is independent so a throw cannot strand the rest.
    const tap = state.tap;
    state.tap = null;
    state.stage = "cleanup_started";
    publish({ startupStage: state.stage });
    try { onStage(state.stage, state); } catch { /* diagnostics must not throw */ }
    // Initiate processor cancellation before stopping the claimed track. The
    // real MediaStreamTrackProcessor stream can otherwise leave cancel()
    // pending after its source has already ended. stop() is idempotent and
    // begins cancellation synchronously before its first await.
    let tapCleanup;
    let drainAfterRelease;
    try {
      if (tap?.beginCancellation) {
        const handle = tap.beginCancellation();
        drainAfterRelease = () => tap.drainAfterCaptureRelease?.(handle);
      } else tapCleanup = tap?.stop?.({ timeoutMs: cleanupTimeoutMs, setTimeoutImpl, clearTimeoutImpl });
    } catch { tapCleanup = Promise.resolve({ confirmed: false, state: "unknown" }); }
    // Stop tracks synchronously immediately after cancellation is initiated.
    const tracks = state.stream?.getTracks?.() || [];
    try { tracks.forEach((t) => t.stop()); } catch { /* gone */ }
    const endedTrackCount = tracks.filter((t) => t?.readyState === "ended").length;
    const tracksEnded = endedTrackCount === tracks.length;
    state.stream = null;
    const claim = state.claim;
    try { claim?.release?.(); } catch { /* already released */ }
    const claimReleased = claim ? (typeof claim.isActive === "function" ? !claim.isActive() : true) : true;
    state.claim = null;
    const captureReleased = tracksEnded && claimReleased;
    publish({ captureReleaseState: captureReleased ? "confirmed" : "failed", trackCount: tracks.length, endedTrackCount, claimState: claimReleased ? "released" : "held", cleanupState: captureReleased ? "microphone_released_pipeline_pending" : "microphone_release_failed" });
    try { onCaptureReleased({ captureReleased, trackCount: tracks.length, endedTrackCount, claimReleased }); } catch { /* diagnostics must not throw */ }
    if (state.deadlineId !== null) {
      clearTimeoutImpl(state.deadlineId);
      state.deadlineId = null;
    }
    if (state.intervalId !== null) {
      state.clearIntervalImpl(state.intervalId);
      state.intervalId = null;
    }
    publish({ phaseAFunctionReturned: true });
    try { onPipelineDiagnostics({ phaseAFunctionReturned: true }); } catch { /* diagnostics must not throw */ }
    let tapResult = { confirmed: true, state: "closed" };
    let pipelineCleanup = "confirmed";
    // Arm the Phase B backstop before invoking drain. A real Streams drain can
    // remain pending, and even a synchronous adapter failure must not prevent
    // the timeout from existing.
    if (drainAfterRelease || tapCleanup) {
      publish({ phaseBEntered: true, hasDrainAfterRelease: Boolean(drainAfterRelease), hasTapCleanup: Boolean(tapCleanup), controllerImplementationId: "calibration-capture-v2-split-drain" });
      try {
        onPipelineDiagnostics({
          phaseBEntered: true,
          hasDrainAfterRelease: Boolean(drainAfterRelease),
          hasTapCleanup: Boolean(tapCleanup),
          controllerImplementationId: "calibration-capture-v2-split-drain",
        });
      } catch { /* diagnostics must not throw */ }
      let settled = false;
      let timeoutId = null;
      let nativeTimeoutId = null;
      let resolveTimeout;
      const timeout = new Promise((resolve) => { resolveTimeout = resolve; });
      const publishTimeout = () => {
        if (settled) return;
        settled = true;
        pipelineCleanup = "timed_out";
        tapResult = { confirmed: false, state: "timed_out" };
        publish({ phaseBTimeoutFired: true, controllerPipelineState: "timed_out", pipelineState: "timed_out", pipelineCallbackCount: snapshot.pipelineCallbackCount + 1, pipelineCallbackLastState: "timed_out", cleanupPromiseState: "settled" });
        try { onPipelineDiagnostics({ phaseBTimeoutFired: true, controllerPipelineState: "timed_out", cleanupPromiseState: "settled" }); } catch { /* diagnostics must not throw */ }
        try { onPipelineCleanup({ pipelineCleanup, ...tapResult }); } catch { /* reporting must not throw */ }
        resolveTimeout(tapResult);
      };
      timeoutId = setTimeoutImpl(publishTimeout, cleanupTimeoutMs);
      // Keep a native wall-clock backstop independent of injected capture
      // timers; Phase A must never be able to clear this deadline.
      nativeTimeoutId = globalThis.setTimeout(publishTimeout, cleanupTimeoutMs);
      try { onPipelineDiagnostics({ phaseBTimeoutArmed: true, controllerPipelineState: "pending", cleanupPromiseState: "pending" }); } catch { /* diagnostics must not throw */ }
      publish({ phaseBTimeoutArmed: true, controllerPipelineState: "pending", cleanupPromiseState: "pending" });
      if (drainAfterRelease) {
        // Defer invocation into a Promise job so synchronous throws become a
        // rejected drain and cannot block timeout construction.
        tapCleanup = Promise.resolve().then(() => drainAfterRelease());
      }
      const drain = Promise.resolve(tapCleanup).then(
        (result) => ({ result: result || { confirmed: true, state: "closed" }, status: "confirmed" }),
        () => ({ result: { confirmed: false, state: "failed" }, status: "failed" }),
      );
      const winner = await Promise.race([drain, timeout.then((result) => ({ result, status: "timed_out" }))]);
      if (!settled) {
        settled = true;
        tapResult = winner.result;
        pipelineCleanup = winner.status;
      }
      if (timeoutId !== null) clearTimeoutImpl(timeoutId);
      if (nativeTimeoutId !== null) globalThis.clearTimeout(nativeTimeoutId);
    }
    state.stage = (tracksEnded && tapResult.confirmed && claimReleased) ? "cleanup_confirmed" : "cleanup_failed";
    publish({ startupStage: state.stage });
    try { onStage(state.stage, state); } catch { /* diagnostics must not throw */ }
    if (pipelineCleanup !== "timed_out") {
      publish({ pipelineState: pipelineCleanup, pipelineCallbackCount: snapshot.pipelineCallbackCount + 1, pipelineCallbackLastState: pipelineCleanup });
      try { onPipelineCleanup({ pipelineCleanup, ...tapResult }); } catch { /* diagnostics must not throw */ }
    }
    publish({ controllerPipelineState: pipelineCleanup, cleanupPromiseState: "settled" });
    try { onPipelineDiagnostics({ controllerPipelineState: pipelineCleanup, cleanupPromiseState: "settled" }); } catch { /* diagnostics must not throw */ }
    return {
      ...tapResult,
      captureReleased,
      pipelineCleanup,
      trackCount: tracks.length,
      endedTrackCount,
      tracksEnded,
      graphClosed: tapResult.confirmed !== false,
      audioContextState: tapResult.state || "unknown",
      claimReleased,
    };
  }

  /** Idempotent per generation. The first reason wins; later ones are ignored. */
  function terminalize(state, reason) {
    if (!state || state.terminal) return false;
    state.terminal = true;
    state.reason = reason;
    publish({ cleanupPromiseState: "pending", cleanupState: "releasing_microphone", captureReleaseState: "pending", claimState: "held", pipelineState: "pending", controllerPipelineState: "pending" });
    try { onCleanupPending(reason, state.generation); } catch { /* reporting must not throw */ }
    state.cleanupPromise = state.cleanupPromise || teardown(state);
    if (run === state) run = null;
    lastRun = state;
    state.cleanupPromise.then((diagnostics) => {
      publish({ terminalCallbackCount: snapshot.terminalCallbackCount + 1, cleanupPromiseState: "settled", pipelineState: diagnostics.pipelineCleanup || "failed", captureReleaseState: diagnostics.captureReleased ? "confirmed" : "failed", trackCount: diagnostics.trackCount || 0, endedTrackCount: diagnostics.endedTrackCount || 0, claimState: diagnostics.claimReleased ? "released" : "held" });
      state.cleanup = {
        ...diagnostics,
        startupStage: state.startupStage || state.stage,
        startupErrorCode: state.startupErrorCode,
        startupErrorName: state.startupErrorName,
      };
      state.cleanupConfirmed = diagnostics.tracksEnded && diagnostics.graphClosed && diagnostics.claimReleased;
      state.cleanupFailed = !state.cleanupConfirmed;
      try { onTerminal(reason, state.generation, state.cleanup); } catch { /* reporting must not throw */ }
    });
    return true;
  }

  return {
    getSnapshot() { return snapshot; },
    subscribe(listener) { subscribers.add(listener); return () => subscribers.delete(listener); },
    get generation() { return generation; },
    isActive() { return Boolean(run) && !run.terminal; },
    currentReason() { return run?.reason ?? null; },

    /**
     * Begin one calibration capture.
     *
     * Returns when the capture is running or has already been terminalized.
     * Never throws: every failure path ends in the same teardown.
     */
    async start({ onFrame, onRunning, setIntervalImpl, clearIntervalImpl } = {}) {
      if (run && !run.terminal) return { started: false, reason: "ALREADY_ACTIVE" };

      generation += 1;
      const state = {
        generation,
        terminal: false,
        reason: null,
        claim: null,
        stream: null,
        tap: null,
        deadlineId: null,
        intervalId: null,
        clearIntervalImpl: clearIntervalImpl || clearInterval,
        cleanupPromise: null,
        cleanupConfirmed: false,
        cleanupFailed: false,
        stage: "idle",
        startupStage: "idle",
        startupErrorCode: null,
        startupErrorName: null,
      };
      run = state;

      // ── armed before anything can open or retain a device ──────────────
      state.deadlineId = setTimeoutImpl(() => {
        state.deadlineId = null;
        terminalize(state, TERMINAL_REASONS.DEADLINE);
      }, deadlineMs);

      const superseded = () => state.terminal || state.generation !== generation;

      try {
        state.claim = acquireClaim({
          onPreempt: () => terminalize(state, TERMINAL_REASONS.PREEMPTED),
        });
        state.stage = state.startupStage = "claim_acquired"; onStage(state.stage, state);
        if (superseded()) { await teardown(state); return { started: false, reason: state.reason }; }

        state.stage = state.startupStage = "capture_requested"; onStage(state.stage, state);
        const stream = await openMicrophone(state.claim);
        if (superseded()) {
          // The deadline (or a Stop) fired while the device was opening. The
          // stream that just arrived is ours to close, and nothing else.
          try { stream?.getTracks?.().forEach((t) => t.stop()); } catch { /* gone */ }
          await teardown(state);
          return { started: false, reason: state.reason };
        }
        state.stream = stream;
        state.stage = state.startupStage = "capture_opened"; onStage(state.stage, state);
        const audioTracks = stream?.getAudioTracks?.() || stream?.getTracks?.()?.filter((t) => t?.kind === "audio") || [];
        if (!audioTracks.length) { const e = new Error("no audio track"); e.code = "NO_AUDIO_TRACK"; throw e; }
        state.stage = state.startupStage = "track_selected"; onStage(state.stage, state);

        state.stage = state.startupStage = "frame_source_constructing"; onStage(state.stage, state);
        const frameHandler = (...args) => {
          if (state.startupStage === "first_frame_received") {
            state.stage = state.startupStage = "measuring";
            onStage(state.stage, state);
          }
          return onFrame?.(...args);
        };
        const tap = createTap(stream, frameHandler, (stage) => { state.stage = state.startupStage = stage; onStage(stage, state); });
        if (superseded()) {
          try { tap?.stop?.(); } catch { /* not started */ }
          await teardown(state);
          return { started: false, reason: state.reason };
        }
        state.tap = tap;

        await tap.start();
        if (superseded()) {
          // A late resolution. Tear down what it just built; do not restart
          // phases and do not overwrite the terminal outcome.
          try { tap.stop?.(); } catch { /* already stopped */ }
          await teardown(state);
          return { started: false, reason: state.reason };
        }
      } catch (error) {
        state.startupErrorCode = error?.code || stageCode(state.stage);
        state.startupErrorName = ERROR_NAMES.has(error?.name) ? error.name : "Error";
        terminalize(state, TERMINAL_REASONS.ERROR);
        return { started: false, reason: TERMINAL_REASONS.ERROR, error };
      }

      // Presentation only. Safety is already guaranteed by the deadline above.
      if (setIntervalImpl && onRunning) {
        state.intervalId = setIntervalImpl(() => {
          if (state.terminal) return;
          const done = onRunning();
          if (done) terminalize(state, TERMINAL_REASONS.COMPLETED);
        }, 200);
      }
      return { started: true, generation: state.generation };
    },

    /** Explicit Stop, completion, route change, logout and unmount all land here. */
    stop(reason = TERMINAL_REASONS.STOPPED) {
      if (run && !run.terminal) return terminalize(run, reason);
      if (lastRun?.cleanupPromise) return lastRun.cleanupPromise;
      return false;
    },
  };
}
