// NEPSE index and sub-indices (NEPSE-PARITY).
//
// The published index the per-company archive cannot provide. Files are one per
// TRADING day, so a missing file means the market was shut, not that the fetch
// failed — the walk-back below treats 404 as "no session" and keeps going until it
// has collected enough real sessions or exhausts its calendar budget.

import { NextResponse } from "next/server";
import {
  parseIndexCsv, indexChanges, sectorIndices, marketIndices, indexSeries,
  pickIndex, MAIN_INDEX, NEPSE_INDEX_SOURCE, KNOWN_MISSING_SECTORS,
} from "@/lib/nepse/indices";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HOST = "raw.githubusercontent.com";
const BASE = `https://${HOST}/socrateai-official/nepse-open-data/main/ohlc_index`;

const SESSIONS = 120;          // trading sessions targeted for the chart
const CALENDAR_BUDGET = 200;   // ~5 non-trading days in 7, plus holidays
const CONCURRENCY = 8;
const TIMEOUT_MS = 45_000;
const MAX_BYTES = 200_000;
const CACHE_MS = 30 * 60 * 1000;

let cache = { at: 0, body: null };

const isoDaysBack = (n) => {
  const out = [];
  const today = Date.now();
  for (let i = 0; i < n; i += 1) out.push(new Date(today - i * 86400000).toISOString().slice(0, 10));
  return out;
};

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
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const days = await pooled(isoDaysBack(CALENDAR_BUDGET), async (day) => {
      const res = await fetch(`${BASE}/adj_${day}.csv`, {
        headers: { accept: "text/csv,text/plain" },
        signal: ac.signal, redirect: "error", cache: "no-store",
      });
      if (!res.ok) return null;              // no file = no trading session
      const text = await res.text();
      if (text.length > MAX_BYTES || /^\s*</.test(text)) return null;
      const parsed = parseIndexCsv(text, { date: day });
      return parsed.rows.length ? { date: parsed.date || day, rows: parsed.rows, conflicts: parsed.conflicts } : null;
    });

    if (days.length < 2) {
      return NextResponse.json(
        { available: false, reason: days.length ? "NO_PRIOR_SESSION" : "INDEX_SOURCE_UNREACHABLE" },
        { status: 503, headers: { "cache-control": "no-store" } },
      );
    }

    days.sort((a, b) => a.date.localeCompare(b.date));
    const latest = days[days.length - 1];
    const prior = days[days.length - 2];
    const changes = indexChanges(latest.rows, prior.rows);
    const main = changes.find((r) => r.index === MAIN_INDEX) || null;

    const body = {
      available: true,
      source: NEPSE_INDEX_SOURCE.id,
      sourceLabel: NEPSE_INDEX_SOURCE.label,
      license: NEPSE_INDEX_SOURCE.license,
      classification: NEPSE_INDEX_SOURCE.classification,
      adjustment: NEPSE_INDEX_SOURCE.adjustment,
      computedAt: new Date().toISOString(),
      asOf: latest.date,
      priorDate: prior.date,
      index: main,
      // The NEPSE row's volume column is the session's total traded VALUE — the
      // published turnover, which is not the same quantity as a sum over whichever
      // companies another archive happens to carry.
      turnover: main && main.volume ? main.volume : null,
      markets: marketIndices(changes),
      sectors: sectorIndices(changes),
      missingSectors: KNOWN_MISSING_SECTORS,
      series: indexSeries(days.slice(-SESSIONS), MAIN_INDEX),
      sessions: days.length,
      // Upstream repeats rows in some files, occasionally with different values.
      conflicts: [...latest.conflicts, ...prior.conflicts],
    };
    cache = { at: Date.now(), body };
    return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json(
      { available: false, reason: "INDEX_SOURCE_UNREACHABLE" },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  } finally {
    clearTimeout(timer);
  }
}
