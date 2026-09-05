// Web search via the local wigolo daemon (NEPSE-COMPLETE-2).
//
// wigolo is AGPL-3.0 and runs as a SEPARATE PROCESS. This route speaks to it over
// its loopback HTTP API; no wigolo source is imported or vendored anywhere in
// SaathiOS, which keeps the licence boundary at the process line.
//
// The daemon is not started by this app. If it is not running the route says so
// and returns nothing — a search surface that silently degrades to no results is
// indistinguishable from a web where nothing was written.

import { NextResponse } from "next/server";
import {
  validateBaseUrl, buildSearchRequest, normalizeSearch, WIGOLO_SOURCE,
} from "@/lib/web/wigolo";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const BASE = process.env.WIGOLO_BASE_URL || "http://127.0.0.1:3333";
const TIMEOUT_MS = 90_000;
const CACHE_MS = 5 * 60 * 1000;
const CACHE_MAX = 40;

const cache = new Map();

const fail = (reason, extra = {}, status = 200) =>
  NextResponse.json({ available: false, reason, ...extra },
    { status, headers: { "cache-control": "no-store" } });

export async function POST(request) {
  const base = validateBaseUrl(BASE);
  if (!base.ok) {
    // A misconfigured base URL is refused rather than dialled: an integration
    // that accepts any host turns this route into a request-forgery proxy.
    return fail("BAD_DAEMON_URL", {
      message: `WIGOLO_BASE_URL must point at loopback (${base.reason}).`,
    }, 500);
  }

  let body;
  try { body = await request.json(); } catch { return fail("BAD_JSON", {}, 400); }

  const req = buildSearchRequest({
    query: body?.query,
    maxResults: body?.maxResults,
    domain: body?.domain,
    timeRange: body?.timeRange,
  });
  if (!req.ok) return fail(req.reason, {}, 400);

  const key = JSON.stringify(req.body);
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_MS) {
    return NextResponse.json(hit.body, { headers: { "cache-control": "no-store" } });
  }

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${base.base}/v1/search`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(process.env.WIGOLO_API_TOKEN ? { authorization: `Bearer ${process.env.WIGOLO_API_TOKEN}` } : {}),
      },
      body: JSON.stringify(req.body),
      signal: ac.signal,
      cache: "no-store",
      redirect: "error",
    });
    if (!res.ok) return fail(`DAEMON_${res.status}`, { source: WIGOLO_SOURCE });

    const normalized = normalizeSearch(await res.json());
    if (!normalized.ok) {
      return fail(normalized.reason, { hint: normalized.hint, stage: normalized.stage, source: WIGOLO_SOURCE });
    }

    const out = {
      available: true,
      ...normalized,
      fetchedAt: new Date().toISOString(),
    };
    cache.set(key, { at: Date.now(), body: out });
    // Bounded: a search box is a way to grow a Map without limit.
    if (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value);
    return NextResponse.json(out, { headers: { "cache-control": "no-store" } });
  } catch (e) {
    const aborted = e?.name === "AbortError";
    return fail(aborted ? "TIMEOUT" : "DAEMON_UNREACHABLE", {
      message: aborted
        ? "The search did not come back in time."
        : "The local wigolo daemon is not answering. Start it with: npx wigolo serve --port 3333",
      source: WIGOLO_SOURCE,
    });
  } finally {
    clearTimeout(timer);
  }
}
