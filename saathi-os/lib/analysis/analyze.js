// Chart analysis orchestrator. PURE — bars in, a complete structured analysis out.
//
// This is the single entry point behind every analysis view. It answers, from
// computed evidence only:
//   what the chart is doing        (trend, structure, levels, momentum, volume)
//   which signals agree or clash   (confluence)
//   what setup is present          (breakout / pullback / continuation / none)
//   the levels that matter         (and why each one earned its place)
//   the plan and its invalidation  (entry, stop, targets, R:R, what kills it)
//   the case against               (challenge)
//
// A language model may narrate this bundle. It may not add a number to it — see
// narrationPrompt() below.

import {
  swingPoints, marketStructure, trendFromMovingAverages, levels as levelsOf,
  pivotPoints, priceAction, volumeState,
} from "./structure.js";
import { signalSet, confluence, invalidation, BIAS } from "./confluence.js";
import { detectSetups, buildPlan, challenge, SETUP } from "./setup.js";

/**
 * @param {Array} bars   oldest → newest, {date, open?, high?, low?, close, volume?}
 * @param {Object} indicators typed results from lib/nepse/indicators.js
 * @param {Object} meta  {instrument, source, adjustment, fieldTrust}
 */
export function analyzeChart(bars, indicators = {}, meta = {}) {
  const usable = (bars || []).filter((b) => b && typeof b.close === "number");
  if (usable.length < 30) {
    return {
      ok: false,
      reason: "INSUFFICIENT_HISTORY",
      observations: usable.length,
      note: `chart analysis needs at least 30 bars, has ${usable.length}`,
      instrument: meta.instrument || "",
    };
  }

  const last = usable[usable.length - 1];
  const price = last.close;

  // Only use high/low for swings when the caller says the range is trustworthy.
  const useRange = meta.fieldTrust?.range !== false;

  const swings = swingPoints(usable, 3, { useRange });
  const structure = marketStructure(swings);
  const lv = levelsOf(swings, price);
  const action = priceAction(usable, 10);
  const volume = volumeState(usable);
  const pivots = useRange ? pivotPoints(last) : null;

  const val = (k) => (indicators[k]?.status === "VALID" ? indicators[k].value : null);
  const maTrend = trendFromMovingAverages(price, {
    sma50: val("sma"),
    ema20: val("ema"),
    sma200: null,
  });
  const atr = val("atr");

  const signals = signalSet({ structure, maTrend, indicators, price, action, volume, levels: lv });
  const conf = confluence(signals);
  const setups = detectSetups({ conf, structure, levels: lv, price, action, volume, indicators, atr });
  const plan = buildPlan({
    setup: setups[0], conf, levels: lv, price, atr,
    instrument: meta.instrument || "", asOf: last.date, source: meta.source || "",
  });
  const invalid = invalidation({ conf, levels: lv, price, atr });
  const against = challenge({ conf, setup: setups[0], levels: lv, indicators, structure });

  return {
    ok: true,
    instrument: meta.instrument || "",
    asOf: last.date,
    price,
    source: meta.source || "",
    adjustment: meta.adjustment || null,
    observations: usable.length,
    fieldTrust: meta.fieldTrust || {},

    structure,
    maTrend,
    levels: lv,
    pivots,
    action,
    volume,
    indicators,

    signals,
    confluence: conf,
    invalidation: invalid,

    setups,
    plan,
    challenge: against,

    authority: {
      isAdvice: false,
      note: "Research and observation only. No order, no size, no approval. The construction engine sizes, the risk engine limits, the Guardian can block.",
    },
  };
}

/**
 * Build the prompt that lets a model NARRATE an analysis.
 *
 * The model receives only computed facts and is forbidden from adding numbers. This
 * is the whole reason the analysis is deterministic first: the explanation can be
 * fluent without any figure in it being invented.
 */
export function narrationPrompt(analysis, question = "") {
  if (!analysis?.ok) return null;
  const a = analysis;
  const fmt = (n) => (typeof n === "number" ? n.toLocaleString(undefined, { maximumFractionDigits: 4 }) : String(n));

  const facts = [
    `Instrument: ${a.instrument}`,
    `As of: ${a.asOf}  Price: ${fmt(a.price)}  Observations: ${a.observations}`,
    `Source: ${a.source}${a.adjustment ? ` (${a.adjustment})` : ""}`,
    "",
    `Structure: ${a.structure.structure} — ${a.structure.reason}`,
    `Moving averages: ${a.maTrend.trend} (above ${a.maTrend.above.join(", ") || "none"}; below ${a.maTrend.below.join(", ") || "none"})`,
    `Volume: ${a.volume.state}${a.volume.ratio ? ` (${a.volume.ratio}× 20-bar average)` : ""}`,
    `Recent action: ${a.action ? `${a.action.changePct}% over ${a.action.bars} bars, ${a.action.upDays} up / ${a.action.downDays} down` : "unavailable"}`,
    "",
    "Support: " + (a.levels.support.map((s) => `${fmt(s.price)} (${s.touches}× , ${s.distancePct}%)`).join("; ") || "none established"),
    "Resistance: " + (a.levels.resistance.map((s) => `${fmt(s.price)} (${s.touches}× , ${s.distancePct}%)`).join("; ") || "none established"),
    "",
    "Signals:",
    ...a.signals.map((s) => `  - ${s.name}: ${s.direction} — ${s.detail}`),
    "",
    `Bias: ${a.confluence.bias} (confidence ${a.confluence.confidence})`,
    `Agreeing: ${a.confluence.counts.bullish} bullish / ${a.confluence.counts.bearish} bearish / ${a.confluence.counts.unavailable} unavailable`,
    "",
    `Leading setup: ${a.setups[0].type} — ${a.setups[0].case}`,
    `Tradeoff: ${a.setups[0].tradeoff}`,
    `Verdict: ${a.plan.verdict}`,
    a.plan.entry ? `Entry: ${a.plan.entry.type} ${fmt(a.plan.entry.from)}` : "Entry: none derived",
    a.plan.stop !== null ? `Stop: ${fmt(a.plan.stop)}` : "Stop: none derived",
    a.plan.targets.length ? `Targets: ${a.plan.targets.map((t) => `${fmt(t.price)} (${t.why})`).join("; ")}` : "Targets: none derived",
    a.plan.riskReward !== null ? `Reward-to-risk: ${a.plan.riskReward}:1` : "Reward-to-risk: not computable",
    "",
    "Invalidation:",
    ...a.invalidation.map((s) => `  - ${s}`),
    "",
    "Case against:",
    ...a.challenge.overlooked.map((s) => `  - ${s}`),
  ].join("\n");

  const rules = [
    "You are explaining a chart analysis that has ALREADY been computed.",
    "",
    "HARD RULES:",
    "1. Every number you use must appear in the FACTS below. Do not compute, round, extrapolate or invent any price, level, percentage or indicator value.",
    "2. If something is marked unavailable, say it is unavailable. Never estimate it.",
    "3. Do not give investment advice, a recommendation to buy or sell, or a position size. Explain what the chart shows and what would change it.",
    "4. Lead with what conflicts, not only what agrees.",
    "5. If the bias is INSUFFICIENT_EVIDENCE or the verdict is AVOID/WAIT, say so plainly rather than finding something encouraging to say.",
  ].join("\n");

  return `${rules}\n\nFACTS:\n${facts}\n\n${question ? `QUESTION: ${question}\n` : ""}Explain this in plain language for an experienced swing trader.`;
}

export { BIAS, SETUP };
