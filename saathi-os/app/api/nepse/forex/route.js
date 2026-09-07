// Nepal Rastra Bank foreign-exchange rates.
//
// Fetched SERVER-SIDE and only from NRB's own host: this is the published rate,
// and a page that quoted one from an aggregator would be quoting a copy whose
// staleness nobody can see. `isAllowedForexUrl` is asserted against the URL that
// is actually about to be requested, so a change to the builder cannot widen the
// host without failing here.
//
// Every failure keeps its own name. UNREACHABLE (the network), MALFORMED (the
// shape moved), EMPTY (no publication for that date) and HOST_NOT_ALLOWED are
// four different things, and collapsing them into "no data" would hide the one —
// MALFORMED — that means our parser is now wrong about NRB.

import { NextResponse } from "next/server";
import {
  FOREX_STATE, bullionRates, buildRatesUrl, isAllowedForexUrl, parseNrbRates,
} from "@/lib/nepse/forex";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const CACHE_MS = 30 * 60 * 1000; // NRB publishes once a day
const TIMEOUT_MS = 12_000;
const MAX_BYTES = 2_000_000;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

const cache = new Map();

export async function GET(request) {
  const raw = new URL(request.url).searchParams.get("date");
  // An unparseable date is refused rather than silently replaced with today:
  // the reader asked about a specific day and would be shown a different one.
  if (raw !== null && !DATE_RE.test(raw)) {
    return NextResponse.json(
      { available: false, state: FOREX_STATE.MALFORMED, detail: "date must be YYYY-MM-DD" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }
  const date = raw || new Date().toISOString().slice(0, 10);

  const hit = cache.get(date);
  if (hit && Date.now() - hit.at < CACHE_MS) {
    return NextResponse.json(hit.body, { headers: { "cache-control": "no-store" } });
  }

  const url = buildRatesUrl({ date });
  if (!isAllowedForexUrl(url)) {
    return NextResponse.json(
      { available: false, state: FOREX_STATE.HOST_NOT_ALLOWED, detail: "rates URL is not on NRB's host" },
      { status: 502, headers: { "cache-control": "no-store" } },
    );
  }

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      headers: { accept: "application/json" },
      signal: ac.signal, redirect: "error", cache: "no-store",
    });
    if (!res.ok) {
      return NextResponse.json(
        { available: false, state: FOREX_STATE.UNREACHABLE, detail: `NRB answered ${res.status}` },
        { status: 502, headers: { "cache-control": "no-store" } },
      );
    }
    const text = await res.text();
    if (text.length > MAX_BYTES) {
      return NextResponse.json(
        { available: false, state: FOREX_STATE.MALFORMED, detail: "response too large to be a rate table" },
        { status: 502, headers: { "cache-control": "no-store" } },
      );
    }
    let payload;
    try { payload = JSON.parse(text); } catch {
      return NextResponse.json(
        { available: false, state: FOREX_STATE.MALFORMED, detail: "response was not JSON" },
        { status: 502, headers: { "cache-control": "no-store" } },
      );
    }

    const parsed = parseNrbRates(payload);
    const body = {
      available: parsed.state === FOREX_STATE.OK,
      requestedDate: date,
      ...parsed,
      // Carried alongside so the page can say why there is no gold price rather
      // than leaving a blank panel that reads as "gold did not move".
      bullion: bullionRates(),
      fetchedAt: new Date().toISOString(),
    };
    if (body.available) cache.set(date, { at: Date.now(), body });
    return NextResponse.json(body, {
      status: body.available ? 200 : 502,
      headers: { "cache-control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { available: false, state: FOREX_STATE.UNREACHABLE, detail: "NRB did not answer" },
      { status: 502, headers: { "cache-control": "no-store" } },
    );
  } finally { clearTimeout(timer); }
}
