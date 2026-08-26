/**
 * One bounded recovery from an idle-expired derived platform session.
 *
 * The derived platform session carries a one-hour idle TTL. That is a security
 * control and stays exactly as it is. What was missing is the client half: when
 * the owner returned to a tab hours later and pressed the microphone, the dock
 * asked the backend to open a voice-runtime session with a token whose idle
 * window had closed, got
 *
 *     401 {"detail": {"code": "SESSION_INVALID", "message":
 *          "session expired, revoked, or unknown"}}
 *
 * and rendered that message as a dead end — while the *canonical* owner session
 * behind it was still perfectly valid for another fourteen hours. The authority
 * to mint a fresh derived session was present the whole time; nothing asked for
 * it.
 *
 * So this recovers once, and only from the one condition it can prove:
 *
 *   - the failure must be HTTP 401 **and** carry the exact bounded code
 *     `SESSION_INVALID`. A generic 401, a 403, a network failure or a malformed
 *     response is not this condition and is never treated as it — an ambiguous
 *     failure might have committed on the server, and retrying it would be a
 *     second write, not a recovery;
 *   - the exchange is the existing D15 canonical-session provisioning endpoint.
 *     No new password, token type, operator proof or auth system;
 *   - exactly one retry. If the retry fails, for any reason including a second
 *     `SESSION_INVALID`, that is terminal and the truth is what the caller sees;
 *   - concurrent callers share a single in-flight exchange, so a dock and a
 *     provider racing on the same expiry cannot mint two sessions;
 *   - the stale token is replaced before the retry, and cleared on terminal
 *     failure. An expired token is never reused or resurrected.
 *
 * The scope is deliberately the voice-runtime session-opening boundary, not a
 * global fetch interceptor: this is the one call where "the credential aged out
 * between readiness and use" is both expected and safely repeatable, because
 * the backend authenticates before it mutates anything.
 */

/** The only failure this module will act on. */
export const RECOVERABLE_CODE = "SESSION_INVALID";

/** Shared in-flight exchange, so simultaneous callers cannot storm the endpoint. */
let inflightExchange = null;

/** Test seam: forget any shared in-flight exchange between cases. */
export function resetPlatformSessionRecovery() {
  inflightExchange = null;
}

/**
 * True only for the backend's explicit pre-handler session rejection.
 *
 * Both halves are required. Status alone is not enough: a 401 without the
 * bounded code is some other refusal, and re-minting a session in response to
 * it would paper over an unrelated authorization failure.
 */
export function isRecoverableSessionFailure(error) {
  if (!error || typeof error !== "object") return false;
  return error.status === 401 && error.code === RECOVERABLE_CODE;
}

/**
 * Exchange the canonical owner session for a fresh derived platform session.
 *
 * Returns the new raw token. Throws if the canonical session is not valid, the
 * endpoint refuses, or the response does not carry a usable token — every one
 * of which is a reason to stop rather than to open a microphone.
 */
export async function exchangeForFreshPlatformSession({ exchange, storeToken } = {}) {
  if (typeof exchange !== "function") {
    throw new Error("platform session exchange is unavailable");
  }
  const result = await exchange();
  const token = result && typeof result.token === "string" ? result.token.trim() : "";
  if (!result || result.ok !== true || !token) {
    // Covers a refused exchange (the canonical session is gone too) and a
    // response whose shape we do not recognise. Both fail closed.
    const code = (result && (result.code || result.error)) || "EXCHANGE_FAILED";
    const err = new Error(String(code));
    err.code = String(code);
    err.status = (result && result.status) || 0;
    throw err;
  }
  if (typeof storeToken === "function") storeToken(token);
  return token;
}

/**
 * Run `attempt(token)`, recovering once from an expired derived session.
 *
 * `attempt` must be the runtime-session *creation* call and nothing else: it is
 * safe to repeat only because the backend resolves the platform context before
 * it writes, so a rejected attempt cannot have created a session.
 */
export async function withPlatformSessionRecovery(token, attempt, {
  exchange,
  storeToken,
  clearToken,
} = {}) {
  try {
    return await attempt(token);
  } catch (error) {
    if (!isRecoverableSessionFailure(error)) throw error;

    let fresh;
    try {
      // Single flight: whoever arrives first performs the exchange, everybody
      // else awaits the same promise and uses the same new session.
      if (!inflightExchange) {
        inflightExchange = exchangeForFreshPlatformSession({ exchange, storeToken })
          .finally(() => { inflightExchange = null; });
      }
      fresh = await inflightExchange;
    } catch (exchangeError) {
      // The canonical session could not mint a new one. The old token is known
      // bad, so it does not stay behind to fail again later.
      if (typeof clearToken === "function") clearToken();
      throw exchangeError;
    }

    try {
      // Exactly one retry, with the replaced token. No loop, no second chance.
      return await attempt(fresh);
    } catch (retryError) {
      if (isRecoverableSessionFailure(retryError) && typeof clearToken === "function") {
        clearToken();
      }
      throw retryError;
    }
  }
}
