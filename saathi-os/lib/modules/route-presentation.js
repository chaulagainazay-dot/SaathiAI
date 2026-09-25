/**
 * SaathiOS UI recovery — truthful presentation for withheld module routes.
 *
 * `ModuleRouteBoundary` withholds a module route whenever shell bootstrap has not
 * reached READY/DEGRADED, or when the guard denies the path. Previously every
 * withheld route rendered the single loading sentence "Checking application
 * availability…", so terminal bootstrap phases (AUTH_REQUIRED, SESSION_EXPIRED,
 * OFFLINE, ERROR, PERMISSION_RESTRICTED) were presented as work still in
 * progress: no explanation, no retry, no sign-in guidance. An unauthenticated
 * operator on a local machine with no reachable API therefore saw a shell whose
 * whole content area looked permanently hung.
 *
 * This module is a pure mapping from (phase, guard outcome) to what the boundary
 * should say and offer. It is presentation only. It never grants access: the
 * caller decides whether children render, and this function is consulted only on
 * the withheld path.
 */
import { BOOT } from "./bootstrap.js";
import { GUARD } from "./guard.js";

/** Presentation kinds. `loading` is the only non-terminal kind. */
export const GATE_KIND = {
  LOADING: "loading",
  AUTH: "auth",
  OFFLINE: "offline",
  ERROR: "error",
  RESTRICTED: "restricted",
  UNAVAILABLE: "unavailable",
};

/** Actions the boundary may offer. `retry` re-runs discovery; others are links. */
export const GATE_ACTION = {
  SIGN_IN: "sign-in",
  RETRY: "retry",
  DIAGNOSTICS: "diagnostics",
  APPLICATIONS: "applications",
};

const SIGN_IN = { id: GATE_ACTION.SIGN_IN, label: "Sign in", href: "/unlock" };
const RETRY = { id: GATE_ACTION.RETRY, label: "Retry" };
const DIAGNOSTICS = {
  id: GATE_ACTION.DIAGNOSTICS,
  label: "Diagnostics",
  href: "/trading/operations/diagnostics",
};
const APPLICATIONS = {
  id: GATE_ACTION.APPLICATIONS,
  label: "Back to Applications",
  href: "/apps",
};

const LOADING_PHASES = new Set([
  BOOT.INITIALIZING,
  BOOT.LOADING_CONTEXT,
  BOOT.LOADING_MODULES,
]);

/**
 * Presentation for a bootstrap phase that never reached READY/DEGRADED.
 * Returns null when the phase is not terminal-or-loading (caller falls through
 * to the guard outcome).
 */
function fromPhase(phase) {
  if (LOADING_PHASES.has(phase)) {
    return {
      kind: GATE_KIND.LOADING,
      title: "Application",
      message: "Checking application availability…",
      detail: "",
      actions: [],
    };
  }
  switch (phase) {
    case BOOT.AUTH_REQUIRED:
      return {
        kind: GATE_KIND.AUTH,
        title: "Sign in required",
        message: "Sign in to open this application.",
        detail:
          "SaathiOS private alpha is invite only. There is no public sign-up.",
        actions: [SIGN_IN],
      };
    case BOOT.SESSION_EXPIRED:
      return {
        kind: GATE_KIND.AUTH,
        title: "Session expired",
        message: "Your session expired. Sign in again to open this application.",
        detail:
          "SaathiOS private alpha is invite only. There is no public sign-up.",
        actions: [SIGN_IN],
      };
    case BOOT.OFFLINE:
      return {
        kind: GATE_KIND.OFFLINE,
        title: "Local services offline",
        message:
          "SaathiOS cannot reach the local platform API, so this application cannot be shown.",
        detail:
          "The interface is running; the local backend is not reachable. Start the local platform service and retry.",
        actions: [RETRY, DIAGNOSTICS],
      };
    case BOOT.PERMISSION_RESTRICTED:
      return {
        kind: GATE_KIND.RESTRICTED,
        title: "Not permitted",
        message: "You do not have permission to open this application.",
        detail: "",
        actions: [APPLICATIONS],
      };
    case BOOT.ERROR:
      return {
        kind: GATE_KIND.ERROR,
        title: "Application discovery failed",
        message:
          "The local platform API did not return a usable application list.",
        detail:
          "This is a local platform fault, not a permission decision. Retry, then check diagnostics.",
        actions: [RETRY, DIAGNOSTICS],
      };
    default:
      return null;
  }
}

const OUTCOME_PRESENTATION = {
  [GUARD.AUTH_REQUIRED]: {
    kind: GATE_KIND.AUTH,
    title: "Sign in required",
    message: "Sign in to open this application.",
    detail:
      "SaathiOS private alpha is invite only. There is no public sign-up.",
    actions: [SIGN_IN],
  },
  [GUARD.NOT_IMPLEMENTED]: {
    kind: GATE_KIND.UNAVAILABLE,
    title: "Not implemented",
    message: "This application is registered but not implemented.",
    detail: "",
    actions: [APPLICATIONS],
  },
  [GUARD.DISABLED]: {
    kind: GATE_KIND.UNAVAILABLE,
    title: "Disabled",
    message: "This application is disabled.",
    detail: "",
    actions: [APPLICATIONS],
  },
  [GUARD.PERMISSION_RESTRICTED]: {
    kind: GATE_KIND.RESTRICTED,
    title: "Not permitted",
    message: "You do not have permission to open this application.",
    detail: "",
    actions: [APPLICATIONS],
  },
  [GUARD.DEGRADED]: {
    kind: GATE_KIND.UNAVAILABLE,
    title: "Degraded",
    message: "This application is degraded and is not currently actionable.",
    detail: "",
    actions: [RETRY, DIAGNOSTICS],
  },
  [GUARD.UNAVAILABLE]: {
    kind: GATE_KIND.UNAVAILABLE,
    title: "Unavailable",
    message: "This application is unavailable.",
    detail: "",
    actions: [RETRY, DIAGNOSTICS],
  },
  [GUARD.NOT_FOUND]: {
    kind: GATE_KIND.UNAVAILABLE,
    title: "Unavailable",
    message: "This application is unavailable.",
    detail: "",
    actions: [APPLICATIONS],
  },
};

/**
 * @param {{phase?:string, outcome?:{outcome:string}|null, moduleName?:string}} input
 * @returns {{kind:string,title:string,message:string,detail:string,actions:Array}}
 *
 * A resolved guard outcome is authoritative over the phase: once discovery is
 * READY/DEGRADED the boundary is denying for a module-specific reason. Otherwise
 * the phase explains why nothing could be decided yet.
 */
export function presentRouteGate({ phase, outcome, moduleName } = {}) {
  const byOutcome = outcome?.outcome
    ? OUTCOME_PRESENTATION[outcome.outcome]
    : null;
  const chosen = byOutcome || fromPhase(phase) || {
    kind: GATE_KIND.LOADING,
    title: "Application",
    message: "Checking application availability…",
    detail: "",
    actions: [],
  };
  return {
    ...chosen,
    title: moduleName && chosen.kind === GATE_KIND.UNAVAILABLE
      ? moduleName
      : chosen.title,
  };
}

/** Loading is announced politely; everything else is a resolved, terminal state. */
export function gateAriaRole(kind) {
  return kind === GATE_KIND.LOADING ? "status" : "alert";
}
