// ShareSansar extraction (NEPSE-PARITY).
//
// Drives the GOVERNED browser twice per page — once for the header row, once for
// the data rows — and hands both to a typed extractor that refuses to parse a
// layout it does not recognise. The header fetch is not optional: without it the
// extractor would be parsing by position on trust, which is the failure mode this
// whole path exists to avoid.
//
// ShareSansar must be allowlisted on the backend (SAATHI_BROWSER_ALLOWED_DOMAINS)
// before any of this returns data. Deny-by-default is not bypassed here.

import { NextResponse } from "next/server";
import { SHARESANSAR_PAGES, parseTodayPrices, parseProposedDividends } from "@/lib/extract/sharesansar";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const BACKEND = process.env.SAATHI_API_BASE || "http://127.0.0.1:8765";
const TIMEOUT_MS = 120_000;
const CACHE_MS = 30 * 60 * 1000;

const DATASETS = {
  prices: { page: SHARESANSAR_PAGES.todayPrices, parse: parseTodayPrices },
  dividends: { page: SHARESANSAR_PAGES.proposedDividends, parse: parseProposedDividends },
};

const cache = new Map();

async function extract(url, selector, headers, signal) {
  const res = await fetch(`${BACKEND}/api/v1/browser/fetch`, {
    method: "POST", headers, signal, cache: "no-store",
    body: JSON.stringify({ url, action: "extract", selector, timeout: 50, actor: "user:saathios-extract" }),
  });
  if (!res.ok) return { ok: false, status: res.status };
  return res.json();
}

export async function GET(request) {
  const which = new URL(request.url).searchParams.get("dataset") || "prices";
  const spec = DATASETS[which];
  if (!spec) {
    return NextResponse.json(
      { available: false, reason: "UNKNOWN_DATASET", datasets: Object.keys(DATASETS) },
      { status: 400 },
    );
  }

  const hit = cache.get(which);
  if (hit && Date.now() - hit.at < CACHE_MS) {
    return NextResponse.json(hit.body, { headers: { "cache-control": "no-store" } });
  }

  const headers = { "content-type": "application/json" };
  const cookie = request.headers.get("cookie");
  const bearer = request.headers.get("authorization");
  if (cookie) headers.cookie = cookie;
  if (bearer) headers.authorization = bearer;

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    // Headers first: if the layout has drifted there is no point fetching rows.
    const head = await extract(spec.page.url, spec.page.headerSelector, headers, ac.signal);
    if (!head?.ok) {
      return NextResponse.json(
        { available: false, reason: head?.status === 401 ? "NOT_SIGNED_IN"
            : head?.failure_category || "BROWSER_DENIED", url: spec.page.url },
        { status: 503, headers: { "cache-control": "no-store" } },
      );
    }
    const body = await extract(spec.page.url, spec.page.rowSelector, headers, ac.signal);
    if (!body?.ok) {
      return NextResponse.json(
        { available: false, reason: body?.failure_category || "BROWSER_DENIED", url: spec.page.url },
        { status: 503, headers: { "cache-control": "no-store" } },
      );
    }

    const parsed = spec.parse(body.content || "", head.content || "", { title: body.page_title || "" });
    if (!parsed.ok) {
      // A layout change is reported as itself, never as an empty dataset.
      return NextResponse.json(
        {
          available: false, reason: parsed.reason, detail: parsed.detail,
          url: spec.page.url, source: parsed.source,
          message: "ShareSansar changed this table's layout. Parsing was refused rather than guessed.",
        },
        { status: 503, headers: { "cache-control": "no-store" } },
      );
    }

    const out = {
      available: true,
      dataset: which,
      source: parsed.source,
      url: parsed.url,
      fetchedAt: new Date().toISOString(),
      count: parsed.rows.length,
      rejected: parsed.rejected.length,
      rows: parsed.rows,
      trust: "SCRAPED_UNTRUSTED_SOURCE",
    };
    cache.set(which, { at: Date.now(), body: out });
    return NextResponse.json(out, { headers: { "cache-control": "no-store" } });
  } catch (e) {
    return NextResponse.json(
      { available: false, reason: e?.name === "AbortError" ? "TIMEOUT" : "BACKEND_UNREACHABLE" },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  } finally {
    clearTimeout(timer);
  }
}
