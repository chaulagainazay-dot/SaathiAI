// NEPSE live feed — governance and normalization. PURE, no I/O.
//
// Policy (NEPSE-DATA-1): SaathiOS does not scrape protected or public NEPSE
// portals. A live feed is only ever a LICENSED vendor endpoint that the operator
// configures explicitly. This module decides whether a configured endpoint is
// allowed to be called at all, and normalizes whatever it returns into the
// canonical shape the UI already uses.
//
// Fail closed everywhere: an unconfigured, malformed, or disallowed feed yields
// "unconfigured"/"blocked" — never a silent fallback presented as live truth.

/** Vendor hosts the operator has explicitly allowlisted, comma-separated. */
export function parseAllowlist(raw) {
  return String(raw || "")
    .split(",")
    .map((h) => h.trim().toLowerCase())
    .filter(Boolean);
}

// Private / link-local / loopback ranges must never be reachable from a
// server-side fetch driven by configuration (SSRF containment).
const PRIVATE_HOST = /^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|169\.254\.|::1|\[::1\]|172\.(1[6-9]|2\d|3[01])\.)/i;

export const FEED_REASON = {
  OK: "OK",
  NOT_CONFIGURED: "NOT_CONFIGURED",
  NO_ALLOWLIST: "NO_ALLOWLIST",
  BAD_URL: "BAD_URL",
  SCHEME_NOT_HTTPS: "SCHEME_NOT_HTTPS",
  HOST_NOT_ALLOWLISTED: "HOST_NOT_ALLOWLISTED",
  PRIVATE_ADDRESS: "PRIVATE_ADDRESS",
  CREDENTIALS_IN_URL: "CREDENTIALS_IN_URL",
  // Named separately from a generic failure because they call for opposite
  // responses: a rate limit means STOP CALLING, and treating it as a transient
  // error means retrying into it forever — which is how a working feed stays
  // dead long after the quota would have reset.
  RATE_LIMITED: "RATE_LIMITED",
  UPSTREAM_BLOCKED: "UPSTREAM_BLOCKED",
  UNEXPECTED_CONTENT: "UNEXPECTED_CONTENT",
  MARKET_CLOSED: "MARKET_CLOSED",
  BACKING_OFF: "BACKING_OFF",
};

// ── when the vendor may be called ────────────────────────────────────────────

/** Nepal Standard Time is UTC+05:45 and observes no daylight saving. */
export const NPT_OFFSET_MINUTES = 5 * 60 + 45;
/** NEPSE trades Sunday to Thursday. 0 is Sunday. */
export const TRADING_DAYS = Object.freeze([0, 1, 2, 3, 4]);
/** Continuous trading, in NPT minutes-from-midnight. Pre-open starts at 10:30. */
export const SESSION_OPEN_MIN = 10 * 60 + 30;
export const SESSION_CLOSE_MIN = 15 * 60;
/** Quotes stay callable briefly after the close so the settling price is caught. */
export const POST_CLOSE_GRACE_MIN = 20;

/**
 * Is the exchange in a window where a price can still change?
 *
 * Anchored to Nepal time, NOT the server's. `isMarketOpen` in format.js reads
 * `getHours()`, which is the host's timezone — correct only on a machine already
 * set to NPT, and silently wrong everywhere else.
 *
 * This is the gate that matters for a metered feed. Polling a vendor every thirty
 * seconds through a night when no price can move is most of a day's quota spent
 * re-reading the same closing number, and it is exactly what exhausted the
 * configured worker.
 */
export function marketWindow(now = new Date()) {
  const t = now instanceof Date ? now.getTime() : Number(now);
  if (!Number.isFinite(t)) return { open: false, reason: "BAD_CLOCK", nptMinutes: null, nptDay: null };
  const npt = new Date(t + NPT_OFFSET_MINUTES * 60_000);
  const day = npt.getUTCDay();
  const minutes = npt.getUTCHours() * 60 + npt.getUTCMinutes();
  if (!TRADING_DAYS.includes(day)) {
    return { open: false, reason: "WEEKEND", nptMinutes: minutes, nptDay: day };
  }
  const open = minutes >= SESSION_OPEN_MIN && minutes <= SESSION_CLOSE_MIN + POST_CLOSE_GRACE_MIN;
  return {
    open,
    reason: open ? "OPEN" : (minutes < SESSION_OPEN_MIN ? "BEFORE_OPEN" : "AFTER_CLOSE"),
    nptMinutes: minutes,
    nptDay: day,
  };
}

