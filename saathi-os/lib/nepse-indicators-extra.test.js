/**
 * NEPSE range indicators — Stochastic and Wilder ADX.
 *
 * Every arithmetic assertion below is checked against a derivation written out in
 * the comment above it, not against the module's own output. The rest encode the
 * invariants the milestone cares about: an untrusted high or low refuses instead of
 * falling back to close, a zero-range window yields null rather than NaN/Infinity/50,
 * a missing field is never coerced through Number(null) === 0, and a short series
 * says so instead of returning a warm-up value.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { INDICATOR_STATUS } from "./nepse/indicators.js";
import {
  stochasticValue, adxValue, INDICATOR_EXTRA_REQUIREMENTS,
} from "./nepse/indicators-extra.js";

/** A bar in the shape parseHistoryCsv emits; `trust` overrides the per-field trust. */
function bar(date, high, low, close, trust = {}) {
  return {
    symbol: "TEST",
    date,
    open: null,
    high,
    low,
    close,
    volume: 1000,
    turnover: null,
    trusted: { close: true, high: true, low: true, open: false, volume: true, ...trust },
    flags: [],
    source: "aabishkar2/nepse-data",
    adjustment: "UNADJUSTED",
  };
}

const day = (i) => `2024-01-${String(i + 1).padStart(2, "0")}`;

/** Sequential dates, one bar per [high, low, close] triple. */
function bars(rows, trustAt = {}) {
  return rows.map((r, i) => bar(day(i), r[0], r[1], r[2], trustAt[i] || {}));
}

/** Every number a result carries must be a real number — no NaN, no Infinity. */
function assertNoJunk(value) {
  for (const [k, v] of Object.entries(value || {})) {
    if (v === null) continue;
    assert.equal(typeof v, "number", `${k} should be a number or null`);
    assert.ok(Number.isFinite(v), `${k} must not be NaN or Infinity, got ${v}`);
  }
}

// ── enablement ───────────────────────────────────────────────────────────────────
test("both indicators declare that they need high, low and close", () => {
  assert.deepEqual(INDICATOR_EXTRA_REQUIREMENTS.stochastic, ["high", "low", "close"]);
  assert.deepEqual(INDICATOR_EXTRA_REQUIREMENTS.adx, ["high", "low", "close"]);
});

// ── stochastic arithmetic ────────────────────────────────────────────────────────

// Five bars, kPeriod=3, smooth=2, dPeriod=2 (minimum = 3 + 2 + 2 - 2 = 5).
//
//   i : high  low  close
//   0 :  10    8     9
//   1 :  11    9    10
//   2 :  12   10    11
//   3 :  13   11    12
//   4 :  14   12    12.5
//
// raw %K = 100 * (close - lowestLow) / (highestHigh - lowestLow) over 3 sessions:
//   i=2: HH=max(10,11,12)=12, LL=min(8,9,10)=8   -> 100*(11-8)/4     = 75
//   i=3: HH=max(11,12,13)=13, LL=min(9,10,11)=9  -> 100*(12-9)/4     = 75
//   i=4: HH=max(12,13,14)=14, LL=min(10,11,12)=10-> 100*(12.5-10)/4  = 62.5
// %K = SMA(raw %K, 2):  i=3 -> (75+75)/2 = 75 ;  i=4 -> (75+62.5)/2 = 68.75
// %D = SMA(%K, 2)   :  i=4 -> (75+68.75)/2 = 71.875
const STOCH_ROWS = [[10, 8, 9], [11, 9, 10], [12, 10, 11], [13, 11, 12], [14, 12, 12.5]];

test("stochastic %K and %D match the hand-computed slow stochastic", () => {
  const res = stochasticValue(bars(STOCH_ROWS), { kPeriod: 3, dPeriod: 2, smooth: 2 });
  assert.equal(res.status, INDICATOR_STATUS.VALID);
  assert.equal(res.value.k, 68.75);
  assert.equal(res.value.d, 71.875);
  // The extremes of the final 3-session window, shown so the reading is auditable.
  assert.equal(res.value.highestHigh, 14);
  assert.equal(res.value.lowestLow, 10);
  assertNoJunk(res.value);
});

