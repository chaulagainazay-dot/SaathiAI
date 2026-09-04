// NEPSE technical indicators — typed results with provenance. PURE.
//
// NEPSE-HIST-2 Phase 8/9. Two rules govern everything here:
//
//   1. An indicator is only computed from fields the source actually supports.
//      RSI, MACD, Bollinger, SMA/EMA need CLOSE alone, so they run on this source.
//      ATR / true-range / Donchian need HIGH and LOW; they run only where those
//      are trusted, and return FIELD_UNAVAILABLE otherwise. Nothing needing OPEN
//      runs at all on this source — open is untrusted before 2018-11-06 and is
//      never fabricated.
//
//   2. A result never carries a bare number. Every value arrives with the series
//      it came from, how many observations backed it, the adjustment policy, and
//      a status — so a caller cannot mistake "no data" for a value. There are no
//      numeric defaults: unknown is null with a status, never 0.

import { ADJUSTMENT, NEPSE_RESEARCH_SOURCE } from "./history.js";

export const INDICATOR_STATUS = {
  VALID: "VALID",
  INSUFFICIENT_HISTORY: "INSUFFICIENT_HISTORY",
  FIELD_UNAVAILABLE: "FIELD_UNAVAILABLE",
  DATA_STALE: "DATA_STALE",
  DATA_CONFLICT: "DATA_CONFLICT",
  SOURCE_UNVERIFIED: "SOURCE_UNVERIFIED",
};

/** Fields each indicator genuinely requires — the enablement gate. */
export const INDICATOR_REQUIREMENTS = {
  sma: ["close"],
  ema: ["close"],
  rsi: ["close"],
  macd: ["close"],
  bollinger: ["close"],
  momentum: ["close"],
  atr: ["high", "low", "close"],
  donchian: ["high", "low"],
};

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
    adjustment: meta.adjustment ?? NEPSE_RESEARCH_SOURCE.adjustment,
    quality: meta.quality ?? null,
    ...(meta.detail ? { detail: meta.detail } : {}),
    ...(meta.note ? { note: meta.note } : {}),
  };
}

// ── primitive maths (arrays of numbers, oldest → newest) ─────────────────────────

export function sma(values, period) {
  if (!Array.isArray(values) || values.length < period || period < 1) return null;
  const w = values.slice(-period);
  return +(w.reduce((a, b) => a + b, 0) / period).toFixed(4);
}

export function emaSeries(values, period) {
  if (!Array.isArray(values) || values.length < period || period < 1) return [];
  const k = 2 / (period + 1);
  const out = [];
  let prev = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out.push(prev);
  for (let i = period; i < values.length; i += 1) {
    prev = values[i] * k + prev * (1 - k);
    out.push(prev);
  }
  return out;
}

export function ema(values, period) {
  const s = emaSeries(values, period);
  return s.length ? +s[s.length - 1].toFixed(4) : null;
}

/** Wilder's RSI over closes. Close-only by construction. */
export function rsiValue(closes, period = 14) {
  if (!Array.isArray(closes) || closes.length < period + 1) return null;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i += 1) {
    const d = closes[i] - closes[i - 1];
    if (d >= 0) gain += d; else loss -= d;
  }
  let ag = gain / period;
  let al = loss / period;
  for (let i = period + 1; i < closes.length; i += 1) {
    const d = closes[i] - closes[i - 1];
    ag = (ag * (period - 1) + Math.max(d, 0)) / period;
    al = (al * (period - 1) + Math.max(-d, 0)) / period;
  }
  if (al === 0) return ag === 0 ? 50 : 100;
  const rs = ag / al;
  return +(100 - 100 / (1 + rs)).toFixed(2);
}

export function macdValue(closes, fast = 12, slow = 26, signal = 9) {
  if (!Array.isArray(closes) || closes.length < slow + signal) return null;
  const fastS = emaSeries(closes, fast);
  const slowS = emaSeries(closes, slow);
  // align the two EMA series on their common tail
  const n = Math.min(fastS.length, slowS.length);
  const macdLine = [];
  for (let i = 0; i < n; i += 1) {
    macdLine.push(fastS[fastS.length - n + i] - slowS[slowS.length - n + i]);
  }
  const sigS = emaSeries(macdLine, signal);
  if (!sigS.length) return null;
  const m = macdLine[macdLine.length - 1];
  const s = sigS[sigS.length - 1];
  return { macd: +m.toFixed(4), signal: +s.toFixed(4), histogram: +(m - s).toFixed(4) };
}

export function bollingerValue(closes, period = 20, mult = 2) {
  if (!Array.isArray(closes) || closes.length < period) return null;
  const w = closes.slice(-period);
  const mean = w.reduce((a, b) => a + b, 0) / period;
  const variance = w.reduce((a, b) => a + (b - mean) ** 2, 0) / period;
  const sd = Math.sqrt(variance);
  const upper = mean + mult * sd;
  const lower = mean - mult * sd;
  const last = closes[closes.length - 1];
  const width = upper - lower;
  return {
    middle: +mean.toFixed(4),
    upper: +upper.toFixed(4),
    lower: +lower.toFixed(4),
    // %B: 0 at the lower band, 1 at the upper. Undefined when the bands collapse.
    percentB: width === 0 ? null : +((last - lower) / width).toFixed(4),
    bandwidth: mean === 0 ? null : +(width / mean).toFixed(4),
  };
}

