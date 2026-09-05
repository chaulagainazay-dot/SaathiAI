// Floorsheet parsing and broker aggregation.
//
// These replace numbers that used to be generated from a symbol's character codes,
// so the tests are about counting exactly: both sides of every trade, no defaulted
// quantities, and no broker given a name this build does not actually know.

import test from "node:test";
import assert from "node:assert/strict";
import {
  parseFloorsheet, brokerActivity, floorsheetTotals, symbolActivity,
} from "./nepse/floorsheet.js";

const CSV = `transaction,symbol,buyer,seller,quantity,rate,amount,date
2026090304004901,UAIL,38,36,49.0,365.0,17885.0,2026-09-03
2026090304004902,UAIL,36,36,100.0,365.0,36500.0,2026-09-03
2026090304004903,NABIL,45,36,50.0,539.0,26950.0,2026-09-03
2026090304004904,NABIL,52,38,10.0,539.0,5390.0,2026-09-03`;

test("a floorsheet parses into typed trades carrying the session date", () => {
  const { trades, date, rejected } = parseFloorsheet(CSV);
  assert.equal(trades.length, 4);
  assert.equal(date, "2026-09-03");
  assert.equal(rejected, 0);
  assert.deepEqual(trades[0], {
    symbol: "UAIL", buyer: "38", seller: "36", quantity: 49, rate: 365, amount: 17885,
  });
});

test("filtering by symbol is case-insensitive and excludes everything else", () => {
  const { trades } = parseFloorsheet(CSV, { symbol: "nabil" });
  assert.equal(trades.length, 2);
  assert.ok(trades.every((t) => t.symbol === "NABIL"));
});

test("a row missing a quantity or a broker is rejected, never defaulted to zero", () => {
  const bad = `transaction,symbol,buyer,seller,quantity,rate,amount,date
1,UAIL,,36,49.0,365.0,17885.0,2026-09-03
2,UAIL,38,36,,365.0,17885.0,2026-09-03
3,UAIL,38,36,0,365.0,0,2026-09-03
4,UAIL,38,36,49.0,365.0,17885.0,2026-09-03`;
  const { trades, rejected } = parseFloorsheet(bad);
  assert.equal(trades.length, 1);
  assert.equal(rejected, 3);
});

test("amount falls back to quantity x rate only when both are present", () => {
  const noAmt = `symbol,buyer,seller,quantity,rate
UAIL,38,36,10,365.0
UAIL,38,36,10,`;
  const { trades, rejected } = parseFloorsheet(noAmt);
  assert.equal(trades.length, 1);
  assert.equal(trades[0].amount, 3650);
  // No rate and no amount: the trade's value is unknown, so the row is dropped.
  assert.equal(rejected, 1);
});

test("both sides of every trade are counted", () => {
  const rows = brokerActivity(parseFloorsheet(CSV).trades);
  const b36 = rows.find((r) => r.code === "36");
  // Broker 36 sold in three trades and bought in one.
  assert.equal(b36.sellQty, 49 + 100 + 50);
  assert.equal(b36.buyQty, 100);
  assert.equal(b36.buyAmount, 36500);
});

test("a broker on both sides of one trade is not double-counted as two trades", () => {
  const self = `symbol,buyer,seller,quantity,rate,amount
UAIL,36,36,100,365.0,36500.0`;
  const rows = brokerActivity(parseFloorsheet(self).trades);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].trades, 1);
});

test("net is buy minus sell, and brokers rank by total value handled", () => {
  const rows = brokerActivity(parseFloorsheet(CSV).trades);
  assert.equal(rows[0].rank, 1);
  for (const r of rows) assert.equal(r.net, +(r.buyAmount - r.sellAmount).toFixed(2));
  assert.ok(rows[0].total >= rows[rows.length - 1].total);
});

test("an unknown broker code gets no name rather than a borrowed one", () => {
  const rows = brokerActivity(parseFloorsheet(CSV).trades, {
    names: new Map([[45, "Kumari Securities"]]),
  });
  assert.equal(rows.find((r) => r.code === "45").name, "Kumari Securities");
  assert.equal(rows.find((r) => r.code === "52").name, null);
});

test("session totals are counted from trades, not summed from closing prices", () => {
  const t = floorsheetTotals(parseFloorsheet(CSV).trades);
  assert.equal(t.trades, 4);
  assert.equal(t.quantity, 49 + 100 + 50 + 10);
  assert.equal(t.amount, 17885 + 36500 + 26950 + 5390);
  assert.equal(t.symbols, 2);
});

test("symbol activity ranks by counted turnover", () => {
  const rows = symbolActivity(parseFloorsheet(CSV).trades);
  assert.equal(rows[0].symbol, "UAIL");   // 54,385 vs NABIL 32,340
  assert.equal(rows[0].amount, 54385);
  assert.equal(rows[0].trades, 2);
});

test("a malformed or empty body yields no trades rather than throwing", () => {
  assert.deepEqual(parseFloorsheet("").trades, []);
  assert.deepEqual(parseFloorsheet("<!doctype html>").trades, []);
  assert.deepEqual(parseFloorsheet("a,b,c\n1,2,3").trades, []);
});
