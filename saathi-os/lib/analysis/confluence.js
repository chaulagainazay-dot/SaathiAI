// Confluence — which signals agree, which conflict, and what would break the read.
// PURE. Consumes only computed structure + typed indicator results.
//
// The point of this module is the CONFLICT list. An analysis that only reports
// agreement is a sales pitch; the disagreements are what tell an operator the read
// is fragile. A signal whose data is missing is recorded as UNAVAILABLE and counted
// in neither column — absence is never evidence.

export const BIAS = {
  BULLISH: "BULLISH",
  BEARISH: "BEARISH",
  NEUTRAL: "NEUTRAL",
  CONFLICTED: "CONFLICTED",
  INSUFFICIENT: "INSUFFICIENT_EVIDENCE",
};

const bull = (name, detail) => ({ name, direction: "BULLISH", detail });
const bear = (name, detail) => ({ name, direction: "BEARISH", detail });
const flat = (name, detail) => ({ name, direction: "NEUTRAL", detail });
const na = (name, reason) => ({ name, direction: "UNAVAILABLE", detail: reason });

/**
 * Turn structure + indicators into a directional signal list.
 * Each entry says what it is, which way it leans, and why — so every claim in a
 * narrative can be traced to one row here.
 */
export function signalSet({ structure, maTrend, indicators = {}, price, action, volume, levels }) {
  const s = [];

  // 1. market structure
  if (!structure || structure.structure === "UNCLEAR") {
    s.push(na("Market structure", structure?.reason || "not enough confirmed swings"));
  } else if (structure.structure === "UPTREND") {
    s.push(bull("Market structure", "higher highs and higher lows"));
  } else if (structure.structure === "DOWNTREND") {
    s.push(bear("Market structure", "lower highs and lower lows"));
  } else {
    s.push(flat("Market structure", structure.reason));
  }

  // 2. moving averages
  if (!maTrend || maTrend.trend === "UNKNOWN") s.push(na("Moving averages", "no MA available"));
  else if (maTrend.trend === "BULLISH") s.push(bull("Moving averages", `price above ${maTrend.above.join(", ")}`));
  else if (maTrend.trend === "BEARISH") s.push(bear("Moving averages", `price below ${maTrend.below.join(", ")}`));
  else s.push(flat("Moving averages", `above ${maTrend.above.join(", ") || "none"}, below ${maTrend.below.join(", ") || "none"}`));

  // 3. RSI
  const rsi = indicators.rsi;
  if (!rsi || rsi.status !== "VALID" || rsi.value === null) {
    s.push(na("RSI", rsi?.status ? `RSI ${rsi.status}` : "no RSI"));
  } else if (rsi.value >= 70) s.push(bear("RSI", `${rsi.value} — overbought, stretched`));
  else if (rsi.value <= 30) s.push(bull("RSI", `${rsi.value} — oversold, washed out`));
  else if (rsi.value >= 55) s.push(bull("RSI", `${rsi.value} — momentum favours buyers`));
  else if (rsi.value <= 45) s.push(bear("RSI", `${rsi.value} — momentum favours sellers`));
  else s.push(flat("RSI", `${rsi.value} — mid-band, no edge`));

  // 4. MACD
  const macd = indicators.macd;
  const hist = macd?.value?.histogram ?? (typeof macd?.value === "number" ? macd.value : null);
  if (!macd || macd.status !== "VALID" || hist === null) {
    s.push(na("MACD", macd?.status ? `MACD ${macd.status}` : "no MACD"));
  } else if (hist > 0) s.push(bull("MACD", `histogram +${hist.toFixed(3)} — above signal`));
  else if (hist < 0) s.push(bear("MACD", `histogram ${hist.toFixed(3)} — below signal`));
  else s.push(flat("MACD", "histogram flat"));

  // 5. Bollinger position
  const bb = indicators.bollinger;
  const pb = bb?.value?.percentB ?? (typeof bb?.value === "number" ? bb.value : null);
  if (!bb || bb.status !== "VALID" || pb === null) {
    s.push(na("Bollinger", bb?.status ? `Bollinger ${bb.status}` : "no bands"));
  } else if (pb > 1) s.push(bear("Bollinger", `%B ${pb.toFixed(2)} — closed outside the upper band`));
  else if (pb < 0) s.push(bull("Bollinger", `%B ${pb.toFixed(2)} — closed outside the lower band`));
  else if (pb > 0.8) s.push(bull("Bollinger", `%B ${pb.toFixed(2)} — pressing the upper band`));
  else if (pb < 0.2) s.push(bear("Bollinger", `%B ${pb.toFixed(2)} — pressing the lower band`));
  else s.push(flat("Bollinger", `%B ${pb.toFixed(2)} — mid-band`));

  // 6. volume
  if (!volume || volume.state === "UNAVAILABLE") s.push(na("Volume", volume?.note || "no reported volume"));
  else if (volume.state === "EXPANDING") s.push(bull("Volume", `${volume.ratio}× its 20-bar average — participation rising`));
  else if (volume.state === "CONTRACTING") s.push(bear("Volume", `${volume.ratio}× its 20-bar average — participation fading`));
  else s.push(flat("Volume", `${volume.ratio}× average`));

  // 7. recent price action
  if (!action) s.push(na("Price action", "not enough bars"));
  else if (action.changePct > 0 && action.closedNearHigh) s.push(bull("Price action", `+${action.changePct}% over ${action.bars} bars, closing near the high`));
  else if (action.changePct < 0 && action.closedNearLow) s.push(bear("Price action", `${action.changePct}% over ${action.bars} bars, closing near the low`));
  else s.push(flat("Price action", `${action.changePct}% over ${action.bars} bars, ${action.upDays} up / ${action.downDays} down`));

  // 8. room to the nearest level
  const r = levels?.resistance?.[0];
  const sup = levels?.support?.[0];
  if (r && sup) {
    const roomUp = r.distancePct;
    const roomDown = Math.abs(sup.distancePct);
    if (roomUp > roomDown * 1.5) s.push(bull("Level room", `${roomUp}% to resistance vs ${roomDown}% to support`));
    else if (roomDown > roomUp * 1.5) s.push(bear("Level room", `only ${roomUp}% to resistance vs ${roomDown}% to support`));
    else s.push(flat("Level room", `${roomUp}% up / ${roomDown}% down — balanced`));
  } else {
    s.push(na("Level room", "no confirmed level on one side"));
  }

  return s;
}

