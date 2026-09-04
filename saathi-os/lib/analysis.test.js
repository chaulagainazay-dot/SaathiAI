/**
 * Chart analysis engine — structure, confluence, setups, plans, narration boundary.
 *
 * The load-bearing assertions are the negative ones: no invented levels, no advice,
 * conflicts surfaced rather than buried, and a language model that cannot introduce
 * a number the engine did not compute.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  swingPoints, marketStructure, trendFromMovingAverages, levels, pivotPoints,
  priceAction, volumeState,
} from "./analysis/structure.js";
import { signalSet, confluence, invalidation, BIAS } from "./analysis/confluence.js";
import { detectSetups, buildPlan, challenge, SETUP } from "./analysis/setup.js";
import { analyzeChart, narrationPrompt } from "./analysis/analyze.js";

const day = (i) => new Date(Date.UTC(2024, 0, 7 + i)).toISOString().slice(0, 10);

/** Bars that zig-zag upward: higher highs and higher lows. */
function uptrend(n = 80, { withRange = true, withVolume = true } = {}) {
  const bars = [];
  for (let i = 0; i < n; i += 1) {
    const base = 100 + i * 0.8 + Math.sin(i / 4) * 6;
    bars.push({
      date: day(i),
      close: +base.toFixed(2),
      high: withRange ? +(base + 2).toFixed(2) : null,
      low: withRange ? +(base - 2).toFixed(2) : null,
      open: withRange ? +(base - 0.5).toFixed(2) : null,
      volume: withVolume ? 1000 + (i % 7) * 120 : null,
    });
  }
  return bars;
}

function downtrend(n = 80) {
  return uptrend(n).map((b, i) => {
    const base = 180 - i * 0.8 + Math.sin(i / 4) * 6;
    return { ...b, close: +base.toFixed(2), high: +(base + 2).toFixed(2), low: +(base - 2).toFixed(2) };
  });
}

// ── structure ────────────────────────────────────────────────────────────────────
test("swing points need confirmation on both sides", () => {
  const { highs, lows } = swingPoints(uptrend(60), 3);
  assert.ok(highs.length > 0 && lows.length > 0);
  for (const h of highs) assert.ok(h.index >= 3, "a swing cannot be confirmed without bars either side");
});

test("structure is UNCLEAR rather than guessed when swings are missing", () => {
  const s = marketStructure({ highs: [{ price: 1 }], lows: [] });
  assert.equal(s.structure, "UNCLEAR");
});

test("uptrend and downtrend are classified from real swings", () => {
  assert.equal(marketStructure(swingPoints(uptrend(80), 3)).structure, "UPTREND");
  assert.equal(marketStructure(swingPoints(downtrend(80), 3)).structure, "DOWNTREND");
});

test("moving-average trend reports UNKNOWN when no MA exists", () => {
  assert.equal(trendFromMovingAverages(100, {}).trend, "UNKNOWN");
  assert.equal(trendFromMovingAverages(100, { sma50: 90, ema20: 95 }).trend, "BULLISH");
  assert.equal(trendFromMovingAverages(100, { sma50: 110, ema20: 105 }).trend, "BEARISH");
  assert.equal(trendFromMovingAverages(100, { sma50: 110, ema20: 95 }).trend, "MIXED");
});

test("levels come from repeated touches and are placed relative to price", () => {
  const bars = uptrend(80);
  const price = bars[bars.length - 1].close;
  const lv = levels(swingPoints(bars, 3), price);
  for (const r of lv.resistance) assert.ok(r.price > price, "resistance must sit above price");
  for (const s of lv.support) assert.ok(s.price < price, "support must sit below price");
});

test("pivots require a real high/low and are null otherwise", () => {
  assert.equal(pivotPoints({ close: 10, high: null, low: null }), null);
  const p = pivotPoints({ high: 110, low: 90, close: 100 });
  assert.equal(p.pivot, 100);
  assert.ok(p.r1 > p.pivot && p.s1 < p.pivot);
});

test("volume state is UNAVAILABLE when volume is not reported", () => {
  const noVol = uptrend(60, { withVolume: false });
  assert.equal(volumeState(noVol).state, "UNAVAILABLE");
  assert.ok(["NORMAL", "EXPANDING", "CONTRACTING"].includes(volumeState(uptrend(60)).state));
});