/**
 * A response body that is not the data we asked for.
 *
 * A rate-limit page is HTML with a 200, so status alone never catches it. Reading
 * "temporarily rate limited" as "no usable quotes" is the difference between
 * "back off" and "the market published nothing", and only one of those is a
 * reason to keep calling.
 */
export function classifyBody(status, contentType, text) {
  if (status === 429) return FEED_REASON.RATE_LIMITED;
  if (status === 403 || status === 503) return FEED_REASON.UPSTREAM_BLOCKED;
  const body = String(text || "");
  const looksHtml = /^\s*</.test(body) || /text\/html/i.test(String(contentType || ""));
  if (!looksHtml) return FEED_REASON.OK;
  if (/rate limited|too many requests|rate.?limit/i.test(body)) return FEED_REASON.RATE_LIMITED;
  if (/cloudflare|access denied|forbidden|attention required/i.test(body)) return FEED_REASON.UPSTREAM_BLOCKED;
  return FEED_REASON.UNEXPECTED_CONTENT;
}

/** Backoff after a refusal: doubling, from one minute to one hour. */
export const BACKOFF_BASE_MS = 60_000;
export const BACKOFF_MAX_MS = 60 * 60_000;

export function backoffMs(consecutiveFailures) {
  const n = Number(consecutiveFailures);
  if (!Number.isFinite(n) || n <= 0) return 0;
  return Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * 2 ** (n - 1));
}

/**
 * Decide whether a configured feed endpoint may be called.
 * @returns {{allowed: boolean, reason: string, host?: string}}
 */
export function evaluateFeedEndpoint(url, allowlistRaw) {
  if (!url) return { allowed: false, reason: FEED_REASON.NOT_CONFIGURED };

  const allowlist = parseAllowlist(allowlistRaw);
  if (!allowlist.length) return { allowed: false, reason: FEED_REASON.NO_ALLOWLIST };

  let u;
  try {
    u = new URL(String(url));
  } catch {
    return { allowed: false, reason: FEED_REASON.BAD_URL };
  }

  if (u.protocol !== "https:") return { allowed: false, reason: FEED_REASON.SCHEME_NOT_HTTPS };
  if (u.username || u.password) return { allowed: false, reason: FEED_REASON.CREDENTIALS_IN_URL };

  const host = u.hostname.toLowerCase();
  if (PRIVATE_HOST.test(host)) return { allowed: false, reason: FEED_REASON.PRIVATE_ADDRESS, host };

  // Exact host or a subdomain of an allowlisted host — never a suffix match on
  // a bare string (so "evil-nepse.com" cannot pass for "nepse.com").
  const ok = allowlist.some((a) => host === a || host.endsWith(`.${a}`));
  if (!ok) return { allowed: false, reason: FEED_REASON.HOST_NOT_ALLOWLISTED, host };

  return { allowed: true, reason: FEED_REASON.OK, host };
}

const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/**
 * Normalize a vendor quote row into the canonical shape the NEPSE UI uses.
 * Vendors differ; accept the common aliases and drop anything unusable rather
 * than inventing a value.
 */
export function normalizeQuote(row) {
  if (!row || typeof row !== "object") return null;
  const symbol = String(
    row.symbol ?? row.Symbol ?? row.scrip ?? row.ticker ?? "",
  ).trim().toUpperCase();
  if (!symbol) return null;

  const ltp = num(row.ltp ?? row.lastTradedPrice ?? row.last_price ?? row.close ?? row.lastPrice);
  if (ltp === null) return null; // a quote without a price is not a quote

  // An unknown previous close stays null. Defaulting it to ltp would render a
  // confident 0.00% day change that the feed never actually reported.
  const prevClose = num(row.previousClose ?? row.prev_close ?? row.previousClosing ?? row.pc);
  return {
    symbol,
    ltp,
    prevClose,
    open: num(row.open ?? row.openPrice),
    high: num(row.high ?? row.highPrice),
    low: num(row.low ?? row.lowPrice),
    volume: num(row.volume ?? row.totalTradedQuantity ?? row.qty),
  };
}

/** Normalize a whole vendor payload; tolerates {data:[…]} / {quotes:[…]} / […]. */
export function normalizeFeedPayload(payload) {
  const rows = Array.isArray(payload)
    ? payload
    : payload?.data ?? payload?.quotes ?? payload?.result ?? [];
  if (!Array.isArray(rows)) return [];
  return rows.map(normalizeQuote).filter(Boolean);
}

