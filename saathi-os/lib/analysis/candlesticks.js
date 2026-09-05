// Candlestick pattern detection over typed bars. PURE.
//
// A candlestick pattern is a claim about where the OPEN and the CLOSE sat inside
// the day's range. That makes open as load-bearing here as close is for RSI — and
// open is precisely the field this project's history source cannot be trusted on
// before 2018-11-06 (see lib/nepse/history.js). So every detection below refuses
// to run on a bar whose open/high/low/close is not trusted: an untrusted open does
// not make a hammer approximate, it makes it UNKNOWABLE. Such a window reports
// FIELD_UNAVAILABLE and no patterns, rather than a pattern read off a guessed body.
//
// Nothing here interpolates, defaults or rounds an input into a match. A window
// that cannot support a verdict returns the status that says so.

import { INDICATOR_STATUS } from "../nepse/indicators.js";

export const PATTERN_DIRECTION = {
  BULLISH: "BULLISH",
  BEARISH: "BEARISH",
  NEUTRAL: "NEUTRAL",
};

export const CANDLESTICK_PATTERN = {
  DOJI: "DOJI",
  MARUBOZU: "MARUBOZU",
  HAMMER: "HAMMER",
  HANGING_MAN: "HANGING_MAN",
  INVERTED_HAMMER: "INVERTED_HAMMER",
  SHOOTING_STAR: "SHOOTING_STAR",
  BULLISH_ENGULFING: "BULLISH_ENGULFING",
  BEARISH_ENGULFING: "BEARISH_ENGULFING",
  PIERCING_LINE: "PIERCING_LINE",
  DARK_CLOUD_COVER: "DARK_CLOUD_COVER",
  MORNING_STAR: "MORNING_STAR",
  EVENING_STAR: "EVENING_STAR",
  THREE_WHITE_SOLDIERS: "THREE_WHITE_SOLDIERS",
  THREE_BLACK_CROWS: "THREE_BLACK_CROWS",
  BULLISH_HARAMI: "BULLISH_HARAMI",
  BEARISH_HARAMI: "BEARISH_HARAMI",
};

// ── thresholds ───────────────────────────────────────────────────────────────────
// Every constant is a hard boundary of a textbook definition, not a tuned parameter.
// They are exported so a caller can quote the rule a match was made under instead of
// trusting the label.

/** Body at or under this fraction of the range is a doji — indecision, not a body. */
export const DOJI_BODY_MAX = 0.10;
/** Marubozu: each shadow must be at most this fraction of the range (so body >= 90%). */
export const MARUBOZU_WICK_MAX = 0.05;
/** Hammer / inverted hammer: the long shadow must be at least this many bodies. */
export const HAMMER_SHADOW_BODIES = 2;
/** Hammer / inverted hammer: the OPPOSITE shadow must stay under this share of range. */
export const HAMMER_OPPOSITE_MAX = 0.15;
/** "Long body" gate for the multi-bar patterns that a long body is part of. */
export const LONG_BODY_MIN = 0.50;
/** A star's body must be at most this fraction of the long body it follows. */
export const STAR_BODY_MAX = 0.50;
/** Harami: the inside body must be at most this fraction of the body containing it. */
export const HARAMI_BODY_MAX = 0.50;
/** Soldiers / crows: an upper (lower) shadow beyond this is a stall, not a march. */
export const SOLDIER_SHADOW_MAX = 0.25;
/** Bars of prior trend used to separate the same-shape reversal pairs. */
export const CONTEXT_BARS = 3;
/** With an `asOf` supplied, a window whose newest bar is older than this is stale. */
export const STALE_AFTER_DAYS = 7;

/**
 * STRENGTH is a GEOMETRY score in 0..1: how cleanly the bars meet the textbook
 * definition — how small the doji's body is, how deep a piercing line closed into
 * the prior body, how little shadow a marubozu carries. It is NOT a probability
 * that price moves in `direction`, and must never be rendered as one: this module
 * never looks at what happened after the pattern, so it cannot know. 0 does not
 * mean "no match" — it means the bars sit exactly on the definition's boundary.
 */
function ramp(value, atZero, atOne) {
  if (typeof value !== "number" || !Number.isFinite(value) || atZero === atOne) return 0;
  const t = (value - atZero) / (atOne - atZero);
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return t;
}

const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
const score = (...criteria) => +mean(criteria).toFixed(4);

