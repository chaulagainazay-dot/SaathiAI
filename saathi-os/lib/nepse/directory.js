// Reference directories — brokers and sectors — with durable state and authority. PURE.
//
// Two defects drove this module, and neither is fixed by editing a list:
//
//   1. A backend restart turned 92 verified broker names into 8 built-in ones and
//      183 mapped sectors into 24, because the good data lived only in memory. The
//      app degraded honestly but almost invisibly.
//   2. The built-in list rendered `49 null` beside real money flows, and calls
//      broker 45 "Kumari Securities" where the verified public source says
//      "Imperial Securities". A fallback that can be WRONG must never outrank a
//      verified source, and must never emit an empty identity.
//
// So this module owns three things: what state the data is in, which source wins
// when two disagree, and how an unknown identity is rendered. The vocabulary is
// deliberately the one already in the codebase — INDICATOR_STATUS for per-entry
// quality, and a display-state map in the same idiom as FEED_SOURCE_LABEL.

import { INDICATOR_STATUS } from "./indicators.js";

/**
 * State of a whole directory. Mirrors FEED_SOURCE_LABEL's idiom rather than
 * inventing a parallel system.
 */
export const DIRECTORY_STATE = {
  LIVE_ENRICHED: "LIVE_ENRICHED",
  CACHED_LAST_VERIFIED: "CACHED_LAST_VERIFIED",
  INCOMPLETE_FALLBACK: "INCOMPLETE_FALLBACK",
  UNAVAILABLE: "UNAVAILABLE",
};

/**
 * Display copy. CACHED must never read as live — that is a permanent invariant,
 * and a test asserts no label here contains the word.
 */
export const DIRECTORY_STATE_LABEL = {
  LIVE_ENRICHED: "Live reference data",
  CACHED_LAST_VERIFIED: "Cached reference data — last verified",
  INCOMPLETE_FALLBACK: "Limited reference data — live enrichment unavailable",
  UNAVAILABLE: "Reference data unavailable",
};

/** How loudly a surface must say it. Fallback is not a caption. */
export const DIRECTORY_STATE_SEVERITY = {
  LIVE_ENRICHED: "none",
  CACHED_LAST_VERIFIED: "notice",
  INCOMPLETE_FALLBACK: "warning",
  UNAVAILABLE: "warning",
};

/** Authority order. Higher wins a disagreement; the loser is recorded, not dropped. */
export const AUTHORITY = {
  [DIRECTORY_STATE.LIVE_ENRICHED]: 3,
  [DIRECTORY_STATE.CACHED_LAST_VERIFIED]: 2,
  [DIRECTORY_STATE.INCOMPLETE_FALLBACK]: 1,
  [DIRECTORY_STATE.UNAVAILABLE]: 0,
};

/**
 * Freshness policy, versioned so a UI never hardcodes its own idea of stale.
 * A trading session is a day, so a directory verified yesterday is still usable
 * and a week-old one is not.
 */
export const FRESHNESS_POLICY = Object.freeze({
  version: 1,
  freshMs: 24 * 60 * 60 * 1000,
  usableMs: 7 * 24 * 60 * 60 * 1000,
});

export const FRESHNESS = {
  FRESH: "FRESH",
  STALE_BUT_USABLE: "STALE_BUT_USABLE",
  EXPIRED: "EXPIRED",
  UNKNOWN: "UNKNOWN",
};

/**
 * Classify age. An unknown timestamp is UNKNOWN, never FRESH — data that cannot
 * say when it was verified has not earned the benefit of the doubt.
 */
export function freshnessOf(verifiedAtMs, nowMs, policy = FRESHNESS_POLICY) {
  if (!Number.isFinite(verifiedAtMs) || !Number.isFinite(nowMs)) return FRESHNESS.UNKNOWN;
  const age = nowMs - verifiedAtMs;
  if (age < 0) return FRESHNESS.UNKNOWN;      // a future timestamp is not freshness
  if (age <= policy.freshMs) return FRESHNESS.FRESH;
  if (age <= policy.usableMs) return FRESHNESS.STALE_BUT_USABLE;
  return FRESHNESS.EXPIRED;
}

/** Human age, for a UI that must show how old "cached" actually is. */
export function describeAge(verifiedAtMs, nowMs) {
  if (!Number.isFinite(verifiedAtMs) || !Number.isFinite(nowMs) || nowMs < verifiedAtMs) return null;
  const mins = Math.floor((nowMs - verifiedAtMs) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} minute${mins === 1 ? "" : "s"} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

const cleanName = (v) => {
  if (v === null || v === undefined) return null;
  if (typeof v !== "string") return null;
  const s = v.trim();
  if (!s) return null;
  // The literal strings a broken pipeline emits. They are not names, and one of
  // them ("null") already reached the brokers table.
  if (/^(null|undefined|none|nan|n\/a|-{1,2})$/i.test(s)) return null;
  return s;
};

const cleanCode = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? Math.trunc(n) : null;
};

/** The label an unknown broker gets. Deterministic, and never a company name. */
export function unknownBrokerLabel(code) {
  const c = cleanCode(code);
  return c === null ? "Unknown broker" : `Broker ${c}`;
}

export const UNKNOWN_SECTOR = "—";

/**
 * Resolve one broker identity across tiers.
 *
 * `tiers` is an ordered list of {state, names: Map|object, verifiedAt, source}.
 * The highest-authority tier that HAS a usable name wins. A lower tier holding a
 * different name is not merged and not discarded — it is reported as a conflict,
 * because "two sources disagree about who handled this money" is a fact a user
 * should be able to see.
 */
