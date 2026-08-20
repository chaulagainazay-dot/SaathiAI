/**
 * R2.1-D10 — elapsed time for one voice turn.
 *
 * The dock used to run its clock from a single effect keyed on the stage:
 *
 *     if (stage === "idle") return undefined;
 *     const timer = setInterval(() => setNow(Date.now()), 1000);
 *
 * Every stage except `idle` was therefore treated as active — including
 * `fail`. During physical Test A the recognizer died with a `network` fault at
 * 00:04 and the counter kept climbing past 01:13, so a dead turn read as a
 * running one. Restarting `since` on every stage change also meant the number
 * measured the current stage rather than the turn, which is why a frozen value
 * could not simply be captured from it.
 *
 * The rules live here, as a pure transition, for two reasons: the component
 * owns the wall clock but should not own the policy, and a pure function can be
 * driven with fake time in a test instead of being inferred from rendered text.
 *
 * No timing is derived from labels, colours or error strings — only from the
 * canonical stage and a turn identity. Nothing is persisted.
 */

/** Rendered when there is no turn to measure. */
export const TIMER_IDLE_DISPLAY = "--:--";

/**
 * Stages whose elapsed time advances.
 *
 * `fail` is deliberately absent: that is the whole defect. `idle` is absent
 * because there is no turn yet.
 */
export const ACTIVE_TURN_STAGES = Object.freeze(["listen", "hear", "think", "speak"]);

/** @param {string} stage */
export function isActiveTurnStage(stage) {
  return ACTIVE_TURN_STAGES.includes(stage);
}

/**
 * mm:ss, clamped at zero and correct beyond an hour.
 * @param {number} ms
 */
export function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = String(Math.floor(total / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

/** The state a fresh dock starts from. */
export function createTurnTimerState() {
  return { epochKey: null, startedAt: null, frozenMs: null };
}

/**
 * Fold one observation into the timer.
 *
 * Pure and idempotent for a given `now`: calling it twice for the same render
 * — which React's Strict Mode does — produces the same state, because
 * `startedAt` and `frozenMs` are only ever set when they are still null.
 *
 * @param {{epochKey: string|null, startedAt: number|null, frozenMs: number|null}} prev
 * @param {{stage: string, epochKey: string, now: number}} obs
 * @returns {{epochKey: string, startedAt: number|null, frozenMs: number|null,
 *            running: boolean, display: string}}
 */
export function advanceTurnTimer(prev, { stage, epochKey, now }) {
  const key = epochKey || "";
  // A new turn identity is a new measurement. Retry finalizes the failed
  // backend session and creates a fresh one, so the id changing is exactly the
  // signal that the previous attempt's frozen value must not be reused.
  const base =
    prev && prev.epochKey === key
      ? prev
      : { epochKey: key, startedAt: null, frozenMs: null };

  if (stage === "idle") {
    return {
      epochKey: key,
      startedAt: null,
      frozenMs: null,
      running: false,
      display: TIMER_IDLE_DISPLAY,
    };
  }

  if (isActiveTurnStage(stage)) {
    const startedAt = base.startedAt == null ? now : base.startedAt;
    return {
      epochKey: key,
      startedAt,
      frozenMs: null,
      running: true,
      display: formatElapsed(now - startedAt),
    };
  }

  // Terminal. Freeze at the transition itself rather than waiting for the next
  // one-second tick, and never re-freeze: the D9 teardown publishes several
  // more snapshots after the fault, and each one arrives here with a later
  // `now`. Keeping the first value is what makes the reading the failure time.
  const frozenMs =
    base.frozenMs != null
      ? base.frozenMs
      : base.startedAt == null
        ? 0
        : Math.max(0, now - base.startedAt);
  return {
    epochKey: key,
    startedAt: base.startedAt,
    frozenMs,
    running: false,
    display: formatElapsed(frozenMs),
  };
}
