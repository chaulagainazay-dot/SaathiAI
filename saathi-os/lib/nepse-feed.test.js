/**
 * NEPSE live feed — policy, SSRF containment, normalization, fail-closed merge.
 * Security-critical: these assertions are what stop a misconfigured or hostile
 * endpoint from being called, and stop snapshot data being shown as live.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import {
  evaluateFeedEndpoint, parseAllowlist, normalizeQuote, normalizeFeedPayload,
  mergeLiveQuotes, FEED_REASON, FEED_SOURCE_LABEL,
} from "./nepse/feed-policy.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const ALLOW = "api.vendor.com,feed.example.np";

// ── configuration gate ───────────────────────────────────────────────────────────
test("no URL configured -> NOT_CONFIGURED (never a default endpoint)", () => {
  const v = evaluateFeedEndpoint("", ALLOW);
  assert.equal(v.allowed, false);
  assert.equal(v.reason, FEED_REASON.NOT_CONFIGURED);
});

test("URL without an allowlist is refused — operator must name the vendor", () => {
  const v = evaluateFeedEndpoint("https://api.vendor.com/q", "");
  assert.equal(v.allowed, false);
  assert.equal(v.reason, FEED_REASON.NO_ALLOWLIST);
});

test("allowlisted https vendor is permitted", () => {
  const v = evaluateFeedEndpoint("https://api.vendor.com/quotes", ALLOW);
  assert.equal(v.allowed, true);
  assert.equal(v.host, "api.vendor.com");
});

test("subdomain of an allowlisted host is permitted", () => {
  assert.equal(evaluateFeedEndpoint("https://eu.api.vendor.com/q", ALLOW).allowed, true);
});

// ── SSRF / spoofing containment ──────────────────────────────────────────────────
test("http is refused — credentials must never cross plaintext", () => {
  const v = evaluateFeedEndpoint("http://api.vendor.com/q", ALLOW);
  assert.equal(v.reason, FEED_REASON.SCHEME_NOT_HTTPS);
});

test("lookalike host cannot pass as the allowlisted one", () => {
  // endsWith(".vendor.com") must not match "evil-api.vendor.com.attacker.io"
  for (const bad of [
    "https://api.vendor.com.attacker.io/q",
    "https://notapi.vendor.com.evil/q",
    "https://evilvendor.com/q",
  ]) {
    const v = evaluateFeedEndpoint(bad, ALLOW);
    assert.equal(v.allowed, false, `${bad} must not be allowed`);
    assert.equal(v.reason, FEED_REASON.HOST_NOT_ALLOWLISTED);
  }
});

test("private / loopback / link-local addresses are refused", () => {
  for (const bad of [
    "https://localhost/q", "https://127.0.0.1/q", "https://10.0.0.5/q",
    "https://192.168.1.10/q", "https://169.254.169.254/latest/meta-data",
    "https://172.16.0.9/q",
  ]) {
    const v = evaluateFeedEndpoint(bad, `${ALLOW},localhost,127.0.0.1,10.0.0.5,192.168.1.10,169.254.169.254,172.16.0.9`);
    assert.equal(v.allowed, false, `${bad} must be refused even if allowlisted`);
    assert.equal(v.reason, FEED_REASON.PRIVATE_ADDRESS);
  }
});

test("credentials embedded in the URL are refused", () => {
  const v = evaluateFeedEndpoint("https://user:pass@api.vendor.com/q", ALLOW);
  assert.equal(v.reason, FEED_REASON.CREDENTIALS_IN_URL);
});

test("malformed URL is refused, not thrown", () => {
  assert.equal(evaluateFeedEndpoint("not a url", ALLOW).reason, FEED_REASON.BAD_URL);
});

test("allowlist parsing is whitespace/case tolerant", () => {
  assert.deepEqual(parseAllowlist(" A.com , b.NP ,, "), ["a.com", "b.np"]);
});

// ── normalization ────────────────────────────────────────────────────────────────
test("vendor aliases normalize to the canonical quote", () => {
  const q = normalizeQuote({ Symbol: "nabil", lastTradedPrice: "512.5", previousClose: 508 });
  assert.equal(q.symbol, "NABIL");
  assert.equal(q.ltp, 512.5);
  assert.equal(q.prevClose, 508);
});

test("a quote without a usable price is dropped, never defaulted to 0", () => {
  assert.equal(normalizeQuote({ symbol: "X" }), null);
  assert.equal(normalizeQuote({ symbol: "X", ltp: "n/a" }), null);
  assert.equal(normalizeQuote(null), null);
});

test("payload shapes {data|quotes|result|array} all normalize", () => {
  const row = { symbol: "A", ltp: 10 };
  for (const p of [[row], { data: [row] }, { quotes: [row] }, { result: [row] }]) {
    assert.equal(normalizeFeedPayload(p).length, 1);
  }
  assert.deepEqual(normalizeFeedPayload({ nope: 1 }), []);
});

// ── merge / fail-closed ──────────────────────────────────────────────────────────
const SNAP = [
  { symbol: "NABIL", ltp: 500, prevClose: 495, eps: 25, bookValue: 250, listedShares: 100 },
  { symbol: "API", ltp: 200, prevClose: 200, eps: 10, bookValue: 100, listedShares: 50 },
];

test("empty live quotes leave the snapshot untouched (no silent blanking)", () => {
  assert.equal(mergeLiveQuotes(SNAP, []), SNAP);
  assert.equal(mergeLiveQuotes(SNAP, null), SNAP);
});

test("live price overrides snapshot and re-derives valuation", () => {
  const merged = mergeLiveQuotes(SNAP, [{ symbol: "NABIL", ltp: 600, prevClose: 590 }]);
  const nabil = merged.find((s) => s.symbol === "NABIL");
  assert.equal(nabil.ltp, 600);
  assert.equal(nabil.pe, 24);          // 600/25 — must not stay stale at 20
  assert.equal(nabil.pb, 2.4);         // 600/250
  assert.equal(nabil.live, true);
  // untouched symbol keeps snapshot values and is NOT marked live
  const api = merged.find((s) => s.symbol === "API");
  assert.equal(api.ltp, 200);
  assert.equal(api.live, undefined);
});

test("every non-live state has an honest label", () => {
  assert.match(FEED_SOURCE_LABEL.snapshot, /NOT A LIVE/i);
  assert.match(FEED_SOURCE_LABEL.unconfigured, /NO LICENSED FEED/i);
  assert.match(FEED_SOURCE_LABEL.blocked, /BLOCKED BY POLICY/i);
  assert.equal(FEED_SOURCE_LABEL.live, "LIVE NEPSE FEED");
});

// ── route + credential discipline ────────────────────────────────────────────────
test("server route exists and is server-only", () => {
  const f = join(ROOT, "app/api/nepse/quotes/route.js");
  assert.equal(existsSync(f), true);
  const src = readFileSync(f, "utf8");
  assert.match(src, /runtime = "nodejs"/);
  assert.match(src, /redirect: "error"/);   // no redirect-based SSRF escape
  assert.match(src, /AbortController/);      // bounded time
  assert.match(src, /MAX_BYTES/);            // bounded size
});

test("the vendor credential is never sent to the client", () => {
  const src = readFileSync(join(ROOT, "app/api/nepse/quotes/route.js"), "utf8");
  // the key is read server-side and must not appear in any JSON response body
  assert.ok(src.includes("process.env.NEPSE_FEED_KEY"));
  assert.ok(!/NextResponse\.json\([^)]*NEPSE_FEED_KEY/.test(src));
  assert.ok(!/quotes,\s*key/.test(src));
});

test("client never calls the vendor directly — only our own route", () => {
  const src = readFileSync(join(ROOT, "lib/nepse/live.js"), "utf8");
  assert.match(src, /fetch\("\/api\/nepse\/quotes"/);
  assert.ok(!src.includes("NEPSE_FEED_URL"), "client must not know the vendor URL");
  assert.ok(!src.includes("NEPSE_FEED_KEY"), "client must never see the credential");
});

// ── unknown previous close must stay unknown (ShareBazaar-shaped feeds) ──────────
test("a feed with no previous close does not fake one", () => {
  const q = normalizeQuote({ symbol: "NABIL", ltp: 539, last_updated: "2026-09-04T04:43:27Z" });
  assert.equal(q.ltp, 539);
  assert.equal(q.prevClose, null, "must not default prevClose to ltp (would show a fake 0.00%)");
});

test("merging an LTP-only quote marks the day change unavailable", () => {
  const merged = mergeLiveQuotes(SNAP, [{ symbol: "NABIL", ltp: 539, prevClose: null }]);
  const n = merged.find((s) => s.symbol === "NABIL");
  assert.equal(n.ltp, 539);
  assert.equal(n.prevClose, null);
  assert.equal(n.changeUnavailable, true);
  // the stale snapshot close (495) must NOT be paired with a live price
  assert.notEqual(n.prevClose, 495);
});

test("provider error objects are not quotes", () => {
  assert.equal(normalizeQuote({ error: "Error retrieving stock data" }), null);
});
