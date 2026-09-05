// Candlestick detection tests. The NEAR-MISS cases carry the weight: a detector
// that fires on everything is worse than none, because a pattern is quoted to a
// user as a fact about the tape.

import test from "node:test";
import assert from "node:assert/strict";

import {
  detectCandlestickPatterns,
  patternNames,
  barGeometry,
  CANDLESTICK_PATTERN as P,
  PATTERN_DIRECTION as DIR,
} from "./analysis/candlesticks.js";
import { INDICATOR_STATUS } from "./nepse/indicators.js";

const d = (n) => `2024-03-${String(n).padStart(2, "0")}`;

/** A fully trusted bar unless the caller says otherwise. */
function bar(n, open, high, low, close, trusted) {
  return {
    symbol: "TEST",
    date: d(n),
    open, high, low, close,
    volume: 1000,
    trusted: { open: true, high: true, low: true, close: true, volume: true, ...(trusted || {}) },
  };
}

// Three prior bars whose closes fall / rise — the context that separates a hammer
// from a hanging man and an inverted hammer from a shooting star.
const downContext = () => [
  bar(1, 121, 122, 119, 120),
  bar(2, 116, 117, 114, 115),
  bar(3, 111, 112, 109, 110),
];
const upContext = () => [
  bar(1, 99, 101, 98, 100),
  bar(2, 104, 106, 103, 105),
  bar(3, 109, 111, 108, 110),
];

const names = (bars, opts = { lookback: 1 }) => patternNames(detectCandlestickPatterns(bars, opts));
const find = (res, name) => res.patterns.find((p) => p.name === name);

// ── doji ─────────────────────────────────────────────────────────────────────────

test("doji: a body under a tenth of the range matches, NEUTRAL", () => {
  const res = detectCandlestickPatterns([...downContext(), bar(4, 100, 105, 95, 100.3)], { lookback: 1 });
  const doji = find(res, P.DOJI);
  assert.ok(doji, "expected a doji");
  assert.equal(doji.direction, DIR.NEUTRAL);
  assert.equal(doji.atIndex, 3);
  assert.equal(doji.date, d(4));
  assert.deepEqual(doji.bars, [3]);
  assert.equal(res.status, INDICATOR_STATUS.VALID);
  assert.equal(res.observations, 1);
});

test("doji NEAR-MISS: a fifth-of-range body is a real body, not indecision", () => {
  assert.ok(!names([...downContext(), bar(4, 100, 105, 95, 102)]).includes(P.DOJI));
});

test("doji strength rewards a smaller body and never leaves 0..1", () => {
  const clean = find(detectCandlestickPatterns([bar(1, 100, 105, 95, 100.1)], { lookback: 1 }), P.DOJI);
  const sloppy = find(detectCandlestickPatterns([bar(1, 100, 105, 95, 100.9)], { lookback: 1 }), P.DOJI);
  assert.ok(clean.strength > sloppy.strength);
  for (const s of [clean.strength, sloppy.strength]) {
    assert.ok(s >= 0 && s <= 1, `strength ${s} out of range`);
  }
});

// ── marubozu ─────────────────────────────────────────────────────────────────────

test("marubozu: body from low to high, direction from its colour", () => {
  const res = detectCandlestickPatterns([...downContext(), bar(4, 100, 110.2, 99.8, 110)], { lookback: 1 });
  const m = find(res, P.MARUBOZU);
  assert.ok(m);
  assert.equal(m.direction, DIR.BULLISH);
});

test("marubozu NEAR-MISS: a 16%-of-range upper shadow disqualifies it", () => {
  assert.ok(!names([...downContext(), bar(4, 100, 112, 99.8, 110)]).includes(P.MARUBOZU));
});

// ── hammer family (shape + prior trend) ──────────────────────────────────────────

test("hammer: long lower shadow after a decline", () => {
  const res = detectCandlestickPatterns([...downContext(), bar(4, 100, 103, 88, 102)], { lookback: 1 });
  const h = find(res, P.HAMMER);
  assert.ok(h);
  assert.equal(h.direction, DIR.BULLISH);
  assert.ok(!patternNames(res).includes(P.HANGING_MAN));
});

