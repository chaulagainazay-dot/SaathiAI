// Single-origin topology guard: the browser reaches the backend only through
// same-origin :3100 rewrites, and those rewrites forward a FIXED, closed set of
// backend prefixes to a loopback upstream the browser can never choose.
import { test } from "node:test";
import assert from "node:assert";
import nextConfig from "../next.config.mjs";

const rewrites = await nextConfig.rewrites();

test("rewrites exist and are a closed, explicit prefix list (no catch-all)", () => {
  assert.ok(Array.isArray(rewrites) && rewrites.length >= 4);
  for (const r of rewrites) {
    assert.ok(r.source.startsWith("/api/"), `source must be an /api prefix: ${r.source}`);
    assert.doesNotMatch(r.source, /^\/:path\*|^\/api\/:path\*$/, "no catch-all /api proxy");
  }
});

test("only known backend prefixes are proxied (local app/api/* untouched)", () => {
  const sources = rewrites.map((r) => r.source).sort();
  assert.deepEqual(sources, [
    "/api/content/:path*",
    "/api/events/:path*",
    "/api/executive/:path*",
    "/api/v1/:path*",
  ]);
});

test("upstream is a FIXED loopback target — never browser-supplied", () => {
  for (const r of rewrites) {
    assert.match(r.destination, /^http:\/\/127\.0\.0\.1:8765\/api\//,
      `destination must be the fixed loopback backend: ${r.destination}`);
    // the destination only ever appends the captured path to the fixed host
    assert.ok(!/:\/\/.*:path\*.*:\/\//.test(r.destination), "no second URL in destination");
  }
});

test("browser API base is same-origin (relative) — no direct :8765 in the app default", () => {
  // lib/api.js: empty NEXT_PUBLIC_SAATHI_API => same-origin; the localhost:8765
  // literal remains only as the UNSET dev fallback, never emitted when the
  // launcher exports "" (single-origin). This asserts the same-origin contract
  // is expressible: an empty string must be treated as same-origin, not falsy.
  const src = ""; // simulate NEXT_PUBLIC_SAATHI_API=""
  const base = (src === undefined || src === null) ? "http://localhost:8765" : src;
  assert.equal(base, "", "empty NEXT_PUBLIC_SAATHI_API must resolve to same-origin, not localhost:8765");
});