// ── bar geometry ─────────────────────────────────────────────────────────────────

/**
 * Geometry of one bar, or null if the bar cannot support any pattern claim.
 * Null is returned — never a zero-filled shape — because a caller that got
 * {body: 0} back would read a missing bar as a perfect doji.
 */
export function barGeometry(bar) {
  if (!bar || typeof bar !== "object") return null;

  const t = bar.trusted;
  // Trust must be asserted true. A bar with no `trusted` map is a bar from an
  // unknown contract, not a trustworthy one.
  if (!t || t.open !== true || t.high !== true || t.low !== true || t.close !== true) return null;

  const { open, high, low, close } = bar;
  // Reject null/undefined/""/non-numbers BEFORE any arithmetic. Number(null) === 0
  // has already cost this codebase a real bug; here a null open would become a
  // price of 0 and every ratio below would be a fabrication, not an estimate.
  for (const v of [open, high, low, close]) {
    if (v === null || v === undefined || v === "" || typeof v !== "number" || !Number.isFinite(v)) {
      return null;
    }
  }

  // A bar can be "trusted" per field and still be internally impossible (this source
  // has rows with high < low, and opens outside the day's range). Those make body and
  // shadow meaningless, so they are refused rather than clamped into shape.
  if (high < low) return null;
  if (open > high || open < low || close > high || close < low) return null;

  const range = high - low;
  // A zero-range bar (one price all day) has no body and no shadows to measure:
  // every ratio would be 0/0. It yields no pattern rather than a divide-by-zero.
  if (range <= 0) return null;

  const body = Math.abs(close - open);
  const bodyHigh = Math.max(open, close);
  const bodyLow = Math.min(open, close);
  return {
    open, high, low, close, range, body,
    bodyHigh, bodyLow,
    bodyMid: (bodyHigh + bodyLow) / 2,
    bodyRatio: body / range,
    upper: high - bodyHigh,
    lower: bodyLow - low,
    upperRatio: (high - bodyHigh) / range,
    lowerRatio: (bodyLow - low) / range,
    bullish: close > open,
    bearish: close < open,
  };
}

/**
 * Direction of the CONTEXT_BARS closes before index i, or null when unknown.
 * Hammer/hanging man and inverted hammer/shooting star are the SAME shape — only
 * the preceding trend separates a bullish reversal from a bearish one. Without
 * that context the shape stays unnamed: guessing "hammer" because hammers are the
 * better-known label would be inventing the half of the definition we lack.
 */
function priorTrend(bars, i) {
  if (i < CONTEXT_BARS) return null;
  const first = bars[i - CONTEXT_BARS];
  const last = bars[i - 1];
  for (const b of [first, last]) {
    if (!b || b.trusted?.close !== true) return null;
    if (typeof b.close !== "number" || !Number.isFinite(b.close)) return null;
  }
  if (last.close < first.close) return "DOWN";
  if (last.close > first.close) return "UP";
  // Dead flat: neither reversal reading is earned.
  return null;
}

function daysBetween(fromIso, toIso) {
  const a = Date.parse(`${fromIso}T00:00:00Z`);
  const b = Date.parse(`${toIso}T00:00:00Z`);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  return Math.round((b - a) / 86400000);
}

// ── the detectors ────────────────────────────────────────────────────────────────
// Each returns a strength for a match, or null. They receive geometry only, so a
// bar that failed the trust gate can never reach them.

