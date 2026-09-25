// Wiring tests — the pure surfaces the new NEPSE pages stand on.
//
// These exist because every defect they cover is SILENT in a browser: a CSV
// column that writes blanks, a calendar that claims a closure it cannot evidence,
// a reading that reports zero where it means "unknown". None of them throws.

import test from "node:test";
import assert from "node:assert/strict";

import { HOLDING_COLUMNS, exportHoldings, exportTransactions } from "./nepse/export.js";
import { computePortfolio } from "./nepse/portfolio.js";
import { calendar, calendarFromCounts, weekdayProfile, DAY_KIND } from "./nepse/holidays.js";
import { READING_REQUIREMENTS, scanReadings, scanUniverseRow } from "./nepse/readings.js";
import { INDICATOR_STATUS } from "./nepse/indicators.js";
import { SCAN_LIBRARY, runScan } from "./nepse/scanners.js";
import { TRUTH } from "../lib/strategy/conditions.js";

// ── export columns match the only producer ──────────────────────────────────

test("holding export writes the fields computePortfolio actually emits", () => {
  const computed = computePortfolio(
    [{ id: "t1", symbol: "NABIL", side: "BUY", qty: 10, price: 500, date: "2024-01-01" }],
    { NABIL: 550 },
  );
  const csv = exportHoldings(computed.holdings);
  const [head, row] = csv.trim().split("\r\n");
  assert.equal(head, "Symbol,Quantity,WACC,Cost,LTP,Value,Unrealized PnL,Return %,Receivable Qty");
  const cells = row.split(",");
  assert.equal(cells[0], "NABIL");
  // The regression this test exists for: every money column was blank because
  // the column keys named fields no producer emits.
  for (const [i, label] of [[1, "qty"], [2, "wacc"], [3, "cost"], [4, "ltp"], [5, "value"]]) {
    assert.notEqual(cells[i], "", `${label} column must not be blank`);
  }
  assert.equal(cells[2], "500");   // WACC
  assert.equal(cells[5], "5500");  // market value
});

test("holding export column count matches its header", () => {
  const csv = exportHoldings([{ symbol: "X", qty: 1, avgCost: 2, invested: 2, ltp: 3, marketValue: 3, unrealizedPnl: 1, returnPct: 50, receivableQty: 0 }]);
  const [head, row] = csv.trim().split("\r\n");
  assert.equal(head.split(",").length, HOLDING_COLUMNS.length);
  assert.equal(row.split(",").length, HOLDING_COLUMNS.length);
});

