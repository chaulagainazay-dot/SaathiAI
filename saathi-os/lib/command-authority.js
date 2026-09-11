/**
 * UI-NEXT-1 — Truthful authority / operating-status strip composition.
 * Pure functions only. Never fabricates healthy/green without evidence.
 * Does not grant authority; display only.
 */

/** @typedef {"HEALTHY"|"DEGRADED"|"BLOCKED"|"DISABLED"|"UNKNOWN"|"STALE"|"ACTIVE"|"PAPER_ONLY"|"GOVERNED"|"UNAVAILABLE"|"OFF"|"READY"|"LISTENING"|"SPEAKING"|"THINKING"|"INTERRUPTED"|"ERROR"} TruthState */

/**
 * Map free-form status strings into the small truthful vocabulary.
 * @param {unknown} raw
 * @returns {TruthState}
 */
export function normalizeTruthState(raw) {
  if (raw == null || raw === "") return "UNKNOWN";
  const s = String(raw).toLowerCase().trim();
  if (["healthy", "ok", "up", "ready", "active", "online", "pass", "green"].includes(s)) return "HEALTHY";
  if (["degraded", "warn", "warning", "yellow", "partial"].includes(s)) return "DEGRADED";
  if (["blocked", "block", "failed", "error", "down", "critical", "red", "fail"].includes(s)) return "BLOCKED";
  if (["disabled", "off", "inactive", "none", "false", "0"].includes(s)) return "DISABLED";
  if (["stale", "expired", "outdated"].includes(s)) return "STALE";
  if (["unavailable", "n/a", "not_available", "missing"].includes(s)) return "UNAVAILABLE";
  if (["paper", "paper_only", "paper-only", "simulation"].includes(s)) return "PAPER_ONLY";
  if (["governed", "gated", "approval"].includes(s)) return "GOVERNED";
  return "UNKNOWN";
}

/**
 * Compose authority strip chips from existing sources.
 * Missing sources → UNKNOWN / DISABLED as appropriate — never invent green.
 *
 * @param {object} input
 * @param {object|null} [input.overview] control overview payload
 * @param {object|null} [input.infra] infrastructure health
 * @param {object|null} [input.tradingSummary] from useTradingOverview().summary
 * @param {boolean} [input.tradingReady]
 * @param {boolean} [input.tradingAuth] operator has trading session token
 * @param {object|null} [input.voiceRuntime] optional VoiceRuntimeProvider snapshot
 * @param {boolean} [input.voicePrefsEnabled]
 * @param {string|null} [input.apiBase]
 * @param {Date|string|null} [input.generatedAt]
 * @param {number|null} [input.maxAgeMs] if generatedAt older → STALE
 */
export function composeAuthorityStrip(input = {}) {
  const {
    overview = null,
    infra = null,
    tradingSummary = null,
    tradingReady = false,
    tradingAuth = false,
    voiceRuntime = null,
    voicePrefsEnabled = null,
    apiBase = null,
    generatedAt = null,
    maxAgeMs = 120_000,
  } = input;

  const env = inferEnvironmentChip(apiBase, overview);
  const execution = composeExecutionChip(overview);
  const trading = composeTradingChip(tradingSummary, tradingReady, tradingAuth);
  const tg = composeTradingGuardianChip(tradingSummary, tradingReady, tradingAuth);
  const liveOrders = {
    id: "live_orders",
    label: "LIVE ORDERS",
    state: "DISABLED",
    detail: "Live order submission remains unauthorized",
    evidence: "policy:live_trading_unauthorized",
  };
  const providers = composeProvidersChip(overview, infra);
  const model = composeModelChip(overview, infra);
  const voice = composeVoiceChip(voiceRuntime, voicePrefsEnabled);
  const system = composeSystemChip(infra, overview);

  const chips = [env, execution, trading, tg, liveOrders, providers, model, voice, system];

  let freshness = "UNKNOWN";
  if (generatedAt) {
    const t = typeof generatedAt === "number" ? generatedAt : Date.parse(generatedAt);
    if (Number.isFinite(t)) {
      freshness = Date.now() - t > maxAgeMs ? "STALE" : "HEALTHY";
    }
  }

  const degraded = chips.some((c) => ["DEGRADED", "BLOCKED", "STALE", "ERROR"].includes(c.state));
  const unknownHeavy = chips.filter((c) => c.state === "UNKNOWN" || c.state === "UNAVAILABLE").length;

  return {
    chips,
    freshness,
    degraded,
    unknownHeavy,
    generatedAt: generatedAt || null,
    note: "Display-only composition. Chips never grant execution authority.",
  };
}