test("stochastic carries lookback, observations and asOf with the value", () => {
  const res = stochasticValue(bars(STOCH_ROWS), { kPeriod: 3, dPeriod: 2, smooth: 2 });
  assert.equal(res.indicator, "stochastic");
  assert.equal(res.lookback, 5, "3 + 2 + 2 - 2 bars are genuinely required");
  assert.equal(res.observations, 5);
  assert.equal(res.asOf, "2024-01-05");
  assert.equal(res.adjustment, "UNADJUSTED");
});

// A close sitting exactly on the window low is 0, and on the window high is 100 —
// the only legitimate way either extreme is ever produced.
test("stochastic reaches 0 and 100 only from a close at the window extreme", () => {
  const low = stochasticValue(
    bars([[10, 8, 9], [11, 9, 10], [12, 8, 8]]), { kPeriod: 3, dPeriod: 1, smooth: 1 },
  );
  assert.equal(low.value.k, 0, "close == lowest low over the window");
  const high = stochasticValue(
    bars([[10, 8, 9], [11, 9, 10], [12, 8, 12]]), { kPeriod: 3, dPeriod: 1, smooth: 1 },
  );
  assert.equal(high.value.k, 100, "close == highest high over the window");
});

// ── ADX arithmetic ───────────────────────────────────────────────────────────────

// Four bars, period=2 (minimum = 2*2 = 4).
//
//   i : high  low  close
//   0 : 10     8    9
//   1 : 12     9   11
//   2 : 13    11   12.5
//   3 : 12.5  10   10.5
//
// up = H-prevH, down = prevL-L; only the larger positive one survives.
//   i=1: up=12-10=2,     down=8-9=-1    -> +DM=2,   -DM=0
//        TR=max(12-9=3, |12-9|=3,     |9-9|=0)      = 3
//   i=2: up=13-12=1,     down=9-11=-2   -> +DM=1,   -DM=0
//        TR=max(13-11=2, |13-11|=2,    |11-11|=0)   = 2
//   i=3: up=12.5-13=-0.5, down=11-10=1  -> +DM=0,   -DM=1
//        TR=max(12.5-10=2.5, |12.5-12.5|=0, |10-12.5|=2.5) = 2.5
//
// Wilder seed (sum of the first 2):  TR=5, +DM=3, -DM=0
//   +DI = 100*3/5 = 60, -DI = 0        -> DX1 = 100*|60-0|/60  = 100
// Next step (prev - prev/2 + current):
//   TR = 5 - 2.5 + 2.5 = 5 ; +DM = 3 - 1.5 + 0 = 1.5 ; -DM = 0 - 0 + 1 = 1
//   +DI = 100*1.5/5 = 30, -DI = 100*1/5 = 20 -> DX2 = 100*|30-20|/50 = 20
// ADX seeds on the mean of the first `period` DX values: (100 + 20)/2 = 60
const ADX_ROWS = [[10, 8, 9], [12, 9, 11], [13, 11, 12.5], [12.5, 10, 10.5]];

test("ADX, +DI and -DI match the hand-computed Wilder seed", () => {
  const res = adxValue(bars(ADX_ROWS), { period: 2 });
  assert.equal(res.status, INDICATOR_STATUS.VALID);
  assert.equal(res.value.adx, 60);
  assert.equal(res.value.plusDI, 30);
  assert.equal(res.value.minusDI, 20);
  assert.equal(res.observations, 4);
  assert.equal(res.lookback, 4, "2*period bars are genuinely required");
  assert.equal(res.asOf, "2024-01-04");
  assertNoJunk(res.value);
});

