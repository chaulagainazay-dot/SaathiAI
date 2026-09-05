// Unified chart analysis — one engine, both markets (NEPSE and crypto).
//
// Computes the complete analysis server-side from real bars and returns a typed
// bundle. The browser renders it; a language model may narrate it via
// narrationPrompt(); neither may add a number the engine did not derive.

import { NextResponse } from "next/server";
import { parseHistoryCsv, NEPSE_RESEARCH_SOURCE } from "@/lib/nepse/history";
import { computeIndicators } from "@/lib/nepse/indicators";
import { analyzeChart, narrationPrompt } from "@/lib/analysis/analyze";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const NEPSE_HOST = "raw.githubusercontent.com";
const NEPSE_BASE = `https://${NEPSE_HOST}/Aabishkar2/nepse-data/main/data/company-wise`;
const CRYPTO_HOST = "data-api.binance.vision";
const CRYPTO_ALLOWED = new Set(["BTCUSDT", "ETHUSDT"]);
const SYMBOL_RE = /^[A-Z0-9]{1,12}$/;
const TIMEOUT_MS = 15_000;
const MAX_BYTES = 6_000_000;
const CACHE_MS = 5 * 60 * 1000;

const cache = new Map();
const fail = (reason) => NextResponse.json({ ok: false, reason }, { headers: { "cache-control": "no-store" } });

async function nepseBars(symbol, signal) {
  const res = await fetch(`${NEPSE_BASE}/${symbol}.csv`, {
    headers: { accept: "text/csv" }, signal, redirect: "error", cache: "no-store",
  });
  if (!res.ok) return null;
  const text = await res.text();
  if (text.length > MAX_BYTES || /^\s*</.test(text)) return null;
  const { bars } = parseHistoryCsv(text, { symbol });
  return bars.length ? bars : null;
}

async function cryptoBars(symbol, signal) {
  const res = await fetch(
    `https://${CRYPTO_HOST}/api/v3/klines?symbol=${symbol}&interval=1d&limit=500`,
    { headers: { accept: "application/json" }, signal, redirect: "error", cache: "no-store" },
  );
  if (!res.ok) return null;
  const text = await res.text();
  if (text.length > MAX_BYTES) return null;
  let raw;
  try { raw = JSON.parse(text); } catch { return null; }
  if (!Array.isArray(raw) || !raw.length) return null;
  const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };
  return raw.map((k) => ({
    date: new Date(k[0]).toISOString().slice(0, 10),
    open: num(k[1]), high: num(k[2]), low: num(k[3]), close: num(k[4]), volume: num(k[5]),
    trusted: { open: true, high: true, low: true, close: true, volume: true },
    flags: [],
  })).filter((b) => b.close !== null);
}

export async function GET(request) {
  const q = new URL(request.url).searchParams;
  const market = (q.get("market") || "nepse").toLowerCase();
  const symbol = (q.get("symbol") || "").trim().toUpperCase();
  const wantPrompt = q.get("prompt") === "1";
  if (!SYMBOL_RE.test(symbol)) return fail("INVALID_SYMBOL");
  if (market === "crypto" && !CRYPTO_ALLOWED.has(symbol)) return fail("SYMBOL_NOT_ALLOWED");
  if (!["nepse", "crypto"].includes(market)) return fail("UNKNOWN_MARKET");

  const key = `${market}:${symbol}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_MS) {
    return NextResponse.json(hit.body, { headers: { "cache-control": "no-store" } });
  }

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const bars = market === "crypto" ? await cryptoBars(symbol, ac.signal) : await nepseBars(symbol, ac.signal);
    if (!bars || !bars.length) return fail("NO_BARS");

    const indicators = computeIndicators(bars, { instrument: symbol });
    const meta = market === "crypto"
      ? { instrument: symbol, source: CRYPTO_HOST, adjustment: "NOT_APPLICABLE",
          fieldTrust: { range: true, open: true, volume: true } }
      : { instrument: symbol, source: NEPSE_RESEARCH_SOURCE.id, adjustment: NEPSE_RESEARCH_SOURCE.adjustment,
          fieldTrust: { range: true, open: false, volume: true } };

    const analysis = analyzeChart(bars, indicators, meta);
    const body = {
      ok: analysis.ok, market, symbol, analysis,
      ...(wantPrompt ? { narrationPrompt: narrationPrompt(analysis) } : {}),
    };
    cache.set(key, { at: Date.now(), body });
    return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
  } catch (e) {
    return fail(e?.name === "AbortError" ? "TIMEOUT" : "UNREACHABLE");
  } finally { clearTimeout(timer); }
}