/** Weigh the signal list into a bias, with the conflicts kept in view. */
export function confluence(signals) {
  const bullish = signals.filter((x) => x.direction === "BULLISH");
  const bearish = signals.filter((x) => x.direction === "BEARISH");
  const neutral = signals.filter((x) => x.direction === "NEUTRAL");
  const unavailable = signals.filter((x) => x.direction === "UNAVAILABLE");

  const decided = bullish.length + bearish.length;
  let bias = BIAS.NEUTRAL;
  let confidence = "LOW";

  if (decided === 0) {
    bias = BIAS.INSUFFICIENT;
  } else if (unavailable.length > signals.length / 2) {
    // More than half the evidence missing is not a read worth trusting.
    bias = BIAS.INSUFFICIENT;
  } else {
    const net = bullish.length - bearish.length;
    const ratio = Math.max(bullish.length, bearish.length) / decided;
    if (Math.abs(net) <= 1 && decided >= 4) bias = BIAS.CONFLICTED;
    else if (net > 0) bias = BIAS.BULLISH;
    else if (net < 0) bias = BIAS.BEARISH;
    else bias = BIAS.CONFLICTED;
    confidence = ratio >= 0.8 && unavailable.length <= 1 ? "HIGH" : ratio >= 0.65 ? "MEDIUM" : "LOW";
  }

  return {
    bias,
    confidence: bias === BIAS.INSUFFICIENT ? "NONE" : confidence,
    agreeing: bias === BIAS.BULLISH ? bullish : bias === BIAS.BEARISH ? bearish : [],
    conflicting: bias === BIAS.BULLISH ? bearish : bias === BIAS.BEARISH ? bullish : [...bullish, ...bearish],
    neutral,
    unavailable,
    counts: { bullish: bullish.length, bearish: bearish.length, neutral: neutral.length, unavailable: unavailable.length },
  };
}

/** What would change the read — stated before any position is considered. */
export function invalidation({ conf, levels, price, atr }) {
  const out = [];
  const sup = levels?.support?.[0];
  const res = levels?.resistance?.[0];
  if (conf.bias === BIAS.BULLISH && sup) {
    out.push(`A close below ${sup.price} (${sup.touches}× tested) breaks the structure this read depends on.`);
  }
  if (conf.bias === BIAS.BEARISH && res) {
    out.push(`A close above ${res.price} (${res.touches}× tested) breaks the structure this read depends on.`);
  }
  if (atr && price) {
    out.push(`Typical daily range is ${atr.toFixed(2)} (${((atr / price) * 100).toFixed(1)}% of price) — moves smaller than this are noise, not signal.`);
  }
  if (conf.counts.unavailable > 0) {
    out.push(`${conf.counts.unavailable} input(s) unavailable; the read would change if that data arrives.`);
  }
  if (conf.bias === BIAS.CONFLICTED) {
    out.push("Signals disagree — waiting for them to align is itself a valid decision.");
  }
  return out;
}