test("a symbol that looks like a formula is neutralised on the way out", () => {
  const csv = exportTransactions([{ name: "P", transactions: [
    { symbol: "=cmd|'/c calc'!A1", side: "BUY", qty: 1, price: 1, date: "2024-01-01" },
  ] }]);
  assert.match(csv, /'=cmd/);
});

// ── trading calendar ────────────────────────────────────────────────────────

test("calendarFromCounts agrees with calendar over the same evidence", () => {
  const entries = [
    { bars: [{ date: "2024-01-01" }, { date: "2024-01-02" }, { date: "2024-01-04" }] },
    { bars: [{ date: "2024-01-01" }, { date: "2024-01-04" }] },
  ];
  const a = calendar(entries);
  const b = calendarFromCounts({ "2024-01-01": 2, "2024-01-02": 1, "2024-01-04": 2 });
  assert.deepEqual(b, a);
});

test("a day whose count cannot be read is dropped, not counted as zero", () => {
  // Zero is the evidence for CLOSED. A parse failure that became zero would turn
  // a bad row into a claim that the exchange was shut.
  const cal = calendarFromCounts({
    "2024-01-01": 5, "2024-01-02": "nonsense", "2024-01-03": 5,
  });
  const second = cal.days.find((d) => d.date === "2024-01-02");
  assert.equal(second.kind, DAY_KIND.CLOSED);
  assert.equal(second.instruments, 0);
  // ...and the surrounding days still carry their real counts.
  assert.equal(cal.days.find((d) => d.date === "2024-01-01").instruments, 5);
});

test("booleans and negative counts never become instrument counts", () => {
  const cal = calendarFromCounts({ "2024-01-01": 4, "2024-01-02": true, "2024-01-03": -3, "2024-01-04": 4 });
  for (const iso of ["2024-01-02", "2024-01-03"]) {
    assert.equal(cal.days.find((d) => d.date === iso).instruments, 0);
  }
});

// ── scan readings ───────────────────────────────────────────────────────────

const bar = (i, over = {}) => ({
  date: `2020-01-${String((i % 28) + 1).padStart(2, "0")}`,
  close: 100 + i * 0.1, high: 105 + i * 0.1, low: 95, volume: 1000,
  trusted: { close: true, high: true, low: true }, ...over,
});
const series = (n, over = () => ({})) => Array.from({ length: n }, (_, i) => bar(i, over(i)));

test("every reading the scan library names is produced", () => {
  const r = scanReadings(series(300));
  for (const name of Object.keys(READING_REQUIREMENTS)) {
    assert.ok(name in r, `missing reading ${name}`);
    assert.ok("status" in r[name] && "observations" in r[name], `${name} is not typed`);
  }
});

test("a short history yields INSUFFICIENT_HISTORY, never a substituted shorter average", () => {
  const r = scanReadings(series(40));
  assert.equal(r.sma200.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
  assert.equal(r.sma200.value, null);
  // A 40-session mean shipped under the name sma200 would silently answer a
  // different question than the scan asked.
  assert.equal(r.rsi.status, INDICATOR_STATUS.VALID);
});

test("a missing volume does not become a zero-volume session", () => {
  const bars = series(60, (i) => (i === 59 ? { volume: null } : {}));
  const r = scanReadings(bars);
  assert.equal(r.volumeRatio.value, null);
  assert.notEqual(r.volumeRatio.status, INDICATOR_STATUS.VALID);
});

test("a zero average volume is undefined, not an infinite surge", () => {
  const bars = series(40, () => ({ volume: 0 }));
  bars[bars.length - 1].volume = 500;
  const r = scanReadings(bars);
  assert.equal(r.volumeRatio.value, null);
  assert.equal(r.volumeRatio.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
});

test("volume ratio measures this session against the preceding twenty", () => {
  const bars = series(40, () => ({ volume: 100 }));
  bars[bars.length - 1].volume = 300;
  assert.equal(scanReadings(bars).volumeRatio.value, 3);
});

test("an untrusted high falls back to the close, never a fabricated range", () => {
  const bars = series(60, (i) => (i === 30
    ? { high: 9999, trusted: { close: true, high: false, low: true } } : {}));
  const r = scanReadings(bars);
  // 9999 would have become the 52-week peak and put every symbol far below it.
  assert.ok(r.pctFrom52wHigh.value > -50, "an untrusted high leaked into the peak");
});

test("previous readings are absent when there is no earlier bar", () => {
  assert.equal(scanUniverseRow("X", [bar(0)]).prevReadings, null);
  assert.notEqual(scanUniverseRow("X", series(40)).prevReadings, null);
});

// ── scans run through the shared evaluator ──────────────────────────────────

test("a symbol with too little history is UNDECIDED by a scan, not rejected", () => {
  const scan = SCAN_LIBRARY.find((s) => s.id === "above-200");
  const res = runScan(scan, [scanUniverseRow("SHORT", series(30))]);
  assert.equal(res.counts.unknown, 1);
  assert.equal(res.counts.rejected, 0);
  assert.equal(res.complete, false);
});

test("a crossing scan without a previous bar is undecided, not 'no cross'", () => {
  const scan = SCAN_LIBRARY.find((s) => s.id === "macd-bullish-cross");
  const row = scanUniverseRow("X", series(300));
  const res = runScan(scan, [{ ...row, prevReadings: null }]);
  assert.equal(res.counts.unknown, 1);
  assert.equal(res.matched.length, 0);
});

test("every built-in scan evaluates to a real truth value on a full series", () => {
  const uni = [scanUniverseRow("FULL", series(300))];
  for (const scan of SCAN_LIBRARY) {
    const res = runScan(scan, uni);
    const all = [...res.matched, ...res.rejected, ...res.unknown];
    assert.equal(all.length, 1, `${scan.id} lost the symbol`);
    assert.ok(Object.values(TRUTH).includes(all[0].value), `${scan.id} produced ${all[0].value}`);
  }
});

test("counts always account for every scanned symbol", () => {
  const uni = [
    scanUniverseRow("A", series(300)),
    scanUniverseRow("B", series(30)),
    scanUniverseRow("C", series(300)),
  ];
  for (const scan of SCAN_LIBRARY) {
    const c = runScan(scan, uni).counts;
    assert.equal(c.matched + c.rejected + c.unknown, c.scanned, `${scan.id} dropped a symbol`);
  }
});

// ── the trading week the archive actually reports ───────────────────────────

test("a month with busy Fridays is refused entirely, not just on the Friday", () => {
  // NEPSE trades Sunday to Thursday. Busy Fridays mean the month's dates are
  // shifted, and a shift moves every date in it — so the neighbouring days that
  // look like closures are the fabricated ones.
  const counts = {};
  // A clean month: Sun-Thu sessions only.
  for (const d of ["01", "02", "03", "04", "05", "08", "09", "10", "11", "12"]) {
    counts[`2024-09-${d}`] = 300;
  }
  // A shifted month: Mon-Fri, no Sundays.
  for (const d of ["02", "03", "04", "05", "06", "09", "10", "11", "12", "13"]) {
    counts[`2024-12-${d}`] = 300;
  }
  const cal = calendarFromCounts(counts, { minTradedFor: 3 });
  assert.ok(cal.disputedMonths.includes("2024-12"), "December was not disputed");
  assert.equal(cal.closures.filter((c) => c.date.startsWith("2024-12")).length, 0,
    "a disputed month must publish no closures at all");
  // Every day of that month is unknown, including the ordinary-looking ones.
  const december = cal.days.filter((d) => d.date.startsWith("2024-12"));
  assert.ok(december.length > 0);
  assert.ok(december.every((d) => d.kind === DAY_KIND.UNCONFIRMED));
});

test("an untouched month still yields closures", () => {
  const counts = {};
  // Sun 2024-09-01 .. Thu 2024-09-12, with Wed 2024-09-04 missing.
  for (const d of ["01", "02", "03", "05", "08", "09", "10", "11", "12"]) {
    counts[`2024-09-${d}`] = 300;
  }
  const cal = calendarFromCounts(counts, { minTradedFor: 3 });
  assert.deepEqual(cal.disputedMonths, []);
  assert.deepEqual(cal.closures.map((c) => c.date), ["2024-09-04"]);
});

test("weekdayProfile counts session DAYS, not instruments, and rejects junk", () => {
  const p = weekdayProfile({
    "2024-09-01": 300,   // Sunday
    "2024-09-02": 300,   // Monday
    "2024-09-03": true,  // Number(true) is 1 — must not count
    "2024-09-04": 0,     // no session
    "2024-09-05": null,
  });
  assert.equal(p[0], 1); // Sun
  assert.equal(p[1], 1); // Mon
  assert.equal(p[2], 0); // Tue — rejected boolean
  assert.equal(p.reduce((a, b) => a + b, 0), 2);
});

// ── the export round trip ───────────────────────────────────────────────────

import { importTransactions } from "./nepse/importers.js";

test("a real portfolio round-trips through export and back exactly", () => {
  const txs = [
    { id: "t1", symbol: "NABIL", side: "BUY", qty: 10, price: 500, date: "2024-01-01" },
    { id: "t2", symbol: "NICA", side: "SELL", qty: 4, price: 348.5, date: "2024-06-02" },
  ];
  const csv = exportTransactions([{ name: "Test", transactions: txs }]);
  const back = importTransactions("tms", csv);
  assert.equal(back.length, 2);
  for (const [i, t] of txs.entries()) {
    assert.equal(back[i].symbol, t.symbol);
    assert.equal(back[i].side, t.side);
    assert.equal(back[i].qty, t.qty);
    assert.equal(back[i].price, t.price);
    assert.equal(back[i].date, t.date);
  }
});

test("no real NEPSE symbol is ever escaped, so escaping never touches the round trip", () => {
  // Escaping is required — a cell starting with = executes in a spreadsheet — and
  // the escape is NOT removed on re-import. That asymmetry only ever applies to a
  // value that could not be a symbol in the first place.
  const SYMBOL_RE = /^[A-Z0-9]{1,12}$/;
  for (const sym of ["NABIL", "NABILP", "NICA", "UPPER", "SKBBL", "API", "H8020"]) {
    assert.ok(SYMBOL_RE.test(sym));
    const csv = exportTransactions([{ name: "P", transactions: [
      { symbol: sym, side: "BUY", qty: 1, price: 1, date: "2024-01-01" },
    ] }]);
    assert.equal(importTransactions("tms", csv)[0].symbol, sym);
    assert.ok(!csv.includes(`'${sym}`), `${sym} was needlessly escaped`);
  }
});
