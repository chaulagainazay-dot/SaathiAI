// Market scanner service.
//
// A scan is NOT a second matching engine. Both entry points below build the same
// reading universe and hand it to `runScan`, which evaluates through the shared
// three-valued evaluator in lib/strategy/conditions.js. A built-in scan and a
// strategy the user saved therefore travel identical code; there is no path where
// "crosses above" means two different things.
//
// WHAT IS RETURNED IS A COUNT OF THREE THINGS, NOT TWO. Symbols the scan could
// not decide are reported as `unknown` with the blocker that stopped them. Folding
// them into rejections would let the page claim it read the whole exchange when it
// read the part with enough history.

import { NextResponse } from "next/server";
import { STOCKS } from "@/lib/nepse/data";
import { NEPSE_RESEARCH_SOURCE } from "@/lib/nepse/history";
import { sectorDirectory } from "@/lib/nepse/enrich";
import { DIRECTORY_STATE, resolveSector } from "@/lib/nepse/directory";
import { readArchive, resolveUniverse, withTimeout } from "@/lib/nepse/archive.server";
import { scanUniverseRow } from "@/lib/nepse/readings";
import { SCAN_LIBRARY, scanById, runScan } from "@/lib/nepse/scanners";
import { validateStrategy } from "@/lib/strategy/conditions";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const CACHE_MS = 10 * 60 * 1000;
// A saved strategy is a small tree. Anything larger is not one, and parsing it
// would be work done on behalf of whoever sent it.
const MAX_BODY_BYTES = 32_000;

let universeCache = { at: 0, rows: null, requested: 0, covered: 0, kind: null, via: null };

// The archive walk is minutes of work for the whole listed universe, so it is
// generous; the per-symbol reads inside it carry their own bounds.
const UNIVERSE_TIMEOUT_MS = 180_000;

async function universe() {
  if (universeCache.rows && Date.now() - universeCache.at < CACHE_MS) return universeCache;
  const { signal, done } = withTimeout(UNIVERSE_TIMEOUT_MS);
  try {
    // The LISTED universe, the same one the market page measures — not this
    // build's 24-symbol curated list. A scan of 24 companies reported as a scan
    // is a scan of 4% of the exchange, and the reader has no way to tell.
    const resolved = await resolveUniverse(signal);
    if (!resolved) return { rows: null, requested: 0, covered: 0, kind: null, via: null };
    const { entries, requested, covered } = await readArchive(resolved.symbols, { signal });
    const rows = entries.map((e) => scanUniverseRow(e.symbol, e.bars));
    universeCache = {
      at: Date.now(), rows, requested, covered,
      kind: resolved.kind, via: resolved.via,
    };
    return universeCache;
  } finally { done(); }
}

const CURATED_SECTOR_OF = new Map(STOCKS.map((s) => [s.symbol, s.sector]));

/**
 * Sector lookup on the same tiers the market page uses.
 *
 * Reading sectors out of the 24-symbol curated list alone left an em dash beside
 * almost every match — which reads as "this company has no sector" rather than
 * "this build did not look it up".
 */
async function sectorLookup(request) {
  const dir = await sectorDirectory(request).catch(() => null);
  const tiers = [
    ...(dir ? [{ state: dir.state, sectors: dir.sectors, verifiedAt: dir.verifiedAt, source: dir.source }] : []),
    { state: DIRECTORY_STATE.INCOMPLETE_FALLBACK, sectors: CURATED_SECTOR_OF, source: "built-in curated list" },
  ];
  return {
    of: (sym) => resolveSector(sym, tiers).sector ?? null,
    // Reported so a column of dashes can be explained. "No sector" and "we did
    // not look it up" are different claims and they look identical in a table.
    state: dir?.state ?? DIRECTORY_STATE.INCOMPLETE_FALLBACK,
    source: dir?.source || "built-in curated list",
    mapped: dir?.sectors?.size || CURATED_SECTOR_OF.size,
  };
}

