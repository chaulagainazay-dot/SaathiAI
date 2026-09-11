/**
 * NEPSE-HIST-2 — historical source qualification and indicator enablement.
 *
 * These assertions encode the milestone's invariants: close-only indicators run,
 * field-gated ones refuse rather than approximate, OPEN is never fabricated,
 * unadjusted corporate actions are surfaced, and unknown is never a number.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import {
  parseHistoryCsv, closeSeries, historyQuality, corporateActionGaps,
  ROW_FLAG, ADJUSTMENT, SOURCE_CLASS, OPEN_TRUSTED_FROM, NEPSE_RESEARCH_SOURCE,
} from "./nepse/history.js";
import {
  computeIndicators, INDICATOR_STATUS, INDICATOR_REQUIREMENTS,
  rsiValue, macdValue, bollingerValue, sma, ema, atrValue, indicatorDisplay,
} from "./nepse/indicators.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");

const HEAD = "published_date,open,high,low,close,per_change,traded_quantity,traded_amount,status";

/** Build a synthetic but calendar-valid close series (Sun–Thu only). */
function series(n, startClose = 100, step = 1, { withRange = true } = {}) {
  const rows = [HEAD];
  const d = new Date(Date.UTC(2024, 0, 7)); // a Sunday
  let c = startClose;
  for (let i = 0; i < n; i += 1) {
    while ([5, 6].includes(d.getUTCDay())) d.setUTCDate(d.getUTCDate() + 1);
    const iso = d.toISOString().slice(0, 10);
    c = +(c + (i % 3 === 0 ? step : -step / 2)).toFixed(2);
    const hi = withRange ? (c + 2).toFixed(2) : "";
    const lo = withRange ? (c - 2).toFixed(2) : "";
    rows.push(`${iso},${c.toFixed(2)},${hi},${lo},${c.toFixed(2)},0.1,1000,100000,1`);
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return rows.join("\n");
}

// ── source classification ────────────────────────────────────────────────────────
test("the qualified source is declared RESEARCH_ONLY, unadjusted, unlicensed", () => {
  assert.equal(NEPSE_RESEARCH_SOURCE.classification, SOURCE_CLASS.RESEARCH_ONLY);
  assert.equal(NEPSE_RESEARCH_SOURCE.adjustment, ADJUSTMENT.UNADJUSTED);
  assert.equal(NEPSE_RESEARCH_SOURCE.license, null);
  assert.equal(NEPSE_RESEARCH_SOURCE.revisionMetadata, false, "no revision metadata -> no universal PIT claim");
  assert.equal(NEPSE_RESEARCH_SOURCE.adjustmentMethod, "ADJUSTMENT_METHOD_UNVERIFIED");
});

// ── parsing + per-field trust ────────────────────────────────────────────────────
test("parses the real source schema", () => {
  const { bars } = parseHistoryCsv(series(5), { symbol: "TEST" });
  assert.equal(bars.length, 5);
  assert.equal(bars[0].symbol, "TEST");
  assert.ok(bars[0].trusted.close);
});

test("OPEN before the trusted era is distrusted, never repaired", () => {
  const csv = [HEAD, "2015-06-07,1091.0,1155.0,1112.0,1155.0,0,10,100,1"].join("\n");
  const { bars } = parseHistoryCsv(csv, { symbol: "OLD" });
  const b = bars[0];
  assert.equal(b.trusted.open, false);
  assert.ok(b.flags.includes(ROW_FLAG.OPEN_ERA_UNTRUSTED));
  assert.equal(b.open, 1091.0, "raw value is preserved, not rewritten");
  assert.ok(b.trusted.close, "a bad open must not invalidate the close");
});

test("OPEN outside the day's range is flagged even after the trusted era", () => {
  const csv = [HEAD, "2024-01-07,999.0,540.0,530.0,535.0,0,10,100,1"].join("\n");
  const { bars } = parseHistoryCsv(csv, { symbol: "X" });
  assert.equal(bars[0].trusted.open, false);
  assert.ok(bars[0].flags.includes(ROW_FLAG.OPEN_OUT_OF_RANGE));
});

test("high < low invalidates the range but not the close", () => {
  const csv = [HEAD, "2024-01-07,100,90,110,100,0,10,100,1"].join("\n");
  const { bars } = parseHistoryCsv(csv, { symbol: "X" });
  assert.ok(bars[0].flags.includes(ROW_FLAG.HIGH_BELOW_LOW));
  assert.equal(bars[0].trusted.high, false);
  assert.equal(bars[0].trusted.close, true);
});

test("Friday and Saturday rows are flagged — NEPSE trades Sun–Thu", () => {
  const csv = [HEAD,
    "2024-01-12,100,101,99,100,0,10,100,1",   // Friday
    "2024-01-13,100,101,99,100,0,10,100,1",   // Saturday
    "2024-01-14,100,101,99,100,0,10,100,1",   // Sunday
  ].join("\n");
  const { bars } = parseHistoryCsv(csv, { symbol: "X" });
  assert.ok(bars[0].flags.includes(ROW_FLAG.CALENDAR_CONFLICT));
  assert.ok(bars[1].flags.includes(ROW_FLAG.CALENDAR_CONFLICT));
  assert.ok(!bars[2].flags.includes(ROW_FLAG.CALENDAR_CONFLICT));
});

test("duplicate and out-of-order dates are flagged, not silently deduped", () => {
  const csv = [HEAD,
    "2024-01-08,100,101,99,100,0,10,100,1",
    "2024-01-08,100,101,99,100,0,10,100,1",
    "2024-01-07,100,101,99,100,0,10,100,1",
  ].join("\n");
  const { bars } = parseHistoryCsv(csv, { symbol: "X" });
  assert.equal(bars.length, 3, "rows are kept and flagged, never dropped silently");
  assert.ok(bars[1].flags.includes(ROW_FLAG.DUPLICATE_DATE));
  assert.ok(bars[2].flags.includes(ROW_FLAG.OUT_OF_ORDER));
});

test("a row without a close is rejected, not defaulted", () => {
  const csv = [HEAD, "2024-01-07,100,101,99,,0,10,100,1"].join("\n");
  const { bars, rejected } = parseHistoryCsv(csv, { symbol: "X" });
  assert.equal(bars.length, 0);
  assert.equal(rejected[0].reason, ROW_FLAG.MISSING_CLOSE);
});

test("missing sessions are never synthesized", () => {
  const csv = [HEAD,
    "2024-01-07,100,101,99,100,0,10,100,1",
    "2024-01-21,100,101,99,100,0,10,100,1",  // two weeks later
  ].join("\n");
  const { bars } = parseHistoryCsv(csv, { symbol: "X" });
  assert.equal(bars.length, 2, "the gap stays a gap");
});

// ── close-only indicators run ────────────────────────────────────────────────────
test("RSI, MACD and Bollinger compute from CLOSE alone (no high/low/open)", () => {
  const csv = series(120, 100, 1, { withRange: false }); // no high/low at all
  const { bars } = parseHistoryCsv(csv, { symbol: "C" });
  const ind = computeIndicators(bars, { instrument: "C" });
  for (const name of ["rsi", "macd", "bollinger"]) {
    assert.equal(ind[name].status, INDICATOR_STATUS.VALID, `${name} must run close-only`);
    assert.notEqual(ind[name].value, null);
  }
  assert.deepEqual(INDICATOR_REQUIREMENTS.rsi, ["close"]);
  assert.deepEqual(INDICATOR_REQUIREMENTS.macd, ["close"]);
  assert.deepEqual(INDICATOR_REQUIREMENTS.bollinger, ["close"]);
});

test("SMA and EMA are close-only too", () => {
  const { bars } = parseHistoryCsv(series(120, 100, 1, { withRange: false }), { symbol: "C" });
  const ind = computeIndicators(bars, { instrument: "C" });
  assert.equal(ind.sma.status, INDICATOR_STATUS.VALID);
  assert.equal(ind.ema.status, INDICATOR_STATUS.VALID);
});

test("RSI maths: monotonic rise saturates, flat series is neutral", () => {
  assert.equal(rsiValue(Array.from({ length: 40 }, (_, i) => 100 + i), 14), 100);
  assert.equal(rsiValue(Array.from({ length: 40 }, () => 100), 14), 50);
});

test("MACD returns line, signal and histogram", () => {
  const m = macdValue(Array.from({ length: 120 }, (_, i) => 100 + Math.sin(i / 5) * 4 + i * 0.2));
  assert.ok(m && typeof m.macd === "number" && typeof m.signal === "number");
  assert.equal(+(m.macd - m.signal).toFixed(4), m.histogram);
});

test("Bollinger %B sits between the bands and is null when they collapse", () => {
  const b = bollingerValue(Array.from({ length: 40 }, (_, i) => 100 + (i % 5)), 20);
  assert.ok(b.upper > b.middle && b.middle > b.lower);
  const flat = bollingerValue(Array.from({ length: 40 }, () => 100), 20);
  assert.equal(flat.percentB, null, "a zero-width band has no defined %B");
});

// ── field-gated indicators refuse rather than approximate ────────────────────────
test("ATR is FIELD_UNAVAILABLE when high/low are absent — never derived from close", () => {
  const { bars } = parseHistoryCsv(series(120, 100, 1, { withRange: false }), { symbol: "C" });
  const ind = computeIndicators(bars, { instrument: "C" });
  assert.equal(ind.atr.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(ind.atr.value, null);
  assert.match(ind.atr.note, /never approximated from close/i);
  assert.deepEqual(INDICATOR_REQUIREMENTS.atr, ["high", "low", "close"]);
});

test("ATR computes when high/low are trusted", () => {
  const { bars } = parseHistoryCsv(series(120, 100, 1, { withRange: true }), { symbol: "R" });
  const ind = computeIndicators(bars, { instrument: "R" });
  assert.equal(ind.atr.status, INDICATOR_STATUS.VALID);
  assert.ok(ind.atr.value > 0);
});

test("anything requiring OPEN is refused on this source", () => {
  const { bars } = parseHistoryCsv(series(120), { symbol: "O" });
  const ind = computeIndicators(bars, { instrument: "O" });
  assert.equal(ind.openGap.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
  assert.equal(ind.openGap.value, null);
  assert.match(ind.openGap.note, /never fabricated/i);
});

// ── insufficient history ─────────────────────────────────────────────────────────
test("short history yields INSUFFICIENT_HISTORY, never a number", () => {
  const { bars } = parseHistoryCsv(series(5), { symbol: "S" });
  const ind = computeIndicators(bars, { instrument: "S" });
  assert.equal(ind.rsi.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
  assert.equal(ind.rsi.value, null);
  assert.equal(ind.rsi.observations, 5);
});

test("no indicator ever returns a fake numeric default", () => {
  const { bars } = parseHistoryCsv(series(3), { symbol: "S" });
  const ind = computeIndicators(bars, { instrument: "S" });
  for (const [name, r] of Object.entries(ind)) {
    if (r.status !== INDICATOR_STATUS.VALID) {
      assert.equal(r.value, null, `${name} must be null when not VALID, never 0`);
    }
  }
});

// ── adjustment safety ────────────────────────────────────────────────────────────
test("unadjusted corporate actions are detected, not smoothed", () => {
  const rows = [HEAD];
  const d = new Date(Date.UTC(2024, 0, 7));
  for (let i = 0; i < 40; i += 1) {
    while ([5, 6].includes(d.getUTCDay())) d.setUTCDate(d.getUTCDate() + 1);
    const c = i === 30 ? 70 : 100; // a -30% ex-date, impossible under a ±10% circuit
    rows.push(`${d.toISOString().slice(0, 10)},${c},${c + 1},${c - 1},${c},0,10,100,1`);
    d.setUTCDate(d.getUTCDate() + 1);
  }
  const { bars } = parseHistoryCsv(rows.join("\n"), { symbol: "CA" });
  const gaps = corporateActionGaps(bars);
  assert.equal(gaps.length >= 1, true);
  assert.ok(Math.abs(gaps[0].pct) > 20);
});

test("an indicator whose window spans a corporate action reports DATA_CONFLICT", () => {
  const rows = [HEAD];
  const d = new Date(Date.UTC(2024, 0, 7));
  for (let i = 0; i < 60; i += 1) {
    while ([5, 6].includes(d.getUTCDay())) d.setUTCDate(d.getUTCDate() + 1);
    const c = i >= 55 ? 60 : 100;
    rows.push(`${d.toISOString().slice(0, 10)},${c},${c + 1},${c - 1},${c},0,10,100,1`);
    d.setUTCDate(d.getUTCDate() + 1);
  }
  const { bars } = parseHistoryCsv(rows.join("\n"), { symbol: "CA" });
  const ind = computeIndicators(bars, { instrument: "CA" });
  assert.equal(ind.rsi.status, INDICATOR_STATUS.DATA_CONFLICT);
  assert.ok(ind.rsi.detail.corporateActionInWindow);
});

test("every indicator result carries its provenance", () => {
  const { bars } = parseHistoryCsv(series(120), { symbol: "P" });
  const ind = computeIndicators(bars, { instrument: "P" });
  for (const r of Object.values(ind)) {
    assert.equal(r.source, NEPSE_RESEARCH_SOURCE.id);
    assert.equal(r.adjustment, ADJUSTMENT.UNADJUSTED);
    assert.ok("status" in r && "observations" in r && "lookback" in r);
  }
});

// ── quality report ───────────────────────────────────────────────────────────────
test("quality report summarises the real defects", () => {
  const csv = [HEAD,
    "2015-06-07,1091,1155,1112,1155,0,10,100,1",  // untrusted-era open, out of range
    "2024-01-12,100,101,99,100,0,10,100,1",       // Friday
    "2024-01-14,100,90,110,100,0,10,100,1",       // high < low
  ].join("\n");
  const { bars, rejected } = parseHistoryCsv(csv, { symbol: "Q" });
  const q = historyQuality(bars, rejected);
  assert.equal(q.rows, 3);
  assert.ok(q.flags.OPEN_ERA_UNTRUSTED >= 1);
  assert.ok(q.flags.CALENDAR_CONFLICT >= 1);
  assert.ok(q.flags.HIGH_BELOW_LOW >= 1);
  assert.equal(q.adjustment, ADJUSTMENT.UNADJUSTED);
  assert.equal(q.classification, SOURCE_CLASS.RESEARCH_ONLY);
});

test("closeSeries drops unusable rows without repairing them", () => {
  const csv = [HEAD,
    "2024-01-07,100,101,99,100,0,10,100,1",
    "2024-01-08,-5,-4,-6,-5,0,10,100,1",   // non-positive
  ].join("\n");
  const { bars } = parseHistoryCsv(csv, { symbol: "Z" });
  assert.equal(closeSeries(bars).length, 1);
});

// ── display + security + route discipline ────────────────────────────────────────
test("unknown renders as an em dash, never zero", () => {
  assert.equal(indicatorDisplay({ value: null, status: INDICATOR_STATUS.FIELD_UNAVAILABLE }), "—");
  assert.equal(indicatorDisplay({ value: null, status: INDICATOR_STATUS.INSUFFICIENT_HISTORY }), "—");
  assert.equal(indicatorDisplay({ value: 61.4, status: INDICATOR_STATUS.VALID }, (v) => v.toFixed(1)), "61.4");
});

test("history route pins host, symbol shape and size", () => {
  const f = join(ROOT, "app/api/nepse/history/route.js");
  assert.equal(existsSync(f), true);
  const src = readFileSync(f, "utf8");
  assert.match(src, /SYMBOL_RE = \/\^\[A-Z0-9\]/, "symbol must be pattern-gated (no path traversal)");
  assert.match(src, /redirect: "error"/);
  assert.match(src, /MAX_BYTES/);
  assert.match(src, /hostname !== HOST/);
  assert.match(src, /UNEXPECTED_CONTENT_TYPE/, "an HTML body must be refused");
  assert.match(src, /runtime = "nodejs"/);
});

test("the historical source never claims to be the live price source", () => {
  const src = readFileSync(join(ROOT, "app/api/nepse/history/route.js"), "utf8");
  assert.ok(!/useNepseQuotes/.test(src), "history must not touch the live quote path");
  assert.match(src, /RESEARCH_ONLY|classification/);
});

// ── the composite must never be padded with seed data ────────────────────────────
import { scoreStock, withAnalytics } from "./nepse/analytics.js";

test("scoreStock ignores a seeded rsi field entirely", () => {
  const stock = { ltp: 100, prevClose: 100, pe: 15, pb: 1.5, eps: 6.7, bookValue: 66, rsi: 99 };
  const withoutReal = scoreStock(stock);              // seed rsi 99 must not be used
  const withReal = scoreStock(stock, 50);             // a real mid-band RSI
  assert.notEqual(withoutReal, withReal, "supplying a real RSI must change the score");
  const ignoringSeed = scoreStock({ ...stock, rsi: 1 });
  assert.equal(withoutReal, ignoringSeed, "changing the seeded rsi must not move the score");
});

test("withAnalytics reports whether a real RSI backed the score", () => {
  const stock = { ltp: 100, prevClose: 100, pe: 15, pb: 1.5, eps: 6.7, bookValue: 66, rsi: 99 };
  assert.equal(withAnalytics(stock).scoreUsedRsi, false);
  assert.equal(withAnalytics(stock, 61.4).scoreUsedRsi, true);
});
