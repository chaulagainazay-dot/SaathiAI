// Canonical SaathiOS frontend auth-state machine (single source of truth).
//
// States: UNKNOWN → CHECKING → AUTHENTICATED | AUTH_REQUIRED | AUTH_ERROR
//         AUTH_REQUIRED → AUTHENTICATING → AUTHENTICATED | AUTH_ERROR
//
// A stale/absent token must never leave Chat/Voice looking functional while
// requests 401 in a loop: bootstrap validates the token against the backend and
// afetch's central 401 handler (lib/api.js) flips us to AUTH_REQUIRED once.
import { API_BASE, afetch, login as apiLogin, logout as apiLogout,
         hasSessionToken, clearSessionToken } from "./api";

export const AuthState = Object.freeze({
  UNKNOWN: "UNKNOWN",
  CHECKING: "CHECKING",
  AUTHENTICATED: "AUTHENTICATED",
  AUTH_REQUIRED: "AUTH_REQUIRED",
  AUTHENTICATING: "AUTHENTICATING",
  AUTH_ERROR: "AUTH_ERROR",
});

// Request replay policy. A genuine 401 never auto-replays a mutation; only the
// caller may re-issue. Sensitive actions are always REQUIRES_USER_REISSUE.
export const ReplayPolicy = Object.freeze({
  SAFE_TO_RETRY: "SAFE_TO_RETRY",             // idempotent reads — UI may re-fetch after login
  REQUIRES_USER_REISSUE: "REQUIRES_USER_REISSUE", // user must deliberately redo
});

// Path fragments that are always user-reissue, regardless of HTTP method.
const SENSITIVE = [
  "/approv", "/execute", "/trading", "/trade", "/authority", "/voice/enroll",
  "/deploy", "/publish", "/revoke", "/rotate", "/change-password", "/reset",
  "/connectors/execute", "/missions/", "/automation/plan", "/kill",
];

export function classifyRequest(method = "GET", url = "") {
  const m = String(method).toUpperCase();
  const u = String(url).toLowerCase();
  if (SENSITIVE.some((s) => u.includes(s))) return ReplayPolicy.REQUIRES_USER_REISSUE;
  if (m === "GET" || m === "HEAD") return ReplayPolicy.SAFE_TO_RETRY;
  return ReplayPolicy.REQUIRES_USER_REISSUE; // every other mutation
}

// ── tiny pub/sub store (no dependency) ───────────────────────────────────────
let _state = AuthState.UNKNOWN;
let _session = null;      // non-secret metadata { id, expires_at, ... } | null
let _error = "";
const _subs = new Set();

function _emit() {
  const snap = { state: _state, session: _session, error: _error };
  _subs.forEach((fn) => { try { fn(snap); } catch {} });
}

export function getAuthSnapshot() { return { state: _state, session: _session, error: _error }; }
export function subscribeAuth(fn) { _subs.add(fn); fn(getAuthSnapshot()); return () => _subs.delete(fn); }

function _set(state, { session, error } = {}) {
  _state = state;
  if (session !== undefined) _session = session;
  if (error !== undefined) _error = error;
  _emit();
}

// ── backend validation (whitelisted endpoint — never 401s) ───────────────────
export async function validateSession() {
  try {
    const r = await afetch(`${API_BASE}/api/v1/auth/session`, { cache: "no-store" });
    if (!r.ok) return { authenticated: false, session: null };
    return await r.json();
  } catch {
    return { authenticated: false, session: null, offline: true };
  }
}

// Startup: decide the canonical state exactly once per load.
let _bootstrapped = false;
export async function bootstrapAuth({ force = false } = {}) {
  if (_bootstrapped && !force) return getAuthSnapshot();
  _bootstrapped = true;
  if (!hasSessionToken()) { _set(AuthState.AUTH_REQUIRED, { session: null }); return getAuthSnapshot(); }
  _set(AuthState.CHECKING);
  const res = await validateSession();
  if (res.authenticated) {
    _set(AuthState.AUTHENTICATED, { session: res.session, error: "" });
  } else {
    clearSessionToken();               // remove the stale token so it can't 401 again
    _set(AuthState.AUTH_REQUIRED, { session: null });
  }
  return getAuthSnapshot();
}

export async function signIn(password, rememberMe = true) {
  _set(AuthState.AUTHENTICATING, { error: "" });
  try {
    const j = await apiLogin(password, rememberMe);   // persists token on success
    if (j && j.ok) {
      const res = await validateSession();
      _set(AuthState.AUTHENTICATED, { session: res.session || null, error: "" });
      return { ok: true };
    }
    _set(AuthState.AUTH_REQUIRED, { error: (j && j.error) || "Wrong password" });
    return { ok: false, error: (j && j.error) || "Wrong password" };
  } catch (e) {
    _set(AuthState.AUTH_ERROR, { error: "Network error" });
    return { ok: false, error: "Network error" };
  }
}

export async function signOut() {
  try { await apiLogout(); } catch {}
  clearSessionToken();
  _set(AuthState.AUTH_REQUIRED, { session: null, error: "" });
}

// Canonical auth-loss handler — the state machine OWNS deduplication.
// Fired (possibly many times, one per concurrent 401) by afetch's raw
// `saathi:auth-401` signal. Only the FIRST call that actually performs the
// transition into AUTH_REQUIRED does work and emits exactly ONE canonical
// `saathi:auth-required` event. Every subsequent concurrent/stale 401 while
// already AUTH_REQUIRED (or mid-AUTHENTICATING) is a no-op: no second
// transition, no second event, no retry, no replay, no extra overlay.
// Dedup derives purely from canonical state ownership — no timers/debounce.
export function onAuthRequired() {
  // Already in (or heading into) a resolved auth-loss state → do nothing.
  if (_state === AuthState.AUTH_REQUIRED || _state === AuthState.AUTHENTICATING) return;
  clearSessionToken();
  _set(AuthState.AUTH_REQUIRED, { session: null });
  // Winning transition only: emit the single canonical notification.
  try {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("saathi:auth-required", { detail: { reason: "session-lost" } }));
    }
  } catch {}
}

// Wire the RAW per-request 401 signal from afetch (module side-effect, guarded).
// authState is the sole emitter of the canonical `saathi:auth-required` event.
if (typeof window !== "undefined" && !window.__saathiAuthWired) {
  window.__saathiAuthWired = true;
  window.addEventListener("saathi:auth-401", onAuthRequired);
}