// ── confluence: conflicts must be visible ────────────────────────────────────────
test("missing indicators are UNAVAILABLE, never counted as evidence", () => {
  const sigs = signalSet({
    structure: { structure: "UPTREND", reason: "x" },
    maTrend: { trend: "UNKNOWN", above: [], below: [] },
    indicators: {},                       // nothing available
    price: 100, action: null, volume: { state: "UNAVAILABLE" }, levels: {},
  });
  const conf = confluence(sigs);
  assert.ok(conf.counts.unavailable >= 4);
  assert.equal(conf.bias, BIAS.INSUFFICIENT, "mostly-missing evidence cannot produce a bias");
  assert.equal(conf.confidence, "NONE");
});

test("a conflicted board is reported as CONFLICTED, not resolved into a call", () => {
  const sigs = signalSet({
    structure: { structure: "UPTREND", reason: "hh/hl" },
    maTrend: { trend: "BEARISH", above: [], below: ["SMA50"] },
    indicators: {
      rsi: { status: "VALID", value: 72 },                       // bearish (overbought)
      macd: { status: "VALID", value: { histogram: 0.5 } },      // bullish
      bollinger: { status: "VALID", value: { percentB: 0.5 } },  // neutral
    },
    price: 100,
    action: { changePct: 1, bars: 10, upDays: 5, downDays: 5, closedNearHigh: false, closedNearLow: false },
    volume: { state: "NORMAL", ratio: 1 },
    levels: { support: [{ price: 95, distancePct: -5, touches: 2 }], resistance: [{ price: 105, distancePct: 5, touches: 2 }] },
  });
  const conf = confluence(sigs);
  assert.equal(conf.bias, BIAS.CONFLICTED);
  assert.ok(conf.conflicting.length > 0, "conflicts must be listed, not hidden");
});

test("invalidation always states what would break the read", () => {
  const conf = { bias: BIAS.BULLISH, counts: { unavailable: 1 }, confidence: "MEDIUM" };
  const inv = invalidation({ conf, levels: { support: [{ price: 95, touches: 3 }] }, price: 100, atr: 2 });
  assert.ok(inv.some((s) => /below 95/.test(s)));
  assert.ok(inv.some((s) => /unavailable/i.test(s)));
});

// ── setups ───────────────────────────────────────────────────────────────────────
test("every setup carries a tradeoff, never only a case for it", () => {
  const bars = uptrend(80);
  const price = bars[bars.length - 1].close;
  const lv = levels(swingPoints(bars, 3), price);
  const setups = detectSetups({
    conf: { bias: BIAS.BULLISH, counts: {} },
    structure: { structure: "UPTREND" },
    levels: lv, price, action: priceAction(bars), volume: volumeState(bars),
    indicators: { rsi: { status: "VALID", value: 60 }, macd: { status: "VALID", value: { histogram: 1 } } },
    atr: 2,
  });
  assert.ok(setups.length >= 1);
  for (const s of setups) {
    assert.ok(s.tradeoff && s.tradeoff.length > 10, `${s.type} must state its tradeoff`);
  }
});

test("no setup yields NONE — 'nothing to trade' is a valid answer", () => {
  const setups = detectSetups({
    conf: { bias: BIAS.NEUTRAL, counts: {} },
    structure: { structure: "UNCLEAR" },
    levels: { support: [], resistance: [] },
    price: 100, action: null, volume: { state: "UNAVAILABLE" }, indicators: {}, atr: null,
  });
  assert.equal(setups[0].type, SETUP.NONE);
});

// ── plan: never invents, never advises ───────────────────────────────────────────
test("a plan without derivable targets states so instead of inventing one", () => {
  const plan = buildPlan({
    setup: { type: SETUP.CONTINUATION, trigger: "t", confirmation: [] },
    conf: { bias: BIAS.BULLISH, confidence: "MEDIUM", counts: {} },
    levels: { support: [], resistance: [] },   // nothing overhead
    price: 100, atr: 2, instrument: "X", asOf: "2024-01-01", source: "test",
  });
  assert.equal(plan.targets.length, 0);
  assert.ok(plan.notes.some((n) => /cannot be derived/i.test(n)));
});

test("a plan is explicitly not advice and claims no authority", () => {
  const plan = buildPlan({
    setup: { type: SETUP.NONE, trigger: "-", confirmation: [] },
    conf: { bias: BIAS.NEUTRAL, confidence: "LOW", counts: {} },
    levels: { support: [], resistance: [] }, price: 100, atr: null,
    instrument: "X", asOf: "d", source: "s",
  });
  assert.equal(plan.authority.isAdvice, false);
  assert.match(plan.authority.note, /Guardian/);
  assert.match(plan.authority.note, /no order/i);
});

