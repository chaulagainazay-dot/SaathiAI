// Floorsheet — the exchange's record of who traded what (NEPSE-PARITY).
//
// Serves the Brokers surface, which previously ran on quantities generated from a
// symbol's character codes. Files are one per trading day and ~2.4 MB, so the walk
// back stops at the FIRST day present rather than collecting a window.

import { NextResponse } from "next/server";
import { parseFloorsheet, brokerActivity, floorsheetTotals, symbolActivity } from "@/lib/nepse/floorsheet";
import { NEPSE_INDEX_SOURCE } from "@/lib/nepse/indices";
import { BROKERS } from "@/lib/nepse/data";
import { brokerNames } from "@/lib/nepse/enrich";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HOST = "raw.githubusercontent.com";
const BASE = `https://${HOST}/socrateai-official/nepse-open-data/main/floorsheet`;

const SYMBOL_RE = /^[A-Z0-9/]{1,16}$/;
const CALENDAR_BUDGET = 12;    // a long holiday, not a search of the archive
const TIMEOUT_MS = 60_000;
const MAX_BYTES = 40_000_000;
const CACHE_MS = 30 * 60 * 1000;

/**
 * Last-resort names. This hardcoded list was also WRONG: it labelled broker 45
 * "Kumari Securities" when 45 is Imperial Securities, and 34 "Online Securities"
 * when that is 49 — wrong firm names attached to real money flows. The live list
 * from ShareSansar is preferred whenever it can be fetched.
 */
const FALLBACK_NAMES = new Map(BROKERS.map((b) => [b.code, b.name]));

let cache = { at: 0, date: null, trades: null };

async function loadLatest(signal) {
  if (cache.trades && Date.now() - cache.at < CACHE_MS) return cache;
  const today = Date.now();
  for (let i = 0; i < CALENDAR_BUDGET; i += 1) {
    const day = new Date(today - i * 86400000).toISOString().slice(0, 10);
    const res = await fetch(`${BASE}/floorsheet_${day}.csv`, {
      headers: { accept: "text/csv,text/plain" },
      signal, redirect: "error", cache: "no-store",
    });
    if (!res.ok) continue;                 // no file = no trading session
    const text = await res.text();
    if (text.length > MAX_BYTES || /^\s*</.test(text)) continue;
    const { trades, date, rejected } = parseFloorsheet(text);
    if (!trades.length) continue;
    cache = { at: Date.now(), date: date || day, trades, rejected };
    return cache;
  }
  return null;
}

export async function GET(request) {
  const raw = new URL(request.url).searchParams.get("symbol");
  const symbol = raw ? raw.trim().toUpperCase() : null;
  if (symbol && !SYMBOL_RE.test(symbol)) {
    return NextResponse.json({ available: false, reason: "BAD_SYMBOL" }, { status: 400 });
  }

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const loaded = await loadLatest(ac.signal);
    if (!loaded) {
      return NextResponse.json(
        { available: false, reason: "FLOORSHEET_UNAVAILABLE" },
        { status: 503, headers: { "cache-control": "no-store" } },
      );
    }

    const scoped = symbol ? loaded.trades.filter((t) => t.symbol === symbol) : loaded.trades;
    // Optional: real names for all 92 brokers. Absent, codes stay codes.
    const live = await brokerNames(request);
    const names = live?.names || FALLBACK_NAMES;
    // A symbol that did not trade gets an explicit empty session, not an error and
    // certainly not another symbol's activity.
    const body = {
      available: true,
      source: NEPSE_INDEX_SOURCE.id,
      license: NEPSE_INDEX_SOURCE.license,
      classification: NEPSE_INDEX_SOURCE.classification,
      computedAt: new Date().toISOString(),
      asOf: loaded.date,
      symbol,
      traded: scoped.length > 0,
      totals: floorsheetTotals(scoped),
      brokers: brokerActivity(scoped, { names }).slice(0, 40),
      topSymbols: symbol ? [] : symbolActivity(loaded.trades, 12),
      rejectedRows: loaded.rejected ?? 0,
      namedBrokers: names.size,
      namesFrom: live ? live.source : "built-in fallback list (incomplete, and known to contain errors)",
    };
    return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json(
      { available: false, reason: "FLOORSHEET_UNAVAILABLE" },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  } finally {
    clearTimeout(timer);
  }
}
