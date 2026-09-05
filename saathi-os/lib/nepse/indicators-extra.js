// NEPSE range indicators — Stochastic oscillator and Wilder ADX. PURE.
//
// Companion to indicators.js. Everything there that runs on CLOSE alone runs on
// this source unconditionally; everything HERE reads the day's HIGH and LOW, and
// on this archive those are trusted per row, not per dataset. So the same two
// rules govern the file:
//
//   1. High/low are used only where trusted.high && trusted.low say so. When they
//      do not, the answer is FIELD_UNAVAILABLE — exactly as ATR refuses in
//      indicators.js. Close is NOT substituted for a missing high or low: doing so
//      collapses the day's range to zero and makes %K read 0 or 100 on a day that
//      simply was not measured.
//
//   2. A result never arrives as a bare number: status, lookback, observations and
//      asOf travel with it, and "unknown" is null — never 0, never an interpolation.
//
// Contiguity is a third rule these two indicators need and the close-only ones do
// not. ATR can drop a bad row and keep going because true range is a per-bar
// quantity. %K is "where does close sit inside the last 14 SESSIONS' range", and
// ADX is a recursive average whose every step depends on the step before — silently
// deleting a session from the middle of either window redefines the window while
// still labelling it 14. So both indicators run on the longest CONTIGUOUS trusted
// suffix of the series, and an untrusted row that cuts that suffix short is
// reported as the blocker rather than skipped over.

import { ADJUSTMENT, NEPSE_RESEARCH_SOURCE } from "./history.js";
import { INDICATOR_STATUS } from "./indicators.js";

/** Fields each indicator genuinely requires — same enablement gate as indicators.js. */
export const INDICATOR_EXTRA_REQUIREMENTS = {
  stochastic: ["high", "low", "close"],
  adx: ["high", "low", "close"],
};

/** Mirrors the typed envelope in indicators.js so both files render identically. */
function result(name, value, status, meta = {}) {
  return {
    indicator: name,
    value,
    status,
    instrument: meta.instrument ?? "",
    asOf: meta.asOf ?? null,
    lookback: meta.lookback ?? null,
    observations: meta.observations ?? 0,
    source: NEPSE_RESEARCH_SOURCE.id,
    dataset: NEPSE_RESEARCH_SOURCE.dataset,
    adjustment: meta.adjustment ?? ADJUSTMENT.UNADJUSTED,
    quality: meta.quality ?? null,
    ...(meta.detail ? { detail: meta.detail } : {}),
    ...(meta.note ? { note: meta.note } : {}),
  };
}

const r4 = (x) => +x.toFixed(4);

/** Periods are structural, not data. A bad one is refused, never quietly defaulted. */
function badPeriod(...periods) {
  return periods.some((p) => !Number.isInteger(p) || p < 1);
}

const RANGE_FIELDS = ["high", "low", "close"];

/**
 * Why a bar cannot back a range indicator, or null if it can.
 *
 * The null/undefined/"" rejection happens BEFORE any arithmetic on purpose:
 * Number(null) === 0, so an absent low would place itself below every price ever
 * traded and pin %K at 100 — the same coercion trap that once scored a missing RSI
 * as maximally oversold.
 */
function unusableField(bar) {
  if (!bar || typeof bar !== "object") return "bar";
  for (const f of RANGE_FIELDS) {
    // trusted.X === false is the archive telling us the value is known bad; reading
    // it anyway is the substitution this module exists to refuse.
    if (bar.trusted?.[f] !== true) return f;
    const v = bar[f];
    if (v === null || v === undefined || v === "") return f;
    // A numeric string would coerce silently; only a real finite number is data.
    if (typeof v !== "number" || !Number.isFinite(v)) return f;
  }
  return null;
}

/**
 * The longest contiguous run of usable bars ending at the newest bar, plus the bar
 * that truncated it. A blocker means the series HAS the field and it is untrusted
 * here — a different failure from simply not having enough history yet.
 */
function trustedTail(bars) {
  const list = Array.isArray(bars) ? bars : [];
  let start = list.length;
  while (start > 0 && unusableField(list[start - 1]) === null) start -= 1;
  const blockerBar = start > 0 ? list[start - 1] : null;
  return {
    tail: list.slice(start),
    blocker: blockerBar
      ? { date: blockerBar?.date ?? null, field: unusableField(blockerBar) }
      : null,
  };
}

/**
 * Shared gate: resolve the usable window or the typed refusal that replaces it.
 * Returns { tail } on success or { refusal } — never both.
 */
