// Market structure — swing pivots, trend, and levels. PURE.
//
// Every number a chart analysis quotes originates here, computed from bars. Nothing
// downstream (including any language model) may invent a level: it may only explain
// what this module found. That is the same boundary the trading program draws
// between explaining risk and setting it.
//
// Works for any market. The caller declares which fields are trustworthy, so NEPSE
// (close trusted, open untrusted pre-2018) and crypto (full OHLCV from the exchange)
// share one implementation without either pretending to data it lacks.

/** Swing pivots: a high with `k` lower highs either side, and the mirror for lows. */
export function swingPoints(bars, k = 3, { useRange = true } = {}) {
  const highs = [];
  const lows = [];
  if (!Array.isArray(bars) || bars.length < k * 2 + 1) return { highs, lows };

  const hi = (b) => (useRange && b.high != null ? b.high : b.close);
  const lo = (b) => (useRange && b.low != null ? b.low : b.close);

  for (let i = k; i < bars.length - k; i += 1) {
    let isHigh = true;
    let isLow = true;
    for (let j = i - k; j <= i + k; j += 1) {
      if (j === i) continue;
      if (hi(bars[j]) >= hi(bars[i])) isHigh = false;
      if (lo(bars[j]) <= lo(bars[i])) isLow = false;
    }
    if (isHigh) highs.push({ index: i, date: bars[i].date, price: hi(bars[i]) });
    if (isLow) lows.push({ index: i, date: bars[i].date, price: lo(bars[i]) });
  }
  return { highs, lows };
}

/**
 * Market structure from the last two swing highs and lows.
 * UPTREND = higher highs and higher lows; DOWNTREND = the mirror; anything else is
 * RANGE or UNCLEAR — never forced into a direction.
 */
export function marketStructure(swings) {
  const { highs, lows } = swings;
  if (highs.length < 2 || lows.length < 2) {
    return { structure: "UNCLEAR", reason: "fewer than two confirmed swings on one side" };
  }
  const h1 = highs[highs.length - 2].price;
  const h2 = highs[highs.length - 1].price;
  const l1 = lows[lows.length - 2].price;
  const l2 = lows[lows.length - 1].price;

  const hh = h2 > h1;
  const hl = l2 > l1;
  if (hh && hl) return { structure: "UPTREND", reason: "higher high and higher low", h1, h2, l1, l2 };
  if (!hh && !hl) return { structure: "DOWNTREND", reason: "lower high and lower low", h1, h2, l1, l2 };
  if (hh && !hl) return { structure: "EXPANDING", reason: "higher high but lower low — widening range", h1, h2, l1, l2 };
  return { structure: "CONTRACTING", reason: "lower high but higher low — compressing range", h1, h2, l1, l2 };
}

/** Trend from price against its moving averages — independent of swing structure. */
export function trendFromMovingAverages(last, { sma50, sma200, ema20 } = {}) {
  const above = [];
  const below = [];
  const put = (name, v) => {
    if (v === null || v === undefined) return;
    (last > v ? above : below).push(name);
  };
  put("EMA20", ema20);
  put("SMA50", sma50);
  put("SMA200", sma200);
  const total = above.length + below.length;
  if (!total) return { trend: "UNKNOWN", above, below, note: "no moving average available" };
  if (below.length === 0) return { trend: "BULLISH", above, below };
  if (above.length === 0) return { trend: "BEARISH", above, below };
  return { trend: "MIXED", above, below };
}

/**
 * Support and resistance by clustering swing prices that repeat within `tolPct`.
 * A level earns its place by being touched more than once — a single wick is noise.
 */
export function levels(swings, lastPrice, { tolPct = 1.5, max = 4 } = {}) {
  const cluster = (points) => {
    const out = [];
    for (const p of points) {
      const hit = out.find((c) => Math.abs((c.price - p.price) / c.price) * 100 <= tolPct);
      if (hit) {
        hit.touches += 1;
        hit.price = +((hit.price * (hit.touches - 1) + p.price) / hit.touches).toFixed(4);
        hit.lastDate = p.date;
      } else {
        out.push({ price: +p.price.toFixed(4), touches: 1, lastDate: p.date });
      }
    }
    return out;
  };

  const all = cluster([...swings.highs, ...swings.lows]);
  const resistance = all
    .filter((c) => c.price > lastPrice)
    .sort((a, b) => a.price - b.price || b.touches - a.touches)
    .slice(0, max)
    .map((c) => ({ ...c, distancePct: +(((c.price - lastPrice) / lastPrice) * 100).toFixed(2) }));
  const support = all
    .filter((c) => c.price < lastPrice)
    .sort((a, b) => b.price - a.price || b.touches - a.touches)
    .slice(0, max)
    .map((c) => ({ ...c, distancePct: +(((c.price - lastPrice) / lastPrice) * 100).toFixed(2) }));
  return { support, resistance };
}

/** Classic floor pivots — only meaningful with a real high/low. */
export function pivotPoints(bar) {
  if (!bar || bar.high == null || bar.low == null || bar.close == null) return null;
  const p = (bar.high + bar.low + bar.close) / 3;
  return {
    pivot: +p.toFixed(4),
    r1: +(2 * p - bar.low).toFixed(4),
    s1: +(2 * p - bar.high).toFixed(4),
    r2: +(p + (bar.high - bar.low)).toFixed(4),
    s2: +(p - (bar.high - bar.low)).toFixed(4),
  };
}

/** Recent price action in plain, checkable terms. */
export function priceAction(bars, lookback = 10) {
  const w = (bars || []).slice(-lookback);
  if (w.length < 2) return null;
  const first = w[0].close;
  const last = w[w.length - 1].close;
  let up = 0;
  let down = 0;
  for (let i = 1; i < w.length; i += 1) {
    if (w[i].close > w[i - 1].close) up += 1;
    else if (w[i].close < w[i - 1].close) down += 1;
  }
  const closes = w.map((b) => b.close);
  return {
    bars: w.length,
    changePct: +(((last - first) / first) * 100).toFixed(2),
    upDays: up,
    downDays: down,
    highestClose: +Math.max(...closes).toFixed(4),
    lowestClose: +Math.min(...closes).toFixed(4),
    closedNearHigh: last >= Math.max(...closes) * 0.99,
    closedNearLow: last <= Math.min(...closes) * 1.01,
  };
}

/** Volume trend — only when volume is actually reported. */
export function volumeState(bars, short = 5, long = 20) {
  const withVol = (bars || []).filter((b) => b.volume != null && b.volume > 0);
  if (withVol.length < long) return { state: "UNAVAILABLE", note: "insufficient reported volume" };
  const avg = (arr) => arr.reduce((a, b) => a + b.volume, 0) / arr.length;
  const s = avg(withVol.slice(-short));
  const l = avg(withVol.slice(-long));
  const ratio = +(s / l).toFixed(2);
  let state = "NORMAL";
  if (ratio >= 1.5) state = "EXPANDING";
  else if (ratio <= 0.7) state = "CONTRACTING";
  return { state, ratio, shortAvg: Math.round(s), longAvg: Math.round(l) };
}
