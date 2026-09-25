/**
 * Market scanners — prebuilt strategies run through the EXISTING evaluator. PURE.
 *
 * A scanner is not a second engine. Each entry below is an ordinary strategy in
 * the schema `lib/strategy/conditions.js` already validates and evaluates, so a
 * scan and a user-built strategy go down exactly the same code path with the
 * same three-valued logic. Writing a parallel matcher here would mean two
 * definitions of "crosses above" that drift apart.
 *
 * THE THIRD VALUE IS THE POINT. A symbol whose RSI has not been computed does
 * not FAIL a scan — it is UNKNOWN, and it is reported separately. Folding those
 * into rejections is how a scanner quietly hides the half of the market it could
 * not read and calls the remainder "the results".
 */

import {
  CONDITION_OP, GROUP_OP, NODE_TYPE, TRUTH, evaluateStrategy,
} from "../strategy/conditions.js";

/** A reading operand — the schema's named-series form. */
const r = (reading, field) => (field ? { reading, field } : { reading });
/** A constant operand — must be a finite number, never a string. */
const k = (value) => ({ value });

const cond = (left, op, right) => ({ type: NODE_TYPE.CONDITION, left, op, right });
const all = (...children) => ({ type: NODE_TYPE.GROUP, op: GROUP_OP.ALL, children });

/**
 * The built-in scans. Each is a plain strategy object, so any of them can be
 * loaded into the strategy builder, edited and saved as the user's own.
 */
export const SCAN_LIBRARY = Object.freeze([
  {
    id: "oversold",
    name: "Oversold (RSI < 30)",
    description: "Momentum stretched to the downside. Not a buy signal on its own.",
    root: all(cond(r("rsi"), CONDITION_OP.LT, k(30))),
  },
  {
    id: "overbought",
    name: "Overbought (RSI > 70)",
    description: "Momentum stretched to the upside.",
    root: all(cond(r("rsi"), CONDITION_OP.GT, k(70))),
  },
  {
    id: "macd-bullish-cross",
    name: "MACD bullish cross",
    description: "MACD line crosses above its signal line this session.",
    root: all(cond(r("macd"), CONDITION_OP.CROSSES_ABOVE, r("macdSignal"))),
  },
  {
    id: "macd-bearish-cross",
    name: "MACD bearish cross",
    description: "MACD line crosses below its signal line this session.",
    root: all(cond(r("macd"), CONDITION_OP.CROSSES_BELOW, r("macdSignal"))),
  },
  {
    id: "above-200",
    name: "Trading above the 200-day average",
    description: "Long-term trend filter.",
    root: all(cond(r("close"), CONDITION_OP.GT, r("sma200"))),
  },
  {
    id: "volume-surge",
    name: "Volume surge (2x average)",
    description: "Session volume at least twice the 20-day average.",
    root: all(cond(r("volumeRatio"), CONDITION_OP.GTE, k(2))),
  },
  {
    id: "squeeze",
    name: "Bollinger squeeze",
    description: "Band width compressed — volatility contraction, direction unknown.",
    root: all(cond(r("bandwidth"), CONDITION_OP.LT, k(0.1))),
  },
  {
    id: "near-52w-high",
    name: "Within 5% of the 52-week high",
    root: all(
      cond(r("pctFrom52wHigh"), CONDITION_OP.GTE, k(-5)),
      cond(r("pctFrom52wHigh"), CONDITION_OP.LTE, k(0)),
    ),
  },
  {
    id: "oversold-uptrend",
    name: "Pullback in an uptrend",
    description: "RSI below 40 while price holds above the 200-day average.",
    root: all(
      cond(r("rsi"), CONDITION_OP.LT, k(40)),
      cond(r("close"), CONDITION_OP.GT, r("sma200")),
    ),
  },
]);

export const scanById = (id) => SCAN_LIBRARY.find((s) => s.id === id) || null;

/**
 * Run one strategy across a universe.
 *
 * @param {object} strategy  any strategy the shared validator accepts
 * @param {Array}  universe  [{ symbol, readings, prevReadings }]
 */
export function runScan(strategy, universe = []) {
  const matched = [];
  const rejected = [];
  const unknown = [];
  for (const row of universe) {
    if (!row?.symbol) continue;
    const result = evaluateStrategy(strategy, row.readings || {}, row.prevReadings || null);
    const entry = { symbol: row.symbol, ...result };
    if (result.matched === true) matched.push(entry);
    else if (result.matched === false) rejected.push(entry);
    // `matched === null` covers both UNKNOWN readings and an invalid strategy;
    // either way the scan has no answer for this symbol and must not pretend to.
    else unknown.push(entry);
  }
  return {
    strategy: strategy?.name ?? null,
    matched,
    rejected,
    unknown,
    counts: {
      matched: matched.length,
      rejected: rejected.length,
      unknown: unknown.length,
      scanned: universe.length,
    },
    // Stated so a UI can show "42 of 586 — 12 unreadable" rather than implying
    // the whole exchange was examined.
    complete: unknown.length === 0,
  };
}

/** Run several scans at once, e.g. a saved dashboard of them. */
export function runScans(strategies = [], universe = []) {
  return strategies.map((s) => ({ id: s.id ?? null, ...runScan(s, universe) }));
}

/** Symbols matching EVERY listed scan — an intersection, not a union. */
export function intersect(results = []) {
  if (!results.length) return [];
  const sets = results.map((r) => new Set(r.matched.map((m) => m.symbol)));
  return [...sets[0]].filter((sym) => sets.every((s) => s.has(sym))).sort();
}

export { TRUTH };
