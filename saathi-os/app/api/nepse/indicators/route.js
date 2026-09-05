// Batch indicator service for the screener (NEPSE-HIST-2 Phase 10).
//
// Indicators are computed HERE, once, from the canonical history — never inside a
// React component and never twice. The browser receives typed results it can only
// render, so the screener and the stock detail page cannot disagree.

import { NextResponse } from "next/server";
import { parseHistoryCsv, NEPSE_RESEARCH_SOURCE } from "@/lib/nepse/history";
import { computeIndicators } from "@/lib/nepse/indicators";
import { STOCKS } from "@/lib/nepse/data";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HOST = "raw.githubusercontent.com";
const BASE = `https://${HOST}/Aabishkar2/nepse-data/main/data/company-wise`;
const SYMBOL_RE = /^[A-Z0-9]{1,12}$/;
const CONCURRENCY = 4;
const TIMEOUT_MS = 20_000;
const MAX_BYTES = 6_000_000;
const CACHE_MS = 10 * 60 * 1000;

let cache = { at: 0, body: null };

async function pooled(items, worker, limit = CONCURRENCY) {
  const out = [];
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (i < items.length) {
      const idx = i++;
      out[idx] = await worker(items[idx]).catch(() => null);
    }
  }));
  return out.filter(Boolean);
}

export async function GET() {
  if (cache.body && Date.now() - cache.at < CACHE_MS) {
    return NextResponse.json(cache.body, { headers: { "cache-control": "no-store" } });
  }
  const symbols = STOCKS.map((s) => s.symbol).filter((s) => SYMBOL_RE.test(s));
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const rows = await pooled(symbols, async (sym) => {
      const res = await fetch(`${BASE}/${sym}.csv`, {
        headers: { accept: "text/csv,text/plain" },
        signal: ac.signal, redirect: "error", cache: "no-store",
      });
      if (!res.ok) return null;
      const text = await res.text();
      if (text.length > MAX_BYTES || /^\s*</.test(text)) return null;
      const { bars } = parseHistoryCsv(text, { symbol: sym });
      if (!bars.length) return null;
      const ind = computeIndicators(bars, { instrument: sym });
      // ship only what the screener renders
      return [sym, {
        rsi: { value: ind.rsi.value, status: ind.rsi.status },
        macd: { value: ind.macd.value ? ind.macd.value.histogram : null, status: ind.macd.status },
        bollinger: { value: ind.bollinger.value ? ind.bollinger.value.percentB : null, status: ind.bollinger.status },
        atr: { value: ind.atr.value, status: ind.atr.status },
        observations: ind.rsi.observations,
        lastDate: ind.rsi.asOf,
      }];
    });
    const body = {
      source: NEPSE_RESEARCH_SOURCE.id,
      classification: NEPSE_RESEARCH_SOURCE.classification,
      adjustment: NEPSE_RESEARCH_SOURCE.adjustment,
      computedAt: new Date().toISOString(),
      covered: rows.length,
      requested: symbols.length,
      indicators: Object.fromEntries(rows),
    };
    cache = { at: Date.now(), body };
    return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json(
      { source: NEPSE_RESEARCH_SOURCE.id, indicators: {}, covered: 0, reason: "UNREACHABLE" },
      { headers: { "cache-control": "no-store" } });
  } finally { clearTimeout(timer); }
}
