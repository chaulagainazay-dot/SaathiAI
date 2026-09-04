/**
 * NEPSE Portfolio Tracker — pure-logic + structural tests (node --test).
 * Convergence gate: every M400-NEPSE-* requirement is exercised below.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { STOCKS, getStock, marketSnapshot, brokersForStock, BROKERS, indexHistory } from "./nepse/data.js";
import { scoreStock, signalFor, evaluationFor, rsi, withAnalytics } from "./nepse/analytics.js";
import { screen, PAGE_SIZE } from "./nepse/screener.js";
import { computePortfolio } from "./nepse/portfolio.js";
import { parseMeroshare, parseTMS, parseNepalShare, importTransactions } from "./nepse/importers.js";
import { fmtRs, fmtPct, dayChangePct, isMarketOpen } from "./nepse/format.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");

// ── M400-NEPSE-001 portfolio math ────────────────────────────────────────────
test("computePortfolio: single BUY lot", () => {
  const r = computePortfolio(
    [{ symbol: "NABIL", side: "BUY", qty: 10, price: 500, date: "2026-01-01" }],
    { NABIL: 512 },
  );
  assert.equal(r.holdings.length, 1);
  const h = r.holdings[0];
  assert.equal(h.qty, 10);
  assert.equal(h.avgCost, 500);
  assert.equal(h.invested, 5000);
  assert.equal(h.marketValue, 5120);
  assert.equal(h.unrealizedPnl, 120);
  assert.equal(r.totals.invested, 5000);
  assert.equal(r.totals.value, 5120);
  assert.equal(r.totals.unrealizedPnl, 120);
});

test("computePortfolio: two BUY lots + partial SELL (weighted avg + realized P&L)", () => {
  const r = computePortfolio(
    [
      { symbol: "API", side: "BUY", qty: 10, price: 100, date: "2026-01-01" },
      { symbol: "API", side: "BUY", qty: 10, price: 200, date: "2026-01-02" }, // avg = 150
      { symbol: "API", side: "SELL", qty: 5, price: 250, date: "2026-01-03" }, // realized (250-150)*5=500
    ],
    { API: 268 },
  );
  const h = r.holdings[0];
  assert.equal(h.qty, 15);
  assert.equal(h.avgCost, 150);
  assert.equal(h.invested, 2250); // 15 * 150
  assert.equal(r.totals.realizedPnl, 500);
  assert.equal(h.marketValue, 15 * 268);
});

test("computePortfolio: over-sell is REJECTED, no negative holding", () => {
  const r = computePortfolio(
    [
      { symbol: "EBL", side: "BUY", qty: 5, price: 600, date: "2026-01-01" },
      { symbol: "EBL", side: "SELL", qty: 9, price: 650, date: "2026-01-02" },
    ],
    { EBL: 640 },
  );
  assert.equal(r.rejected.length, 1);
  assert.equal(r.rejected[0].reason, "oversell");
  assert.equal(r.holdings[0].qty, 5); // unchanged
});

test("computePortfolio: RECEIVABLE shares counted in receivable, not invested", () => {
  const r = computePortfolio(
    [
      { symbol: "UPPER", side: "BUY", qty: 100, price: 300, date: "2026-01-01" },
      { symbol: "UPPER", side: "RECEIVABLE", qty: 10, price: 0, date: "2026-02-01" },
    ],
    { UPPER: 300 },
  );
  assert.equal(r.totals.invested, 30000);
  assert.equal(r.totals.receivable, 3000); // 10 * 300
});

test("computePortfolio: fully sold position drops out", () => {
  const r = computePortfolio(
    [
      { symbol: "API", side: "BUY", qty: 10, price: 100, date: "2026-01-01" },
      { symbol: "API", side: "SELL", qty: 10, price: 120, date: "2026-01-02" },
    ],
    { API: 130 },
  );
  assert.equal(r.holdings.length, 0);
  assert.equal(r.totals.realizedPnl, 200);
});

// ── M400-NEPSE-002 screener ──────────────────────────────────────────────────
test("screen: sector filter", () => {
  const r = screen(STOCKS, { sector: "Hydropower" });
  assert.ok(r.rows.length >= 3);
  assert.ok(r.rows.every((x) => x.sector === "Hydropower"));
});

test("screen: search matches symbol or company (case-insensitive)", () => {
  const bySym = screen(STOCKS, { query: "nabil" });
  assert.ok(bySym.rows.some((x) => x.symbol === "NABIL"));
  const byName = screen(STOCKS, { query: "chartered" });
  assert.ok(byName.rows.some((x) => x.symbol === "SCB"));
});

test("screen: sort by change desc + pagination window", () => {
  const r = screen(STOCKS, { sort: { key: "change", dir: "desc" }, page: 1, pageSize: 5 });
  assert.equal(r.pageSize, 5);
  assert.equal(r.rows.length, 5);
  const changes = r.rows.map((x) => dayChangePct(x.ltp, x.prevClose));
  for (let i = 1; i < changes.length; i += 1) assert.ok(changes[i - 1] >= changes[i]);
});

test("screen: default page size constant", () => {
  assert.equal(PAGE_SIZE, 50);
});

// ── M400-NEPSE-003 analytics ─────────────────────────────────────────────────
test("scoreStock is bounded 0..100 for every seed stock", () => {
  for (const s of STOCKS) {
    const sc = scoreStock(s);
    assert.ok(sc >= 0 && sc <= 100, `${s.symbol} score ${sc}`);
  }
});

test("signalFor thresholds", () => {
  assert.equal(signalFor(80), "Buy");
  assert.equal(signalFor(50), "Neutral");
  assert.equal(signalFor(20), "Sell");
});

test("evaluationFor valuation tags", () => {
  assert.equal(evaluationFor({ pe: 8 }), "Undervalued");
  assert.equal(evaluationFor({ pe: 18 }), "Fairly valued");
  assert.equal(evaluationFor({ pe: 40 }), "Overvalued");
  assert.equal(evaluationFor({ pe: null }), "Unrated");
});

test("rsi bounds and monotone series", () => {
  assert.equal(rsi([1, 2, 3, 4, 5]), 100); // only gains
  const r = rsi([5, 4, 5, 6, 5, 7, 6, 8]);
  assert.ok(r >= 0 && r <= 100);
});

test("withAnalytics attaches score/signal/evaluation", () => {
  const a = withAnalytics(getStock("NABIL"));
  assert.ok("score" in a && "signal" in a && "evaluation" in a);
});

// ── M400-NEPSE-004 market ────────────────────────────────────────────────────
test("marketSnapshot breadth + sectors", () => {
  const m = marketSnapshot();
  assert.equal(m.advancing + m.declining + m.unchanged, STOCKS.length);
  assert.ok(m.sectors.length >= 5);
  assert.ok(m.totalMarketCap > 0);
});

test("indexHistory ends exactly at target", () => {
  const h = indexHistory(30, 2557.31);
  assert.equal(h.length, 30);
  assert.equal(h[h.length - 1].v, 2557.31);
});

test("brokers ranked + per-stock breakdown", () => {
  assert.equal(BROKERS[0].rank, 1);
  const b = brokersForStock("NABIL");
  assert.ok(b.length === BROKERS.length);
  assert.ok(b.every((x) => x.buyQty > 0));
});

// ── M400-NEPSE-005 importers ─────────────────────────────────────────────────
test("parseMeroshare CSV -> BUY lots", () => {
  const csv = "S.N.,Scrip,Current Balance,Previous Closing Price\n1,NABIL,10,508.5\n2,API,50,259";
  const txs = parseMeroshare(csv);
  assert.equal(txs.length, 2);
  assert.deepEqual(txs[0], { symbol: "NABIL", side: "BUY", qty: 10, price: 508.5, date: null, source: "meroshare" });
});

test("parseTMS CSV -> BUY/SELL per trade", () => {
  const csv = "Symbol,Transaction Type,Quantity,Rate,Date\nEBL,Buy,5,600,2026-01-01\nEBL,Sell,2,650,2026-01-02";
  const txs = parseTMS(csv);
  assert.equal(txs.length, 2);
  assert.equal(txs[0].side, "BUY");
  assert.equal(txs[1].side, "SELL");
});

test("parseNepalShare TSV (tab-delimited) at WACC", () => {
  const tsv = "Symbol\tQuantity\tWACC\nUPPER\t100\t305.5";
  const txs = parseNepalShare(tsv);
  assert.equal(txs.length, 1);
  assert.equal(txs[0].price, 305.5);
  assert.equal(txs[0].source, "nepalshare");
});

test("importTransactions dispatch + unknown source throws", () => {
  const txs = importTransactions("meroshare", "Scrip,Current Balance,Previous Closing Price\nNABIL,10,508");
  assert.equal(txs.length, 1);
  assert.throws(() => importTransactions("etrade", "x"));
});

test("import -> compute end to end", () => {
  const txs = parseTMS("Symbol,Type,Qty,Rate,Date\nAPI,Buy,10,100,2026-01-01\nAPI,Buy,10,200,2026-01-02");
  const r = computePortfolio(txs, { API: 268 });
  assert.equal(r.holdings[0].qty, 20);
  assert.equal(r.holdings[0].avgCost, 150);
});

// ── format helpers ───────────────────────────────────────────────────────────
test("formatters", () => {
  assert.equal(fmtRs(1234.5), "Rs 1,234.50");
  assert.equal(fmtPct(2.5), "+2.50%");
  assert.equal(fmtPct(-1), "-1.00%");
  assert.equal(isMarketOpen(new Date("2026-08-28T12:00:00")), false); // Friday
  assert.equal(isMarketOpen(new Date("2026-08-30T12:00:00")), true); // Sunday noon
});

// ── M400-NEPSE-006/007 structural: routes + boundary labels ──────────────────
const ROUTES = [
  "app/nepse/layout.jsx",
  "app/nepse/nepse.css",
  "app/nepse/page.jsx",
  "app/nepse/market/page.jsx",
  "app/nepse/stocks/page.jsx",
  "app/nepse/stocks/[symbol]/page.jsx",
  "app/nepse/watchlist/page.jsx",
  "app/nepse/brokers/page.jsx",
  "components/nepse/NepseShell.jsx",
];

test("all NEPSE route + component files exist", () => {
  for (const f of ROUTES) assert.equal(existsSync(join(ROOT, f)), true, `missing ${f}`);
});

test("NepseShell carries the snapshot-data boundary banner", () => {
  const src = readFileSync(join(ROOT, "components/nepse/NepseShell.jsx"), "utf8");
  assert.ok(/SNAPSHOT|SEED/i.test(src), "boundary banner text missing");
  assert.ok(/NOT a live/i.test(src), "not-live disclaimer missing");
});

test("no password field anywhere in the NEPSE module (no broker login)", () => {
  for (const f of ROUTES) {
    const src = readFileSync(join(ROOT, f), "utf8");
    assert.ok(!src.includes('type="password"'), `password field in ${f}`);
  }
});

test("nepse.css defines light + dark palettes", () => {
  const css = readFileSync(join(ROOT, "app/nepse/nepse.css"), "utf8");
  assert.ok(css.includes("prefers-color-scheme: dark") || css.includes('data-theme="dark"'));
  assert.ok(css.includes("--accent"));
});
