// The quote route, driven end to end against a fixed clock and a stubbed network.
//
// The unit tests next door cover the DECISION; these cover the ROUTE — that it
// honours that decision, counts its upstream requests, and stops when a vendor
// refuses. Every number asserted below was a real outage: per-symbol mode fired
// one request per symbol every 15 seconds, around the clock, and read a 200-OK
// Cloudflare rate-limit page as "no usable quotes" — so it retried into the block
// forever and the feed never came back on its own.

import test from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(HERE, "..");

// The route is Next code: it imports `next/server` and the `@/` alias, neither of
// which plain node resolves. Both are mapped here so the REAL module under
// app/api is exercised — a copy of it would drift from the thing that ships.
const STUB = new URL("./__next-server-stub.mjs", import.meta.url).href;
registerHooks({
  resolve(specifier, context, next) {
    if (specifier === "next/server") return { url: STUB, shortCircuit: true };
    if (specifier.startsWith("@/")) {
      let p = path.join(APP_ROOT, specifier.slice(2));
      if (!/\.(js|jsx|mjs|json)$/.test(p)) p += ".js";
      return next("file://" + p, context);
    }
    return next(specifier, context);
  },
});

const ROUTE = path.join(APP_ROOT, "app/api/nepse/quotes/route.js");
const MON_1145 = Date.parse("2026-09-07T06:00:00Z"); // Monday, 11:45 NPT — open
const MON_2345 = Date.parse("2026-09-07T18:00:00Z"); // Monday, 23:45 NPT — shut
const CLOUDFLARE =
  "<!doctype html><title>This website has been temporarily rate limited | Cloudflare</title>";

const REQ = { nextUrl: { origin: "http://127.0.0.1:3000" }, headers: { get: () => null } };

/** A fresh module instance, so module-level cache and breaker start empty. */
async function loadRoute(env) {
  Object.assign(process.env, env);
  const { GET } = await import(`${ROUTE}?t=${Math.random()}`);
  return GET;
}

function harness({ body, clock }) {
  const calls = [];
  const realNow = Date.now;
  const realFetch = globalThis.fetch;
  let at = clock;
  Date.now = () => at;
  globalThis.fetch = async (url) => {
    calls.push(String(url));
    return body();
  };
  return {
    calls,
    advance: (ms) => { at += ms; },
    set: (t) => { at = t; },
    restore: () => { Date.now = realNow; globalThis.fetch = realFetch; },
  };
}

const rows = Array.from({ length: 40 }, (_, i) => ({
  symbol: `SYM${i}`, ltp: 100 + i, previousClose: 99 + i, open: 100, high: 101, low: 98, volume: 10,
}));
const okBody = () => new Response(JSON.stringify({ available: true, rows, source: "sharesansar.com" }),
  { status: 200, headers: { "content-type": "application/json" } });
const blockedBody = () => new Response(CLOUDFLARE,
  { status: 200, headers: { "content-type": "text/html" } });

test("an open market fetches once, then serves cache without calling again", async () => {
  const h = harness({ body: okBody, clock: MON_1145 });
  try {
    const GET = await loadRoute({ NEPSE_FEED_MODE: "sharesansar" });
    const first = await (await GET(REQ)).json();
    assert.equal(first.source, "live");
    assert.equal(first.count, rows.length);
    assert.equal(h.calls.length, 1);

    const second = await (await GET(REQ)).json();
    assert.equal(second.cached, true);
    assert.equal(h.calls.length, 1, "a cached answer must not touch the network");

    h.advance(60_000);
    await GET(REQ);
    assert.equal(h.calls.length, 2, "an expired cache refetches");
  } finally { h.restore(); }
});

test("a shut market serves the cache and spends nothing", async () => {
  const h = harness({ body: okBody, clock: MON_1145 });
  try {
    const GET = await loadRoute({ NEPSE_FEED_MODE: "sharesansar" });
    await GET(REQ);
    const spent = h.calls.length;
    h.set(MON_2345);
    const shut = await (await GET(REQ)).json();
    assert.equal(shut.cached, true);
    assert.equal(shut.stale, true, "an out-of-hours answer must say it is stale");
    assert.equal(h.calls.length, spent, "nothing may be spent while the market is shut");
  } finally { h.restore(); }
});

test("a shut market with no cache refuses rather than calling the vendor", async () => {
  const h = harness({ body: okBody, clock: MON_2345 });
  try {
    const GET = await loadRoute({ NEPSE_FEED_MODE: "sharesansar" });
    const body = await (await GET(REQ)).json();
    assert.equal(body.source, "closed");
    assert.equal(body.reason, "MARKET_CLOSED");
    assert.equal(h.calls.length, 0);
  } finally { h.restore(); }
});

test("a rate-limit page stops the sweep and then stops the route", async () => {
  const h = harness({ body: blockedBody, clock: MON_1145 });
  try {
    const GET = await loadRoute({
      NEPSE_FEED_MODE: "per-symbol",
      NEPSE_FEED_URL: "https://vendor.example.com/api/stock",
      NEPSE_FEED_ALLOWLIST: "vendor.example.com",
    });

    const first = await (await GET(REQ)).json();
    assert.equal(first.source, "blocked");
    assert.equal(first.reason, "RATE_LIMITED");
    // The refusal aborts the sweep. Firing the rest of the symbols after being
    // told to stop is what turns a brief throttle into a sustained block.
    const swept = h.calls.length;
    assert.ok(swept > 0 && swept < 24, `sweep should abort early, made ${swept} calls`);

    const during = await (await GET(REQ)).json();
    assert.equal(during.reason, "BACKING_OFF");
    assert.equal(h.calls.length, swept, "a backing-off route must not call at all");

    h.advance(30_000);
    await GET(REQ);
    assert.equal(h.calls.length, swept, "still inside the first backoff");

    h.advance(90_000); // past the 1-minute backoff
    const retry = await (await GET(REQ)).json();
    assert.ok(h.calls.length > swept, "the route must retry once the backoff lapses");
    assert.equal(retry.consecutiveFailures, 2);
    assert.ok(retry.retryInMs > 60_000, "backoff must widen after a second refusal");
  } finally { h.restore(); }
});

test("a recovered vendor clears the breaker", async () => {
  let blocked = true;
  const h = harness({ body: () => (blocked ? blockedBody() : okBody()), clock: MON_1145 });
  try {
    const GET = await loadRoute({ NEPSE_FEED_MODE: "sharesansar" });
    const first = await (await GET(REQ)).json();
    assert.equal(first.source, "error");

    blocked = false;
    h.advance(120_000);
    const ok = await (await GET(REQ)).json();
    assert.equal(ok.source, "live");

    // Breaker cleared: the very next expiry refetches instead of backing off.
    h.advance(60_000);
    const after = await (await GET(REQ)).json();
    assert.equal(after.source, "live");
  } finally { h.restore(); }
});
