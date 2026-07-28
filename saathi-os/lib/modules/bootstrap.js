/**
 * M64 — shell bootstrap state machine.
 *
 * A pure reducer that models truthful shell states during module discovery. The
 * shell never shows stale modules as operational while the authoritative request
 * is unresolved. Keeping this pure makes every transition unit-testable without a
 * browser.
 */
export const BOOT = {
  INITIALIZING: "INITIALIZING",
  AUTH_REQUIRED: "AUTH_REQUIRED",
  LOADING_CONTEXT: "LOADING_CONTEXT",
  LOADING_MODULES: "LOADING_MODULES",
  READY: "READY",
  DEGRADED: "DEGRADED",
  OFFLINE: "OFFLINE",
  PERMISSION_RESTRICTED: "PERMISSION_RESTRICTED",
  SESSION_EXPIRED: "SESSION_EXPIRED",
  ERROR: "ERROR",
};

export const initialBootState = () => ({
  phase: BOOT.INITIALIZING,
  modules: [],
  cards: [],
  navigation: null,
  contractVersion: "",
  errorCategory: null,
  stale: false,
  retryCount: 0,
});

/**
 * Reduce a bootstrap event into the next state. Events:
 *  - {type:"NO_TOKEN"}                 → AUTH_REQUIRED
 *  - {type:"HAVE_TOKEN"}               → LOADING_CONTEXT
 *  - {type:"CONTEXT_READY"}            → LOADING_MODULES
 *  - {type:"MODULES_OK", payload}      → READY | DEGRADED
 *  - {type:"MODULES_ERR", category}    → SESSION_EXPIRED | PERMISSION_RESTRICTED | OFFLINE | ERROR
 *  - {type:"RETRY"}                    → LOADING_MODULES (bounded)
 *  - {type:"LOGOUT"}                   → AUTH_REQUIRED (clears module state)
 *  - {type:"CONTEXT_SWITCH"}          → LOADING_MODULES (invalidates module state)
 */
export function bootReducer(state, event) {
  switch (event.type) {
    case "NO_TOKEN":
      return { ...initialBootState(), phase: BOOT.AUTH_REQUIRED };

    case "HAVE_TOKEN":
      return { ...state, phase: BOOT.LOADING_CONTEXT, errorCategory: null };

    case "CONTEXT_READY":
      return { ...state, phase: BOOT.LOADING_MODULES };

    case "MODULES_OK": {
      const p = event.payload || {};
      const anyDegraded = (p.modules || []).some(
        (m) => m.state === "degraded" || m.state === "unavailable"
      );
      return {
        ...state,
        phase: anyDegraded ? BOOT.DEGRADED : BOOT.READY,
        modules: p.modules || [],
        cards: p.cards || [],
        navigation: p.navigation || null,
        contractVersion: p.contractVersion || "",
        errorCategory: null,
        stale: false,
        retryCount: 0,
      };
    }

    case "MODULES_ERR": {
      const cat = event.category;
      // discovery failed → NEVER keep showing modules as operational
      const cleared = { modules: [], cards: [], navigation: null };
      if (cat === "session_expired") return { ...state, ...cleared, phase: BOOT.SESSION_EXPIRED, errorCategory: cat };
      if (cat === "permission_restricted") return { ...state, ...cleared, phase: BOOT.PERMISSION_RESTRICTED, errorCategory: cat };
      if (cat === "network") return { ...state, ...cleared, phase: BOOT.OFFLINE, errorCategory: cat };
      return { ...state, ...cleared, phase: BOOT.ERROR, errorCategory: cat };
    }

    case "RETRY":
      // bounded: caller decides the cap; we just track count and re-enter loading
      return { ...state, phase: BOOT.LOADING_MODULES, retryCount: state.retryCount + 1 };

    case "LOGOUT":
      // logout clears module state entirely
      return { ...initialBootState(), phase: BOOT.AUTH_REQUIRED };

    case "CONTEXT_SWITCH":
      // tenant/workspace switch invalidates ALL prior module state (no cross-tenant flash)
      return {
        ...initialBootState(),
        phase: BOOT.LOADING_MODULES,
        retryCount: 0,
      };

    default:
      return state;
  }
}

/** Phases in which the shell may render actionable module surfaces. */
export function canRenderModules(phase) {
  return phase === BOOT.READY || phase === BOOT.DEGRADED;
}