test("hammer NEAR-MISS: a long upper shadow makes it neither hammer nor inverted", () => {
  const n = names([...downContext(), bar(4, 100, 112, 88, 104)]);
  assert.ok(!n.includes(P.HAMMER));
  assert.ok(!n.includes(P.INVERTED_HAMMER));
});

test("hammer shape after a RALLY is a hanging man, not a hammer", () => {
  const n = names([...upContext(), bar(4, 100, 103, 88, 102)]);
  assert.ok(n.includes(P.HANGING_MAN));
  assert.ok(!n.includes(P.HAMMER));
});

test("hammer NEAR-MISS: without enough prior bars the trend is unknown, so no label", () => {
  const n = names([bar(2, 116, 117, 114, 115), bar(3, 111, 112, 109, 110), bar(4, 100, 103, 88, 102)]);
  assert.deepEqual(n, []);
});

test("inverted hammer: long upper shadow after a decline", () => {
  const res = detectCandlestickPatterns([...downContext(), bar(4, 100, 115, 99, 102)], { lookback: 1 });
  assert.equal(find(res, P.INVERTED_HAMMER)?.direction, DIR.BULLISH);
});

test("shooting star: the same shape after a rally reads bearish", () => {
  const res = detectCandlestickPatterns([...upContext(), bar(4, 100, 115, 99, 102)], { lookback: 1 });
  assert.equal(find(res, P.SHOOTING_STAR)?.direction, DIR.BEARISH);
});

test("shooting-star NEAR-MISS: identical shape in a downtrend must NOT be a shooting star", () => {
  const n = names([...downContext(), bar(4, 100, 115, 99, 102)]);
  assert.ok(!n.includes(P.SHOOTING_STAR));
  assert.ok(n.includes(P.INVERTED_HAMMER));
});

// ── engulfing ────────────────────────────────────────────────────────────────────

test("bullish engulfing: white body swallows the prior black body", () => {
  const res = detectCandlestickPatterns(
    [bar(1, 110, 111, 99, 100), bar(2, 99, 112, 98, 111)], { lookback: 1 },
  );
  const e = find(res, P.BULLISH_ENGULFING);
  assert.ok(e);
  assert.equal(e.direction, DIR.BULLISH);
  assert.deepEqual(e.bars, [0, 1], "an engulfing pattern spans the two bars that made it");
  assert.equal(e.atIndex, 1);
});

test("bullish engulfing NEAR-MISS: a body that only overlaps is not an engulfing", () => {
  const res = detectCandlestickPatterns(
    [bar(1, 110, 111, 99, 100), bar(2, 100.5, 110, 99, 109)], { lookback: 1 },
  );
  assert.deepEqual(res.patterns, []);
});

test("bearish engulfing: black body swallows the prior white body", () => {
  const res = detectCandlestickPatterns(
    [bar(1, 100, 111, 99, 110), bar(2, 111, 112, 98, 99)], { lookback: 1 },
  );
  assert.equal(find(res, P.BEARISH_ENGULFING)?.direction, DIR.BEARISH);
});

test("bearish engulfing NEAR-MISS: prior body not fully covered", () => {
  const n = names([bar(1, 100, 111, 99, 110), bar(2, 109, 110, 100.5, 101)]);
  assert.ok(!n.includes(P.BEARISH_ENGULFING));
});

test("engulfing NEAR-MISS: swallowing a doji is not an engulfing pattern", () => {
  const n = names([bar(1, 100.1, 101.5, 99.5, 100), bar(2, 99, 112, 98, 111)]);
  assert.ok(!n.includes(P.BULLISH_ENGULFING));
});

// ── piercing line / dark cloud cover ─────────────────────────────────────────────

test("piercing line: gap below the prior low, close back above the body midpoint", () => {
  const res = detectCandlestickPatterns(
    [bar(1, 110, 111, 99, 100), bar(2, 97, 107, 96, 106)], { lookback: 1 },
  );
  const p = find(res, P.PIERCING_LINE);
  assert.ok(p);
  assert.equal(p.direction, DIR.BULLISH);
});

test("piercing NEAR-MISS: closing under the midpoint is on-neck, not piercing", () => {
  const res = detectCandlestickPatterns(
    [bar(1, 110, 111, 99, 100), bar(2, 97, 107, 96, 104)], { lookback: 1 },
  );
  assert.deepEqual(res.patterns, []);
});