// One more bar exercises the ADX recursion past its seed.
//   i=4: high=13, low=11, close=12.8
//        up=13-12.5=0.5, down=10-11=-1 -> +DM=0.5, -DM=0
//        TR=max(13-11=2, |13-10.5|=2.5, |11-10.5|=0.5) = 2.5
//   TR = 5 - 2.5 + 2.5 = 5 ; +DM = 1.5 - 0.75 + 0.5 = 1.25 ; -DM = 1 - 0.5 + 0 = 0.5
//   +DI = 100*1.25/5 = 25 , -DI = 100*0.5/5 = 10
//   DX3 = 100*|25-10|/35 = 1500/35 = 300/7 = 42.857142...
//   ADX = (prevADX*(period-1) + DX3)/period = (60 + 300/7)/2 = (720/7)/2 = 360/7
//       = 51.428571... -> 51.4286 at four decimals
test("ADX continues with Wilder's recursive average after the seed", () => {
  const res = adxValue(bars([...ADX_ROWS, [13, 11, 12.8]]), { period: 2 });
  assert.equal(res.value.adx, 51.4286);
  assert.equal(res.value.plusDI, 25);
  assert.equal(res.value.minusDI, 10);
  assert.equal(res.observations, 5);
  assertNoJunk(res.value);
});

// An inside day (higher low AND lower high) has no directional movement at all;
// both DMs are zero and the trend reading must not invent one.
test("ADX gives an inside day no directional movement", () => {
  // i=1 is inside i=0: up = 9-10 = -1, down = 8-8.5 = -0.5 -> +DM = -DM = 0.
  const res = adxValue(bars([[10, 8, 9], [9, 8.5, 8.8], [9.2, 8.6, 9], [9.1, 8.4, 8.5]]), { period: 2 });
  assert.equal(res.status, INDICATOR_STATUS.VALID);
  assertNoJunk(res.value);
});

