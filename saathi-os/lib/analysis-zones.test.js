/**
 * Demand/supply zones and volume participation.
 *
 * The load-bearing assertions are the refusals: no zone without a real base, no zone
 * built from an untrusted high or low, no ratio invented from an absent volume, and
 * no division by a zero baseline. Touch counts and base sizes are asserted as exact
 * numbers because the whole point of the module is that those two facts stay apart.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  demandZones, supplyZones, priceZones, volumeRatio, relativeVolumeSeries,
  ZONE_KIND, ZONE_DEFAULTS,
} from "./analysis/zones.js";
import { INDICATOR_STATUS } from "./nepse/indicators.js";

const day = (i) => new Date(Date.UTC(2024, 0, 7 + i)).toISOString().slice(0, 10);

/** [close, high, low] rows → typed bars with full per-field trust. */
function bars(rows, { volume = 1000 } = {}) {
  return rows.map(([close, high, low], i) => ({
    symbol: "TEST",
    date: day(i),
    open: null,
    high, low, close,
    volume,
    trusted: { close: true, high: true, low: true, open: false, volume: true },
  }));
}

/**
 * A textbook drop-base-rally: a 6-bar drop into a 4-bar base at ~100 (span 1.5),
 * a two-bar impulse out to 109, then two separate returns to the base.
 */
const DROP_BASE_RALLY = [
  [120.0, 121.0, 119.0],
  [116.0, 120.5, 115.5],
  [112.0, 116.5, 111.5],
  [108.0, 112.5, 107.5],
  [104.0, 108.5, 103.5],
  [100.5, 104.5, 100.0],
  [100.2, 100.8, 99.6],   // 6  base
  [100.0, 100.6, 99.5],   // 7  base
  [100.4, 100.9, 99.7],   // 8  base
  [100.1, 100.7, 99.4],   // 9  base ends — zone is 99.4 → 100.9
  [104.5, 105.0, 100.5],  // 10 impulse
  [109.0, 109.5, 104.0],  // 11 impulse ends
  [112.0, 113.0, 111.0],
  [114.0, 115.0, 113.0],
  [110.0, 114.5, 109.5],
  [104.0, 110.0, 103.0],
  [100.5, 104.5, 100.0],  // 16 first return
  [106.0, 106.5, 101.5],  // 17 back out of the zone
  [110.0, 111.0, 109.0],
  [108.0, 111.0, 107.0],
  [101.0, 108.0, 100.7],  // 20 second return
  [106.0, 107.0, 101.5],
];

/** The same tape reflected through 220 — a rally-base-drop, bar for bar. */
const mirrored = DROP_BASE_RALLY.map(([c, h, l]) => [220 - c, 220 - l, 220 - h]);

/** Steady drift with 8-wide bars: never tight enough to be a base. */
const NO_BASE = Array.from({ length: 20 }, (_, i) => {
  const c = 100 + i * 3;
  return [c, c + 4, c - 4];
});

test("demand zone: a clean drop-base-rally yields exactly one typed zone", () => {
  const res = demandZones(bars(DROP_BASE_RALLY));

  assert.equal(res.status, INDICATOR_STATUS.VALID);
  assert.equal(res.kind, ZONE_KIND.DEMAND);
  assert.equal(res.observations, DROP_BASE_RALLY.length);
  assert.equal(res.zones.length, 1);

  const z = res.zones[0];
  assert.equal(z.low, 99.4, "zone floor is the lowest base low, not a rounded guess");
  assert.equal(z.high, 100.9);
  assert.equal(z.basisBars, 4, "four bars built the base");
  assert.equal(z.formedAt, day(9), "the zone forms on the last base bar");
  assert.equal(z.departureAt, day(11));
  assert.equal(z.status, INDICATOR_STATUS.VALID);
  // (109.0 - 100.9) / 100.15 * 100 — measured from the zone edge, close to close.
  assert.equal(z.departureStrength, 8.09);
  assert.equal(z.broken, false);
  assert.equal(z.brokenAt, null);
});

test("no base means no zone — a trending tape is not squeezed into one", () => {
  const res = demandZones(bars(NO_BASE));
  assert.equal(res.status, INDICATOR_STATUS.VALID);
  assert.deepEqual(res.zones, [], "nothing found is reported as nothing, not as a weak zone");
  assert.equal(supplyZones(bars(NO_BASE)).zones.length, 0);
});

test("a departure in the wrong direction is not a zone of the other kind", () => {
  // The rally out of the base makes this demand-only; supply must find nothing here.
  assert.equal(supplyZones(bars(DROP_BASE_RALLY)).zones.length, 0);
});

test("supply zone: the mirrored tape gives the mirrored zone", () => {
  const res = supplyZones(bars(mirrored));
  assert.equal(res.zones.length, 1);
  const z = res.zones[0];
  assert.equal(z.kind, ZONE_KIND.SUPPLY);
  assert.equal(z.low, 119.1);
  assert.equal(z.high, 120.6);
  assert.equal(z.basisBars, 4);
  assert.equal(z.touches, 2, "the reflection is tested exactly as often as the original");
  assert.ok(z.departureStrength > 0, "strength is signed by kind, never negative");
  assert.equal(demandZones(bars(mirrored)).zones.length, 0);
});

