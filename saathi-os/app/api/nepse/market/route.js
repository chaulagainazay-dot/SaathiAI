// Market-wide aggregates from the daily archive (NEPSE-PARITY).
//
// The page this feeds previously rendered a HARDCODED index value, a hardcoded
// turnover figure and a sine-wave "index history". This route replaces the parts
// that can be computed from real data — breadth, gainers, losers, most-traded,
// sector performance — and deliberately supplies NO index: the archive is
// per-company, and an index synthesized from company prices would be a number
// nobody published. Absent stays absent.
//
// Bandwidth: only the last two closes of each company matter, so each file is
// fetched as a ~3 KB TAIL via a Range request rather than in full — ~1 MB across
// the whole market instead of ~31 MB. The header is read once from the archive in
// the same cycle and passed to the tail parser, so a column reorder upstream
// fails loudly instead of being silently misread.

import { NextResponse } from "next/server";
import { parseHistoryTail, NEPSE_RESEARCH_SOURCE } from "@/lib/nepse/history";
import { marketSummary, sessionChanges } from "@/lib/nepse/market";
import { STOCKS } from "@/lib/nepse/data";
import { sectorDirectory } from "@/lib/nepse/enrich";
import { resolveSector, DIRECTORY_STATE, stateBanner } from "@/lib/nepse/directory";
// Universe resolution lives in the shared server module so the market page, the
// indicator service and the scanner all measure the SAME set of companies. Two
// copies would drift, and "586 scanned" against "372 measured" is a contradiction
// a reader cannot resolve.
import { resolveUniverse } from "@/lib/nepse/archive.server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const RAW_HOST = "raw.githubusercontent.com";
const BASE = `https://${RAW_HOST}/Aabishkar2/nepse-data/main/data/company-wise`;
const HEADER_SYMBOL = "NABIL"; // any file; the archive shares one schema

const SYMBOL_RE = /^[A-Z0-9]{1,12}$/;
const CONCURRENCY = 8;
const TAIL_BYTES = 3000;      // ~30 daily rows — far more than the two we need
const HEADER_BYTES = 300;
const TIMEOUT_MS = 60_000;
const CACHE_MS = 30 * 60 * 1000;

/** The curated fallback: 24 symbols. Widened at request time where possible. */
const CURATED_SECTOR_OF = new Map(STOCKS.map((s) => [s.symbol, s.sector]));

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

async function fetchHeader(signal) {
  const res = await fetch(`${BASE}/${HEADER_SYMBOL}.csv`, {
    headers: { accept: "text/csv,text/plain", range: `bytes=0-${HEADER_BYTES}` },
    signal, redirect: "error", cache: "no-store",
  });
  if (!res.ok) return null;
  const text = await res.text();
  const first = text.split(/\r?\n/)[0];
  return /published_date/i.test(first || "") ? first : null;
}

export async function GET(request) {
  if (cache.body && Date.now() - cache.at < CACHE_MS) {
    return NextResponse.json(cache.body, { headers: { "cache-control": "no-store" } });
  }

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const [resolved, header] = await Promise.all([resolveUniverse(ac.signal), fetchHeader(ac.signal)]);
    // Without the real header the tails cannot be parsed safely, and without any
    // universe there is nothing to measure. Either way: say so, compute nothing.
    if (!resolved || !header) {
      return NextResponse.json(
        { available: false, reason: !header ? "HEADER_UNAVAILABLE" : "UNIVERSE_UNAVAILABLE" },
        { status: 503, headers: { "cache-control": "no-store" } },
      );
    }
    const universe = resolved.symbols;

    // Tiered: live enrichment, else the durable last-known-good, else the 24-symbol
    // curated list. A restart no longer silently drops this from 183 to 24 — the
    // cache carries it, and whichever tier answered is reported below.
    const dir = await sectorDirectory(request);
    const tiers = [
      { state: dir.state, sectors: dir.sectors, verifiedAt: dir.verifiedAt, source: dir.source },
      { state: DIRECTORY_STATE.INCOMPLETE_FALLBACK, sectors: CURATED_SECTOR_OF, source: "built-in curated list" },
    ];
    // A symbol nobody classifies stays null here so the aggregate treats it as
    // Unclassified — resolveSector's em dash is for display, not for grouping.
    const sectorOf = (sym) => resolveSector(sym, tiers).sector;

    const entries = await pooled(universe, async (sym) => {
      const res = await fetch(`${BASE}/${sym}.csv`, {
        headers: { accept: "text/csv,text/plain", range: `bytes=-${TAIL_BYTES}` },
        signal: ac.signal, redirect: "error", cache: "no-store",
      });
      // 206 is the expected answer; a 200 means the whole (small) file came back.
      if (!res.ok) return null;
      const text = await res.text();
      if (/^\s*</.test(text)) return null;
      const { bars } = parseHistoryTail(text, header, { symbol: sym });
      if (bars.length < 2) return null;
      return { symbol: sym, sector: sectorOf(sym), bars };
    });

    const summary = marketSummary(entries, { listedTotal: universe.length, limit: 10 });
    // The heatmap sizes every tile by turnover, so it needs the whole measured
    // set, not the top-10 slices `marketSummary` returns. Five fields per symbol
    // is a fraction of the bars they were derived from, and computing the layout
    // here instead would fix the tile geometry to a server-side pixel size that
    // no browser actually has.
    const sessionRows = sessionChanges(entries).rows.map((r) => ({
      symbol: r.symbol, sector: r.sector, changePct: r.changePct,
      turnover: r.turnover, volume: r.volume,
    }));
    const body = {
      available: true,
      source: NEPSE_RESEARCH_SOURCE.id,
      classification: NEPSE_RESEARCH_SOURCE.classification,
      adjustment: NEPSE_RESEARCH_SOURCE.adjustment,
      computedAt: new Date().toISOString(),
      // No index. The archive is per-company; an index built from these prices
      // would be ours, not NEPSE's, and would read as the published one.
      index: null,
      indexReason: "NO_INDEX_SOURCE",
      sectorsKnownFor: entries.filter((e) => e.sector).length,
      sectorDirectory: stateBanner(dir.state, {
        verifiedAt: dir.verifiedAt, nowMs: Date.now(),
        entries: dir.sectors.size, expected: universe.length,
      }),
      sectorSource: {
        id: dir.source || "built-in curated list",
        state: dir.state,
        mapped: dir.sectors.size || CURATED_SECTOR_OF.size,
        verifiedAt: dir.verifiedAt,
        freshness: dir.freshness,
      },
      universeVia: resolved.via,
      // LISTED = every listed company; TRADED = only what changed hands that
      // session; CURATED = this build's own short list. The page says which.
      universeKind: resolved.kind,
      ...summary,
      rows: sessionRows,
    };
    cache = { at: Date.now(), body };
    return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json(
      { available: false, reason: "ARCHIVE_UNREACHABLE" },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  } finally {
    clearTimeout(timer);
  }
}
