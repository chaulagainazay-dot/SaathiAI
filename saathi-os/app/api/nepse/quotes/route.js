// Server-side NEPSE quote proxy.
//
// The licensed vendor credential lives ONLY here. It is read from the server
// environment and never serialized to the client — the browser calls this route,
// not the vendor. The route refuses to call anything the operator has not
// explicitly allowlisted, and fails closed to "snapshot" rather than erroring the
// page or inventing prices.
//
// TWO THINGS THIS ROUTE LEARNED THE HARD WAY.
//
//   1. IT MUST NOT CALL A VENDOR WHEN NO PRICE CAN CHANGE. NEPSE trades Sunday to
//      Thursday, 10:30–15:00 Nepal time. The client polls every 30 seconds; in
//      per-symbol mode that was 24 requests a poll, around the clock, seven days a
//      week — roughly 2,900 requests an hour per open tab, nearly all of them
//      re-reading a closing price that had not moved since the previous week. The
//      configured worker was rate-limited into a Cloudflare block page by our own
//      traffic.
//
//   2. A REFUSAL IS NOT A RETRY. That block page returns HTTP 200 with HTML, so it
//      was read as "no usable quotes" and retried 15 seconds later, forever. A
//      rate limit means STOP CALLING; without a backoff the limit can never lapse.
//
// Configure (server env only):
//   NEPSE_FEED_URL        https://<licensed-vendor>/path/to/quotes
//   NEPSE_FEED_ALLOWLIST  comma-separated vendor hosts, e.g. api.vendor.com
//   NEPSE_FEED_KEY        bearer token / api key (optional, vendor-dependent)
//   NEPSE_FEED_HEADER     header name for the key (default: Authorization)
//   NEPSE_FEED_MODE       bulk | per-symbol | sharesansar
//
// `sharesansar` mode needs no vendor URL: it reads the whole market in ONE request
// through the governed browser, and carries the previous close that the per-symbol
// worker does not report — so day changes become computable instead of blank.

import { NextResponse } from "next/server";
import {
  FEED_ACTION, FEED_REASON, backoffMs, classifyBody, evaluateFeedEndpoint,
  feedAction, normalizeFeedPayload, normalizeQuote,
} from "@/lib/nepse/feed-policy";
import { STOCKS } from "@/lib/nepse/data";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const TIMEOUT_MS = 6000;
const SHARESANSAR_TIMEOUT_MS = 150_000; // a governed browser read, not an API call
const MAX_BYTES = 2_000_000; // bounded response — a feed cannot exhaust memory
const CONCURRENCY = 6;       // per-symbol providers must not be hammered

let cache = { at: 0, body: null };
// The circuit breaker. `until` is when the vendor may next be called at all.
let breaker = { failures: 0, until: 0, reason: null };

function tripBreaker(reason) {
  breaker.failures += 1;
  breaker.until = Date.now() + backoffMs(breaker.failures);
  breaker.reason = reason;
  return breaker;
}

function resetBreaker() {
  breaker = { failures: 0, until: 0, reason: null };
}

