// When the quote route may call a vendor, and how it reads a refusal.
//
// These exist because of a real outage: the client polled every 30 seconds, in
// per-symbol mode that was 24 requests a poll, around the clock, seven days a
// week — and the configured worker was rate-limited into a Cloudflare block page
// by our own traffic. That page returns HTTP 200 with HTML, so it was read as
// "no usable quotes" and retried 15 seconds later, forever.

import test from "node:test";
import assert from "node:assert/strict";

import {
  BACKOFF_MAX_MS, CLOSED_CACHE_MS, FEED_ACTION, FEED_REASON, OPEN_CACHE_MS,
  SESSION_CLOSE_MIN, SESSION_OPEN_MIN, backoffMs, classifyBody, feedAction,
  marketWindow,
} from "./nepse/feed-policy.js";

// 2026-09-07 is a Monday. NPT is UTC+05:45 and never shifts.
const MON_1145 = Date.parse("2026-09-07T06:00:00Z");
const MON_0745 = Date.parse("2026-09-07T02:00:00Z");
const MON_2345 = Date.parse("2026-09-07T18:00:00Z");
const FRI_1145 = Date.parse("2026-09-11T06:00:00Z");
const SUN_1145 = Date.parse("2026-09-06T06:00:00Z");

// ── the trading window ──────────────────────────────────────────────────────

test("the window is anchored to Nepal time, not the server's", () => {
  // 06:00Z is 11:45 NPT — mid-session — whatever timezone this test runs in.
  const w = marketWindow(new Date(MON_1145));
  assert.equal(w.open, true);
  assert.equal(w.nptMinutes, 11 * 60 + 45);
  assert.ok(w.nptMinutes >= SESSION_OPEN_MIN && w.nptMinutes <= SESSION_CLOSE_MIN);
});

test("NEPSE trades Sunday to Thursday", () => {
  assert.equal(marketWindow(new Date(SUN_1145)).open, true, "Sunday is a trading day");
  assert.equal(marketWindow(new Date(FRI_1145)).open, false, "Friday is not");
  assert.equal(marketWindow(new Date(FRI_1145)).reason, "WEEKEND");
});

test("before the open and after the close are distinguished", () => {
  assert.equal(marketWindow(new Date(MON_0745)).reason, "BEFORE_OPEN");
  assert.equal(marketWindow(new Date(MON_2345)).reason, "AFTER_CLOSE");
});

test("an unreadable clock never reports the market open", () => {
  assert.equal(marketWindow(new Date("nonsense")).open, false);
  assert.equal(marketWindow(Number.NaN).open, false);
});

// ── reading a refusal ───────────────────────────────────────────────────────

const CLOUDFLARE = `<!doctype html><html><head><title>
  This website has been temporarily rate limited | nepsetty.kokomo.workers.dev
  | Cloudflare</title></head><body></body></html>`;

test("a 200 HTML rate-limit page is a rate limit, not an empty market", () => {
  // The exact failure: read as "no usable quotes" it was retried into the limit
  // forever. Read as RATE_LIMITED it trips the breaker and the limit can lapse.
  assert.equal(classifyBody(200, "text/html", CLOUDFLARE), FEED_REASON.RATE_LIMITED);
});

test("status codes that mean 'stop' are classified before the body is read", () => {
  assert.equal(classifyBody(429, "application/json", "{}"), FEED_REASON.RATE_LIMITED);
  assert.equal(classifyBody(403, "application/json", "{}"), FEED_REASON.UPSTREAM_BLOCKED);
  assert.equal(classifyBody(503, "application/json", "{}"), FEED_REASON.UPSTREAM_BLOCKED);
});

test("real JSON passes through untouched", () => {
  assert.equal(classifyBody(200, "application/json", '{"ltp":552.5}'), FEED_REASON.OK);
});

test("unrecognised HTML is UNEXPECTED_CONTENT, never OK", () => {
  assert.equal(classifyBody(200, "text/html", "<html><body>hello</body></html>"),
    FEED_REASON.UNEXPECTED_CONTENT);
});

// ── backoff ─────────────────────────────────────────────────────────────────

test("backoff doubles and is capped", () => {
  assert.equal(backoffMs(1), 60_000);
  assert.equal(backoffMs(2), 120_000);
  assert.equal(backoffMs(5), 16 * 60_000);
  assert.equal(backoffMs(99), BACKOFF_MAX_MS);
});

test("no failures means no wait", () => {
  for (const v of [0, -1, null, undefined, "x", Number.NaN]) assert.equal(backoffMs(v), 0);
});

// ── the decision, and its ordering ──────────────────────────────────────────

test("an open market with nothing cached fetches", () => {
  assert.equal(feedAction({ now: MON_1145 }).action, FEED_ACTION.FETCH);
});

test("a fresh cache is served without calling the vendor", () => {
  const r = feedAction({ now: MON_1145, hasCache: true, cachedAt: MON_1145 - 5_000 });
  assert.equal(r.action, FEED_ACTION.SERVE_CACHE);
});

test("a stale cache during trading hours fetches", () => {
  const r = feedAction({ now: MON_1145, hasCache: true, cachedAt: MON_1145 - OPEN_CACHE_MS - 1 });
  assert.equal(r.action, FEED_ACTION.FETCH);
});

test("a tripped breaker refuses instead of fetching", () => {
  const r = feedAction({
    now: MON_1145, hasCache: true, cachedAt: MON_1145 - 60_000,
    breakerUntil: MON_1145 + 60_000,
  });
  assert.equal(r.action, FEED_ACTION.REFUSE_BACKOFF);
  assert.equal(r.retryInMs, 60_000);
});

test("a fresh cache wins over a tripped breaker", () => {
  // Withholding a price we already have because a LATER request failed would be
  // worse data, not safer data.
  const r = feedAction({
    now: MON_1145, hasCache: true, cachedAt: MON_1145 - 1_000,
    breakerUntil: MON_1145 + 60_000,
  });
  assert.equal(r.action, FEED_ACTION.SERVE_CACHE);
});

test("a shut market with nothing cached refuses rather than spending a request", () => {
  const r = feedAction({ now: MON_2345 });
  assert.equal(r.action, FEED_ACTION.REFUSE_CLOSED);
  assert.equal(r.reason, FEED_REASON.MARKET_CLOSED);
});

test("a shut market serves even a very old cache, marked stale", () => {
  const r = feedAction({ now: MON_2345, hasCache: true, cachedAt: MON_2345 - 6 * 3_600_000 });
  assert.equal(r.action, FEED_ACTION.SERVE_CACHE);
  assert.equal(r.stale, true);
});

test("the closed-hours cache lives far longer than the trading-hours one", () => {
  // This ratio IS the fix: a tab left open overnight makes ~6 calls an hour
  // instead of ~240, and none of them can learn anything new.
  assert.ok(CLOSED_CACHE_MS >= 20 * OPEN_CACHE_MS);
});

test("a weekend never fetches, however stale the cache", () => {
  const r = feedAction({ now: FRI_1145, hasCache: true, cachedAt: FRI_1145 - 24 * 3_600_000 });
  assert.notEqual(r.action, FEED_ACTION.FETCH);
});