test("poor reward-to-risk produces WAIT, not an encouraging verdict", () => {
  const plan = buildPlan({
    setup: { type: SETUP.PULLBACK, trigger: "t", confirmation: [] },
    conf: { bias: BIAS.BULLISH, confidence: "HIGH", counts: {} },
    levels: { support: [{ price: 99, touches: 2 }], resistance: [{ price: 101, touches: 2 }] },
    price: 100, atr: 1, instrument: "X", asOf: "d", source: "s",
  });
  assert.ok(plan.riskReward !== null);
  if (plan.riskReward < 1.5) {
    assert.match(plan.verdict, /WAIT/);
    assert.ok(plan.notes.some((n) => /below the 1.5:1/.test(n)));
  }
});

test("insufficient evidence yields AVOID", () => {
  const plan = buildPlan({
    setup: { type: SETUP.NONE, trigger: "-", confirmation: [] },
    conf: { bias: BIAS.INSUFFICIENT, confidence: "NONE", counts: {} },
    levels: { support: [], resistance: [] }, price: 100, atr: null,
    instrument: "X", asOf: "d", source: "s",
  });
  assert.match(plan.verdict, /AVOID/);
});

test("challenge argues both sides and names what is overlooked", () => {
  const c = challenge({
    conf: { bias: BIAS.BULLISH, counts: { bullish: 2, bearish: 1, unavailable: 2 },
            agreeing: [{ name: "A", direction: "BULLISH", detail: "d" }],
            conflicting: [{ name: "B", direction: "BEARISH", detail: "d" }] },
    setup: { type: SETUP.CONTINUATION },
    levels: { support: [] },
    indicators: { rsi: { status: "VALID", value: 75 } },
    structure: { structure: "UNCLEAR" },
  });
  assert.ok(c.bullCase.length && c.bearCase.length, "both sides must be argued");
  assert.ok(c.overlooked.some((s) => /unavailable/i.test(s)));
  assert.ok(c.overlooked.some((s) => /overbought/i.test(s)));
  assert.ok(c.wouldConvince.length > 0);
});

// ── orchestrator ─────────────────────────────────────────────────────────────────
test("short history refuses to analyse rather than guessing", () => {
  const a = analyzeChart(uptrend(10), {}, { instrument: "X" });
  assert.equal(a.ok, false);
  assert.equal(a.reason, "INSUFFICIENT_HISTORY");
});

test("a full analysis produces every section from computed evidence", () => {
  const bars = uptrend(90);
  const a = analyzeChart(bars, {
    rsi: { status: "VALID", value: 58 },
    macd: { status: "VALID", value: { histogram: 0.8 } },
    bollinger: { status: "VALID", value: { percentB: 0.7 } },
    sma: { status: "VALID", value: bars[bars.length - 1].close * 0.95 },
    ema: { status: "VALID", value: bars[bars.length - 1].close * 0.97 },
    atr: { status: "VALID", value: 2.2 },
  }, { instrument: "TEST", source: "unit", adjustment: "UNADJUSTED" });

  assert.equal(a.ok, true);
  for (const k of ["structure", "maTrend", "levels", "signals", "confluence", "setups", "plan", "challenge", "invalidation"]) {
    assert.ok(a[k], `missing ${k}`);
  }
  assert.equal(a.authority.isAdvice, false);
  assert.ok(a.signals.length >= 6);
});

test("range-derived work is skipped when the caller distrusts high/low", () => {
  const bars = uptrend(90);
  const a = analyzeChart(bars, {}, { instrument: "X", fieldTrust: { range: false } });
  assert.equal(a.pivots, null, "pivots need a trusted high/low");
});

// ── narration boundary: the model may not add numbers ────────────────────────────
test("narration prompt forbids inventing numbers and giving advice", () => {
  const a = analyzeChart(uptrend(90), { rsi: { status: "VALID", value: 58 } }, { instrument: "T", source: "unit" });
  const p = narrationPrompt(a);
  assert.match(p, /Every number you use must appear in the FACTS/i);
  assert.match(p, /Do not compute, round, extrapolate or invent/i);
  assert.match(p, /Do not give investment advice/i);
  assert.match(p, /Lead with what conflicts/i);
});

test("narration prompt carries the facts it permits, including unavailability", () => {
  const a = analyzeChart(uptrend(90, { withVolume: false }), {}, { instrument: "T", source: "unit" });
  const p = narrationPrompt(a);
  assert.match(p, /Instrument: T/);
  assert.match(p, /Bias:/);
  assert.match(p, /UNAVAILABLE/, "unavailable inputs must reach the model as unavailable");
});

test("no narration for an analysis that failed", () => {
  assert.equal(narrationPrompt(analyzeChart(uptrend(5), {}, {})), null);
});
