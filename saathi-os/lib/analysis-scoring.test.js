/**
 * Unified signal scoring.
 *
 * The load-bearing assertions here are the negative ones. A missing component must
 * change the WEIGHT BASE, not the value being weighted: the two bugs this module
 * exists to prevent are (a) scoring a number nobody computed, and (b) an absent
 * reading arriving as Number(null) === 0, which on the RSI scale is the strongest
 * bullish reading available. Every "must not contribute as 0" test below is a
 * regression test for a bug that actually shipped.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  scoreSignal, scoreDisplay, SIGNAL_DIRECTION, DROP_REASON, COMPONENT_ROLE,
  DEFAULT_WEIGHTS, INDICATOR_STATUS,
} from "./analysis/scoring.js";

/** The module rounds to 6dp; expected values are rounded the same way. */
const r6 = (n) => +n.toFixed(6);

/** A typed reading in the shape lib/nepse/indicators.js emits. */
const reading = (value, status = INDICATOR_STATUS.VALID, observations = 120) =>
  ({ indicator: "x", value, status, observations });

/** Deliberately extreme, unambiguous readings so every sub-score is exact. */
const RSI_OVERSOLD = reading(25); //            -> +0.6
const RSI_OVERBOUGHT = reading(75); //          -> -0.6
const MACD_UP = reading({ macd: 1, signal: 0, histogram: 1 }); //   -> +1 (clamped)
const MACD_DOWN = reading({ macd: -1, signal: 0, histogram: -1 }); // -> -1 (clamped)
const STOCH_OVERSOLD = reading(15); //          -> +0.6
const BB_AT_LOWER = reading({ percentB: 0.05 }); //  -> +0.25
const ADX_STRONG = reading(45); //              -> strength 1
const VOL_HEAVY = reading(2.5); //              -> strength 1

const byName = (list) => Object.fromEntries(list.map((d) => [d.component, d]));

test("full inputs: weighted mean of every component, weights untouched", () => {
  const r = scoreSignal({
    rsi: RSI_OVERSOLD,
    macd: MACD_UP,
    stochastic: STOCH_OVERSOLD,
    bollinger: BB_AT_LOWER,
    adx: ADX_STRONG,
    volumeRatio: VOL_HEAVY,
  });

  assert.equal(r.status, INDICATOR_STATUS.VALID);
  assert.equal(r.dropped.length, 0);
  assert.equal(r.contributors.length, 6);
  assert.equal(r.basis.directionalContributors, 4);
  assert.equal(r.basis.convictionContributors, 2);

  // Nothing dropped -> the weights used are the declared weights.
  assert.deepEqual(r.weightsUsed, {
    rsi: DEFAULT_WEIGHTS.rsi,
    macd: DEFAULT_WEIGHTS.macd,
    stochastic: DEFAULT_WEIGHTS.stochastic,
    bollinger: DEFAULT_WEIGHTS.bollinger,
    adx: DEFAULT_WEIGHTS.adx,
    volumeRatio: DEFAULT_WEIGHTS.volumeRatio,
  });

  // 0.3(+0.6) + 0.3(+1) + 0.2(+0.6) + 0.2(+0.25) = 0.65
  assert.equal(r.raw, 0.65);
  assert.equal(r.score, 82.5);
  assert.equal(r.direction, SIGNAL_DIRECTION.BULLISH);
  assert.equal(r.confidence, 1); // full coverage, fully confirmed
  assert.equal(r.observations, 6);
});

test("partial inputs: surviving weights are renormalised, not zero-filled", () => {
  const r = scoreSignal({ rsi: RSI_OVERSOLD, macd: MACD_UP });

  assert.equal(r.status, INDICATOR_STATUS.VALID);
  // 0.3 and 0.3 of an original 1.0 directional pool -> 0.5 / 0.5 of 0.6.
  assert.deepEqual(r.weightsUsed, { rsi: 0.5, macd: 0.5 });
  assert.equal(r.raw, 0.8); // 0.5(+0.6) + 0.5(+1)
  assert.equal(r.score, 90);

  // Zero-filling the two missing components would have given
  // 0.3(0.6) + 0.3(1) + 0.2(0) + 0.2(0) = 0.48 — a materially weaker, wrong number.
  assert.notEqual(r.raw, 0.48);

  const drops = byName(r.dropped);
  assert.equal(drops.stochastic.reason, DROP_REASON.NOT_PROVIDED);
  assert.equal(drops.bollinger.reason, DROP_REASON.NOT_PROVIDED);
  assert.equal(drops.adx.reason, DROP_REASON.NOT_PROVIDED);
  assert.equal(drops.volumeRatio.reason, DROP_REASON.NOT_PROVIDED);

  // Coverage records that this is 0.6 of the intended evidence base.
  assert.equal(r.basis.coverage, 0.6);
  assert.equal(r.basis.directionalContributors, 2);
  assert.equal(r.basis.directionalOffered, 4);
});

