// Batch indicator service for the screener (NEPSE-HIST-2 Phase 10).
//
// Indicators are computed HERE, once, from the canonical history — never inside a
// React component and never twice. The browser receives typed results it can only
// render, so the screener and the stock detail page cannot disagree.
//
// The archive walk now also yields SESSION COUNTS PER DAY, which is what the
// trading calendar is derived from. It is the same fetch either way; the counts
// are two integers per day rather than the several megabytes of bars a browser
// would need to re-derive them.

import { NextResponse } from "next/server";
import { NEPSE_RESEARCH_SOURCE } from "@/lib/nepse/history";
import { computeIndicators } from "@/lib/nepse/indicators";
import { sessionContext } from "@/lib/nepse/session";
import { STOCKS } from "@/lib/nepse/data";
import { readArchive, resolveUniverse, withTimeout } from "@/lib/nepse/archive.server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const CACHE_MS = 10 * 60 * 1000;

let cache = { at: 0, body: null };

/** date -> number of instruments that reported a bar. Evidence for the calendar. */
function sessionCounts(entries) {
  const counts = {};
  for (const e of entries) {
    for (const b of e.bars || []) {
      if (!b?.date) continue;
      const d = String(b.date).slice(0, 10);
      counts[d] = (counts[d] || 0) + 1;
    }
  }
  return counts;
}

export async function GET() {
  if (cache.body && Date.now() - cache.at < CACHE_MS) {
    return NextResponse.json(cache.body, { headers: { "cache-control": "no-store" } });
  }
  const { signal, done } = withTimeout(180_000);
  try {
    // The listed universe, falling back to the curated list only when no listing
    // source answers — and reporting which one it got, because the trading
    // calendar derived downstream is only as dense as this set.
    const resolved = await resolveUniverse(signal);
    const symbols = resolved?.symbols || STOCKS.map((s) => s.symbol);
    const { entries, requested, covered } = await readArchive(symbols, { signal });
    const rows = entries.map((e) => {
      const ind = computeIndicators(e.bars, { instrument: e.symbol });
      const ctx = sessionContext(e.bars);
      // ship only what the screener renders
      return [e.symbol, {
        session: ctx,
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
      covered,
      requested,
      universeKind: resolved?.kind ?? "CURATED",
      universeVia: resolved?.via ?? "built-in curated list",
      indicators: Object.fromEntries(rows),
      // Session evidence for the trading calendar. Named for what it is — a count
      // of instruments that reported, never a claim the exchange was open.
      sessions: sessionCounts(entries),
    };
    cache = { at: Date.now(), body };
    return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json(
      { source: NEPSE_RESEARCH_SOURCE.id, indicators: {}, covered: 0, sessions: {}, reason: "UNREACHABLE" },
      { headers: { "cache-control": "no-store" } });
  } finally { done(); }
}