function singleBarPatterns(g, trend) {
  const out = [];

  if (g.bodyRatio <= DOJI_BODY_MAX) {
    out.push({
      name: CANDLESTICK_PATTERN.DOJI,
      direction: PATTERN_DIRECTION.NEUTRAL,
      strength: score(ramp(g.bodyRatio, DOJI_BODY_MAX, 0)),
    });
  }

  // Marubozu: body from low to high. Mutually exclusive with doji by construction
  // (both shadows under 5% forces a body over 90% of the range).
  if (g.body > 0 && g.upperRatio <= MARUBOZU_WICK_MAX && g.lowerRatio <= MARUBOZU_WICK_MAX) {
    out.push({
      name: CANDLESTICK_PATTERN.MARUBOZU,
      direction: g.bullish ? PATTERN_DIRECTION.BULLISH : PATTERN_DIRECTION.BEARISH,
      strength: score(
        ramp(g.upperRatio, MARUBOZU_WICK_MAX, 0),
        ramp(g.lowerRatio, MARUBOZU_WICK_MAX, 0),
      ),
    });
  }

  // The hammer family needs a real body. Below the doji line the bar IS a doji
  // (dragonfly/gravestone), and reporting it as a hammer would overstate a body
  // that is not there — so the two vocabularies never overlap.
  const hasBody = g.bodyRatio > DOJI_BODY_MAX;

  if (hasBody && g.lower >= HAMMER_SHADOW_BODIES * g.body && g.upperRatio <= HAMMER_OPPOSITE_MAX && trend) {
    const strength = score(
      ramp(g.lower / g.body, HAMMER_SHADOW_BODIES, HAMMER_SHADOW_BODIES + 1),
      ramp(g.upperRatio, HAMMER_OPPOSITE_MAX, 0),
    );
    out.push(trend === "DOWN"
      ? { name: CANDLESTICK_PATTERN.HAMMER, direction: PATTERN_DIRECTION.BULLISH, strength }
      : { name: CANDLESTICK_PATTERN.HANGING_MAN, direction: PATTERN_DIRECTION.BEARISH, strength });
  }

  if (hasBody && g.upper >= HAMMER_SHADOW_BODIES * g.body && g.lowerRatio <= HAMMER_OPPOSITE_MAX && trend) {
    const strength = score(
      ramp(g.upper / g.body, HAMMER_SHADOW_BODIES, HAMMER_SHADOW_BODIES + 1),
      ramp(g.lowerRatio, HAMMER_OPPOSITE_MAX, 0),
    );
    out.push(trend === "DOWN"
      ? { name: CANDLESTICK_PATTERN.INVERTED_HAMMER, direction: PATTERN_DIRECTION.BULLISH, strength }
      : { name: CANDLESTICK_PATTERN.SHOOTING_STAR, direction: PATTERN_DIRECTION.BEARISH, strength });
  }

  return out;
}

function twoBarPatterns(prev, cur) {
  const out = [];
  // Engulfing swallows a BODY, so the swallowed body must be one: engulfing a doji
  // is a different (and weaker) event and is not reported under this name.
  const prevHasBody = prev.bodyRatio > DOJI_BODY_MAX;

  if (prevHasBody && prev.bearish && cur.bullish
      && cur.bodyLow <= prev.bodyLow && cur.bodyHigh >= prev.bodyHigh
      && cur.body > prev.body) {
    out.push({
      name: CANDLESTICK_PATTERN.BULLISH_ENGULFING,
      direction: PATTERN_DIRECTION.BULLISH,
      strength: score(ramp(cur.body / prev.body, 1, 2)),
    });
  }

  if (prevHasBody && prev.bullish && cur.bearish
      && cur.bodyLow <= prev.bodyLow && cur.bodyHigh >= prev.bodyHigh
      && cur.body > prev.body) {
    out.push({
      name: CANDLESTICK_PATTERN.BEARISH_ENGULFING,
      direction: PATTERN_DIRECTION.BEARISH,
      strength: score(ramp(cur.body / prev.body, 1, 2)),
    });
  }

  // Piercing line: gap under the prior LOW, then close back above the midpoint of a
  // long black body. Closing at or under the midpoint is the on-neck/in-neck family,
  // which carries the opposite message — so the midpoint is a hard boundary, not a
  // tolerance to be rounded through.
  if (prev.bearish && prev.bodyRatio >= LONG_BODY_MIN && cur.bullish
      && cur.open < prev.low && cur.close > prev.bodyMid && cur.close < prev.open) {
    out.push({
      name: CANDLESTICK_PATTERN.PIERCING_LINE,
      direction: PATTERN_DIRECTION.BULLISH,
      strength: score(ramp((cur.close - prev.close) / prev.body, 0.5, 1)),
    });
  }

  if (prev.bullish && prev.bodyRatio >= LONG_BODY_MIN && cur.bearish
      && cur.open > prev.high && cur.close < prev.bodyMid && cur.close > prev.open) {
    out.push({
      name: CANDLESTICK_PATTERN.DARK_CLOUD_COVER,
      direction: PATTERN_DIRECTION.BEARISH,
      strength: score(ramp((prev.close - cur.close) / prev.body, 0.5, 1)),
    });
  }

  // Harami: the second body sits strictly inside the first. Strict on both edges —
  // a body that merely touches the prior open or close is a tweezer/inside-close
  // situation, not the "pregnant" containment the pattern names.
  const contained = cur.bodyHigh < prev.bodyHigh && cur.bodyLow > prev.bodyLow
    && cur.body <= HARAMI_BODY_MAX * prev.body;

  if (prev.bodyRatio >= LONG_BODY_MIN && contained && prev.bearish && cur.bullish) {
    out.push({
      name: CANDLESTICK_PATTERN.BULLISH_HARAMI,
      direction: PATTERN_DIRECTION.BULLISH,
      strength: score(ramp(cur.body / prev.body, HARAMI_BODY_MAX, 0)),
    });
  }
  if (prev.bodyRatio >= LONG_BODY_MIN && contained && prev.bullish && cur.bearish) {
    out.push({
      name: CANDLESTICK_PATTERN.BEARISH_HARAMI,
      direction: PATTERN_DIRECTION.BEARISH,
      strength: score(ramp(cur.body / prev.body, HARAMI_BODY_MAX, 0)),
    });
  }

  return out;
}