function inferEnvironmentChip(apiBase, overview) {
  const fromOv = overview?.environment || overview?.env || overview?.deployment?.environment;
  if (fromOv) {
    return {
      id: "environment",
      label: "ENVIRONMENT",
      state: String(fromOv).toUpperCase().includes("PROD") ? "DEGRADED" : "ACTIVE",
      detail: String(fromOv),
      evidence: "control.overview.environment",
    };
  }
  const base = String(apiBase || "");
  if (!base || base.includes("localhost") || base.includes("127.0.0.1")) {
    return {
      id: "environment",
      label: "ENVIRONMENT",
      state: "ACTIVE",
      detail: "PRIVATE ALPHA · loopback",
      evidence: "api_base_loopback",
    };
  }
  return {
    id: "environment",
    label: "ENVIRONMENT",
    state: "UNKNOWN",
    detail: "Could not classify environment",
    evidence: null,
  };
}

function composeExecutionChip(overview) {
  // Execution is always governed in SaathiOS product truth
  const path = overview?.execution_path || overview?.execution?.path || overview?.gates?.execution;
  return {
    id: "execution",
    label: "EXECUTION",
    state: "GOVERNED",
    detail: path ? String(path) : "ExecutionGateway · approval-gated",
    evidence: path ? "control.overview.execution" : "policy:execution_gateway_sole_authority",
  };
}

function composeTradingChip(summary, ready, auth) {
  if (!auth) {
    return {
      id: "trading",
      label: "TRADING",
      state: "UNKNOWN",
      detail: "Session required for paper state",
      evidence: null,
    };
  }
  if (!ready) {
    return {
      id: "trading",
      label: "TRADING",
      state: "UNKNOWN",
      detail: "Paper overview not ready",
      evidence: null,
    };
  }
  if (!summary) {
    return {
      id: "trading",
      label: "TRADING",
      state: "UNAVAILABLE",
      detail: "Paper overview unavailable",
      evidence: "trading.overview",
    };
  }
  return {
    id: "trading",
    label: "TRADING",
    state: "PAPER_ONLY",
    detail: `${summary.accounts || 0} paper account(s) · live disabled`,
    evidence: "paper.accounts",
  };
}

function composeTradingGuardianChip(summary, ready, auth) {
  if (!auth || !ready) {
    return {
      id: "tg",
      label: "TG",
      state: "UNKNOWN",
      detail: "Trading Guardian state not loaded",
      evidence: null,
    };
  }
  if (!summary) {
    return {
      id: "tg",
      label: "TG",
      state: "UNAVAILABLE",
      detail: "No safety state payload",
      evidence: "paper.safety",
    };
  }
  if ((summary.blockingBreakers || 0) > 0) {
    return {
      id: "tg",
      label: "TG",
      state: "BLOCKED",
      detail: `${summary.blockingBreakers} blocking breaker(s)`,
      evidence: "paper.safety.states",
    };
  }
  if ((summary.unackAlerts || 0) > 0 || (summary.critDrift || 0) > 0) {
    return {
      id: "tg",
      label: "TG",
      state: "DEGRADED",
      detail: `${summary.unackAlerts || 0} unacked alert(s) · ${summary.critDrift || 0} critical recon`,
      evidence: "paper.safety.alerts",
    };
  }
  return {
    id: "tg",
    label: "TG",
    state: "ACTIVE",
    detail: "Paper safety surface loaded · live orders disabled",
    evidence: "paper.safety",
  };
}

function composeProvidersChip(overview, infra) {
  const p =
    overview?.providers?.status ||
    overview?.provider_status ||
    infra?.providers?.status ||
    overview?.connectors?.status;
  if (p == null) {
    return {
      id: "providers",
      label: "PROVIDERS",
      state: "DISABLED",
      detail: "External providers mock/disabled unless certified",
      evidence: "policy:provider_connectivity_disabled",
    };
  }
  const st = normalizeTruthState(p);
  return {
    id: "providers",
    label: "PROVIDERS",
    state: st === "HEALTHY" ? "DISABLED" : st, // never promote to healthy without explicit live cert
    detail: String(p),
    evidence: "control.overview.providers",
  };
}