export function resolveBroker(code, tiers = []) {
  const c = cleanCode(code);
  const ranked = [...tiers]
    .filter((t) => t && AUTHORITY[t.state] !== undefined)
    .sort((a, b) => AUTHORITY[b.state] - AUTHORITY[a.state]);

  const seen = [];
  for (const t of ranked) {
    const map = t.names instanceof Map ? t.names : new Map(Object.entries(t.names || {}));
    const raw = c === null ? undefined : (map.get(c) ?? map.get(String(c)));
    const name = cleanName(raw);
    if (name) seen.push({ name, state: t.state, source: t.source ?? null, verifiedAt: t.verifiedAt ?? null });
  }

  if (!seen.length) {
    return {
      code: c,
      displayName: unknownBrokerLabel(code),
      known: false,
      source: null,
      state: DIRECTORY_STATE.UNAVAILABLE,
      quality: INDICATOR_STATUS.FIELD_UNAVAILABLE,
      lastVerified: null,
      conflict: null,
    };
  }

  const [winner, ...rest] = seen;
  const disagreeing = rest.filter((r) => r.name !== winner.name);
  return {
    code: c,
    displayName: winner.name,
    known: true,
    source: winner.source,
    state: winner.state,
    // A disagreement is real information about the data, so it downgrades the
    // per-entry quality even though the winning name is still used.
    quality: disagreeing.length ? INDICATOR_STATUS.DATA_CONFLICT : INDICATOR_STATUS.VALID,
    lastVerified: winner.verifiedAt ?? null,
    conflict: disagreeing.length
      ? { chosen: winner.name, chosenFrom: winner.state, rejected: disagreeing.map((d) => ({ name: d.name, from: d.state })) }
      : null,
  };
}

/** Resolve one symbol's sector. Unknown is UNKNOWN_SECTOR — never a guess. */
export function resolveSector(symbol, tiers = []) {
  const s = String(symbol || "").trim().toUpperCase();
  const ranked = [...tiers]
    .filter((t) => t && AUTHORITY[t.state] !== undefined)
    .sort((a, b) => AUTHORITY[b.state] - AUTHORITY[a.state]);

  const seen = [];
  for (const t of ranked) {
    const map = t.sectors instanceof Map ? t.sectors : new Map(Object.entries(t.sectors || {}));
    const name = cleanName(map.get(s));
    if (name) seen.push({ name, state: t.state, source: t.source ?? null, verifiedAt: t.verifiedAt ?? null });
  }

  if (!seen.length) {
    return {
      symbol: s || null,
      sector: null,
      displaySector: UNKNOWN_SECTOR,
      known: false,
      source: null,
      state: DIRECTORY_STATE.UNAVAILABLE,
      quality: INDICATOR_STATUS.FIELD_UNAVAILABLE,
      lastVerified: null,
      conflict: null,
    };
  }

  const [winner, ...rest] = seen;
  const disagreeing = rest.filter((r) => r.name !== winner.name);
  return {
    symbol: s,
    sector: winner.name,
    displaySector: winner.name,
    known: true,
    source: winner.source,
    state: winner.state,
    quality: disagreeing.length ? INDICATOR_STATUS.DATA_CONFLICT : INDICATOR_STATUS.VALID,
    lastVerified: winner.verifiedAt ?? null,
    conflict: disagreeing.length
      ? { chosen: winner.name, chosenFrom: winner.state, rejected: disagreeing.map((d) => ({ name: d.name, from: d.state })) }
      : null,
  };
}

/**
 * The state a whole directory is in, given what each tier produced.
 * Freshness can only ever DOWNGRADE: an expired cache is not usable data, and a
 * live fetch whose timestamp is unknown does not get to claim LIVE.
 */
export function directoryState({ live = null, cached = null, fallback = null, nowMs = null } = {}) {
  if (live && live.entries > 0) {
    const fresh = freshnessOf(live.verifiedAt, nowMs);
    if (fresh === FRESHNESS.FRESH || fresh === FRESHNESS.UNKNOWN) {
      return { state: DIRECTORY_STATE.LIVE_ENRICHED, entries: live.entries, source: live.source ?? null,
               verifiedAt: live.verifiedAt ?? null, freshness: fresh };
    }
  }
  if (cached && cached.entries > 0) {
    const fresh = freshnessOf(cached.verifiedAt, nowMs);
    if (fresh !== FRESHNESS.EXPIRED) {
      return { state: DIRECTORY_STATE.CACHED_LAST_VERIFIED, entries: cached.entries, source: cached.source ?? null,
               verifiedAt: cached.verifiedAt ?? null, freshness: fresh };
    }
  }
  if (fallback && fallback.entries > 0) {
    return { state: DIRECTORY_STATE.INCOMPLETE_FALLBACK, entries: fallback.entries, source: fallback.source ?? null,
             verifiedAt: null, freshness: FRESHNESS.UNKNOWN };
  }
  return { state: DIRECTORY_STATE.UNAVAILABLE, entries: 0, source: null, verifiedAt: null, freshness: FRESHNESS.UNKNOWN };
}

/** What a surface should render about its own data quality. */
export function stateBanner(state, { verifiedAt = null, nowMs = null, entries = null, expected = null } = {}) {
  const label = DIRECTORY_STATE_LABEL[state] || DIRECTORY_STATE_LABEL.UNAVAILABLE;
  const severity = DIRECTORY_STATE_SEVERITY[state] || "warning";
  const age = describeAge(verifiedAt, nowMs);
  const coverage = Number.isFinite(entries) && Number.isFinite(expected) && expected > 0
    ? `${entries} of about ${expected} known` : null;
  return {
    state,
    label,
    severity,
    age,
    coverage,
    // Never the word "live" unless the data actually is.
    isLive: state === DIRECTORY_STATE.LIVE_ENRICHED,
  };
}
