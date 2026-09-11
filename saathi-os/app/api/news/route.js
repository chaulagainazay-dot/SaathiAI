// News context for an instrument. Allowlisted RSS only — never scraped HTML.
//
// The feeds are syndication endpoints, which is a materially better licensing
// posture than scraping a portal. Everything returned is UNTRUSTED_EXTERNAL_DATA:
// sanitized, injection-fenced, and labelled as correlation-in-time, never cause.

import { NextResponse } from "next/server";
import {
  NEWS_SOURCES, ALLOWED_NEWS_HOSTS, parseFeed, matchToSymbol, recentItems,
} from "@/lib/news/feed";
import { STOCKS } from "@/lib/nepse/data";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SYMBOL_RE = /^[A-Z0-9]{1,12}$/;
const TIMEOUT_MS = 12_000;
const MAX_BYTES = 3_000_000;
const CACHE_MS = 15 * 60 * 1000; // headlines do not need to be fresher than this

const cache = new Map();

const CRYPTO_ALIASES = {
  BTCUSDT: ["bitcoin", "btc"],
  ETHUSDT: ["ethereum", "eth", "ether"],
};

function aliasesFor(market, symbol) {
  if (market === "crypto") return CRYPTO_ALIASES[symbol] || [];
  const s = STOCKS.find((x) => x.symbol === symbol);
  if (!s) return [];
  // Company name minus the corporate suffix, which never appears in a headline.
  const name = s.name.replace(/\b(limited|ltd\.?|company|co\.?|bank|plc)\b/gi, "").trim();
  return name.length >= 3 ? [name] : [];
}

export async function GET(request) {
  const q = new URL(request.url).searchParams;
  const market = (q.get("market") || "nepse").toLowerCase();
  const symbol = (q.get("symbol") || "").trim().toUpperCase();
  if (!["nepse", "crypto"].includes(market)) {
    return NextResponse.json({ ok: false, reason: "UNKNOWN_MARKET" }, { headers: { "cache-control": "no-store" } });
  }
  if (symbol && !SYMBOL_RE.test(symbol)) {
    return NextResponse.json({ ok: false, reason: "INVALID_SYMBOL" }, { headers: { "cache-control": "no-store" } });
  }

  const key = `${market}:${symbol}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_MS) {
    return NextResponse.json(hit.body, { headers: { "cache-control": "no-store" } });
  }

  const sources = NEWS_SOURCES[market] || [];
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  const all = [];
  const failures = [];

  try {
    for (const src of sources) {
      // Defence in depth: the URL is a constant, and its host is re-checked anyway.
      const u = new URL(src.url);
      if (u.protocol !== "https:" || !ALLOWED_NEWS_HOSTS.has(u.hostname)) {
        failures.push({ source: src.id, reason: "HOST_NOT_ALLOWED" });
        continue;
      }
      try {
        const res = await fetch(src.url, {
          headers: { accept: "application/rss+xml, application/xml, text/xml" },
          signal: ac.signal, redirect: "follow", cache: "no-store",
        });
        if (!res.ok) { failures.push({ source: src.id, reason: `HTTP_${res.status}` }); continue; }
        const text = await res.text();
        if (text.length > MAX_BYTES) { failures.push({ source: src.id, reason: "TOO_LARGE" }); continue; }
        const { items, reason } = parseFeed(text, { sourceId: src.id, sourceLabel: src.label, host: src.host, scope: src.scope });
        if (!items.length) { failures.push({ source: src.id, reason: reason || "NO_ITEMS" }); continue; }
        all.push(...items);
      } catch (e) {
        failures.push({ source: src.id, reason: e?.name === "AbortError" ? "TIMEOUT" : "UNREACHABLE" });
      }
    }

    const recent = recentItems(all, 7);
    const { direct, context } = symbol
      ? matchToSymbol(recent, { symbol, aliases: aliasesFor(market, symbol) })
      : { direct: [], context: recent };

    const body = {
      ok: true,
      market, symbol,
      trust: "UNTRUSTED_EXTERNAL_DATA",
      causality: "CORRELATION_IN_TIME_ONLY",
      note: "Headlines near this instrument. Timing overlap is not causation; no catalyst is attributed.",
      fetchedAt: new Date().toISOString(),
      sources: sources.map((s) => ({ id: s.id, label: s.label, host: s.host, scope: s.scope })),
      marketSpecific: recent.filter((i) => i.scope === "business").length,
      counts: { total: all.length, recent: recent.length, direct: direct.length, context: context.length },
      injectionFlagged: recent.filter((i) => i.injectionFlagged).length,
      direct,
      context: context.slice(0, 8),
      failures,
      earnings: {
        available: false,
        reason: "NO_EARNINGS_SOURCE",
        note: "No feed here carries structured earnings or quarterly financials. Fundamentals shown elsewhere come from the in-repo snapshot, not from news.",
      },
    };
    cache.set(key, { at: Date.now(), body });
    return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
  } finally { clearTimeout(timer); }
}