test("piercing NEAR-MISS: no gap below the prior low", () => {
  const res = detectCandlestickPatterns(
    [bar(1, 110, 111, 99, 100), bar(2, 99.5, 107, 99, 106)], { lookback: 1 },
  );
  assert.deepEqual(res.patterns, []);
});

test("dark cloud cover: gap above the prior high, close back under the midpoint", () => {
  const res = detectCandlestickPatterns(
    [bar(1, 100, 111, 99, 110), bar(2, 113, 114, 103, 104)], { lookback: 1 },
  );
  assert.equal(find(res, P.DARK_CLOUD_COVER)?.direction, DIR.BEARISH);
});

test("dark cloud NEAR-MISS: a close above the midpoint fails the definition", () => {
  const res = detectCandlestickPatterns(
    [bar(1, 100, 111, 99, 110), bar(2, 113, 114, 105, 106)], { lookback: 1 },
  );
  assert.deepEqual(res.patterns, []);
});

// ── stars ────────────────────────────────────────────────────────────────────────

const morningStar = () => [
  bar(1, 110, 110.5, 99.5, 100),
  bar(2, 97, 98, 95, 96.5),
  bar(3, 98, 108, 97, 107),
];

test("morning star: long black body, gapped star, long white body back over the midpoint", () => {
  const res = detectCandlestickPatterns(morningStar(), { lookback: 1 });
  const s = find(res, P.MORNING_STAR);
  assert.ok(s);
  assert.equal(s.direction, DIR.BULLISH);
  assert.deepEqual(s.bars, [0, 1, 2]);
});

test("morning star NEAR-MISS: no body gap — a pullback, not a star", () => {
  const bars = morningStar();
  bars[1] = bar(2, 101, 102, 99, 100.5);
  assert.ok(!names(bars).includes(P.MORNING_STAR));
});

test("morning star NEAR-MISS: third bar stops below the midpoint of the first", () => {
  const bars = morningStar();
  bars[2] = bar(3, 98, 105, 97, 104);
  assert.ok(!names(bars).includes(P.MORNING_STAR));
});

const eveningStar = () => [
  bar(1, 100, 110.5, 99.5, 110),
  bar(2, 113, 115, 112, 113.5),
  bar(3, 112, 113, 102, 103),
];

test("evening star: the mirror image reads bearish", () => {
  const res = detectCandlestickPatterns(eveningStar(), { lookback: 1 });
  assert.equal(find(res, P.EVENING_STAR)?.direction, DIR.BEARISH);
});

test("evening star NEAR-MISS: star body overlaps the first body", () => {
  const bars = eveningStar();
  bars[1] = bar(2, 109, 111, 108, 109.5);
  assert.ok(!names(bars).includes(P.EVENING_STAR));
});

// ── soldiers / crows ─────────────────────────────────────────────────────────────

const soldiers = () => [
  bar(1, 100, 106.5, 99.5, 106),
  bar(2, 103, 109.5, 102.5, 109),
  bar(3, 106, 112.5, 105.5, 112),
];

test("three white soldiers: three long bodies, each opening inside the last", () => {
  const res = detectCandlestickPatterns(soldiers(), { lookback: 1 });
  const s = find(res, P.THREE_WHITE_SOLDIERS);
  assert.ok(s);
  assert.equal(s.direction, DIR.BULLISH);
  assert.deepEqual(s.bars, [0, 1, 2]);
});

test("three white soldiers NEAR-MISS: the third gaps open above the prior body", () => {
  const bars = soldiers();
  bars[2] = bar(3, 110, 116, 109.5, 115);
  assert.ok(!names(bars).includes(P.THREE_WHITE_SOLDIERS));
});

test("three white soldiers NEAR-MISS: a long upper shadow is a stall, not a march", () => {
  const bars = soldiers();
  bars[2] = bar(3, 106, 118, 105.5, 112);
  assert.ok(!names(bars).includes(P.THREE_WHITE_SOLDIERS));
});

const crows = () => [
  bar(1, 112, 112.5, 105.5, 106),
  bar(2, 109, 109.5, 102.5, 103),
  bar(3, 106, 106.5, 99.5, 100),
];

test("three black crows: the bearish mirror", () => {
  const res = detectCandlestickPatterns(crows(), { lookback: 1 });
  assert.equal(find(res, P.THREE_BLACK_CROWS)?.direction, DIR.BEARISH);
});

