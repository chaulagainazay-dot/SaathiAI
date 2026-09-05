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
};

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
};
