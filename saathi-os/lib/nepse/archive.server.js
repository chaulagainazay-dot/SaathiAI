/**
 * Server-side archive reader — the one place company history is fetched.
 *
 * The indicator service and the scan service both need every listed company's
 * daily bars. Before this module they would have been two copies of the same
 * pool, timeout, size cap and host constant, and the second copy is where the
 * cap quietly goes missing. SERVER ONLY: it performs network I/O and must never
 * be imported into a component.
 *
 * The guards are not decoration:
 *   - `redirect: "error"` — a redirect off this host is a different source, and
 *     silently following one would relabel someone else's numbers as ours.
 *   - `MAX_BYTES` and the leading-`<` check — an HTML error page parses to zero
 *     bars, which is indistinguishable from a company that never traded.
 *   - A failed symbol is DROPPED, and the caller is told how many were requested
 *     against how many answered, so a half-read exchange can never be presented
 *     as the whole of it.
 */

import { parseHistoryCsv } from "./history.js";
import { STOCKS } from "./data.js";

export const ARCHIVE_HOST = "raw.githubusercontent.com";
export const ARCHIVE_BASE =
  `https://${ARCHIVE_HOST}/Aabishkar2/nepse-data/main/data/company-wise`;

export const SYMBOL_RE = /^[A-Z0-9]{1,12}$/;
export const DEFAULT_CONCURRENCY = 4;
export const DEFAULT_TIMEOUT_MS = 20_000;
export const MAX_BYTES = 6_000_000;

/** Bounded-concurrency map that never rejects; failures come back as null. */
export async function pooled(items, worker, limit = DEFAULT_CONCURRENCY) {
  const out = [];
  let i = 0;
  await Promise.all(
    Array.from({ length: Math.min(limit, items.length) }, async () => {
      while (i < items.length) {
        const idx = i++;
        out[idx] = await worker(items[idx]).catch(() => null);
      }
    }),
  );
  return out.filter(Boolean);
}

/** One company's parsed bars, or null when the file cannot be trusted. */
export async function fetchSymbolBars(symbol, signal) {
  const res = await fetch(`${ARCHIVE_BASE}/${symbol}.csv`, {
    headers: { accept: "text/csv,text/plain" },
    signal, redirect: "error", cache: "no-store",
  });
  if (!res.ok) return null;
  const text = await res.text();
  if (text.length > MAX_BYTES || /^\s*</.test(text)) return null;
  const { bars } = parseHistoryCsv(text, { symbol });
  if (!bars.length) return null;
  return { symbol, bars };
}

/**
 * Read the archive for a symbol list.
 *
 * @returns {{entries: Array<{symbol, bars}>, requested: number, covered: number}}
 */
export async function readArchive(symbols, { signal, concurrency } = {}) {
  const list = (symbols || []).filter((s) => SYMBOL_RE.test(s));
  const entries = await pooled(
    list, (sym) => fetchSymbolBars(sym, signal), concurrency || DEFAULT_CONCURRENCY,
  );
  return { entries, requested: list.length, covered: entries.length };
}

/** An AbortController that fires after `ms`, plus its cleanup. */
export function withTimeout(ms = DEFAULT_TIMEOUT_MS) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), ms);
  return { signal: ac.signal, done: () => clearTimeout(timer) };
}

// ── the listed universe ──────────────────────────────────────────────────────

const API_HOST = "api.github.com";
const LIST_URL = `https://${API_HOST}/repos/Aabishkar2/nepse-data/contents/data/company-wise`;
// The traded universe, read from a raw file rather than an API listing. The GitHub
// contents API allows 60 unauthenticated calls an hour ACROSS the whole host, so
// hanging a page on it means an unrelated caller can take it down — which is
// exactly what happened in testing. Raw file fetches are not metered that way.
const DAILY_BASE =
  `https://${ARCHIVE_HOST}/socrateai-official/nepse-open-data/main/ohlc_adjusted_stock`;

export const UNIVERSE_CACHE_MS = 24 * 60 * 60 * 1000; // the listed universe barely moves

let universeCache = { at: 0, symbols: null, via: null, kind: null };

/** Symbols traded in the most recent session, from a raw daily market file. */
async function universeFromDailyFile(signal) {
  for (let i = 0; i < 10; i += 1) {
    const day = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
    const res = await fetch(`${DAILY_BASE}/adj_${day}.csv`, {
      headers: { accept: "text/csv,text/plain" },
      signal, redirect: "error", cache: "no-store",
    }).catch(() => null);
    if (!res || !res.ok) continue;
    const text = await res.text();
    if (/^\s*</.test(text)) continue;
    const lines = text.split(/\r?\n/).filter((l) => l.trim());
    if (lines.length < 2) continue;
    const col = lines[0].split(",").map((h) => h.trim().toLowerCase()).indexOf("symbol");
    if (col < 0) continue;
    const syms = [...new Set(lines.slice(1)
      .map((l) => String(l.split(",")[col] || "").trim().toUpperCase())
      .filter((sy) => SYMBOL_RE.test(sy)))];
    if (syms.length) return syms;
  }
  return null;
}

/** The archive's own directory listing — accurate, but rate-limited, so it is second. */
async function universeFromContentsApi(signal) {
  const res = await fetch(LIST_URL, {
    headers: { accept: "application/vnd.github+json" },
    signal, redirect: "error", cache: "no-store",
  }).catch(() => null);
  if (!res || !res.ok) return null;
  const json = await res.json().catch(() => null);
  if (!Array.isArray(json)) return null;
  const syms = json
    .filter((f) => f && typeof f.name === "string" && f.name.endsWith(".csv"))
    .map((f) => f.name.slice(0, -4))
    .filter((sy) => SYMBOL_RE.test(sy));
  return syms.length ? syms : null;
}

/**
 * Resolve the universe, preferring the unmetered source and never letting a
 * transient listing failure erase a universe we already knew.
 *
 * `kind` is the load-bearing field. LISTED is every listed company, TRADED is only
 * what changed hands that session, and CURATED is this build's own 24-symbol list.
 * A caller that reports "full coverage" without saying WHICH universe was covered
 * would present 24 companies as the exchange, so every consumer must carry `kind`
 * through to whatever it tells the reader.
 */
export async function resolveUniverse(signal) {
  if (universeCache.symbols && Date.now() - universeCache.at < UNIVERSE_CACHE_MS) {
    return { symbols: universeCache.symbols, via: universeCache.via, kind: universeCache.kind, cached: true };
  }
  const attempts = [
    ["contents-api", universeFromContentsApi, "LISTED"],
    ["daily-file", universeFromDailyFile, "TRADED"],
  ];
  for (const [via, fn, kind] of attempts) {
    const symbols = await fn(signal).catch(() => null);
    if (symbols && symbols.length) {
      universeCache = { at: Date.now(), symbols, via, kind };
      return { symbols, via, kind, cached: false };
    }
  }
  if (universeCache.symbols) {
    return {
      symbols: universeCache.symbols, via: `${universeCache.via} (stale)`,
      kind: universeCache.kind, cached: true,
    };
  }
  const fallback = STOCKS.map((st) => st.symbol).filter((sy) => SYMBOL_RE.test(sy));
  return fallback.length
    ? { symbols: fallback, via: "curated-fallback", kind: "CURATED", cached: false }
    : null;
}
