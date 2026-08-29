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
} = {}) {
  let generation = 0;
  let run = null;
  let lastRun = null;

  async function teardown(state) {
    // Stop timers and tracks synchronously first; then close the graph and hand
    // ownership back. Each step is independent so a throw cannot strand the rest.
    if (state.deadlineId !== null) {
      clearTimeoutImpl(state.deadlineId);
      state.deadlineId = null;
    }
    if (state.intervalId !== null) {
      state.clearIntervalImpl(state.intervalId);
      state.intervalId = null;
    }
    const tap = state.tap;
    state.tap = null;
    // Initiate processor cancellation before stopping the claimed track. The
    // real MediaStreamTrackProcessor stream can otherwise leave cancel()
    // pending after its source has already ended. stop() is idempotent and
    // begins cancellation synchronously before its first await.
    let tapCleanup;
    try { tapCleanup = tap?.stop?.({ timeoutMs: cleanupTimeoutMs, setTimeoutImpl, clearTimeoutImpl }); } catch { tapCleanup = Promise.resolve({ confirmed: false, state: "unknown" }); }
    // Stop tracks synchronously immediately after cancellation is initiated.
    const tracks = state.stream?.getTracks?.() || [];
    try { tracks.forEach((t) => t.stop()); } catch { /* gone */ }
    const endedTrackCount = tracks.filter((t) => t?.readyState === "ended").length;
    state.stream = null;
    let tapResult = { confirmed: true, state: "closed" };
    try { tapResult = await tapCleanup || tapResult; } catch { tapResult = { confirmed: false, state: "unknown" }; }
    const claim = state.claim;
    try { claim?.release?.(); } catch { /* already released */ }
    const claimReleased = claim ? (typeof claim.isActive === "function" ? !claim.isActive() : true) : true;
    state.claim = null;
    return { trackCount: tracks.length, endedTrackCount, tracksEnded: endedTrackCount === tracks.length, graphClosed: Boolean(tapResult.confirmed), audioContextState: tapResult.state, claimReleased };
  }

  /** Idempotent per generation. The first reason wins; later ones are ignored. */
  function terminalize(state, reason) {
    if (!state || state.terminal) return false;
    state.terminal = true;
    state.reason = reason;
    try { onCleanupPending(reason, state.generation); } catch { /* reporting must not throw */ }
    state.cleanupPromise = state.cleanupPromise || teardown(state);
    if (run === state) run = null;
    lastRun = state;
    state.cleanupPromise.then((diagnostics) => {
      state.cleanup = diagnostics;
      state.cleanupConfirmed = diagnostics.tracksEnded && diagnostics.graphClosed && diagnostics.claimReleased;
      state.cleanupFailed = !state.cleanupConfirmed;
      try { onTerminal(reason, state.generation, diagnostics); } catch { /* reporting must not throw */ }
    });
    return true;
  }

  return {
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
        if (superseded()) { await teardown(state); return { started: false, reason: state.reason }; }

        const stream = await openMicrophone(state.claim);
        if (superseded()) {
          // The deadline (or a Stop) fired while the device was opening. The
          // stream that just arrived is ours to close, and nothing else.
          try { stream?.getTracks?.().forEach((t) => t.stop()); } catch { /* gone */ }
          await teardown(state);
          return { started: false, reason: state.reason };
        }
        state.stream = stream;

        const tap = createTap(stream, onFrame);
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
