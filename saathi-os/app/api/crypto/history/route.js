// Crypto daily bars from Binance's PUBLIC market-data host.
//
// data-api.binance.vision serves market data only — no account, order, or wallet
// endpoint exists on it at all, so this path cannot reach private functionality even
// by mistake. No API key is sent, and none is needed. Matches CRYPTO-DATA-1: public
// SPOT data, symbol allowlist, bounded response, no private API.

import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HOST = "data-api.binance.vision";
const ALLOWED = new Set(["BTCUSDT", "ETHUSDT"]); // certified scope
const INTERVALS = new Set(["1d", "4h", "1h"]);
const LIMIT = 500;
const TIMEOUT_MS = 12_000;
const MAX_BYTES = 4_000_000;
const CACHE_MS = 5 * 60 * 1000;

const cache = new Map();

const fail = (reason) =>
  NextResponse.json({ source: HOST, bars: [], reason }, { headers: { "cache-control": "no-store" } });

export async function GET(request) {
  const q = new URL(request.url).searchParams;
  const symbol = (q.get("symbol") || "BTCUSDT").toUpperCase();
  const interval = (q.get("interval") || "1d").toLowerCase();
  if (!ALLOWED.has(symbol)) return fail("SYMBOL_NOT_ALLOWED");
  if (!INTERVALS.has(interval)) return fail("INTERVAL_NOT_ALLOWED");

  const key = `${symbol}:${interval}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_MS) {
    return NextResponse.json(hit.body, { headers: { "cache-control": "no-store" } });
  }

  const url = `https://${HOST}/api/v3/klines?symbol=${symbol}&interval=${interval}&limit=${LIMIT}`;
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { headers: { accept: "application/json" }, signal: ac.signal, redirect: "error", cache: "no-store" });
    if (!res.ok) return fail(`UPSTREAM_${res.status}`);
    const text = await res.text();
    if (text.length > MAX_BYTES) return fail("RESPONSE_TOO_LARGE");
    let raw;
    try { raw = JSON.parse(text); } catch { return fail("INVALID_JSON"); }
    if (!Array.isArray(raw) || !raw.length) return fail("NO_BARS");

    const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };
    const bars = raw.map((k) => ({
      date: new Date(k[0]).toISOString().slice(0, 10),
      open: num(k[1]), high: num(k[2]), low: num(k[3]), close: num(k[4]), volume: num(k[5]),
      // The exchange is first-party for its own market: all fields are trusted.
      trusted: { open: true, high: true, low: true, close: true, volume: true },
      flags: [],
    })).filter((b) => b.close !== null);

    const body = {
      symbol, interval,
      source: HOST,
      provider: "Binance public market data",
      classification: "EXCHANGE_PUBLIC_MARKET_DATA",
      adjustment: "NOT_APPLICABLE",  // spot crypto has no corporate actions
      receivedAt: new Date().toISOString(),
      bars,
    };
    cache.set(key, { at: Date.now(), body });
    return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
  } catch (e) {
    return fail(e?.name === "AbortError" ? "TIMEOUT" : "UNREACHABLE");
  } finally { clearTimeout(timer); }
}
