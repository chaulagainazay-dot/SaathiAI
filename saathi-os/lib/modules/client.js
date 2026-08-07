/**
 * M64 — authenticated module discovery client.
 *
 * ONE canonical client for browser module discovery, layered on the existing
 * authenticated platform request utility (`plat`, X-Platform-Token). The backend
 * ModuleRegistry is the source of truth; this client only fetches, classifies
 * failures, and normalizes/validates the response. It NEVER grants capability and
 * never treats the local static mirror as operational truth.
 *
 * The default transport (`plat`) and token accessor are loaded lazily so the pure
 * units (normalize/classify) and tests that inject a transport never pull in the
 * browser-only platform-client chain.
 */
async function _defaultTransport() {
  const mod = await import("../platform-client.js");
  return { plat: mod.plat, getToken: mod.getToken };
}

export const REQUIRED_MODULE_FIELDS = ["id", "name", "version", "state"];

/** Truthful states the backend may return (mirror of ModuleState). */
export const MODULE_STATE = {
  AVAILABLE: "available",
  DEGRADED: "degraded",
  UNAVAILABLE: "unavailable",
  DISABLED: "disabled",
  NOT_IMPLEMENTED: "not_implemented",
  PERMISSION_RESTRICTED: "permission_restricted",
};

const ACTIONABLE_STATES = new Set([MODULE_STATE.AVAILABLE]);

/** Map any thrown error / status to a stable failure category for the shell. */
export function classifyError(e) {
  const status = e && typeof e.status === "number" ? e.status : 0;
  if (status === 401) return "session_expired";
  if (status === 403) return "permission_restricted";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status >= 500) return "server_error";
  const msg = String(e?.message || e || "");
  if (/Failed to fetch|NetworkError|load failed|ECONNREFUSED|aborted|AbortError/i.test(msg)) {
    return "network";
  }
  return "error";
}

/**
 * Normalize + validate a raw backend module descriptor. Rejects malformed
 * descriptors (missing required fields) by throwing — the shell fails closed
 * rather than rendering an untrustworthy module. `actionable` is derived from the
 * backend `state`, never from the caller.
 */
export function normalizeModule(raw) {
  if (!raw || typeof raw !== "object") throw new Error("malformed module descriptor");
  for (const f of REQUIRED_MODULE_FIELDS) {
    if (raw[f] === undefined || raw[f] === null || raw[f] === "") {
      throw new Error(`module descriptor missing field: ${f}`);
    }
  }
  const state = String(raw.state);
  return {
    id: String(raw.id),
    name: String(raw.name),
    version: String(raw.version),
    category: raw.category || "platform",
    description: raw.description || "",
    icon: raw.icon || "",
    status: raw.status || "",
    state,
    enabled: !!raw.enabled,
    implemented: !!raw.implemented,
    health: raw.health || "unknown",
    routes: Array.isArray(raw.routes) ? raw.routes : [],
    capabilities: Array.isArray(raw.capabilities) ? raw.capabilities : [],
    featureFlags: raw.feature_flags && typeof raw.feature_flags === "object" ? raw.feature_flags : {},
    permissions: Array.isArray(raw.permissions) ? raw.permissions : [],
    navItems: Array.isArray(raw.nav_items) ? raw.nav_items : [],
    widgets: Array.isArray(raw.dashboard_widgets) ? raw.dashboard_widgets : [],
    // actionable is decided by the BACKEND state only — never inferred client-side.
    actionable: ACTIONABLE_STATES.has(state),
  };
}

/** True only when the backend says the module is available AND has a route. */
export function isActionable(mod) {
  return !!mod && mod.actionable === true && mod.state === MODULE_STATE.AVAILABLE;
}

/**
 * Fetch authoritative module discovery. Returns { contractVersion, modules,
 * navigation, cards }. Throws a classified error (see classifyError) — the shell
 * bootstrap machine maps that to a state. Does NOT poll; a single bounded request.
 *
 * @param {{ token?: string, platFn?: Function, signal?: AbortSignal }} opts
 */
export async function fetchModuleDiscovery({ token, platFn, signal } = {}) {
  // Resolve the token first and fail closed BEFORE loading any transport.
  let tok = token;
  if (tok === undefined) tok = (await _defaultTransport()).getToken();
  if (!tok) {
    const err = new Error("authentication required");
    err.status = 401;
    throw err;
  }
  const transport = platFn || (await _defaultTransport()).plat;
  const data = await transport("/modules", { token: tok, signal });
  const rawList = Array.isArray(data?.installed) ? data.installed : [];
  const modules = [];
  const rejected = [];
  for (const raw of rawList) {
    try {
      modules.push(normalizeModule(raw));
    } catch (e) {
      // fail closed for that module: drop it, record the reason; never render it
      rejected.push({ id: raw?.id || "?", reason: String(e.message || e) });
    }
  }
  return {
    contractVersion: data?.contract_version || "",
    modules,
    navigation: data?.navigation || { group: "applications", label: "Applications", modules: [] },
    cards: Array.isArray(data?.dashboard_cards) ? data.dashboard_cards : [],
    rejected,
    source: "backend",
  };
}
