/**
 * Terminal cleanup for backend voice sessions.
 *
 * Ending voice in the browser used to be entirely client-side: the recognizer
 * stopped, the claim was released, and the backend session stayed in
 * LISTENING forever. `POST /stop` only moves `input_state`; the conversation
 * state machine leaves LISTENING via `POST /finish`, which nothing called. So
 * every route change, logout, retry and unmount stranded one active session,
 * and after eight of them the per-user budget rejected all new voice with
 * RESOURCE_BUDGET_EXHAUSTED — voice simply stopped working, with a 409 the UI
 * surfaced as a generic failure.
 *
 * This module owns that terminal request. Three properties matter:
 *
 *   - it is callable from synchronous teardown. Teardown paths cannot await a
 *     network round trip (that is what let the recognizer restart win races),
 *     so `finalize()` returns immediately and the request is observed here;
 *   - it is exactly-once per session id. Teardown paths overlap — an unmount
 *     during a route change runs both — and the backend endpoint is itself
 *     idempotent, but sending three of them for one session is still noise;
 *   - a failed request is *pending*, not done. A dropped network call must not
 *     let the app claim the session was cleaned up. It stays in `getPending()`
 *     until a retry succeeds, so the truthful state is visible and the next
 *     opportunity can flush it.
 */

import { recordVoiceTelemetry } from "./telemetry.js";

/**
 * @param {object} opts
 * @param {(token: string, sessionId: string, opts: {keepalive: boolean}) => Promise<unknown>} opts.finish
 *   the backend terminal call. `keepalive` is set when the page is going away
 *   and the request has to outlive it.
 * @param {(pending: Array<object>) => void} [opts.onPendingChange]
 */
export function createSessionFinalizer({ finish, onPendingChange } = {}) {
  if (typeof finish !== "function") {
    throw new Error("createSessionFinalizer requires a finish() implementation");
  }

  /** Session ids already terminated, so a repeat teardown is a no-op. */
  const done = new Set();
  /** Session ids with a request in flight. */
  const inFlight = new Set();
  /** @type {Map<string, {sessionId: string, reason: string, attempts: number, lastError: string}>} */
  const pending = new Map();
  /** Settled promise chain, so tests can await without teardown becoming async. */
  let tail = Promise.resolve();

  function publishPending() {
    if (!onPendingChange) return;
    try {
      onPendingChange([...pending.values()]);
    } catch {
      /* a consumer failure must not break cleanup */
    }
  }

  function send(token, sessionId, reason, attempts, keepalive) {
    inFlight.add(sessionId);
    const attempt = Promise.resolve()
      .then(() => finish(token, sessionId, { keepalive: Boolean(keepalive) }))
      .then(
        () => {
          inFlight.delete(sessionId);
          done.add(sessionId);
          if (pending.delete(sessionId)) publishPending();
          recordVoiceTelemetry("session_finalized", { sessionId, reason });
          return { status: "finalized", sessionId };
        },
        (err) => {
          inFlight.delete(sessionId);
          const lastError = String(err?.message || err).slice(0, 120);
          // Not done. The backend session may still be active, and saying
          // otherwise would be a lie the next talk attempt pays for.
          pending.set(sessionId, { sessionId, reason, attempts, lastError });
          publishPending();
          recordVoiceTelemetry("session_finalize_failed", {
            sessionId,
            reason,
            errorCode: lastError.slice(0, 80),
          });
          return { status: "pending", sessionId, errorCode: lastError };
        }
      );
    tail = tail.then(() => attempt);
    return attempt;
  }

  return {
    /**
     * Terminate a backend session. Synchronous by contract; never throws.
     * @returns {"skipped"|"already_finalized"|"in_flight"|"sent"}
     */
    finalize({ token, sessionId, reason = "SESSION_CLOSE", keepalive = false } = {}) {
      const id = String(sessionId || "");
      if (!id || !token) return "skipped";
      if (done.has(id)) return "already_finalized";
      if (inFlight.has(id)) return "in_flight";
      const previous = pending.get(id);
      send(token, id, reason, (previous?.attempts || 0) + 1, keepalive);
      return "sent";
    },

    /** Flush sessions whose terminal request has not yet succeeded. */
    retryPending({ token } = {}) {
      if (!token) return 0;
      let retried = 0;
      for (const entry of [...pending.values()]) {
        if (inFlight.has(entry.sessionId)) continue;
        send(token, entry.sessionId, entry.reason, entry.attempts + 1, false);
        retried += 1;
      }
      return retried;
    },

    /** Sessions this client believes may still be active on the backend. */
    getPending() {
      return [...pending.values()];
    },

    isFinalized(sessionId) {
      return done.has(String(sessionId || ""));
    },

    /** Resolve once every issued request has settled. Never rejects. */
    whenSettled() {
      return tail;
    },
  };
}