/** Merge live quotes over the snapshot, keeping snapshot fundamentals. */
export function mergeLiveQuotes(snapshotStocks, liveQuotes) {
  if (!Array.isArray(liveQuotes) || !liveQuotes.length) return snapshotStocks;
  const byS = new Map(liveQuotes.map((q) => [q.symbol, q]));
  return snapshotStocks.map((s) => {
    const q = byS.get(s.symbol);
    if (!q) return s;
    const ltp = q.ltp;
    // The snapshot's previous close belongs to the snapshot's trading day; pairing
    // it with a live price would produce a wrong day change. Mark it unavailable.
    const hasPrev = q.prevClose !== null && q.prevClose !== undefined;
    return {
      ...s,
      ltp,
      prevClose: hasPrev ? q.prevClose : null,
      changeUnavailable: !hasPrev,
      // derived valuation must follow the live price, not stay stale
      pe: s.eps > 0 ? +(ltp / s.eps).toFixed(2) : null,
      pb: s.bookValue > 0 ? +(ltp / s.bookValue).toFixed(2) : null,
      marketCap: ltp * s.listedShares * 1e6,
      live: true,
    };
  });
}

export const FEED_SOURCE_LABEL = {
  live: "LIVE NEPSE FEED",
  snapshot: "SNAPSHOT / SEED DATA — NOT A LIVE NEPSE FEED",
  unconfigured: "NO LICENSED FEED CONFIGURED — SHOWING SNAPSHOT",
  blocked: "FEED BLOCKED BY POLICY — SHOWING SNAPSHOT",
  error: "FEED UNREACHABLE — SHOWING SNAPSHOT",
  // Not a failure. The exchange is shut, so the last settled prices ARE the
  // current ones, and calling this an error sends someone debugging a feed that
  // is working exactly as intended.
  closed: "MARKET CLOSED — SHOWING THE LAST SETTLED PRICES",
};

// ── what the quote route should do right now ─────────────────────────────────

export const FEED_ACTION = Object.freeze({
  SERVE_CACHE: "SERVE_CACHE",
  FETCH: "FETCH",
  REFUSE_CLOSED: "REFUSE_CLOSED",
  REFUSE_BACKOFF: "REFUSE_BACKOFF",
});

export const OPEN_CACHE_MS = 15_000;
/** Shut, the price is fixed until the next session; re-reading it is pure spend. */
export const CLOSED_CACHE_MS = 10 * 60_000;

/**
 * Decide whether the vendor may be called, without calling anything.
 *
 * Extracted from the route so every branch is testable against a fixed clock. The
 * ordering is the whole point and is asserted in the tests:
 *
 *   1. A FRESH CACHE WINS OVER EVERYTHING, including a tripped breaker — holding
 *      back a good price because a later request failed would be worse data, not
 *      safer data.
 *   2. A CLOSED MARKET BEATS A STALE CACHE. Stale here means "older than ten
 *      minutes", and outside trading hours nothing has happened in those ten
 *      minutes, so the answer is the cache if we have one and a plain refusal if
 *      we do not.
 *   3. THE BREAKER BEATS A FETCH. A rate limit only lapses if we stop calling.
 *
 * @param {{now?:number, cachedAt?:number|null, hasCache?:boolean,
 *          breakerUntil?:number|null}} state
 */
export function feedAction({ now = Date.now(), cachedAt = null, hasCache = false,
                             breakerUntil = null } = {}) {
  const win = marketWindow(new Date(now));
  const ttl = win.open ? OPEN_CACHE_MS : CLOSED_CACHE_MS;
  const age = hasCache && Number.isFinite(cachedAt) ? now - cachedAt : null;

  if (hasCache && age !== null && age < ttl) {
    return { action: FEED_ACTION.SERVE_CACHE, window: win, ageMs: age };
  }
  if (!win.open) {
    return hasCache
      ? { action: FEED_ACTION.SERVE_CACHE, window: win, ageMs: age, stale: true }
      : { action: FEED_ACTION.REFUSE_CLOSED, window: win, reason: FEED_REASON.MARKET_CLOSED };
  }
  if (Number.isFinite(breakerUntil) && now < breakerUntil) {
    return {
      action: FEED_ACTION.REFUSE_BACKOFF, window: win,
      reason: FEED_REASON.BACKING_OFF, retryInMs: breakerUntil - now,
    };
  }
  return { action: FEED_ACTION.FETCH, window: win };
}