function gate(name, bars, needed, base) {
  const { tail, blocker } = trustedTail(bars);
  if (tail.length >= needed) return { tail };

  const asOf = tail.length ? tail[tail.length - 1].date ?? null : null;
  // Precedence matches ATR's: when the field itself is unavailable that is the
  // finding, even though the count is also short — otherwise a caller reads
  // INSUFFICIENT_HISTORY and waits for bars that will never fix an untrusted column.
  if (blocker) {
    return {
      refusal: result(name, null, INDICATOR_STATUS.FIELD_UNAVAILABLE, {
        ...base, asOf, lookback: needed, observations: tail.length,
        detail: { blockedAt: blocker },
        note: `${name} requires ${needed} contiguous bars with trusted high, low and close; `
          + `the run ends at an untrusted ${blocker.field}. Close is never substituted for a missing range.`,
      }),
    };
  }
  return {
    refusal: result(name, null, INDICATOR_STATUS.INSUFFICIENT_HISTORY, {
      ...base, asOf, lookback: needed, observations: tail.length,
      note: `needs ${needed} contiguous usable bars, has ${tail.length}`,
    }),
  };
}

// ── Stochastic oscillator ────────────────────────────────────────────────────────

/**
 * Slow stochastic. raw %K = 100 * (close - lowestLow) / (highestHigh - lowestLow)
 * over kPeriod sessions; %K = SMA(raw %K, smooth); %D = SMA(%K, dPeriod).
 *
 * Minimum bars = kPeriod + smooth + dPeriod - 2: kPeriod to open the first window,
 * then smooth-1 and dPeriod-1 more to fill each successive average.
 *
 * A zero-range window (highestHigh === lowestLow) has no denominator, so %K is
 * undefined there — not 0, not 50. That null propagates through both averages
 * instead of being averaged around, mirroring how bollingerValue() reports a null
 * percentB when its bands collapse.
 */
export function stochasticValue(bars, { kPeriod = 14, dPeriod = 3, smooth = 3 } = {}) {
  const base = { instrument: "", adjustment: ADJUSTMENT.UNADJUSTED };
  if (badPeriod(kPeriod, dPeriod, smooth)) {
    return result("stochastic", null, INDICATOR_STATUS.INSUFFICIENT_HISTORY, {
      ...base, note: "kPeriod, dPeriod and smooth must be positive integers",
    });
  }

  const needed = kPeriod + smooth + dPeriod - 2;
  const gated = gate("stochastic", bars, needed, base);
  if (gated.refusal) return gated.refusal;
  const { tail } = gated;

  const highs = tail.map((b) => b.high);
  const lows = tail.map((b) => b.low);
  const closes = tail.map((b) => b.close);

  // raw %K, oldest → newest; null wherever the window had no range.
  const rawK = [];
  for (let i = kPeriod - 1; i < tail.length; i += 1) {
    let hh = -Infinity;
    let ll = Infinity;
    for (let j = i - kPeriod + 1; j <= i; j += 1) {
      if (highs[j] > hh) hh = highs[j];
      if (lows[j] < ll) ll = lows[j];
    }
    const range = hh - ll;
    rawK.push(range === 0 ? null : ((closes[i] - ll) / range) * 100);
  }

  // Averages refuse to close over a hole: one undefined member makes the mean
  // undefined too, rather than an average of the members that happened to exist.
  const meanOrNull = (arr) => (arr.some((v) => v === null)
    ? null
    : arr.reduce((a, b) => a + b, 0) / arr.length);

  const kSeries = [];
  for (let i = smooth - 1; i < rawK.length; i += 1) {
    kSeries.push(meanOrNull(rawK.slice(i - smooth + 1, i + 1)));
  }
  const k = kSeries[kSeries.length - 1];
  const d = meanOrNull(kSeries.slice(-dPeriod));

  // The last window's extremes, so a caller can see the range the reading came from.
  let hh = -Infinity;
  let ll = Infinity;
  for (let j = tail.length - kPeriod; j < tail.length; j += 1) {
    if (highs[j] > hh) hh = highs[j];
    if (lows[j] < ll) ll = lows[j];
  }

  const flat = hh === ll;
  // A zero-range window has no denominator, so %K does not exist for it. The
  // status stays VALID because it describes the INPUTS — the bars were present,
  // trusted and sufficient — while FIELD_UNAVAILABLE in this codebase means an
  // input field was missing, which is not what happened. The absence lives in the
  // value, as null. Consumers must therefore check the value and not the status
  // alone; the scorer does exactly that, and a test below holds it to it.
  const undefinedK = flat || k === null || d === null;
  return result("stochastic", {
    k: k === null ? null : r4(k),
    d: d === null ? null : r4(d),
    highestHigh: r4(hh),
    lowestLow: r4(ll),
  }, INDICATOR_STATUS.VALID, {
    ...base,
    asOf: tail[tail.length - 1].date ?? null,
    lookback: needed,
    observations: tail.length,
    detail: { kPeriod, dPeriod, smooth },
    ...(undefinedK
      ? { note: "%K is undefined across a zero-range window — reported as null, never 0 or 50" }
      : {}),
  });
}

