import test from "node:test";
import assert from "node:assert/strict";

import {
  csvField, exportHoldings, exportPortfolioBundle, exportTransactions,
  neutralize, toCsv,
} from "./nepse/export.js";
import { parseTMS } from "./nepse/importers.js";

const PORTFOLIOS = [{
  id: "p1", name: "Main",
  transactions: [
    { id: "t1", symbol: "NABIL", side: "BUY", qty: 100, price: 505.5, date: "2026-08-01", source: "manual" },
    { id: "t2", symbol: "UPPER", side: "SELL", qty: 50, price: 210, date: "2026-08-14", source: "tms" },
  ],
}];

// ── the property that makes export worth having ────────────────────────────
test("exported transactions re-import through parseTMS unchanged", () => {
  const back = parseTMS(exportTransactions(PORTFOLIOS));
  assert.equal(back.length, 2);
  assert.deepEqual(
    back.map((t) => [t.symbol, t.side, t.qty, t.price]),
    [["NABIL", "BUY", 100, 505.5], ["UPPER", "SELL", 50, 210]],
  );
  // An export nobody can read back is a decoy: portability in name only.
  assert.equal(back[0].date, "2026-08-01");
});

test("a SELL survives the round trip as a SELL", () => {
  // Side is the field most likely to be silently coerced to BUY.
  const back = parseTMS(exportTransactions(PORTFOLIOS));
  assert.equal(back[1].side, "SELL");
});

// ── CSV injection ──────────────────────────────────────────────────────────
test("formula-leading cells are neutralised", () => {
  for (const payload of ["=1+1", "+HYPERLINK(0)", "@SUM(A1)", "=cmd|'/c calc'!A0"]) {
    assert.equal(neutralize(payload), `'${payload}`);
  }
});

test("a formula smuggled through a symbol cannot execute from the backup", () => {
  const csv = exportTransactions([{
    id: "p", name: "x",
    transactions: [{ symbol: '=HYPERLINK("http://evil","click")', side: "BUY", qty: 1, price: 1 }],
  }]);
  // The user opens their OWN export; it must not run anything.
  assert.ok(!/^=HYPERLINK/m.test(csv));
  assert.match(csv, /'=HYPERLINK/);
});

test("negative numbers are not quoted, so arithmetic survives", () => {
  // `-42` is a value, not a formula; quoting it would break the round trip.
  assert.equal(neutralize(-42), "-42");
  assert.equal(neutralize("-42"), "-42");
  assert.equal(neutralize("-42.5"), "-42.5");
  assert.equal(neutralize("-not-a-number"), "'-not-a-number");
});

// ── RFC 4180 ───────────────────────────────────────────────────────────────
test("fields containing a delimiter, quote or newline are quoted", () => {
  assert.equal(csvField("a,b"), '"a,b"');
  assert.equal(csvField('say "hi"'), '"say ""hi"""');
  assert.equal(csvField("line1\nline2"), '"line1\nline2"');
  assert.equal(csvField("plain"), "plain");
});

test("null and undefined become empty cells, never the string null", () => {
  assert.equal(csvField(null), "");
  assert.equal(csvField(undefined), "");
});

test("toCsv emits a header row and CRLF line endings", () => {
  const csv = toCsv([{ a: 1, b: 2 }], [{ key: "a", header: "A" }, { key: "b", header: "B" }]);
  assert.equal(csv, "A,B\r\n1,2\r\n");
});

test("an empty portfolio exports a header and no rows", () => {
  const csv = exportTransactions([]);
  assert.equal(csv.trim().split("\r\n").length, 1);
});

// ── bundle ─────────────────────────────────────────────────────────────────
test("the bundle exports transactions, not derived holdings", () => {
  const b = exportPortfolioBundle({ portfolios: PORTFOLIOS, exportedAt: "2026-09-07T00:00:00Z" });
  assert.equal(b.transactions, 2);
  assert.equal(b.portfolios, 1);
  assert.match(b.filename, /2026-09-07\.csv$/);
  // Restoring a computed position would discard the history that produced it.
  assert.match(b.csv, /Transaction Type/);
});

test("holdings export is a report and says so by its columns", () => {
  const csv = exportHoldings([{ symbol: "NABIL", qty: 10, wacc: 500, cost: 5000, ltp: 520, value: 5200, pnl: 200 }]);
  assert.match(csv, /^Symbol,Quantity,WACC,Cost,LTP,Value,Unrealized PnL/);
});