/** True range needs the day's high and low — never approximate it from close. */
export function atrValue(bars, period = 14) {
  if (!Array.isArray(bars) || bars.length < period + 1) return null;
  const trs = [];
  for (let i = 1; i < bars.length; i += 1) {
    const { high, low } = bars[i];
    const prevClose = bars[i - 1].close;
    if (high === null || low === null || prevClose === null) return null;
    trs.push(Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose)));
  }
  if (trs.length < period) return null;
  let atr = trs.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < trs.length; i += 1) atr = (atr * (period - 1) + trs[i]) / period;
  return +atr.toFixed(4);
}

// ── typed indicator services (what the UI consumes) ──────────────────────────────

/** Bars whose lookback window is free of unadjusted corporate-action jumps. */
function conflictInWindow(bars, lookback, limitPct = 20) {
  const w = bars.slice(-Math.min(lookback + 1, bars.length));
  for (let i = 1; i < w.length; i += 1) {
    const prev = w[i - 1].close;
    const cur = w[i].close;
    if (!prev) continue;
    if (Math.abs(((cur - prev) / prev) * 100) > limitPct) {
      return { date: w[i].date, pct: +(((cur - prev) / prev) * 100).toFixed(2) };
    }
  }
  return null;
}

/**
 * Compute the close-only indicator set for one instrument.
 * @param {Array} bars typed bars from parseHistoryCsv (oldest → newest)
 */
export function computeIndicators(bars, { instrument = "", periods = {} } = {}) {
  const p = { rsi: 14, sma: 50, ema: 20, bb: 20, atr: 14, ...periods };
  const usable = (bars || []).filter((b) => b.trusted?.close);
  const asOf = usable.length ? usable[usable.length - 1].date : null;
  const closes = usable.map((b) => b.close);
  const base = { instrument, asOf, adjustment: ADJUSTMENT.UNADJUSTED };

  const out = {};

  const need = (name, minObs) => {
    if (closes.length < minObs) {
      out[name] = result(name, null, INDICATOR_STATUS.INSUFFICIENT_HISTORY, {
        ...base, lookback: minObs, observations: closes.length,
        note: `needs ${minObs} usable closes, has ${closes.length}`,
      });
      return false;
    }
    return true;
  };

  // RSI — close only
  if (need("rsi", p.rsi + 1)) {
    const conflict = conflictInWindow(usable, p.rsi);
    out.rsi = result("rsi", rsiValue(closes, p.rsi),
      conflict ? INDICATOR_STATUS.DATA_CONFLICT : INDICATOR_STATUS.VALID,
      { ...base, lookback: p.rsi, observations: closes.length,
        ...(conflict ? { detail: { corporateActionInWindow: conflict } } : {}) });
  }

  // MACD — close only
  if (need("macd", 26 + 9)) {
    const conflict = conflictInWindow(usable, 26 + 9);
    out.macd = result("macd", macdValue(closes),
      conflict ? INDICATOR_STATUS.DATA_CONFLICT : INDICATOR_STATUS.VALID,
      { ...base, lookback: 35, observations: closes.length,
        ...(conflict ? { detail: { corporateActionInWindow: conflict } } : {}) });
  }

  // Bollinger — close only
  if (need("bollinger", p.bb)) {
    const conflict = conflictInWindow(usable, p.bb);
    out.bollinger = result("bollinger", bollingerValue(closes, p.bb),
      conflict ? INDICATOR_STATUS.DATA_CONFLICT : INDICATOR_STATUS.VALID,
      { ...base, lookback: p.bb, observations: closes.length,
        ...(conflict ? { detail: { corporateActionInWindow: conflict } } : {}) });
  }

  // SMA / EMA — close only
  if (need("sma", p.sma)) {
    out.sma = result("sma", sma(closes, p.sma), INDICATOR_STATUS.VALID,
      { ...base, lookback: p.sma, observations: closes.length });
  }
  if (need("ema", p.ema)) {
    out.ema = result("ema", ema(closes, p.ema), INDICATOR_STATUS.VALID,
      { ...base, lookback: p.ema, observations: closes.length });
  }

  // ATR — gated on trusted high/low, never approximated from close
  const rangeBars = usable.filter((b) => b.trusted?.high && b.trusted?.low);
  if (rangeBars.length < p.atr + 1) {
    out.atr = result("atr", null,
      rangeBars.length === 0 ? INDICATOR_STATUS.FIELD_UNAVAILABLE : INDICATOR_STATUS.INSUFFICIENT_HISTORY,
      { ...base, lookback: p.atr, observations: rangeBars.length,
        note: "ATR requires trusted high and low; it is never approximated from close" });
  } else {
    out.atr = result("atr", atrValue(rangeBars, p.atr), INDICATOR_STATUS.VALID,
      { ...base, lookback: p.atr, observations: rangeBars.length });
  }

  // Anything requiring OPEN is refused on this source rather than approximated.
  out.openGap = result("openGap", null, INDICATOR_STATUS.FIELD_UNAVAILABLE, {
    ...base,
    note: "source OPEN is untrusted before 2018-11-06 and is never fabricated",
  });

  return out;
}

/** Display helper: a typed result renders as a number or an em dash, never a zero. */
export function indicatorDisplay(res, format = (v) => String(v)) {
  if (!res || res.value === null || res.value === undefined) return "—";
  if (res.status === INDICATOR_STATUS.FIELD_UNAVAILABLE) return "—";
  if (res.status === INDICATOR_STATUS.INSUFFICIENT_HISTORY) return "—";
  return format(res.value);
}