/** Trim a scan result to what a table renders — never the whole reading map. */
function present(result, uni, sectors) {
  return {
    strategy: result.strategy,
    counts: result.counts,
    complete: result.complete,
    matched: result.matched.map((m) => ({
      symbol: m.symbol,
      sector: sectors.of(m.symbol),
      // `observations` counts OPERANDS the evaluator resolved, which is a fact
      // about the strategy tree, not the data — every row read "1" under a
      // heading that promised sessions. `readingObservations` is the smallest
      // session count behind any reading the decision actually used.
      sessions: m.readingObservations ?? null,
    })),
    // The blocker, not just the count: "42 unreadable" is a number, "42 have no
    // 200-day average yet" is a reason someone can act on.
    unknown: result.unknown.map((u) => ({
      symbol: u.symbol,
      status: u.status,
      // The blocker's own wording — `reason`, not `message`. Reading the wrong
      // key here produced a column of nulls that looked like "no reason given".
      reason: u.blockers?.[0]?.reason ?? null,
      reading: u.blockers?.[0]?.reading ?? null,
    })),
    coverage: {
      requested: uni.requested,
      archived: uni.covered,
      scanned: result.counts.scanned,
      // WHICH universe was scanned, not just how much of it. LISTED is every
      // listed company; TRADED is what changed hands that session; CURATED is
      // this build's own short list. "Full coverage" of CURATED is 24 companies.
      universeKind: uni.kind,
      universeVia: uni.via,
      complete: uni.covered >= uni.requested,
      isFullUniverse: uni.kind === "LISTED" && uni.covered >= uni.requested,
    },
    sectorDirectory: { state: sectors.state, source: sectors.source, mapped: sectors.mapped },
    source: NEPSE_RESEARCH_SOURCE.id,
    adjustment: NEPSE_RESEARCH_SOURCE.adjustment,
    computedAt: new Date().toISOString(),
  };
}

export async function GET(request) {
  const id = new URL(request.url).searchParams.get("id");
  if (!id) {
    return NextResponse.json(
      { library: SCAN_LIBRARY.map((s) => ({ id: s.id, name: s.name, description: s.description ?? null })) },
      { headers: { "cache-control": "no-store" } },
    );
  }
  const scan = scanById(id);
  if (!scan) {
    return NextResponse.json({ available: false, reason: "UNKNOWN_SCAN" },
      { status: 404, headers: { "cache-control": "no-store" } });
  }
  try {
    const [uni, sectors] = await Promise.all([universe(), sectorLookup(request)]);
    if (!uni.rows?.length) {
      return NextResponse.json({ available: false, reason: "ARCHIVE_UNREACHABLE" },
        { status: 503, headers: { "cache-control": "no-store" } });
    }
    return NextResponse.json(
      { available: true, id: scan.id, ...present(runScan(scan, uni.rows), uni, sectors) },
      { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ available: false, reason: "ARCHIVE_UNREACHABLE" },
      { status: 503, headers: { "cache-control": "no-store" } });
  }
}

export async function POST(request) {
  let strategy;
  try {
    const text = await request.text();
    if (text.length > MAX_BODY_BYTES) {
      return NextResponse.json({ available: false, reason: "STRATEGY_TOO_LARGE" },
        { status: 413, headers: { "cache-control": "no-store" } });
    }
    strategy = JSON.parse(text);
  } catch {
    return NextResponse.json({ available: false, reason: "MALFORMED_BODY" },
      { status: 400, headers: { "cache-control": "no-store" } });
  }

  // Validated BEFORE the archive is touched. An unusable tree does not justify
  // 586 network reads, and the caller gets the actual validation errors rather
  // than an empty result set they would read as "nothing matched".
  const validation = validateStrategy(strategy);
  if (!validation.valid) {
    return NextResponse.json(
      { available: false, reason: "INVALID_STRATEGY", errors: validation.errors },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }

  try {
    const [uni, sectors] = await Promise.all([universe(), sectorLookup(request)]);
    if (!uni.rows?.length) {
      return NextResponse.json({ available: false, reason: "ARCHIVE_UNREACHABLE" },
        { status: 503, headers: { "cache-control": "no-store" } });
    }
    return NextResponse.json(
      { available: true, id: strategy.id ?? null, ...present(runScan(strategy, uni.rows), uni, sectors) },
      { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ available: false, reason: "ARCHIVE_UNREACHABLE" },
      { status: 503, headers: { "cache-control": "no-store" } });
  }
}