test("three black crows NEAR-MISS: the third opens below the prior body", () => {
  const bars = crows();
  bars[2] = bar(3, 102, 102.5, 95.5, 96);
  assert.ok(!names(bars).includes(P.THREE_BLACK_CROWS));
});

// ── harami ───────────────────────────────────────────────────────────────────────

test("bullish harami: a small white body strictly inside a long black one", () => {
  const res = detectCandlestickPatterns(
    [bar(1, 112, 113, 99, 100), bar(2, 103, 109, 102, 108)], { lookback: 1 },
  );
  const h = find(res, P.BULLISH_HARAMI);
  assert.ok(h);
  assert.equal(h.direction, DIR.BULLISH);
});

test("bullish harami NEAR-MISS: the second body escapes the first", () => {
  const res = detectCandlestickPatterns(
    [bar(1, 112, 113, 99, 100), bar(2, 99, 111, 98, 110)], { lookback: 1 },
  );
  assert.deepEqual(res.patterns, []);
});

test("bullish harami NEAR-MISS: contained but not small — 83% of the prior body", () => {
  const n = names([bar(1, 112, 113, 99, 100), bar(2, 101, 111.5, 100.5, 111)]);
  assert.ok(!n.includes(P.BULLISH_HARAMI));
});

test("bearish harami: a small black body inside a long white one", () => {
  const res = detectCandlestickPatterns(
    [bar(1, 100, 113, 99, 112), bar(2, 108, 109, 102, 103)], { lookback: 1 },
  );
  assert.equal(find(res, P.BEARISH_HARAMI)?.direction, DIR.BEARISH);
});

// ── trust gate ───────────────────────────────────────────────────────────────────

test("an untrusted OPEN makes the shape unknowable: FIELD_UNAVAILABLE, no patterns", () => {
  const res = detectCandlestickPatterns([bar(4, 100, 105, 95, 100.3, { open: false })]);
  assert.deepEqual(res.patterns, []);
  assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(res.observations, 0);
});

test("an untrusted high or low is equally fatal to the bar", () => {
  for (const field of ["high", "low", "close"]) {
    const res = detectCandlestickPatterns([bar(4, 100, 105, 95, 100.3, { [field]: false })]);
    assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE, field);
  }
});

test("one untrusted bar inside a pattern kills that pattern, not the whole window", () => {
  const res = detectCandlestickPatterns(
    [bar(1, 110, 111, 99, 100, { open: false }), bar(2, 99, 112, 98, 111)], { lookback: 1 },
  );
  assert.ok(!patternNames(res).includes(P.BULLISH_ENGULFING));
  assert.equal(res.status, INDICATOR_STATUS.VALID, "the confirming bar itself was usable");
  assert.equal(res.observations, 1);
});

test("a null price is never coerced to 0, even when the field claims to be trusted", () => {
  const b = bar(4, null, 105, 95, 100.3);
  assert.equal(barGeometry(b), null, "Number(null) === 0 would fabricate an open at zero");
  const res = detectCandlestickPatterns([b]);
  assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(res.observations, 0);
});

test("a bar with no trust map is not assumed trustworthy", () => {
  const res = detectCandlestickPatterns([{ date: d(4), open: 100, high: 105, low: 95, close: 100.3 }]);
  assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
});

test("internally impossible bars are refused rather than clamped into shape", () => {
  assert.equal(barGeometry(bar(4, 100, 95, 105, 100)), null, "high below low");
  assert.equal(barGeometry(bar(4, 120, 105, 95, 100)), null, "open above the day's high");
  assert.equal(barGeometry(bar(4, 100, 105, 95, 90)), null, "close below the day's low");
});