test("renormalised directional weights always sum to 1", () => {
  const subsets = [
    { rsi: RSI_OVERSOLD, macd: MACD_UP, stochastic: STOCH_OVERSOLD },
    { macd: MACD_UP, bollinger: BB_AT_LOWER },
    { rsi: RSI_OVERBOUGHT, stochastic: STOCH_OVERSOLD, bollinger: BB_AT_LOWER },
    { rsi: RSI_OVERSOLD, macd: MACD_UP, stochastic: STOCH_OVERSOLD, bollinger: BB_AT_LOWER },
  ];
  for (const s of subsets) {
    const r = scoreSignal(s);
    const sum = r.contributors
      .filter((c) => c.role === COMPONENT_ROLE.DIRECTIONAL)
      .reduce((a, c) => a + c.weightUsed, 0);
    assert.ok(Math.abs(sum - 1) < 1e-5, `weights summed to ${sum}`);
    assert.ok(r.score >= 0 && r.score <= 100);
  }
});

test("a null-valued component is dropped, never scored as 0", () => {
  // A bearish surround, so the phantom shows up as an inversion rather than as a
  // rounding difference: MACD -1, and two readings that genuinely say nothing.
  const base = {
    macd: MACD_DOWN,
    stochastic: reading(50), //          %K mid-range -> 0
    bollinger: reading({ percentB: 0.5 }), // mid-band -> 0
  };

  const withNullRsi = scoreSignal({ ...base, rsi: reading(null) });
  const withoutRsi = scoreSignal(base);
  const withZeroRsi = scoreSignal({ ...base, rsi: reading(0) });

  // A null RSI must land exactly where an absent RSI lands.
  assert.equal(withNullRsi.raw, withoutRsi.raw);
  assert.deepEqual(withNullRsi.weightsUsed, withoutRsi.weightsUsed);
  assert.equal("rsi" in withNullRsi.weightsUsed, false);
  assert.equal(withNullRsi.raw, r6(-1 * (0.3 / 0.7))); // renormalised over the survivors

  // Number(null) === 0 would have read as RSI 0 — maximally oversold, +0.6, the
  // strongest bullish vote on the scale. That phantom drags a bearish read to a
  // draw, which is exactly the bug that shipped.
  assert.equal(withZeroRsi.contributors.find((c) => c.component === "rsi").subScore, 0.6);
  assert.equal(withZeroRsi.raw, r6(0.3 * 0.6 + 0.3 * -1));
  assert.ok(withZeroRsi.raw > withNullRsi.raw);
  assert.equal(withNullRsi.direction, SIGNAL_DIRECTION.BEARISH);
  assert.equal(withZeroRsi.direction, SIGNAL_DIRECTION.NEUTRAL);

  const drop = byName(withNullRsi.dropped).rsi;
  assert.equal(drop.reason, DROP_REASON.VALUE_NULL);
  assert.equal(withNullRsi.contributors.some((c) => c.component === "rsi"), false);
});

test("undefined and empty-string values are refused before any coercion", () => {
  for (const bad of [undefined, ""]) {
    const r = scoreSignal({
      rsi: reading(bad), macd: MACD_UP, stochastic: STOCH_OVERSOLD, bollinger: BB_AT_LOWER,
    });
    assert.equal(byName(r.dropped).rsi.reason, DROP_REASON.VALUE_NULL);
    assert.equal("rsi" in r.weightsUsed, false);
  }
  // Number("") === 0 and Number(undefined) is NaN; neither may reach the maths.
  const r = scoreSignal({ rsi: reading(""), macd: MACD_UP, stochastic: STOCH_OVERSOLD });
  assert.ok(Number.isFinite(r.raw));
});

