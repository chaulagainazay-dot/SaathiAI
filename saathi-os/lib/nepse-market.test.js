// Market-wide aggregates — breadth, movers, sector performance.
//
// The tests that matter here are the ones about ABSENCE: a symbol we could not
// measure must not be counted as flat, and a one-member sector must not be
// reported as a sector move.

import test from "node:test";
import assert from "node:assert/strict";
import {
  sessionChanges, breadth, topMovers, activityLeaders,
  sectorPerformance, marketActivity, marketSummary, MIN_SECTOR_MEMBERS,
  CIRCUIT_LIMIT_PCT, UNCLASSIFIED,
} from "./nepse/market.js";

const bar = (date, close, extra = {}) => ({
  date, close, trusted: { close: true, high: true, low: true, ...(extra.trusted || {}) },
  volume: extra.volume ?? null, turnover: extra.turnover ?? null,
});

const entry = (symbol, sector, closes, extras = []) => ({
  symbol, sector,
  bars: closes.map((c, i) => bar(`2026-09-0${i + 1}`, c, extras[i] || {})),
});

test("sessionChanges computes last-session change from the final two bars", () => {
  const { rows } = sessionChanges([entry("NABIL", "Commercial Banks", [500, 510])]);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].close, 510);
  assert.equal(rows[0].priorClose, 500);
  assert.equal(rows[0].change, 10);
  assert.equal(rows[0].changePct, 2);
  assert.equal(rows[0].priorDate, "2026-09-01");
});

test("a symbol with one bar is EXCLUDED, not counted as unchanged", () => {
  const { rows, excluded } = sessionChanges([entry("NEW", "Hydropower", [100])]);
  assert.equal(rows.length, 0);
  assert.deepEqual(excluded, [{ symbol: "NEW", reason: "INSUFFICIENT_HISTORY" }]);
  // The distinction the whole module exists for: unknown never becomes flat.
  assert.equal(breadth(rows).unchanged, 0);
  assert.equal(breadth(rows).measured, 0);
});

test("untrusted closes are skipped before the last-two are chosen", () => {
  const e = entry("X", "Banks", [100, 999, 110]);
  e.bars[1].trusted.close = false;
  const { rows } = sessionChanges([e]);
  // The untrusted 999 must not become either side of the comparison.
  assert.equal(rows[0].priorClose, 100);
  assert.equal(rows[0].close, 110);
});

test("a zero prior close is excluded rather than dividing by zero", () => {
  const { rows, excluded } = sessionChanges([entry("Z", "Banks", [0, 50])]);
  assert.equal(rows.length, 0);
  assert.equal(excluded[0].reason, "ZERO_PRIOR_CLOSE");
});

test("breadth counts advancing, declining and genuinely flat separately", () => {
  const { rows } = sessionChanges([
    entry("A", "Banks", [100, 110]),
    entry("B", "Banks", [100, 90]),
    entry("C", "Banks", [100, 100]),
  ]);
  const b = breadth(rows);
  assert.deepEqual(
    { advancing: b.advancing, declining: b.declining, unchanged: b.unchanged, measured: b.measured },
    { advancing: 1, declining: 1, unchanged: 1, measured: 3 },
  );
  assert.equal(b.advanceDeclineRatio, 1);
  assert.equal(b.mood, "MIXED");
});

test("advance/decline ratio is null rather than Infinity when nothing declined", () => {
  const { rows } = sessionChanges([entry("A", "Banks", [100, 110])]);
  const b = breadth(rows);
  assert.equal(b.advanceDeclineRatio, null);
  assert.equal(b.mood, "BULLISH");
});

test("empty market reports UNKNOWN mood, not a flat one", () => {
  assert.equal(breadth([]).mood, "UNKNOWN");
});

test("topMovers ranks gainers descending and losers ascending", () => {
  const { rows } = sessionChanges([
    entry("A", "Banks", [100, 105]),   // +5%
    entry("B", "Banks", [100, 110]),   // +10%
    entry("C", "Banks", [100, 92]),    // -8%
    entry("D", "Banks", [100, 97]),    // -3%
  ]);
  const { gainers, losers } = topMovers(rows);
  assert.deepEqual(gainers.map((r) => r.symbol), ["B", "A"]);
  assert.deepEqual(losers.map((r) => r.symbol), ["C", "D"]);
});

test("equal moves break the tie on turnover, so a thin move ranks below a traded one", () => {
  const { rows } = sessionChanges([
    entry("THIN", "Banks", [100, 110], [{}, { turnover: 1000 }]),
    entry("LIQUID", "Banks", [100, 110], [{}, { turnover: 9_000_000 }]),
  ]);
  assert.deepEqual(topMovers(rows).gainers.map((r) => r.symbol), ["LIQUID", "THIN"]);
});

test("activity leaders only rank instruments that actually reported activity", () => {
  const { rows } = sessionChanges([
    entry("A", "Banks", [100, 101], [{}, { turnover: 500, volume: 5 }]),
    entry("B", "Banks", [100, 101], [{}, {}]),  // nothing reported
  ]);
  const l = activityLeaders(rows);
  assert.deepEqual(l.byTurnover.map((r) => r.symbol), ["A"]);
  assert.deepEqual(l.byVolume.map((r) => r.symbol), ["A"]);
});

test("a sector below the member threshold reports INSUFFICIENT_MEMBERS, never an average", () => {
  const { rows } = sessionChanges([entry("SOLO", "Life Insurance", [100, 150])]);
  const s = sectorPerformance(rows);
  assert.equal(s[0].status, "INSUFFICIENT_MEMBERS");
  assert.equal(s[0].changePct, null);
  assert.equal(s[0].members, 1);
  assert.equal(MIN_SECTOR_MEMBERS, 2);
});