test("a zero-range bar yields no pattern and no NaN", () => {
  const res = detectCandlestickPatterns([bar(4, 100, 100, 100, 100)]);
  assert.deepEqual(res.patterns, []);
  assert.equal(res.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
});

// ── history / window ─────────────────────────────────────────────────────────────

test("no bars at all is INSUFFICIENT_HISTORY with zero observations", () => {
  for (const input of [[], null, undefined, "nope"]) {
    const res = detectCandlestickPatterns(input);
    assert.deepEqual(res.patterns, []);
    assert.equal(res.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
    assert.equal(res.observations, 0);
  }
});

test("an unusable lookback is refused, not quietly replaced by the default", () => {
  const bars = [...downContext(), bar(4, 100, 105, 95, 100.3)];
  for (const lookback of [null, 0, -3, "5", Number.NaN]) {
    const res = detectCandlestickPatterns(bars, { lookback });
    assert.equal(res.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY, String(lookback));
    assert.deepEqual(res.patterns, []);
  }
});

test("lookback bounds which bars may ANCHOR a pattern", () => {
  const filler = [bar(2, 100, 106, 99, 105), bar(3, 100, 106, 99, 105), bar(4, 100, 106, 99, 105)];
  const bars = [bar(1, 100, 105, 95, 100.3), ...filler];
  assert.ok(!names(bars, { lookback: 3 }).includes(P.DOJI), "the doji is outside the window");
  assert.ok(names(bars, { lookback: 4 }).includes(P.DOJI), "widening the window reaches it");
});

test("a pattern may read bars before the window; only its anchor must be inside", () => {
  const res = detectCandlestickPatterns(morningStar(), { lookback: 1 });
  const s = find(res, P.MORNING_STAR);
  assert.deepEqual(s.bars, [0, 1, 2]);
  assert.equal(res.observations, 1, "observations count anchors examined, not bars read");
});

test("observations counts only the trusted bars in the window", () => {
  const bars = [
    bar(1, 100, 106, 99, 105),
    bar(2, 100, 106, 99, 105, { open: false }),
    bar(3, 100, 106, 99, 105),
    bar(4, 100, 106, 99, 105, { low: false }),
  ];
  const res = detectCandlestickPatterns(bars, { lookback: 4 });
  assert.equal(res.observations, 2);
  assert.equal(res.status, INDICATOR_STATUS.VALID);
});

test("staleness is only asserted when the caller supplies asOf", () => {
  const bars = [...downContext(), bar(4, 100, 105, 95, 100.3)];
  assert.equal(detectCandlestickPatterns(bars, { lookback: 1 }).status, INDICATOR_STATUS.VALID);
  assert.equal(
    detectCandlestickPatterns(bars, { lookback: 1, asOf: d(6) }).status,
    INDICATOR_STATUS.VALID,
  );
  const stale = detectCandlestickPatterns(bars, { lookback: 1, asOf: "2024-03-20" });
  assert.equal(stale.status, INDICATOR_STATUS.DATA_STALE);
  assert.ok(stale.patterns.length > 0, "a stale window still reports what it saw, flagged");
});

// ── result contract ──────────────────────────────────────────────────────────────

test("every emitted pattern carries the documented shape and a 0..1 strength", () => {
  const windows = [
    [...downContext(), bar(4, 100, 103, 88, 102)],
    [...upContext(), bar(4, 100, 115, 99, 102)],
    morningStar(), eveningStar(), soldiers(), crows(),
    [bar(1, 110, 111, 99, 100), bar(2, 99, 112, 98, 111)],
    [bar(1, 110, 111, 99, 100), bar(2, 97, 107, 96, 106)],
    [bar(1, 112, 113, 99, 100), bar(2, 103, 109, 102, 108)],
  ];
  let seen = 0;
  for (const w of windows) {
    const res = detectCandlestickPatterns(w, { lookback: 5 });
    assert.deepEqual(Object.keys(res).sort(), ["observations", "patterns", "status"]);
    for (const p of res.patterns) {
      seen += 1;
      assert.equal(typeof p.name, "string");
      assert.ok(Object.values(DIR).includes(p.direction), p.direction);
      assert.equal(typeof p.strength, "number");
      assert.ok(p.strength >= 0 && p.strength <= 1, `${p.name} strength ${p.strength}`);
      assert.equal(p.date, w[p.atIndex].date);
      assert.equal(p.bars[p.bars.length - 1], p.atIndex);
      assert.ok(p.bars.every((i) => i >= 0));
    }
  }
  assert.ok(seen >= 9, `expected the fixtures to produce matches, got ${seen}`);
});

test("patterns come back newest bar first", () => {
  const bars = [...soldiers(), bar(4, 112, 117, 111, 116.5)];
  const res = detectCandlestickPatterns(bars, { lookback: 4 });
  for (let i = 1; i < res.patterns.length; i += 1) {
    assert.ok(res.patterns[i - 1].atIndex >= res.patterns[i].atIndex);
  }
});
