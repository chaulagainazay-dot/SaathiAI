/**
 * Scan readings — the typed series a strategy is evaluated against. PURE.
 *
 * `lib/strategy/conditions.js` resolves an operand by looking up a named reading
 * and demanding `{value, status, observations}` where the status is VALID. This
 * module is the only place those names are minted, so a scan in the library and a
 * strategy the user builds are comparing the same quantity under the same label.
 *
 * TWO THINGS ARE DELIBERATELY NOT DONE HERE.
 *
 *   - Nothing is back-filled. A symbol with 40 sessions has no 200-day average,
 *     and the reading says INSUFFICIENT_HISTORY rather than substituting a
 *     shorter average under the name `sma200`. A scan that silently compared
 *     against a 40-day mean would return matches nobody asked for.
 *   - Nothing is coerced. `Number(null)` is 0 and 0 is finite, so a missing
 *     volume would read as a genuine zero-volume session and hand `volumeRatio`
 *     a confident 0 — below every threshold, quietly excluding the symbol. Every
 *     input is checked for absence BEFORE it reaches arithmetic.
 */

import {
  INDICATOR_STATUS, macdValue, bollingerValue, rsiValue, sma,
} from "./indicators.js";

/** Sessions required before each reading is computed at all. */
export const READING_REQUIREMENTS = Object.freeze({
  close: 1,
  rsi: 15,
  macd: 35,
  macdSignal: 35,
  sma200: 200,
  volumeRatio: 21,
  bandwidth: 20,
  pctFrom52wHigh: 2,
});

/** The reading names a scan or a saved strategy may refer to. */
export const READING_NAMES = Object.freeze(Object.keys(READING_REQUIREMENTS));

const VOLUME_WINDOW = 20;
const HIGH_WINDOW = 252; // ~one trading year of sessions

const num = (v) => {
  if (v === null || v === undefined || v === "" || typeof v === "boolean") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

function reading(value, status, observations) {
  return { value, status, observations };
}

const unavailable = (obs, need) =>
  reading(null,
    obs === 0 ? INDICATOR_STATUS.FIELD_UNAVAILABLE : INDICATOR_STATUS.INSUFFICIENT_HISTORY,
    obs);

/**
 * Build the reading map for one instrument at the END of the supplied bars.
 *
 * Pass `bars.slice(0, -1)` to get the previous session's map, which is what the
 * crossing operators need. Evaluating a cross without it is UNKNOWN by design —
 * see `evaluateStrategy` — so the caller must supply both or accept unknowns.
 *
 * @param {Array} bars typed bars, oldest -> newest
 */
export function scanReadings(bars = []) {
  const usable = (bars || []).filter(
    (b) => b?.trusted?.close !== false && num(b?.close) !== null && b?.date,
  );
  const closes = usable.map((b) => Number(b.close));
  const n = closes.length;
  const out = {};

  out.close = n >= 1
    ? reading(closes[n - 1], INDICATOR_STATUS.VALID, n)
    : unavailable(n);

  out.rsi = n >= READING_REQUIREMENTS.rsi
    ? reading(rsiValue(closes, 14), INDICATOR_STATUS.VALID, n)
    : unavailable(n);

  const macd = n >= READING_REQUIREMENTS.macd ? macdValue(closes) : null;
  // macdValue returns null on a series it cannot decompose even when the length
  // gate passed; that is still no reading, not a zero-valued one.
  out.macd = macd ? reading(macd.macd, INDICATOR_STATUS.VALID, n) : unavailable(n);
  out.macdSignal = macd ? reading(macd.signal, INDICATOR_STATUS.VALID, n) : unavailable(n);

  out.sma200 = n >= READING_REQUIREMENTS.sma200
    ? reading(sma(closes, 200), INDICATOR_STATUS.VALID, n)
    : unavailable(n);

  const bb = n >= READING_REQUIREMENTS.bandwidth ? bollingerValue(closes, 20) : null;
  // A collapsed band has a null bandwidth — an undefined ratio, not a zero one.
  out.bandwidth = bb && bb.bandwidth !== null
    ? reading(bb.bandwidth, INDICATOR_STATUS.VALID, n)
    : unavailable(n);

  // Volume ratio — this session against its own 20-session mean.
  const volumes = usable.map((b) => num(b.volume));
  const window = volumes.slice(-(VOLUME_WINDOW + 1), -1);
  const last = volumes[volumes.length - 1];
  if (window.length < VOLUME_WINDOW || window.some((v) => v === null) || last === null) {
    out.volumeRatio = unavailable(volumes.filter((v) => v !== null).length);
  } else {
    const mean = window.reduce((a, b) => a + b, 0) / window.length;
    // A zero mean makes the ratio undefined. Reporting Infinity would put the
    // symbol at the top of every volume-surge scan on no evidence at all.
    out.volumeRatio = mean > 0
      ? reading(+(last / mean).toFixed(4), INDICATOR_STATUS.VALID, window.length + 1)
      : reading(null, INDICATOR_STATUS.FIELD_UNAVAILABLE, window.length + 1);
  }

  // Distance from the 52-week high, as a signed percentage (0 at the high).
  const highs = usable.slice(-HIGH_WINDOW).map((b) => {
    const h = num(b.high);
    // The archive's high is untrusted on some rows; the close is a floor for the
    // high and is the honest fallback, never a fabricated wider range.
    return b?.trusted?.high === false || h === null ? num(b.close) : h;
  }).filter((v) => v !== null);
  if (highs.length < READING_REQUIREMENTS.pctFrom52wHigh || n < 1) {
    out.pctFrom52wHigh = unavailable(highs.length);
  } else {
    const peak = Math.max(...highs);
    out.pctFrom52wHigh = peak > 0
      ? reading(+(((closes[n - 1] - peak) / peak) * 100).toFixed(4),
                INDICATOR_STATUS.VALID, highs.length)
      : reading(null, INDICATOR_STATUS.FIELD_UNAVAILABLE, highs.length);
  }

  return out;
}

/**
 * Current and previous reading maps for one instrument.
 *
 * `prev` is null when there is no earlier bar to stand on — the crossing
 * operators then report UNKNOWN rather than "no cross happened".
 */
export function scanUniverseRow(symbol, bars = []) {
  const list = Array.isArray(bars) ? bars : [];
  return {
    symbol,
    readings: scanReadings(list),
    prevReadings: list.length >= 2 ? scanReadings(list.slice(0, -1)) : null,
  };
}