function threeBarPatterns(a, b, c) {
  const out = [];

  // Morning star: long black body, a small body that GAPS clear of it, then a long
  // white body closing back above the black body's midpoint. The body gap is what
  // makes it a star; without it this is a three-bar pullback and is not reported.
  if (a.bearish && a.bodyRatio >= LONG_BODY_MIN
      && b.body <= STAR_BODY_MAX * a.body && b.bodyHigh < a.bodyLow
      && c.bullish && c.bodyRatio >= LONG_BODY_MIN && c.close > a.bodyMid) {
    out.push({
      name: CANDLESTICK_PATTERN.MORNING_STAR,
      direction: PATTERN_DIRECTION.BULLISH,
      strength: score(
        ramp((c.close - a.close) / a.body, 0.5, 1),
        ramp(b.body / a.body, STAR_BODY_MAX, 0),
      ),
    });
  }

  if (a.bullish && a.bodyRatio >= LONG_BODY_MIN
      && b.body <= STAR_BODY_MAX * a.body && b.bodyLow > a.bodyHigh
      && c.bearish && c.bodyRatio >= LONG_BODY_MIN && c.close < a.bodyMid) {
    out.push({
      name: CANDLESTICK_PATTERN.EVENING_STAR,
      direction: PATTERN_DIRECTION.BEARISH,
      strength: score(
        ramp((a.close - c.close) / a.body, 0.5, 1),
        ramp(b.body / a.body, STAR_BODY_MAX, 0),
      ),
    });
  }

  // Three soldiers / crows: three long bodies marching one way, each OPENING INSIDE
  // the previous body. An open beyond the prior body is a gap-driven run, and long
  // shadows against the march mean the advance is being sold — both are excluded,
  // since the pattern's whole content is an orderly, unbroken advance.
  const allBull = [a, b, c].every((g) => g.bullish && g.bodyRatio >= LONG_BODY_MIN);
  if (allBull
      && b.close > a.close && c.close > b.close
      && b.open >= a.open && b.open <= a.close
      && c.open >= b.open && c.open <= b.close
      && [a, b, c].every((g) => g.upperRatio <= SOLDIER_SHADOW_MAX)) {
    out.push({
      name: CANDLESTICK_PATTERN.THREE_WHITE_SOLDIERS,
      direction: PATTERN_DIRECTION.BULLISH,
      strength: score(
        ramp(Math.min(a.bodyRatio, b.bodyRatio, c.bodyRatio), LONG_BODY_MIN, 1),
        ramp(Math.max(a.upperRatio, b.upperRatio, c.upperRatio), SOLDIER_SHADOW_MAX, 0),
      ),
    });
  }

  const allBear = [a, b, c].every((g) => g.bearish && g.bodyRatio >= LONG_BODY_MIN);
  if (allBear
      && b.close < a.close && c.close < b.close
      && b.open <= a.open && b.open >= a.close
      && c.open <= b.open && c.open >= b.close
      && [a, b, c].every((g) => g.lowerRatio <= SOLDIER_SHADOW_MAX)) {
    out.push({
      name: CANDLESTICK_PATTERN.THREE_BLACK_CROWS,
      direction: PATTERN_DIRECTION.BEARISH,
      strength: score(
        ramp(Math.min(a.bodyRatio, b.bodyRatio, c.bodyRatio), LONG_BODY_MIN, 1),
        ramp(Math.max(a.lowerRatio, b.lowerRatio, c.lowerRatio), SOLDIER_SHADOW_MAX, 0),
      ),
    });
  }

  return out;
}