test("touches count returns, and one touch is not five", () => {
  const full = demandZones(bars(DROP_BASE_RALLY)).zones[0];
  assert.equal(full.touches, 2);
  assert.equal(full.lastTouchAt, day(20));

  // Cut the tape before the second return: the same zone, a different fact.
  const once = demandZones(bars(DROP_BASE_RALLY.slice(0, 18))).zones[0];
  assert.equal(once.low, full.low);
  assert.equal(once.high, full.high);
  assert.equal(once.basisBars, full.basisBars);
  assert.equal(once.touches, 1, "touch count is per zone-visit and must not be flattened");
  assert.equal(once.lastTouchAt, day(16));

  // And before any return at all.
  const untested = demandZones(bars(DROP_BASE_RALLY.slice(0, 15))).zones[0];
  assert.equal(untested.touches, 0);
  assert.equal(untested.lastTouchAt, null);
});

test("a multi-bar stay inside the zone is one touch, not one per bar", () => {
  // Three consecutive bars sitting in the zone after the impulse.
  const rows = [...DROP_BASE_RALLY.slice(0, 16),
    [100.5, 104.5, 100.0],
    [100.3, 101.0, 99.8],
    [100.6, 101.2, 99.9],
    [110.0, 111.0, 109.0],
  ];
  const z = demandZones(bars(rows)).zones[0];
  assert.equal(z.touches, 1, "one excursion into the zone, however long it lingers");
});

test("a close through the floor breaks the zone and stops the count", () => {
  const rows = [...DROP_BASE_RALLY.slice(0, 16),
    [95.0, 104.0, 94.0],   // closes below the zone floor
    [100.0, 100.9, 99.5],  // back inside — but the zone died on the bar before
  ];
  const z = demandZones(bars(rows)).zones[0];
  assert.equal(z.broken, true);
  assert.equal(z.brokenAt, day(16));
  assert.equal(z.touches, 0, "visits after the break are not tests of a live zone");
});

test("an untrusted low is never used to build a base", () => {
  const b = bars(DROP_BASE_RALLY);
  for (const i of [6, 7, 8, 9]) b[i].trusted.low = false;
  const res = demandZones(b);
  assert.equal(res.zones.length, 0, "the base cannot be measured, so no zone is reported");
  assert.equal(res.status, INDICATOR_STATUS.VALID);
});

test("a null low is dropped from the base, never coerced into a floor of 0", () => {
  const b = bars(DROP_BASE_RALLY);
  b[7].low = null;
  const res = demandZones(b);

  // The 4-bar base cannot be measured any more, so the module falls back to the
  // longest base it CAN see (bars 8-9) rather than reading the hole as 0.
  assert.equal(res.zones.length, 1);
  const z = res.zones[0];
  assert.equal(z.basisBars, 2, "the unreadable bar is excluded from the base, not valued at 0");
  assert.equal(z.low, 99.4, "Number(null)===0 must never reach the zone floor");
  assert.equal(z.formedAt, day(9));
});

test("close-only bars report FIELD_UNAVAILABLE rather than a fabricated box", () => {
  const b = DROP_BASE_RALLY.map(([close], i) => ({
    date: day(i), close, high: null, low: null, volume: null,
    trusted: { close: true, high: false, low: false, open: false, volume: false },
  }));
  const res = demandZones(b);
  assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.deepEqual(res.zones, []);
  assert.equal(res.observations, 0);
});