// ── Average Directional Index (Wilder) ───────────────────────────────────────────

/**
 * Wilder's ADX with +DI / -DI.
 *
 * Per bar: TR = max(H-L, |H-prevC|, |L-prevC|); +DM and -DM are the day's outside
 * move, and only the LARGER of the two survives (an inside day yields neither).
 * All three are Wilder-smoothed — seed with the first `period` sum, then
 * next = prev - prev/period + current — giving +DI/-DI as percentages of true
 * range. DX = 100*|+DI - -DI|/(+DI + -DI); ADX seeds on the mean of the first
 * `period` DX values and then runs (prev*(period-1) + DX)/period.
 *
 * Minimum bars = 2*period: n bars give n-1 TR/DM values, `period` of them are
 * consumed by the seed, and `period` DX values are needed to seed ADX in turn.
 *
 * Two denominators can vanish. Smoothed TR is 0 on a series that never moved, so
 * +DI and -DI are undefined; +DI + -DI is 0 when neither direction registered, so
 * DX is undefined. Both are reported as null. A null anywhere in the DX chain kills
 * ADX outright: the recursion has no way past a missing term that is not invention.
 */
export function adxValue(bars, { period = 14 } = {}) {
  const base = { instrument: "", adjustment: ADJUSTMENT.UNADJUSTED };
  if (badPeriod(period)) {
    return result("adx", null, INDICATOR_STATUS.INSUFFICIENT_HISTORY, {
      ...base, note: "period must be a positive integer",
    });
  }

  const needed = 2 * period;
  const gated = gate("adx", bars, needed, base);
  if (gated.refusal) return gated.refusal;
  const { tail } = gated;

  const tr = [];
  const plusDM = [];
  const minusDM = [];
  for (let i = 1; i < tail.length; i += 1) {
    const h = tail[i].high;
    const l = tail[i].low;
    const ph = tail[i - 1].high;
    const pl = tail[i - 1].low;
    const pc = tail[i - 1].close;
    const up = h - ph;
    const down = pl - l;
    plusDM.push(up > down && up > 0 ? up : 0);
    minusDM.push(down > up && down > 0 ? down : 0);
    tr.push(Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc)));
  }

  const seed = (arr) => arr.slice(0, period).reduce((a, b) => a + b, 0);
  let sTR = seed(tr);
  let sPlus = seed(plusDM);
  let sMinus = seed(minusDM);

  const dx = [];
  let plusDI = null;
  let minusDI = null;
  const step = () => {
    if (sTR === 0) {
      // No true range at all: direction as a fraction of range has no meaning.
      plusDI = null;
      minusDI = null;
      dx.push(null);
      return;
    }
    plusDI = (100 * sPlus) / sTR;
    minusDI = (100 * sMinus) / sTR;
    const total = plusDI + minusDI;
    dx.push(total === 0 ? null : (100 * Math.abs(plusDI - minusDI)) / total);
  };
  step();
  for (let i = period; i < tr.length; i += 1) {
    sTR = sTR - sTR / period + tr[i];
    sPlus = sPlus - sPlus / period + plusDM[i];
    sMinus = sMinus - sMinus / period + minusDM[i];
    step();
  }

  let adx = null;
  const shouldHave = dx.length >= period;
  if (shouldHave && !dx.slice(0, period).some((v) => v === null)) {
    adx = dx.slice(0, period).reduce((a, b) => a + b, 0) / period;
    for (let i = period; i < dx.length; i += 1) {
      if (dx[i] === null) { adx = null; break; }
      adx = (adx * (period - 1) + dx[i]) / period;
    }
  }

  return result("adx", {
    adx: adx === null ? null : r4(adx),
    plusDI: plusDI === null ? null : r4(plusDI),
    minusDI: minusDI === null ? null : r4(minusDI),
    // Same contract as %K above: the inputs were fine, the output is undefined.
  }, INDICATOR_STATUS.VALID, {
    ...base,
    asOf: tail[tail.length - 1].date ?? null,
    lookback: needed,
    observations: tail.length,
    detail: { period },
    ...(adx === null
      ? { note: "directional movement is undefined across a zero-range stretch — ADX reported as null, never 0" }
      : {}),
  });
}
