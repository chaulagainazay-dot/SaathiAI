// Server-side NEPSE historical bar proxy (NEPSE-HIST-2).
//
// Fetches one symbol's daily history from the qualified RESEARCH source, validates
// it, and returns typed bars + indicators. The archive is untrusted input: the
// symbol is pattern-checked before it ever reaches a URL (no path traversal), the
// host is fixed, the response is size-capped, and every row is validated rather
// than trusted.
//
// This source is RESEARCH_ONLY — scraped, unlicensed, unadjusted, without revision
// metadata. The response says so on every call so no caller can mistake it for a
// licensed production feed.

import { NextResponse } from "next/server";
import { parseHistoryCsv, historyQuality, NEPSE_RESEARCH_SOURCE } from "@/lib/nepse/history";
import { computeIndicators } from "@/lib/nepse/indicators";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HOST = "raw.githubusercontent.com";
const BASE = `https://${HOST}/Aabishkar2/nepse-data/main/data/company-wise`;
const TIMEOUT_MS = 12_000;
const MAX_BYTES = 6_000_000;
const CACHE_MS = 10 * 60 * 1000; // history changes at most daily

// Symbols are uppercase alphanumerics only — this is what stops "../" ever
// reaching the URL, before any encoding is considered.
const SYMBOL_RE = /^[A-Z0-9]{1,12}$/;

const cache = new Map(); // symbol -> {at, body}

function fail(reason, extra = {}) {
  return NextResponse.json(
    { source: NEPSE_RESEARCH_SOURCE.id, classification: NEPSE_RESEARCH_SOURCE.classification, bars: [], reason, ...extra },
    { headers: { "cache-control": "no-store" } },
  );
}

export async function GET(request) {
  const raw = new URL(request.url).searchParams.get("symbol") || "";
  const symbol = raw.trim().toUpperCase();
  if (!SYMBOL_RE.test(symbol)) return fail("INVALID_SYMBOL");

  const hit = cache.get(symbol);
  if (hit && Date.now() - hit.at < CACHE_MS) {
    return NextResponse.json(hit.body, { headers: { "cache-control": "no-store" } });
  }

  const url = `${BASE}/${symbol}.csv`;
  // Defence in depth: even with the regex, refuse anything that is not the host
  // and path shape we intend to call.
  const parsed = new URL(url);
  if (parsed.hostname !== HOST || parsed.protocol !== "https:") return fail("HOST_NOT_ALLOWED");

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      headers: { accept: "text/csv,text/plain" },
      signal: ac.signal,
      redirect: "error",
      cache: "no-store",
    });
    if (res.status === 404) return fail("SYMBOL_NOT_IN_DATASET");
    if (!res.ok) return fail(`UPSTREAM_${res.status}`);

    const len = Number(res.headers.get("content-length") || 0);
    if (len && len > MAX_BYTES) return fail("RESPONSE_TOO_LARGE");
    const text = await res.text();
    if (text.length > MAX_BYTES) return fail("RESPONSE_TOO_LARGE");
    // A CSV archive must not be HTML (an error page, or anything scriptable).
    if (/^\s*</.test(text)) return fail("UNEXPECTED_CONTENT_TYPE");

    const { bars, rejected } = parseHistoryCsv(text, { symbol });
    if (!bars.length) return fail("NO_USABLE_BARS");

    const quality = historyQuality(bars, rejected);
    const indicators = computeIndicators(bars, { instrument: symbol });

    const body = {
      symbol,
      source: NEPSE_RESEARCH_SOURCE.id,
      provider: NEPSE_RESEARCH_SOURCE.provider,
      classification: NEPSE_RESEARCH_SOURCE.classification,
      adjustment: NEPSE_RESEARCH_SOURCE.adjustment,
      adjustmentMethod: NEPSE_RESEARCH_SOURCE.adjustmentMethod,
      revisionMetadata: NEPSE_RESEARCH_SOURCE.revisionMetadata,
      receivedAt: new Date().toISOString(),
      quality,
      indicators,
      // Only the recent tail is shipped to the browser; the full series stays server-side.
      bars: bars.slice(-400).map((b) => ({
        date: b.date, open: b.open, high: b.high, low: b.low, close: b.close,
        volume: b.volume, trusted: b.trusted, flags: b.flags,
      })),
    };
    cache.set(symbol, { at: Date.now(), body });
    return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
  } catch (e) {
    return fail(e?.name === "AbortError" ? "TIMEOUT" : "UNREACHABLE");
  } finally {
    clearTimeout(timer);
  }
}