test("too few bars is INSUFFICIENT_HISTORY, carrying what it did have", () => {
  const res = demandZones(bars(DROP_BASE_RALLY.slice(0, 3)));
  assert.equal(res.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
  assert.equal(res.observations, 3);
  assert.equal(res.lookback, ZONE_DEFAULTS.minBaseBars + ZONE_DEFAULTS.departureBars);
  assert.deepEqual(res.zones, []);
  assert.deepEqual(demandZones([]).zones, []);
  assert.deepEqual(demandZones(null).zones, []);
});

test("staleness is only claimed when the caller supplies the reference date", () => {
  const b = bars(DROP_BASE_RALLY);
  const fresh = demandZones(b);
  assert.equal(fresh.status, INDICATOR_STATUS.VALID, "no clock is read inside the module");

  const stale = demandZones(b, { asOf: day(60) });
  assert.equal(stale.status, INDICATOR_STATUS.DATA_STALE);
  assert.equal(stale.zones[0].status, INDICATOR_STATUS.DATA_STALE);
  assert.ok(stale.zones[0].low === fresh.zones[0].low, "stale data is flagged, not discarded");
});

test("priceZones returns both sides and does not mutate the input bars", () => {
  const b = bars(DROP_BASE_RALLY);
  const before = JSON.stringify(b);
  const both = priceZones(b);
  assert.equal(both.demand.zones.length, 1);
  assert.equal(both.supply.zones.length, 0);
  assert.equal(JSON.stringify(b), before, "pure function: bars in, facts out");
});

// ── volume ────────────────────────────────────────────────────────────────────────

/** Volume-only bars; `volumes` may contain null for an unreported session. */
function volBars(volumes, { trusted = true } = {}) {
  return volumes.map((volume, i) => ({
    date: day(i), close: 100, high: 101, low: 99, volume,
    trusted: { close: true, high: true, low: true, open: false, volume },
  })).map((b, i) => ({
    ...b,
    trusted: { ...b.trusted, volume: trusted && volumes[i] !== null && volumes[i] !== undefined },
  }));
}

test("volumeRatio is the latest volume over the average of the prior N", () => {
  const res = volumeRatio(volBars([100, 200, 300, 400]), { period: 3 });
  assert.equal(res.status, INDICATOR_STATUS.VALID);
  assert.equal(res.value, 2, "400 / mean(100,200,300) = 400 / 200");
  assert.equal(res.observations, 3);
  assert.equal(res.lookback, 3);
  assert.equal(res.asOf, day(3));
  assert.equal(res.detail.average, 200);
  assert.equal(res.detail.latest, 400);

  const quiet = volumeRatio(volBars([100, 200, 300, 100]), { period: 3 });
  assert.equal(quiet.value, 0.5);
});

test("the latest bar's average excludes the latest bar itself", () => {
  // If the latest were included the mean would be 250 and the ratio 1.6.
  const res = volumeRatio(volBars([100, 200, 300, 400]), { period: 3 });
  assert.notEqual(res.value, 1.6);
});

test("absent volume is FIELD_UNAVAILABLE — an unreported day is not a quiet day", () => {
  const res = volumeRatio(volBars([100, 200, 300, null]), { period: 3 });
  assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(res.value, null, "never 0, which would read as total silence");
});

test("untrusted volume is refused exactly like an absent one", () => {
  const b = volBars([100, 200, 300, 400]);
  b[3].trusted.volume = false;
  const res = volumeRatio(b, { period: 3 });
  assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(res.value, null);
});

test("a gap in the baseline shortens the sample instead of averaging in a zero", () => {
  const res = volumeRatio(volBars([100, null, 300, 400]), { period: 3 });
  assert.equal(res.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
  assert.equal(res.value, null);
  assert.equal(res.observations, 2, "two real observations, honestly reported");
  // The two wrong answers this guards against:
  assert.notEqual(res.value, 3, "mean(100,0,300)=133.3 → 3.0 would treat null as zero volume");
  assert.notEqual(res.value, 2, "mean(100,300)=200 → 2.0 would silently shorten the window");
});

test("a zero-volume baseline does not divide by zero", () => {
  const res = volumeRatio(volBars([0, 0, 0, 400]), { period: 3 });
  assert.equal(res.value, null);
  assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(res.detail.average, 0, "the average is known; the ratio is not");
  assert.ok(!Number.isNaN(res.value) && res.value !== Infinity);

  const allZero = volumeRatio(volBars([0, 0, 0, 0]), { period: 3 });
  assert.equal(allZero.value, null);
  assert.ok(Number.isFinite(allZero.value) === false);
});

test("volumeRatio never returns a non-finite number, whatever it is fed", () => {
  const hostile = [
    [], [100], [0, 0], [null, null, null, null], [100, 200, 0], [0, 0, 0, 1],
  ];
  for (const vols of hostile) {
    for (const period of [1, 3, 20]) {
      const res = volumeRatio(volBars(vols), { period });
      assert.ok(res.value === null || Number.isFinite(res.value),
        `value must be a finite number or null, got ${res.value}`);
      assert.ok(Object.values(INDICATOR_STATUS).includes(res.status));
      assert.ok(Number.isInteger(res.observations));
    }
  }
  assert.equal(volumeRatio([], { period: 3 }).status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
});

test("relativeVolumeSeries stays index-aligned with the bars it was given", () => {
  const vols = [100, 200, 300, 400, 500, 600];
  const series = relativeVolumeSeries(volBars(vols), { period: 3 });
  assert.equal(series.length, vols.length, "uncomputable bars are kept, not dropped");

  for (let i = 0; i < 3; i += 1) {
    assert.equal(series[i].status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
    assert.equal(series[i].value, null);
    assert.equal(series[i].asOf, day(i), "each point still names the bar it belongs to");
    assert.equal(series[i].index, i);
  }
  assert.equal(series[3].status, INDICATOR_STATUS.VALID);
  assert.equal(series[3].value, 2);              // 400 / mean(100,200,300)
  assert.equal(series[5].value, 1.5);            // 600 / mean(300,400,500)
  assert.equal(series[5].observations, 3);
});

test("relativeVolumeSeries reports the missing bar and keeps computing after it", () => {
  const series = relativeVolumeSeries(volBars([100, 200, null, 400, 500, 600]), { period: 2 });
  assert.equal(series[2].status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(series[3].status, INDICATOR_STATUS.INSUFFICIENT_HISTORY,
    "the window straddling the gap holds one observation, not two");
  assert.equal(series[5].status, INDICATOR_STATUS.VALID);
  assert.equal(series[5].value, 1.3333, "600 / mean(400,500), rounded once at the edge");
  assert.deepEqual(relativeVolumeSeries(null), []);
});