// ── insufficient history ─────────────────────────────────────────────────────────
test("stochastic refuses a series shorter than its window instead of warming up", () => {
  const res = stochasticValue(bars(STOCH_ROWS.slice(0, 4)), { kPeriod: 3, dPeriod: 2, smooth: 2 });
  assert.equal(res.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
  assert.equal(res.value, null, "unknown is null, never 0");
  assert.equal(res.observations, 4);
  assert.equal(res.lookback, 5);
});

test("ADX refuses fewer than 2*period bars", () => {
  const res = adxValue(bars(ADX_ROWS.slice(0, 3)), { period: 2 });
  assert.equal(res.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
  assert.equal(res.value, null);
  assert.equal(res.observations, 3);
  assert.equal(res.lookback, 4);
});

test("an empty or non-array series is insufficient history, not zero", () => {
  for (const input of [[], null, undefined, "nope"]) {
    const s = stochasticValue(input, { kPeriod: 3, dPeriod: 2, smooth: 2 });
    const a = adxValue(input, { period: 2 });
    assert.equal(s.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
    assert.equal(s.value, null);
    assert.equal(s.observations, 0);
    assert.equal(a.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
    assert.equal(a.value, null);
    assert.equal(a.observations, 0);
  }
});

test("the default 14/3/3 and 14 periods need 18 and 28 bars respectively", () => {
  const flatish = Array.from({ length: 17 }, (_, i) => [102 + i, 100 + i, 101 + i]);
  assert.equal(stochasticValue(bars(flatish)).status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
  assert.equal(stochasticValue(bars([...flatish, [119, 117, 118]])).status, INDICATOR_STATUS.VALID);

  const long = Array.from({ length: 27 }, (_, i) => [102 + i, 100 + i, 101 + i]);
  assert.equal(adxValue(bars(long)).status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
  assert.equal(adxValue(bars([...long, [129, 127, 128]])).status, INDICATOR_STATUS.VALID);
});

// ── untrusted high / low ─────────────────────────────────────────────────────────
test("an untrusted high is FIELD_UNAVAILABLE, not a fallback to close", () => {
  // Bar 2's high is flagged bad. Substituting close there would still yield a
  // number, which is exactly the silent lie this status exists to prevent.
  const res = stochasticValue(bars(STOCH_ROWS, { 2: { high: false } }), {
    kPeriod: 3, dPeriod: 2, smooth: 2,
  });
  assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(res.value, null);
  assert.equal(res.detail.blockedAt.date, "2024-01-03");
  assert.equal(res.detail.blockedAt.field, "high");
});

test("an untrusted low blocks ADX at the bar that broke the run", () => {
  const res = adxValue(bars(ADX_ROWS, { 1: { low: false } }), { period: 2 });
  assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(res.value, null);
  assert.equal(res.detail.blockedAt.date, "2024-01-02");
  assert.equal(res.detail.blockedAt.field, "low");
  assert.equal(res.observations, 2, "only the two bars after the blocker are contiguous and usable");
});

test("a series with no trusted range at all is FIELD_UNAVAILABLE, not short history", () => {
  const none = bars(STOCH_ROWS).map((b) => ({ ...b, trusted: { ...b.trusted, high: false, low: false } }));
  assert.equal(stochasticValue(none, { kPeriod: 3, dPeriod: 2, smooth: 2 }).status,
    INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(adxValue(none, { period: 2 }).status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
});

test("an untrusted bar older than the window does not block a fresh reading", () => {
  const rows = [[9, 7, 8], ...STOCH_ROWS];
  const res = stochasticValue(bars(rows, { 0: { low: false } }), { kPeriod: 3, dPeriod: 2, smooth: 2 });
  assert.equal(res.status, INDICATOR_STATUS.VALID);
  assert.equal(res.value.k, 68.75, "the bad bar sits outside the contiguous tail that was used");
  assert.equal(res.observations, 5);
});

// ── zero range ───────────────────────────────────────────────────────────────────
test("a flat series yields null, never NaN, Infinity, 0 or a made-up 50", () => {
  // Six identical sessions: highestHigh === lowestLow, so %K has no denominator.
  const flat = bars(Array.from({ length: 6 }, () => [100, 100, 100]));
  const res = stochasticValue(flat, { kPeriod: 3, dPeriod: 2, smooth: 2 });
  assert.equal(res.status, INDICATOR_STATUS.VALID, "the data is present and trusted — it just has no range");
  assert.equal(res.value.k, null);
  assert.equal(res.value.d, null);
  assert.equal(res.value.highestHigh, 100);
  assert.equal(res.value.lowestLow, 100);
  assert.ok(/zero-range/.test(res.note));
  assertNoJunk(res.value);
});

test("a flat series leaves ADX and both DIs undefined rather than dividing by zero", () => {
  const flat = bars(Array.from({ length: 6 }, () => [100, 100, 100]));
  const res = adxValue(flat, { period: 2 });
  assert.equal(res.value.adx, null, "smoothed true range is 0 — +DI/-DI have no denominator");
  assert.equal(res.value.plusDI, null);
  assert.equal(res.value.minusDI, null);
  assertNoJunk(res.value);
});

test("a trendless but ranging series leaves DX undefined without touching +DI/-DI", () => {
  // Identical highs and lows every day: true range is non-zero (gaps to prevClose),
  // but neither +DM nor -DM ever fires, so +DI + -DI = 0 and DX has no denominator.
  const res = adxValue(bars(Array.from({ length: 6 }, () => [102, 98, 100])), { period: 2 });
  assert.equal(res.value.plusDI, 0, "measured: zero directional movement, not missing");
  assert.equal(res.value.minusDI, 0);
  assert.equal(res.value.adx, null, "DX is 0/0 — undefined, not 0");
  assertNoJunk(res.value);
});

// ── null vs zero ─────────────────────────────────────────────────────────────────
test("a null low is rejected before coercion, not read as a price of 0", () => {
  // Number(null) === 0 would put the window low at zero and pin %K near 100.
  const rows = bars(STOCH_ROWS);
  rows[4] = { ...rows[4], low: null };
  const res = stochasticValue(rows, { kPeriod: 3, dPeriod: 2, smooth: 2 });
  assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(res.value, null);
  assert.notEqual(res.value, 0);
  assert.equal(res.detail.blockedAt.field, "low");
});

test("undefined and empty-string fields are missing data, not zeroes", () => {
  for (const [field, bad] of [["high", undefined], ["low", ""], ["close", null]]) {
    const rows = bars(ADX_ROWS);
    rows[3] = { ...rows[3], [field]: bad };
    const res = adxValue(rows, { period: 2 });
    assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE, `${field}=${String(bad)}`);
    assert.equal(res.value, null);
    assert.equal(res.detail.blockedAt.field, field);
  }
});

test("a numeric string is not silently coerced into the series", () => {
  const rows = bars(ADX_ROWS);
  rows[3] = { ...rows[3], high: "12.5" };
  const res = adxValue(rows, { period: 2 });
  assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(res.value, null);
});

test("a genuine zero close is still refused as non-positive-looking data, never averaged in", () => {
  // trusted.close would be false for a non-positive row upstream; assert the guard
  // keys on trust, so a 0 that slipped through with trust revoked cannot be used.
  const rows = bars(ADX_ROWS);
  rows[3] = { ...rows[3], close: 0, trusted: { ...rows[3].trusted, close: false } };
  const res = adxValue(rows, { period: 2 });
  assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(res.detail.blockedAt.field, "close");
});

// ── parameter hygiene ────────────────────────────────────────────────────────────
test("a nonsense period is refused rather than quietly defaulted", () => {
  for (const opts of [{ kPeriod: 0 }, { dPeriod: -1 }, { smooth: 1.5 }]) {
    const res = stochasticValue(bars(STOCH_ROWS), { kPeriod: 3, dPeriod: 2, smooth: 2, ...opts });
    assert.equal(res.value, null);
    assert.equal(res.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
  }
  assert.equal(adxValue(bars(ADX_ROWS), { period: 0 }).value, null);
});

// ── status/value contract ────────────────────────────────────────────────────
// A zero-range window returns status VALID with a null value: the status
// describes the INPUTS (present, trusted, sufficient) and the absence lives in
// the value. That is defensible, but it means `status === VALID` alone is NOT a
// licence to read the number — and a consumer that assumed otherwise would hit
// the Number(null) === 0 bug this codebase is built against. These tests pin the
// contract and hold the one real consumer to it.

test("a zero-range window keeps VALID but carries a null value and says why", () => {
  const flat = Array.from({ length: 20 }, (_, i) => ({
    date: `2026-08-${String(i + 1).padStart(2, "0")}`,
    open: 5, high: 5, low: 5, close: 5, volume: 100,
    trusted: { open: true, high: true, low: true, close: true, volume: true },
  }));
  const s = stochasticValue(flat, { kPeriod: 14, dPeriod: 3, smooth: 1 });
  assert.equal(s.status, INDICATOR_STATUS.VALID);
  assert.equal(s.value.k, null);
  assert.ok(/zero-range/.test(s.note), "the reason must travel with the reading");
  // The extremes are still reported so a caller can see WHY there is no range.
  assert.equal(s.value.highestHigh, 5);
  assert.equal(s.value.lowestLow, 5);
});

test("the scorer drops a VALID-but-valueless reading instead of scoring it as zero", async () => {
  const { scoreSignal } = await import("./analysis/scoring.js");
  const r = scoreSignal({
    rsi: { value: 55, status: INDICATOR_STATUS.VALID, observations: 30 },
    stochastic: { value: { k: null, d: null }, status: INDICATOR_STATUS.VALID, observations: 30 },
  });
  const names = r.contributors.map((c) => c.component);
  assert.ok(!names.includes("stochastic"), "a null %K must never contribute");
  const dropped = r.dropped.find((d) => d.component === "stochastic");
  assert.ok(dropped, "and it must be reported as dropped, not silently ignored");
  // A stochastic of 0 would read as maximally oversold. It must not appear at all.
  assert.ok(!r.contributors.some((c) => c.value === 0 && c.component === "stochastic"));
});