test("a bare number is not a reading — the static-seed bug cannot recur", () => {
  const r = scoreSignal({
    rsi: 25, // a number nobody computed, with no status and no provenance
    macd: MACD_UP,
    stochastic: STOCH_OVERSOLD,
    bollinger: BB_AT_LOWER,
  });
  assert.equal(byName(r.dropped).rsi.reason, DROP_REASON.UNTYPED_READING);
  assert.equal("rsi" in r.weightsUsed, false);

  // An object without a status is equally untyped: plausible, unprovenanced.
  const r2 = scoreSignal({
    rsi: { value: 25 }, macd: MACD_UP, stochastic: STOCH_OVERSOLD, bollinger: BB_AT_LOWER,
  });
  assert.equal(byName(r2.dropped).rsi.reason, DROP_REASON.UNTYPED_READING);
});

test("non-VALID statuses are dropped and the status is reported", () => {
  const r = scoreSignal({
    rsi: reading(25, INDICATOR_STATUS.DATA_STALE),
    stochastic: reading(15, INDICATOR_STATUS.INSUFFICIENT_HISTORY),
    bollinger: reading({ percentB: 0.05 }, INDICATOR_STATUS.FIELD_UNAVAILABLE),
    macd: MACD_UP,
    adx: ADX_STRONG,
  });
  const drops = byName(r.dropped);
  assert.equal(drops.rsi.reason, DROP_REASON.STATUS_NOT_VALID);
  assert.equal(drops.rsi.status, INDICATOR_STATUS.DATA_STALE);
  assert.equal(drops.stochastic.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
  assert.equal(drops.bollinger.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);

  // One directional survivor is below the floor: no score is manufactured from it.
  assert.equal(r.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
  assert.equal(r.score, null);
});

test("every component invalid: a status, never a score of 0", () => {
  const r = scoreSignal({
    rsi: reading(null),
    macd: reading(undefined),
    stochastic: 15,
    bollinger: reading({ percentB: null }),
    adx: reading(null),
    volumeRatio: reading(""),
  });
  assert.equal(r.score, null);
  assert.equal(r.raw, null);
  assert.equal(r.confidence, null);
  assert.notEqual(r.score, 0);
  assert.notEqual(r.score, 50);
  assert.equal(r.direction, SIGNAL_DIRECTION.UNKNOWN);
  assert.equal(r.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(r.contributors.length, 0);
  assert.deepEqual(r.weightsUsed, {});
  assert.equal(scoreDisplay(r), "—");
});

test("when every directional reading failed the same way, that status is passed through", () => {
  const stale = (v) => reading(v, INDICATOR_STATUS.DATA_STALE);
  const r = scoreSignal({
    rsi: stale(25), macd: stale({ macd: 1, signal: 0, histogram: 1 }),
    stochastic: stale(15), bollinger: stale({ percentB: 0.05 }),
  });
  assert.equal(r.status, INDICATOR_STATUS.DATA_STALE);
  assert.equal(r.score, null);
});

test("confidence falls as contributors fall", () => {
  const full = scoreSignal({
    rsi: RSI_OVERSOLD, macd: MACD_UP, stochastic: STOCH_OVERSOLD, bollinger: BB_AT_LOWER,
    adx: ADX_STRONG, volumeRatio: VOL_HEAVY,
  });
  const noVolume = scoreSignal({
    rsi: RSI_OVERSOLD, macd: MACD_UP, stochastic: STOCH_OVERSOLD, bollinger: BB_AT_LOWER,
    adx: ADX_STRONG,
  });
  const noConviction = scoreSignal({
    rsi: RSI_OVERSOLD, macd: MACD_UP, stochastic: STOCH_OVERSOLD, bollinger: BB_AT_LOWER,
  });
  const threeDirectional = scoreSignal({
    rsi: RSI_OVERSOLD, macd: MACD_UP, stochastic: STOCH_OVERSOLD,
  });
  const twoDirectional = scoreSignal({ rsi: RSI_OVERSOLD, macd: MACD_UP });

  const chain = [full, noVolume, noConviction, threeDirectional, twoDirectional];
  for (let i = 1; i < chain.length; i += 1) {
    assert.ok(
      chain[i].confidence < chain[i - 1].confidence,
      `confidence ${chain[i].confidence} did not fall below ${chain[i - 1].confidence} at step ${i}`,
    );
  }
  assert.equal(full.confidence, 1);
  assert.equal(noConviction.confidence, 0.5); // full directional coverage, nothing confirming it
  assert.equal(twoDirectional.confidence, 0.3); // 0.6 coverage, unconfirmed
});

test("dropping a WEAK conviction reading lowers confidence too — absence is not confirmation", () => {
  const weakVolume = scoreSignal({
    rsi: RSI_OVERSOLD, macd: MACD_UP, adx: ADX_STRONG, volumeRatio: reading(0.3),
  });
  const noVolume = scoreSignal({ rsi: RSI_OVERSOLD, macd: MACD_UP, adx: ADX_STRONG });
  assert.ok(noVolume.confidence < weakVolume.confidence);
});

test("conviction components never move the score or the direction", () => {
  const directional = { rsi: RSI_OVERBOUGHT, macd: MACD_DOWN };
  const weak = scoreSignal({ ...directional, adx: reading(10), volumeRatio: reading(0.4) });
  const strong = scoreSignal({ ...directional, adx: ADX_STRONG, volumeRatio: VOL_HEAVY });

  assert.equal(weak.raw, strong.raw);
  assert.equal(weak.direction, strong.direction);
  assert.equal(strong.direction, SIGNAL_DIRECTION.BEARISH);
  assert.equal(strong.raw, -0.8); // 0.5(-0.6) + 0.5(-1)
  assert.equal(strong.score, 10);
  assert.ok(weak.confidence < strong.confidence);

  // They are recorded as conviction, with no directional vote at all.
  const adx = strong.contributors.find((c) => c.component === "adx");
  assert.equal(adx.role, COMPONENT_ROLE.CONVICTION);
  assert.equal(adx.subScore, null);
  assert.equal(adx.strength, 1);
});

test("a genuine draw scores 50 and is distinguishable from having no data", () => {
  const draw = scoreSignal({ rsi: reading(50), macd: reading({ macd: 1, signal: 1, histogram: 0 }) });
  assert.equal(draw.status, INDICATOR_STATUS.VALID);
  assert.equal(draw.raw, 0);
  assert.equal(draw.score, 50);
  assert.equal(draw.direction, SIGNAL_DIRECTION.NEUTRAL);

  const nothing = scoreSignal({});
  assert.equal(nothing.score, null);
  assert.notEqual(nothing.score, draw.score);
  assert.notEqual(nothing.status, draw.status);
});

test("out-of-range readings are dropped rather than clamped into plausibility", () => {
  const r = scoreSignal({
    rsi: reading(150), stochastic: reading(-4), volumeRatio: reading(0),
    macd: MACD_UP, bollinger: BB_AT_LOWER,
  });
  const drops = byName(r.dropped);
  assert.equal(drops.rsi.reason, DROP_REASON.VALUE_OUT_OF_RANGE);
  assert.equal(drops.stochastic.reason, DROP_REASON.VALUE_OUT_OF_RANGE);
  // A volume RATIO of 0 is a broken division, not "no volume".
  assert.equal(drops.volumeRatio.reason, DROP_REASON.VALUE_OUT_OF_RANGE);
  assert.deepEqual(Object.keys(r.weightsUsed).sort(), ["bollinger", "macd"]);
});

test("collapsed Bollinger bands (percentB null) drop out instead of reading as below the lower band", () => {
  const collapsed = scoreSignal({
    rsi: RSI_OVERSOLD, macd: MACD_UP, bollinger: reading({ percentB: null, middle: 100 }),
  });
  const omitted = scoreSignal({ rsi: RSI_OVERSOLD, macd: MACD_UP });
  assert.equal(byName(collapsed.dropped).bollinger.reason, DROP_REASON.VALUE_NULL);
  assert.equal(collapsed.raw, omitted.raw);
  // percentB 0 would have scored +0.5 (below the lower band) — a bullish phantom.
  const zeroB = scoreSignal({ rsi: RSI_OVERSOLD, macd: MACD_UP, bollinger: reading({ percentB: 0 }) });
  assert.notEqual(zeroB.raw, collapsed.raw);
});

test("MACD without comparable lines contributes sign only, at half strength", () => {
  const scaled = scoreSignal({ rsi: RSI_OVERSOLD, macd: MACD_UP });
  const bare = scoreSignal({ rsi: RSI_OVERSOLD, macd: reading(1) });
  assert.equal(scaled.contributors.find((c) => c.component === "macd").subScore, 1);
  assert.equal(bare.contributors.find((c) => c.component === "macd").subScore, 0.5);
  assert.match(bare.contributors.find((c) => c.component === "macd").reading, /unscaled/);

  // A histogram can be restated from the two lines, but nothing is invented when
  // neither is present.
  const derived = scoreSignal({ rsi: RSI_OVERSOLD, macd: reading({ macd: 2, signal: 1 }) });
  assert.equal(derived.contributors.find((c) => c.component === "macd").value, 1);
  const empty = scoreSignal({ rsi: RSI_OVERSOLD, macd: reading({ notALine: 3 }) });
  assert.equal(byName(empty.dropped).macd.reason, DROP_REASON.FIELD_MISSING);
});

test("the contributor floor is explicit and overridable", () => {
  const one = { rsi: RSI_OVERSOLD };
  const refused = scoreSignal(one);
  assert.equal(refused.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
  assert.equal(refused.score, null);
  assert.equal(refused.basis.minContributors, 2);

  const allowed = scoreSignal(one, { minContributors: 1 });
  assert.equal(allowed.status, INDICATOR_STATUS.VALID);
  assert.deepEqual(allowed.weightsUsed, { rsi: 1 });
  assert.equal(allowed.raw, 0.6);
  assert.equal(allowed.score, 80);
  assert.equal(scoreDisplay(allowed), "80.0 (1/4)");
});

test("weight overrides are validated; a bad weight is a caller bug, not silent data loss", () => {
  const r = scoreSignal(
    { rsi: RSI_OVERSOLD, macd: MACD_UP },
    { weights: { rsi: 0.9, macd: 0.1 } },
  );
  assert.equal(r.weightsUsed.rsi, 0.9);
  assert.equal(r.weightsUsed.macd, 0.1);
  assert.equal(r.raw, r6(0.9 * 0.6 + 0.1 * 1));

  assert.throws(() => scoreSignal({}, { weights: { rsi: 0 } }), TypeError);
  assert.throws(() => scoreSignal({}, { weights: { rsi: null } }), TypeError);
  assert.throws(() => scoreSignal({}, { weights: { nope: 1 } }), TypeError);
  assert.throws(() => scoreSignal({}, { weights: [0.5] }), TypeError);
});

test("unrecognised keys are reported, never silently ignored", () => {
  const r = scoreSignal({ rsi: RSI_OVERSOLD, macd: MACD_UP, volumeRation: reading(2) });
  assert.equal(byName(r.dropped).volumeRation.reason, DROP_REASON.UNKNOWN_COMPONENT);
});

test("pure and non-mutating: same input, same result, input untouched", () => {
  const input = {
    rsi: RSI_OVERSOLD, macd: MACD_UP, stochastic: STOCH_OVERSOLD,
    bollinger: BB_AT_LOWER, adx: ADX_STRONG, volumeRatio: VOL_HEAVY,
  };
  const before = JSON.stringify(input);
  const a = scoreSignal(input);
  const b = scoreSignal(input);
  assert.deepEqual(a, b);
  assert.equal(JSON.stringify(input), before);
});

test("every result states that it is a summary of agreement, not a forecast", () => {
  const r = scoreSignal({ rsi: RSI_OVERSOLD, macd: MACD_UP });
  assert.match(r.basisNote, /not a prediction/);
  assert.match(r.basisNote, /not advice/);
  const none = scoreSignal({});
  assert.match(none.basisNote, /not a prediction/);
});

test("the reported contributor count is the observation count behind the score", () => {
  const r = scoreSignal({ rsi: RSI_OVERSOLD, macd: MACD_UP, adx: ADX_STRONG });
  assert.equal(r.observations, 3);
  assert.equal(r.basis.directionalContributors, 2);
  // Each contributor carries the observation count of the indicator it came from,
  // so a score standing on 20 bars cannot pass for one standing on 200.
  assert.equal(r.contributors.every((c) => c.observations === 120), true);
  assert.equal(scoreDisplay(r), "90.0 (2/4)");
});
