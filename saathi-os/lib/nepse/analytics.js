// NEPSE analytics — transparent, deterministic scoring. Pure.
//
// IMPORTANT: this is an ILLUSTRATIVE composite, not "AI" and NOT investment advice.
// It combines observable momentum, RSI mean-reversion, and valuation into a bounded
// 0–100 number so the screener has a sortable column. It is documented, reproducible,
// and must never be presented as a recommendation to buy or sell real securities.

import { dayChangePct } from "./format.js";

const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

// Wilder-style RSI over a series of closes; returns 0..100. Falls back gracefully.
export function rsi(closes, period = 14) {
  if (!Array.isArray(closes) || closes.length < 2) return 50;
  let gain = 0;
  let loss = 0;
  const n = Math.min(period, closes.length - 1);
  for (let i = closes.length - n; i < closes.length; i += 1) {
    const d = closes[i] - closes[i - 1];
    if (d >= 0) gain += d; else loss -= d;
  }
  if (loss === 0) return 100;
  const rs = gain / loss;
  return +(100 - 100 / (1 + rs)).toFixed(2);
}

// Momentum sub-score (0..100) from day change, saturating at ±5%.
function momentumScore(stock) {
  const chg = dayChangePct(stock.ltp, stock.prevClose);
  return clamp(50 + chg * 10, 0, 100);
}

// RSI sub-score: rewards the 40–60 "healthy" band, penalizes overbought/oversold.
function rsiScore(stock) {
  const r = Number(stock.rsi);
  if (!Number.isFinite(r)) return 50;
  return clamp(100 - Math.abs(r - 50) * 1.6, 0, 100);
}

// Valuation sub-score: lower P/E and P/B => higher score (cheaper = better), bounded.
function valuationScore(stock) {
  const pe = Number(stock.pe);
  const pb = Number(stock.pb);
  let s = 50;
  if (Number.isFinite(pe) && pe > 0) s += clamp((20 - pe) * 2, -30, 30);
  if (Number.isFinite(pb) && pb > 0) s += clamp((2 - pb) * 15, -20, 20);
  return clamp(s, 0, 100);
}

export const SCORE_WEIGHTS = { momentum: 0.3, rsi: 0.3, valuation: 0.4 };

export function scoreStock(stock) {
  if (!stock) return 0;
  const s =
    momentumScore(stock) * SCORE_WEIGHTS.momentum +
    rsiScore(stock) * SCORE_WEIGHTS.rsi +
    valuationScore(stock) * SCORE_WEIGHTS.valuation;
  return Math.round(clamp(s, 0, 100));
}

export function signalFor(score) {
  if (score >= 66) return "Buy";
  if (score <= 39) return "Sell";
  return "Neutral";
}

// Valuation tag from P/E vs a coarse market anchor (~18x).
export function evaluationFor(stock) {
  const pe = Number(stock?.pe);
  if (!Number.isFinite(pe) || pe <= 0) return "Unrated";
  if (pe < 12) return "Undervalued";
  if (pe < 22) return "Fairly valued";
  if (pe < 35) return "Fully valued";
  return "Overvalued";
}

// Attach all derived analytics fields to a stock (non-mutating).
export function withAnalytics(stock) {
  const score = scoreStock(stock);
  return { ...stock, score, signal: signalFor(score), evaluation: evaluationFor(stock) };
}