function emptyResult(status) {
  return { patterns: [], status, observations: 0 };
}

/**
 * Detect candlestick patterns anchored on the last `lookback` bars.
 *
 * Anchoring: a pattern is reported at its CONFIRMING (last) bar, so `atIndex` and
 * `date` are the session on which the pattern completed. The window governs anchors
 * only — a three-bar pattern anchored at the first bar of the window legitimately
 * reads the two bars before it.
 *
 * `observations` is the number of bars in the window that passed the trust gate,
 * i.e. how many sessions this verdict actually got to look at. Fewer observations
 * than `lookback` means part of the window was unusable, not that nothing happened.
 *
 * @param {Array} bars typed bars, oldest → newest (see lib/nepse/history.js)
 * @param {{lookback?: number, asOf?: string|null, staleAfterDays?: number}} options
 *        `asOf` (ISO date) is supplied by the caller because this module owns no
 *        clock; without it staleness is simply not asserted.
 * @returns {{patterns: Array, status: string, observations: number}}
 */
export function detectCandlestickPatterns(bars, options = {}) {
  const { lookback = 5, asOf = null, staleAfterDays = STALE_AFTER_DAYS } = options ?? {};

  if (!Array.isArray(bars) || bars.length === 0) {
    return emptyResult(INDICATOR_STATUS.INSUFFICIENT_HISTORY);
  }
  // An unusable lookback is refused, never silently replaced by the default: a
  // caller passing null meant "I don't know", and answering on 5 bars would be
  // answering a question nobody asked.
  if (typeof lookback !== "number" || !Number.isFinite(lookback) || lookback < 1) {
    return emptyResult(INDICATOR_STATUS.INSUFFICIENT_HISTORY);
  }

  const geo = bars.map(barGeometry);
  const start = Math.max(0, bars.length - Math.floor(lookback));

  let observations = 0;
  let newestUsable = null;
  for (let i = start; i < bars.length; i += 1) {
    if (geo[i]) {
      observations += 1;
      newestUsable = bars[i];
    }
  }
  // Bars exist but not one of them carries a trustworthy OHLC set: the shapes are
  // unknowable, which is a different answer from "no patterns were present".
  if (observations === 0) {
    return { patterns: [], status: INDICATOR_STATUS.FIELD_UNAVAILABLE, observations: 0 };
  }

  const patterns = [];
  const emit = (found, i, span) => {
    for (const p of found) {
      patterns.push({
        name: p.name,
        direction: p.direction,
        atIndex: i,
        date: bars[i].date ?? null,
        strength: p.strength,
        // Indices of the bars that constitute the pattern, oldest → newest.
        bars: Array.from({ length: span }, (_, k) => i - span + 1 + k),
      });
    }
  };

  for (let i = start; i < bars.length; i += 1) {
    const cur = geo[i];
    if (!cur) continue; // untrusted confirming bar: nothing anchored here is knowable

    emit(singleBarPatterns(cur, priorTrend(bars, i)), i, 1);

    const prev = i >= 1 ? geo[i - 1] : null;
    if (prev) emit(twoBarPatterns(prev, cur), i, 2);

    const first = i >= 2 ? geo[i - 2] : null;
    // Every bar of a three-bar pattern must be trusted; one untrusted body in the
    // middle is enough to make the whole formation a guess.
    if (first && prev) emit(threeBarPatterns(first, prev, cur), i, 3);
  }

  // Newest first within a bar, so a caller taking patterns[0] gets the cleanest
  // match on the most recent session rather than an arbitrary one.
  patterns.sort((x, y) => (y.atIndex - x.atIndex) || (y.strength - x.strength));

  let status = INDICATOR_STATUS.VALID;
  if (asOf && newestUsable?.date) {
    const age = daysBetween(newestUsable.date, asOf);
    if (age !== null && age > staleAfterDays) status = INDICATOR_STATUS.DATA_STALE;
  }

  return { patterns, status, observations };
}

/** Names found in a result — a convenience for callers that only need the labels. */
export function patternNames(result) {
  return (result?.patterns ?? []).map((p) => p.name);
}
