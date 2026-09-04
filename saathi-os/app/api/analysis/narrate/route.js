// Narrate a computed chart analysis (NEPSE or crypto).
//
// Safety shape that matters: the CLIENT SENDS ONLY {market, symbol}. The server
// recomputes the analysis, builds the prompt from its own facts, calls the governed
// model, and then VERIFIES the reply introduced no number the facts do not contain.
// A browser cannot inject a prompt, and a model cannot smuggle in a price.

import { NextResponse } from "next/server";
import { parseHistoryCsv, NEPSE_RESEARCH_SOURCE } from "@/lib/nepse/history";
import { computeIndicators } from "@/lib/nepse/indicators";
import { analyzeChart, narrationPrompt } from "@/lib/analysis/analyze";
import { gateNarration } from "@/lib/analysis/guard";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const NEPSE_BASE = "https://raw.githubusercontent.com/Aabishkar2/nepse-data/main/data/company-wise";
const CRYPTO_HOST = "data-api.binance.vision";
const CRYPTO_ALLOWED = new Set(["BTCUSDT", "ETHUSDT"]);
const SYMBOL_RE = /^[A-Z0-9]{1,12}$/;
const BACKEND = process.env.SAATHI_API_BASE || "http://127.0.0.1:8765";
const TIMEOUT_MS = 20_000;
const MAX_BYTES = 6_000_000;

const fail = (reason, extra = {}) =>
  NextResponse.json({ ok: false, reason, ...extra }, { headers: { "cache-control": "no-store" } });

async function barsFor(market, symbol, signal) {
  if (market === "crypto") {
    const r = await fetch(`https://${CRYPTO_HOST}/api/v3/klines?symbol=${symbol}&interval=1d&limit=500`,
      { headers: { accept: "application/json" }, signal, redirect: "error", cache: "no-store" });
    if (!r.ok) return null;
    const raw = JSON.parse(await r.text());
    const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };
    return raw.map((k) => ({
      date: new Date(k[0]).toISOString().slice(0, 10),
      open: num(k[1]), high: num(k[2]), low: num(k[3]), close: num(k[4]), volume: num(k[5]),
      trusted: { open: true, high: true, low: true, close: true, volume: true }, flags: [],
    })).filter((b) => b.close !== null);
  }
  const r = await fetch(`${NEPSE_BASE}/${symbol}.csv`,
    { headers: { accept: "text/csv" }, signal, redirect: "error", cache: "no-store" });
  if (!r.ok) return null;
  const text = await r.text();
  if (text.length > MAX_BYTES || /^\s*</.test(text)) return null;
  const { bars } = parseHistoryCsv(text, { symbol });
  return bars.length ? bars : null;
}

export async function POST(request) {
  let body;
  try { body = await request.json(); } catch { return fail("BAD_REQUEST"); }

  const market = String(body?.market || "nepse").toLowerCase();
  const symbol = String(body?.symbol || "").trim().toUpperCase();
  // A question is allowed to steer emphasis, but it is bounded and never becomes
  // the system prompt — that lives server-side in the backend endpoint.
  const question = String(body?.question || "").slice(0, 300);

  if (!SYMBOL_RE.test(symbol)) return fail("INVALID_SYMBOL");
  if (!["nepse", "crypto"].includes(market)) return fail("UNKNOWN_MARKET");
  if (market === "crypto" && !CRYPTO_ALLOWED.has(symbol)) return fail("SYMBOL_NOT_ALLOWED");

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const bars = await barsFor(market, symbol, ac.signal);
    if (!bars?.length) return fail("NO_BARS");

    const indicators = computeIndicators(bars, { instrument: symbol });
    const meta = market === "crypto"
      ? { instrument: symbol, source: CRYPTO_HOST, adjustment: "NOT_APPLICABLE", fieldTrust: { range: true, open: true } }
      : { instrument: symbol, source: NEPSE_RESEARCH_SOURCE.id, adjustment: NEPSE_RESEARCH_SOURCE.adjustment, fieldTrust: { range: true, open: false } };

    const analysis = analyzeChart(bars, indicators, meta);
    if (!analysis.ok) return fail(analysis.reason || "ANALYSIS_FAILED");

    const facts = narrationPrompt(analysis, question);
    if (!facts) return fail("NO_FACTS");

    // Narration calls a paid model, so the backend keeps it behind auth rather than
    // exposing a free LLM endpoint. Forward the operator's own session; an
    // unauthenticated caller gets a clear 401 and the computed analysis is unaffected.
    const auth = {};
    const cookie = request.headers.get("cookie");
    const bearer = request.headers.get("authorization");
    const platform = request.headers.get("x-platform-token");
    if (cookie) auth.cookie = cookie;
    if (bearer) auth.authorization = bearer;
    if (platform) auth["x-platform-token"] = platform;

    const res = await fetch(`${BACKEND}/api/v1/analysis/narrate`, {
      method: "POST",
      headers: { "content-type": "application/json", ...auth },
      body: JSON.stringify({ facts, question }),
      signal: ac.signal, cache: "no-store",
    });
    if (res.status === 401 || res.status === 403) return fail("NOT_SIGNED_IN");
    if (!res.ok) return fail(`BACKEND_${res.status}`);
    const out = await res.json();
    if (!out?.ok) return fail(out?.reason || "LLM_UNAVAILABLE", { detail: out?.detail });

    const text = String(out.text || "").trim();
    if (!text) return fail("EMPTY_NARRATION");

    // The control: verify the model added no number and no advice.
    const gate = gateNarration(text, facts);

    return NextResponse.json({
      ok: true,
      market, symbol,
      model: out.model || "",
      narration: gate.ok ? text : null,
      gate,
      // Withheld rather than shown when the guard trips — a narration that invents a
      // price is worse than no narration.
      withheld: !gate.ok,
      verdict: analysis.plan.verdict,
      bias: analysis.confluence.bias,
    }, { headers: { "cache-control": "no-store" } });
  } catch (e) {
    return fail(e?.name === "AbortError" ? "TIMEOUT" : "UNREACHABLE");
  } finally { clearTimeout(timer); }
}
