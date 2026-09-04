// Server-side NEPSE quote proxy.
//
// The licensed vendor credential lives ONLY here. It is read from the server
// environment and never serialized to the client — the browser calls this route,
// not the vendor. The route refuses to call anything the operator has not
// explicitly allowlisted, and fails closed to "snapshot" rather than erroring the
// page or inventing prices.
//
// Configure (server env only):
//   NEPSE_FEED_URL        https://<licensed-vendor>/path/to/quotes
//   NEPSE_FEED_ALLOWLIST  comma-separated vendor hosts, e.g. api.vendor.com
//   NEPSE_FEED_KEY        bearer token / api key (optional, vendor-dependent)
//   NEPSE_FEED_HEADER     header name for the key (default: Authorization)

import { NextResponse } from "next/server";
import { evaluateFeedEndpoint, normalizeFeedPayload, FEED_REASON } from "@/lib/nepse/feed-policy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const TIMEOUT_MS = 6000;
const MAX_BYTES = 2_000_000; // bounded response — a feed cannot exhaust memory

function payload(source, quotes, extra = {}) {
  return NextResponse.json(
    { source, asOf: new Date().toISOString(), count: quotes.length, quotes, ...extra },
    { headers: { "cache-control": "no-store" } },
  );
}

export async function GET() {
  const url = process.env.NEPSE_FEED_URL || "";
  const allowlist = process.env.NEPSE_FEED_ALLOWLIST || "";

  const verdict = evaluateFeedEndpoint(url, allowlist);
  if (!verdict.allowed) {
    const source = verdict.reason === FEED_REASON.NOT_CONFIGURED ? "unconfigured" : "blocked";
    // Never echo the configured URL back to the client.
    return payload(source, [], { reason: verdict.reason });
  }

  const key = process.env.NEPSE_FEED_KEY || "";
  const headerName = process.env.NEPSE_FEED_HEADER || "Authorization";
  const headers = { accept: "application/json" };
  if (key) headers[headerName] = headerName.toLowerCase() === "authorization" ? `Bearer ${key}` : key;

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { headers, signal: ac.signal, redirect: "error", cache: "no-store" });
    if (!res.ok) return payload("error", [], { reason: `upstream_${res.status}` });

    const len = Number(res.headers.get("content-length") || 0);
    if (len && len > MAX_BYTES) return payload("error", [], { reason: "response_too_large" });

    const text = await res.text();
    if (text.length > MAX_BYTES) return payload("error", [], { reason: "response_too_large" });

    let json;
    try { json = JSON.parse(text); } catch { return payload("error", [], { reason: "invalid_json" }); }

    const quotes = normalizeFeedPayload(json);
    if (!quotes.length) return payload("error", [], { reason: "no_usable_quotes" });
    return payload("live", quotes);
  } catch (e) {
    const reason = e?.name === "AbortError" ? "timeout" : "unreachable";
    return payload("error", [], { reason });
  } finally {
    clearTimeout(timer);
  }
}