test("sector performance averages members and counts its own breadth", () => {
  const { rows } = sessionChanges([
    entry("A", "Banks", [100, 110]),   // +10%
    entry("B", "Banks", [100, 98]),    // -2%
    entry("H", "Hydropower", [100, 108]),
    entry("I", "Hydropower", [100, 106]),
  ]);
  const s = sectorPerformance(rows);
  const banks = s.find((x) => x.sector === "Banks");
  assert.equal(banks.changePct, 4);   // (10 + -2) / 2
  assert.equal(banks.advancing, 1);
  assert.equal(banks.declining, 1);
  // Sorted best-first.
  assert.equal(s[0].sector, "Hydropower");
});

test("turnover weighting follows the money, not the member count", () => {
  const { rows } = sessionChanges([
    entry("BIG", "Banks", [100, 90], [{}, { turnover: 9_000_000 }]),   // -10%, heavy
    entry("TINY", "Banks", [100, 120], [{}, { turnover: 1000 }]),      // +20%, thin
  ]);
  const banks = sectorPerformance(rows)[0];
  assert.equal(banks.changePct, 5);              // unweighted: misleading
  assert.ok(banks.weightedChangePct < -9);       // weighted: the truth
});

test("weighted change is null when no member reported turnover", () => {
  const { rows } = sessionChanges([
    entry("A", "Banks", [100, 110]),
    entry("B", "Banks", [100, 90]),
  ]);
  assert.equal(sectorPerformance(rows)[0].weightedChangePct, null);
});

test("market activity sums only reported values and says how many reported", () => {
  const { rows } = sessionChanges([
    entry("A", "Banks", [100, 101], [{}, { turnover: 500, volume: 5 }]),
    entry("B", "Banks", [100, 101], [{}, { turnover: 1500, volume: 15 }]),
    entry("C", "Banks", [100, 101], [{}, {}]),
  ]);
  const a = marketActivity(rows);
  assert.equal(a.totalTurnover, 2000);
  assert.equal(a.totalVolume, 20);
  assert.equal(a.turnoverReportedBy, 2);
});

test("market activity is null, never 0, when nothing reported", () => {
  const { rows } = sessionChanges([entry("A", "Banks", [100, 101])]);
  const a = marketActivity(rows);
  assert.equal(a.totalTurnover, null);
  assert.equal(a.totalVolume, null);
});

test("coverage never claims to be the whole market when it is not", () => {
  const s = marketSummary([
    entry("A", "Banks", [100, 110]),
    entry("B", "Banks", [100, 90]),
  ], { listedTotal: 372 });
  assert.equal(s.coverage.measured, 2);
  assert.equal(s.coverage.listedTotal, 372);
  assert.equal(s.coverage.isFullMarket, false);
  assert.equal(s.basis, "LAST_COMPLETED_SESSION");
  assert.equal(s.asOf, "2026-09-02");
  assert.equal(s.priorDate, "2026-09-01");
});

test("coverage cannot claim full market when listedTotal is unknown", () => {
  const s = marketSummary([entry("A", "Banks", [100, 110])], {});
  assert.equal(s.coverage.listedTotal, null);
  assert.equal(s.coverage.isFullMarket, false);
});

test("an unclassified symbol lands in its own bucket rather than a real sector", () => {
  const s = marketSummary([
    { symbol: "MYSTERY", bars: [bar("2026-09-01", 100), bar("2026-09-02", 110)] },
    { symbol: "OTHER", bars: [bar("2026-09-01", 100), bar("2026-09-02", 105)] },
  ], {});
  assert.equal(s.sectors[0].sector, UNCLASSIFIED);
  // Never "OK" — the bucket holds an average, but not a sector's average.
  assert.equal(s.sectors[0].status, "UNCLASSIFIED");
});

test("a move beyond the circuit is flagged — unadjusted data reprices, it does not trade", () => {
  const { rows } = sessionChanges([entry("BONUS", "Banks", [100, 80])]); // -20%
  assert.equal(rows[0].circuitExceeded, true);
  assert.equal(CIRCUIT_LIMIT_PCT, 10);
});

test("an ordinary move inside the circuit is not flagged", () => {
  const { rows } = sessionChanges([entry("A", "Banks", [100, 109])]);
  assert.equal(rows[0].circuitExceeded, false);
});

test("a repriced stock is held out of the losers table, not ranked at the top of it", () => {
  const { rows } = sessionChanges([
    entry("BONUS", "Banks", [100, 80]),   // -20%, a corporate action
    entry("REAL", "Banks", [100, 95]),    // -5%, an actual down day
  ]);
  const { losers, repriced } = topMovers(rows);
  assert.deepEqual(losers.map((r) => r.symbol), ["REAL"]);
  assert.deepEqual(repriced.map((r) => r.symbol), ["BONUS"]);
});

test("repriced names are surfaced by marketSummary rather than silently dropped", () => {
  const s = marketSummary([
    entry("BONUS", "Banks", [100, 80]),
    entry("REAL", "Banks", [100, 95]),
  ], { listedTotal: 372 });
  assert.equal(s.repriced.length, 1);
  assert.equal(s.circuitLimitPct, 10);
  // Still counted in breadth: it did decline, we just will not call it the loser.
  assert.equal(s.breadth.declining, 2);
});

test("marketSummary carries exclusions through so the gap is visible", () => {
  const s = marketSummary([
    entry("A", "Banks", [100, 110]),
    entry("NEW", "Banks", [100]),
  ], { listedTotal: 372 });
  assert.equal(s.coverage.excluded, 1);
  assert.equal(s.excluded[0].symbol, "NEW");
});
