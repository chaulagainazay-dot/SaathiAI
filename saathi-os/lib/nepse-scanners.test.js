import test from "node:test";
import assert from "node:assert/strict";

import { SCAN_LIBRARY, intersect, runScan, runScans, scanById } from "./nepse/scanners.js";
import { STRATEGY_STATUS, validateStrategy } from "./strategy/conditions.js";

/**
 * Readings are TYPED, not bare numbers: every value carries a status, so a
 * stale or thin-history figure can never be silently compared against. These
 * helpers build that shape rather than pretending a number is a reading.
 */
const v = (value) => ({ value, status: STRATEGY_STATUS.VALID });
const reads = (obj) => Object.fromEntries(
  Object.entries(obj).map(([kk, vv]) => [kk, vv === undefined || vv === null ? vv : v(vv)]),
);
const row = (symbol, readings, prev = null) => ({
  symbol,
  readings: reads(readings),
  prevReadings: prev ? reads(prev) : null,
});

test("every built-in scan is a valid strategy in the shared schema", () => {
  // Scans are ordinary strategies, so they must pass the same validator a
  // user-built one does. A scan the builder could not load would be a fork.
  for (const scan of SCAN_LIBRARY) {
    const v = validateStrategy(scan);
    assert.equal(v.valid, true, `${scan.id}: ${JSON.stringify(v.errors)}`);
  }
});

test("scan ids are unique and addressable", () => {
  const ids = SCAN_LIBRARY.map((s) => s.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(scanById("oversold").name, "Oversold (RSI < 30)");
  assert.equal(scanById("nope"), null);
});

test("a scan separates matches from rejections", () => {
  const r = runScan(scanById("oversold"), [
    row("A", { rsi: 22 }), row("B", { rsi: 55 }), row("C", { rsi: 28 }),
  ]);
  assert.deepEqual(r.matched.map((m) => m.symbol), ["A", "C"]);
  assert.equal(r.counts.rejected, 1);
  assert.equal(r.complete, true);
});

test("an unreadable symbol is UNKNOWN, never a rejection", () => {
  // Folding unknowns into rejections is how a scanner hides the half of the
  // market it could not read and calls the rest "the results".
  const r = runScan(scanById("oversold"), [
    row("A", { rsi: 22 }), row("B", {}), row("C", { rsi: null }),
  ]);
  assert.equal(r.counts.matched, 1);
  assert.equal(r.counts.unknown, 2);
  assert.equal(r.counts.rejected, 0);
  assert.equal(r.complete, false);
});

test("the scan reports how much of the universe it actually examined", () => {
  const r = runScan(scanById("oversold"), [row("A", { rsi: 10 }), row("B", {})]);
  assert.equal(r.counts.scanned, 2);
  assert.equal(r.counts.matched + r.counts.rejected + r.counts.unknown, 2);
});

test("a cross scan needs the previous session and says so when absent", () => {
  const cross = scanById("macd-bullish-cross");
  const withPrev = runScan(cross, [
    row("A", { macd: 1.2, macdSignal: 1.0 }, { macd: 0.8, macdSignal: 1.0 }),
  ]);
  assert.equal(withPrev.counts.matched, 1);

  const noPrev = runScan(cross, [row("A", { macd: 1.2, macdSignal: 1.0 })]);
  assert.equal(noPrev.counts.unknown, 1);   // not a rejection
});

test("a multi-condition scan requires all of them", () => {
  const r = runScan(scanById("oversold-uptrend"), [
    row("A", { rsi: 35, close: 120, sma200: 100 }),   // both true
    row("B", { rsi: 35, close: 90, sma200: 100 }),    // below the average
  ]);
  assert.deepEqual(r.matched.map((m) => m.symbol), ["A"]);
});

test("an empty universe scans nothing and claims nothing", () => {
  const r = runScan(scanById("oversold"), []);
  assert.equal(r.counts.scanned, 0);
  assert.deepEqual(r.matched, []);
});

test("rows without a symbol are skipped rather than counted", () => {
  const r = runScan(scanById("oversold"), [{ readings: { rsi: 10 } }, row("A", { rsi: 10 })]);
  assert.equal(r.counts.matched, 1);
});

test("an invalid strategy yields no answer instead of rejecting everything", () => {
  const r = runScan({ name: "broken", root: null }, [row("A", { rsi: 10 })]);
  assert.equal(r.counts.unknown, 1);
  assert.equal(r.counts.rejected, 0);
});

test("several scans run together and intersect", () => {
  const universe = [
    row("A", { rsi: 25, volumeRatio: 3 }),
    row("B", { rsi: 25, volumeRatio: 1 }),
    row("C", { rsi: 80, volumeRatio: 4 }),
  ];
  const results = runScans([scanById("oversold"), scanById("volume-surge")], universe);
  assert.equal(results.length, 2);
  // Intersection, not union: only A satisfies both.
  assert.deepEqual(intersect(results), ["A"]);
});

test("intersecting nothing returns nothing", () => {
  assert.deepEqual(intersect([]), []);
});