function composeModelChip(overview, infra) {
  const m =
    overview?.models?.status ||
    overview?.model_status ||
    overview?.inference?.status ||
    infra?.models?.status ||
    infra?.inference?.status;
  if (m == null) {
    return {
      id: "model",
      label: "MODEL",
      state: "UNKNOWN",
      detail: "Qualification ≠ availability · state not in overview",
      evidence: null,
    };
  }
  return {
    id: "model",
    label: "MODEL",
    state: normalizeTruthState(m),
    detail: String(m),
    evidence: "control.overview.models",
  };
}

/**
 * Map voice runtime snapshot to reserved product states.
 * Only use real fields; never invent LISTENING without evidence.
 */
export function mapVoiceSessionViewState(voiceRuntime, prefsEnabled) {
  if (prefsEnabled === false) return "OFF";
  if (!voiceRuntime || typeof voiceRuntime !== "object") {
    return prefsEnabled == null ? "UNKNOWN" : "READY";
  }
  if (voiceRuntime.error || voiceRuntime.state === "FAILED" || voiceRuntime.state === "ERROR") return "ERROR";
  if (voiceRuntime.interrupted) return "INTERRUPTED";
  if (voiceRuntime.speaking) return "SPEAKING";
  if (voiceRuntime.state === "THINKING") return "THINKING";
  if (voiceRuntime.recording || voiceRuntime.listening) return "LISTENING";
  if (voiceRuntime.degraded) return "DEGRADED";
  if (voiceRuntime.state === "READY" || voiceRuntime.state === "IDLE") return "READY";
  if (voiceRuntime.state) return normalizeTruthState(voiceRuntime.state);
  return "READY";
}

function composeVoiceChip(voiceRuntime, prefsEnabled) {
  const vs = mapVoiceSessionViewState(voiceRuntime, prefsEnabled);
  const stateMap = {
    OFF: "DISABLED",
    READY: "ACTIVE",
    LISTENING: "ACTIVE",
    THINKING: "ACTIVE",
    SPEAKING: "ACTIVE",
    INTERRUPTED: "DEGRADED",
    DEGRADED: "DEGRADED",
    ERROR: "BLOCKED",
    UNKNOWN: "UNKNOWN",
  };
  return {
    id: "voice",
    label: "VOICE",
    state: stateMap[vs] || "UNKNOWN",
    detail: `session ${vs}`,
    sessionState: vs,
    evidence: voiceRuntime ? "voice.runtime" : prefsEnabled == null ? null : "voice.prefs",
  };
}

function composeSystemChip(infra, overview) {
  const raw =
    infra?.status ||
    infra?.overall ||
    overview?.platform_health?.status ||
    overview?.platform_health?.value ||
    overview?.health?.status;
  if (raw == null && !infra && !overview) {
    return {
      id: "system",
      label: "SYSTEM",
      state: "UNKNOWN",
      detail: "No health payload",
      evidence: null,
    };
  }
  if (raw == null) {
    return {
      id: "system",
      label: "SYSTEM",
      state: "UNKNOWN",
      detail: "Health fields absent in payload",
      evidence: infra ? "infrastructure.health" : "control.overview",
    };
  }
  return {
    id: "system",
    label: "SYSTEM",
    state: normalizeTruthState(raw),
    detail: String(raw),
    evidence: "infrastructure.health|control.overview",
  };
}

/** UI tone for StatusBadge mapping */
export function truthStateToBadgeStatus(state) {
  switch (state) {
    case "HEALTHY":
    case "ACTIVE":
    case "GOVERNED":
    case "PAPER_ONLY":
      return "success";
    case "DEGRADED":
    case "STALE":
    case "INTERRUPTED":
      return "warning";
    case "BLOCKED":
    case "ERROR":
      return "error";
    case "DISABLED":
    case "OFF":
    case "UNAVAILABLE":
      return "neutral";
    default:
      return "pending";
  }
}
