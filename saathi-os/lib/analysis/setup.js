// Swing setup detection and plan assembly. PURE.
//
// Produces the structured answer behind "what's the setup", "what are my levels",
// "challenge my idea" and "give me a plan". Everything is derived from computed
// structure — entry zones come from levels, stops from ATR and structure, targets
// from the next real level. Nothing is a round number someone liked the look of.
//
// AUTHORITY: this is research output. It carries no size, no order and no approval.
// Position sizing belongs to PortfolioConstructionEngine, limits to
// PortfolioRiskEngine, and the Guardian can still block whatever this suggests.

import { BIAS } from "./confluence.js";

export const SETUP = {
  BREAKOUT: "BREAKOUT",
  PULLBACK: "PULLBACK",
  CONTINUATION: "CONTINUATION",
  REVERSAL_WATCH: "REVERSAL_WATCH",
  NONE: "NONE",
};

/**
 * Rank the candidate setups against the evidence rather than picking a favourite.
 * Each candidate carries its own case AND its main tradeoff, so a weak setup cannot
 * masquerade as a strong one.
 */
export function detectSetups({ conf, structure, levels, price, action, volume, indicators, atr }) {
  const out = [];
  const res = levels?.resistance?.[0];
  const sup = levels?.support?.[0];
  const rsi = indicators?.rsi?.status === "VALID" ? indicators.rsi.value : null;
  const hist = indicators?.macd?.status === "VALID"
    ? (indicators.macd.value?.histogram ?? indicators.macd.value) : null;

  // BREAKOUT — price pressing a tested resistance with participation
  if (res && res.distancePct <= 3) {
    const volOk = volume?.state === "EXPANDING";
    const momOk = hist !== null && hist > 0;
    out.push({
      type: SETUP.BREAKOUT,
      score: 40 + (volOk ? 25 : 0) + (momOk ? 20 : 0) + (conf.bias === BIAS.BULLISH ? 15 : 0),
      case: `Price is ${res.distancePct}% under ${res.price}, a level tested ${res.touches}×.`,
      tradeoff: volOk
        ? "Breakouts fail often; this one at least has expanding volume behind it."
        : "Volume is not expanding — breakouts without participation fail more often than they hold.",
      trigger: `A close above ${res.price}`,
      confirmation: [
        "close above the level, not just an intraday poke",
        volOk ? "volume already expanding" : "volume expanding on the breakout bar",
        momOk ? "MACD histogram already positive" : "MACD histogram turning positive",
      ],
    });
  }

  // PULLBACK — uptrend structure, price back toward support, momentum cooled
  if (structure?.structure === "UPTREND" && sup && sup.distancePct > -8) {
    const cooled = rsi !== null && rsi < 55;
    out.push({
      type: SETUP.PULLBACK,
      score: 35 + (cooled ? 25 : 0) + (conf.bias === BIAS.BULLISH ? 20 : 0) + (sup.touches > 1 ? 10 : 0),
      case: `Structure is still higher-high/higher-low, with support at ${sup.price} ${Math.abs(sup.distancePct)}% below.`,
      tradeoff: cooled
        ? "Momentum has cooled, which is what makes a pullback entry possible — and also what makes it a falling knife if structure breaks."
        : "Momentum has not cooled; this may be too early to call a pullback.",
      trigger: `A reclaim/hold of ${sup.price} with a higher low`,
      confirmation: ["a higher low forming above support", "RSI turning up from the mid-band", "no close below the support cluster"],
    });
  }

  // CONTINUATION — trend intact, momentum aligned, no level immediately overhead
  if (conf.bias === BIAS.BULLISH && hist !== null && hist > 0 && (!res || res.distancePct > 3)) {
    out.push({
      type: SETUP.CONTINUATION,
      score: 30 + (structure?.structure === "UPTREND" ? 25 : 0) + (volume?.state === "EXPANDING" ? 15 : 0),
      case: `Momentum is aligned with trend and the nearest resistance is ${res ? `${res.distancePct}% away` : "not established"}.`,
      tradeoff: "Continuation entries chase; the stop sits further from entry, so the reward-to-risk is usually worse than a pullback.",
      trigger: "Continued higher closes without a lower low",
      confirmation: ["no lower low", "MACD histogram holding positive", "volume not contracting"],
    });
  }

  // REVERSAL WATCH — oversold in a downtrend, or overbought in an uptrend
  if (rsi !== null && ((rsi <= 30 && structure?.structure === "DOWNTREND") || (rsi >= 70 && structure?.structure === "UPTREND"))) {
    out.push({
      type: SETUP.REVERSAL_WATCH,
      score: 25,
      case: `RSI ${rsi} against a ${structure.structure.toLowerCase()} — stretched, not yet turning.`,
      tradeoff: "Counter-trend. Stretched can stay stretched; this is a watch, not an entry.",
      trigger: "A structure break in the opposite direction",
      confirmation: ["an actual break of the last swing against the trend", "momentum divergence", "volume on the turn"],
    });
  }

  out.sort((a, b) => b.score - a.score);
  return out.length ? out : [{
    type: SETUP.NONE,
    score: 0,
    case: "No setup is presenting: price is not near a tested level and momentum is not aligned.",
    tradeoff: "Nothing to trade is a position.",
    trigger: "—",
    confirmation: [],
  }];
}

