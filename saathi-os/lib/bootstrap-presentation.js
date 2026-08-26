/**
 * What the unlock screen is allowed to say about initialisation state.
 *
 * The bug this exists to prevent: `/unlock` fetched the bootstrap status and,
 * on *any* rejection, set `{state: "UNKNOWN"}`. The panel then chose its copy
 * with `!boot.bootstrap_enabled`, and `undefined` is falsy, so a backend the
 * page could not reach was reported as
 *
 *     "Setup is disabled. An operator must arm it on this machine."
 *
 * That is a claim about the operator's configuration, made by code that never
 * received an answer. It was reproduced by opening the app on
 * `http://localhost:3000` instead of `http://127.0.0.1:3000`: the CORS
 * allowlist named only the latter, the request was blocked, and the screen told
 * the operator to go change a setting that was already correct.
 *
 * Two rules follow, and both are enforced here rather than in JSX:
 *
 *   1. "unreachable" is its own state. Absence of an answer is never evidence
 *      about what the answer would have been.
 *   2. Only an explicit `bootstrap_enabled === false` renders "disabled".
 *      Missing, undefined or malformed data renders "unknown" and shows no
 *      form, because a setup form offered on the strength of data we do not
 *      have is a form that will fail confusingly at submit time.
 *
 * Every branch is a pure function of its inputs so it can be tested without a
 * DOM: the suite is `node --test`, and a presentation rule that can only be
 * exercised by rendering React is a rule that will not be tested.
 */

/** @typedef {"loading"|"unreachable"|"unknown"|"armed"|"disabled"|"expired"|"active"|"contaminated"} BootstrapKind */

/** Sentinel the page stores when the status request rejects. */
export const UNREACHABLE = { unreachable: true };

export const COPY = {
  loading: "Checking this installation…",
  unreachable:
    "Cannot reach the SaathiOS platform API. Check that the local server is " +
    "running and that this page is using the correct loopback address.",
  unknown:
    "This installation did not report a usable setup state. Setup is unavailable " +
    "until it does.",
  armed:
    "Enter the one-time setup token from this machine, and choose the owner password.",
  disabled:
    "Setup is disabled. An operator must arm it on this machine before an owner " +
    "can be created.",
  expired:
    "The one-time setup token has expired. Generate a new one on this machine, " +
    "then enter it here.",
  active: "This installation already has an owner. Sign in instead.",
  contaminated:
    "This installation has credentials but no completed setup. Setup is blocked " +
    "until an operator reviews it.",
};

/**
 * Decide what the unlock screen shows.
 *
 * Fails closed: `showForm` is true only for a status that positively says this
 * installation is armed and available. Anything else — no answer yet, no
 * answer at all, a shape we do not recognise — shows no form.
 *
 * @param {object|null|undefined} status parsed bootstrap status, `UNREACHABLE`,
 *   or null/undefined while the request is still in flight
 * @param {string} [lastErrorCode] bounded refusal code from the most recent
 *   bootstrap submission, if any
 * @returns {{kind: BootstrapKind, copy: string, showForm: boolean, showPanel: boolean}}
 */
export function bootstrapPresentation(status, lastErrorCode = "") {
  const kind = bootstrapKind(status, lastErrorCode);
  return {
    kind,
    copy: COPY[kind],
    // The token/password form belongs to exactly two states: armed, and armed
    // with a token that turned out to be stale. Never to a state we inferred.
    showForm: kind === "armed" || kind === "expired",
    // ACTIVE is the sign-in screen's business, not first-time setup's.
    showPanel: kind !== "active",
  };
}

/** @returns {BootstrapKind} */
function bootstrapKind(status, lastErrorCode) {
  if (status === null || status === undefined) return "loading";
  if (typeof status !== "object") return "unknown";

  // Checked before anything else: an unreachable backend has told us nothing,
  // so no field on this object may be read as though it had.
  if (status.unreachable === true) return "unreachable";

  const state = status.state;
  if (typeof state !== "string" || state.length === 0) return "unknown";
  if (state === "ACTIVE") return "active";
  if (state === "CONTAMINATED_UNINITIALIZED") return "contaminated";

  // Strict `=== false`. `!status.bootstrap_enabled` was the original defect:
  // it made "the field is missing" indistinguishable from "the operator turned
  // setup off", and the two call for opposite actions.
  if (status.bootstrap_enabled === false) return "disabled";

  if (
    state === "BOOTSTRAP_ARMED" &&
    status.bootstrap_available === true &&
    status.bootstrap_enabled === true
  ) {
    // A token that has aged out still means the installation is armed; only the
    // operator's artefact is stale. Distinguishing this is what stops an
    // operator re-arming an installation that was never disarmed.
    return lastErrorCode === "BOOTSTRAP_TOKEN_EXPIRED" ? "expired" : "armed";
  }

  return "unknown";
}