/** Bounded-concurrency map — keeps a per-symbol provider to a civil request rate. */
async function pooled(items, worker, limit = CONCURRENCY) {
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

/**
 * Read one response with the guards every path needs: size cap, then body
 * classification. Returns {ok, quotesText} or {ok:false, reason}.
 */
async function readGuarded(res) {
  const len = Number(res.headers.get("content-length") || 0);
  if (len && len > MAX_BYTES) return { ok: false, reason: "response_too_large" };
  const text = await res.text();
  if (text.length > MAX_BYTES) return { ok: false, reason: "response_too_large" };
  const verdict = classifyBody(res.status, res.headers.get("content-type"), text);
  if (verdict !== FEED_REASON.OK) return { ok: false, reason: verdict, refusal: true };
  if (!res.ok) return { ok: false, reason: `upstream_${res.status}` };
  return { ok: true, text };
}

/**
 * Per-symbol provider (e.g. ShareBazaar): the base URL is called once per symbol
 * with ?symbol=SYM. Used when NEPSE_FEED_MODE=per-symbol.
 *
 * A REFUSAL FROM ANY SYMBOL STOPS THE WHOLE SWEEP. Continuing after a rate limit
 * to fire the remaining twenty-three requests is what turns a brief throttle into
 * a sustained block.
 */
async function fetchPerSymbol(baseUrl, headers, signal) {
  const symbols = STOCKS.map((s) => s.symbol);
  let refusal = null;
  const rows = await pooled(symbols, async (sym) => {
    if (refusal) return null;
    const u = new URL(baseUrl);
    u.searchParams.set("symbol", sym);
    const r = await fetch(u.toString(), { headers, signal, redirect: "error", cache: "no-store" });
    const guarded = await readGuarded(r);
    if (!guarded.ok) {
      if (guarded.refusal) refusal = guarded.reason;
      return null;
    }
    let j;
    try { j = JSON.parse(guarded.text); } catch { return null; }
    if (!j || j.error) return null;          // provider signals miss with {error}
    return normalizeQuote(j);
  });
  return { rows, refusal };
}

/**
 * The whole market in one request, via the governed ShareSansar extractor.
 *
 * Same-origin, so the caller's session travels with it — this route holds no
 * credential of its own for the backend and must not invent one.
 */
async function fetchSharesansar(request, signal) {
  const origin = request?.nextUrl?.origin || "";
  const headers = { accept: "application/json" };
  const cookie = request?.headers?.get?.("cookie");
  const auth = request?.headers?.get?.("authorization");
  if (cookie) headers.cookie = cookie;
  if (auth) headers.authorization = auth;

  const res = await fetch(`${origin}/api/nepse/sharesansar?dataset=prices`, {
    headers, signal, cache: "no-store",
  });
  const json = await res.json().catch(() => null);
  if (!json?.available) {
    return { rows: [], refusal: null, reason: json?.reason || "sharesansar_unavailable" };
  }
  const rows = (json.rows || []).map(normalizeQuote).filter(Boolean);
  return { rows, refusal: null, asOf: json.fetchedAt || null, upstream: json.source || null };
}

function payload(source, quotes, extra = {}) {
  return NextResponse.json(
    { source, asOf: new Date().toISOString(), count: quotes.length, quotes, ...extra },
    { headers: { "cache-control": "no-store" } },
  );
}

export async function GET(request) {
  const mode = (process.env.NEPSE_FEED_MODE || "bulk").toLowerCase();

  // One decision, made in one pure function, so the ordering of "fresh cache
  // beats everything / closed beats stale / breaker beats fetch" is asserted by
  // tests rather than by reading this file.
  const decision = feedAction({
    cachedAt: cache.at, hasCache: Boolean(cache.body), breakerUntil: breaker.until,
  });
  const window = decision.window;

  if (decision.action === FEED_ACTION.SERVE_CACHE) {
    return NextResponse.json(
      { ...cache.body, cached: true, marketOpen: window.open,
        marketWindow: window.reason, stale: Boolean(decision.stale) },
      { headers: { "cache-control": "no-store" } },
    );
  }
  if (decision.action === FEED_ACTION.REFUSE_CLOSED) {
    // Say so rather than spending a request on a price that cannot have moved.
    // The page falls back to the snapshot and the banner states it is not live.
    return payload("closed", [], {
      reason: decision.reason,
      marketWindow: window.reason,
      detail: "NEPSE trades Sunday to Thursday, 10:30–15:00 Nepal time",
    });
  }
  if (decision.action === FEED_ACTION.REFUSE_BACKOFF) {
    return payload("blocked", [], {
      reason: decision.reason,
      after: breaker.reason,
      retryInMs: decision.retryInMs,
      consecutiveFailures: breaker.failures,
    });
  }

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(),
    mode === "sharesansar" ? SHARESANSAR_TIMEOUT_MS : TIMEOUT_MS);
  try {
    if (mode === "sharesansar") {
      // No vendor endpoint to evaluate: this path calls our own origin, and the
      // host policy that matters is the backend's browser allowlist.
      const { rows, reason, upstream } = await fetchSharesansar(request, ac.signal);
      if (!rows.length) {
        tripBreaker(reason || "no_usable_quotes");
        return payload("error", [], { reason: reason || "no_usable_quotes" });
      }
      resetBreaker();
      const body = {
        source: "live", asOf: new Date().toISOString(), count: rows.length,
        quotes: rows, upstream, marketOpen: true,
      };
      cache = { at: Date.now(), body };
      return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
    }

    const url = process.env.NEPSE_FEED_URL || "";
    const allowlist = process.env.NEPSE_FEED_ALLOWLIST || "";
    const verdict = evaluateFeedEndpoint(url, allowlist);
    if (!verdict.allowed) {
      const source = verdict.reason === FEED_REASON.NOT_CONFIGURED ? "unconfigured" : "blocked";
      // Never echo the configured URL back to the client.
      return payload(source, [], { reason: verdict.reason });
    }

    const key = process.env.NEPSE_FEED_KEY || "";
    const headerName = process.env.NEPSE_FEED_HEADER || "Authorization";
    const headers = { accept: "application/json" };
    if (key) headers[headerName] = headerName.toLowerCase() === "authorization" ? `Bearer ${key}` : key;

    if (mode === "per-symbol") {
      const { rows, refusal } = await fetchPerSymbol(url, headers, ac.signal);
      if (refusal) {
        const b = tripBreaker(refusal);
        return payload("blocked", [], {
          reason: refusal, retryInMs: b.until - Date.now(), consecutiveFailures: b.failures,
        });
      }
      if (!rows.length) {
        tripBreaker("no_usable_quotes");
        return payload("error", [], { reason: "no_usable_quotes" });
      }
      resetBreaker();
      const body = {
        source: "live", asOf: new Date().toISOString(), count: rows.length,
        quotes: rows, marketOpen: true,
      };
      cache = { at: Date.now(), body };
      return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
    }

    const res = await fetch(url, { headers, signal: ac.signal, redirect: "error", cache: "no-store" });
    const guarded = await readGuarded(res);
    if (!guarded.ok) {
      if (guarded.refusal) {
        const b = tripBreaker(guarded.reason);
        return payload("blocked", [], {
          reason: guarded.reason, retryInMs: b.until - Date.now(), consecutiveFailures: b.failures,
        });
      }
      return payload("error", [], { reason: guarded.reason });
    }

    let json;
    try { json = JSON.parse(guarded.text); } catch { return payload("error", [], { reason: "invalid_json" }); }

    const quotes = normalizeFeedPayload(json);
    if (!quotes.length) {
      tripBreaker("no_usable_quotes");
      return payload("error", [], { reason: "no_usable_quotes" });
    }
    resetBreaker();
    const body = {
      source: "live", asOf: new Date().toISOString(), count: quotes.length,
      quotes, marketOpen: true,
    };
    cache = { at: Date.now(), body };
    return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
  } catch (e) {
    const reason = e?.name === "AbortError" ? "timeout" : "unreachable";
    tripBreaker(reason);
    return payload("error", [], { reason });
  } finally {
    clearTimeout(timer);
  }
}