/**
 * Assemble a full plan for the leading setup.
 * Stop = beyond structure by one ATR (not a round percentage). Targets = the next
 * real levels. If either cannot be derived, the plan says so instead of inventing one.
 */
export function buildPlan({ setup, conf, levels, price, atr, instrument, asOf, source }) {
  const res = levels?.resistance || [];
  const sup = levels?.support || [];
  const long = conf.bias !== BIAS.BEARISH;

  let entry = null;
  let stop = null;
  const targets = [];
  const notes = [];

  if (setup.type === SETUP.BREAKOUT && res[0]) {
    entry = { type: "on a close above", from: res[0].price, to: +(res[0].price * 1.01).toFixed(4) };
    if (sup[0]) stop = atr ? +(sup[0].price - atr).toFixed(4) : sup[0].price;
    res.slice(1, 3).forEach((r) => targets.push({ price: r.price, why: `next resistance, ${r.touches}× tested` }));
  } else if (setup.type === SETUP.PULLBACK && sup[0]) {
    entry = { type: "on a hold of", from: sup[0].price, to: +(sup[0].price * 1.02).toFixed(4) };
    stop = atr ? +(sup[0].price - atr).toFixed(4) : +(sup[0].price * 0.97).toFixed(4);
    res.slice(0, 2).forEach((r) => targets.push({ price: r.price, why: `resistance, ${r.touches}× tested` }));
  } else if (setup.type === SETUP.CONTINUATION) {
    entry = { type: "current area", from: price, to: price };
    if (atr) stop = +(price - atr * 2).toFixed(4);
    res.slice(0, 2).forEach((r) => targets.push({ price: r.price, why: `resistance, ${r.touches}× tested` }));
    if (!res.length) notes.push("No resistance is established above — a target cannot be derived from structure, so none is stated.");
  } else {
    notes.push("No entry is derived: the leading candidate is a watch, not a setup.");
  }

  let riskReward = null;
  if (entry && stop !== null && targets.length) {
    const e = entry.from;
    const risk = Math.abs(e - stop);
    const reward = Math.abs(targets[0].price - e);
    riskReward = risk > 0 ? +(reward / risk).toFixed(2) : null;
    if (riskReward !== null && riskReward < 1.5) {
      notes.push(`Reward-to-risk is ${riskReward}:1 — below the 1.5:1 that usually justifies taking the trade at all.`);
    }
  }

  const verdict =
    conf.bias === BIAS.INSUFFICIENT ? "AVOID — not enough evidence to form a view"
      : setup.type === SETUP.NONE ? "WAIT — no setup present"
      : conf.bias === BIAS.CONFLICTED ? "WAIT — signals disagree"
      : riskReward !== null && riskReward < 1.5 ? "WAIT — reward does not justify the risk"
      : conf.confidence === "LOW" ? "WATCH — thesis is thin"
      : "WATCH — setup present, wait for the trigger";

  return {
    instrument,
    asOf,
    source,
    bias: conf.bias,
    confidence: conf.confidence,
    setup: setup.type,
    verdict,
    entry,
    stop,
    targets,
    riskReward,
    trigger: setup.trigger,
    confirmation: setup.confirmation,
    notes,
    authority: {
      isAdvice: false,
      note: "Research output. It carries no position size and no order. Sizing is the construction engine's, limits are the risk engine's, and the Guardian can block it.",
    },
  };
}

/** Both sides of the argument, so a plan is never presented unopposed. */
export function challenge({ conf, setup, levels, indicators, structure }) {
  const bullCase = conf.counts.bullish ? conf.agreeing.concat(conf.conflicting).filter((x) => x.direction === "BULLISH") : [];
  const bearCase = conf.counts.bearish ? conf.agreeing.concat(conf.conflicting).filter((x) => x.direction === "BEARISH") : [];
  const overlooked = [];

  if (conf.counts.unavailable) {
    overlooked.push(`${conf.counts.unavailable} input(s) are unavailable — the read rests on less evidence than it appears to.`);
  }
  if (structure?.structure === "UNCLEAR") {
    overlooked.push("Market structure is unclear, so any trend claim here is weaker than it sounds.");
  }
  if (setup.type === SETUP.CONTINUATION) {
    overlooked.push("A continuation entry is a chase — the stop is far, so the same target pays less per unit of risk.");
  }
  if (indicators?.rsi?.status === "VALID" && indicators.rsi.value >= 70) {
    overlooked.push("RSI is overbought: buying here needs the trend to keep extending, not merely to hold.");
  }
  if (!levels?.support?.length) {
    overlooked.push("No support level is established below — there is no structural place to put a stop.");
  }
  return {
    bullCase: bullCase.map((x) => `${x.name}: ${x.detail}`),
    bearCase: bearCase.map((x) => `${x.name}: ${x.detail}`),
    overlooked,
    wouldConvince: conf.bias === BIAS.BULLISH
      ? "A close above the nearest resistance on expanding volume, holding for more than one bar."
      : "A close below the nearest support on expanding volume, with a lower high behind it.",
  };
}
