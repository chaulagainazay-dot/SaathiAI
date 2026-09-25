import test from "node:test";
import assert from "node:assert/strict";

import {
  AUTHORIZES_EXECUTION, MCP_PROTOCOL_VERSION, REASON, TOOL_NAMES, TOOL_SCHEMAS,
  callTool, createHandlers,
} from "./mcp/tools.js";

const STOCKS = [{ symbol: "NABIL", name: "Nabil Bank Limited", sector: "Commercial Banks", ltp: 520, prevClose: 510 }];
const bars = (n, base = 100) =>
  Array.from({ length: n }, (_, i) => ({
    date: `2026-0${1 + Math.floor(i / 28)}-${String((i % 28) + 1).padStart(2, "0")}`,
    close: base + i, volume: 1000, turnover: 1000 * (base + i),
    trusted: { close: true },
  }));

const HOST = {
  stocks: STOCKS,
  entries: [{ symbol: "NABIL", sector: "Commercial Banks", bars: bars(40) },
            { symbol: "UPPER", sector: "Hydro Power", bars: bars(40, 200) }],
  dividends: [
    { symbol: "NABIL", bonus: 8, cash: 3, fiscalYear: "2081/82" },
    { symbol: "UPPER", bonus: 0, cash: 10, fiscalYear: "2081/82" },
  ],
  directory: { state: "LIVE_ENRICHED", records: { NABIL: { name: "Nabil Bank Limited", sector: "Commercial Banks", marketCap: 1e11 } } },
  listedTotal: 586,
};

const h = () => createHandlers(HOST);

// ── the five required tools ────────────────────────────────────────────────
test("the five specified tools are exposed with schemas", () => {
  assert.deepEqual([...TOOL_NAMES].sort(), [
    "get_company_financials", "get_dividends", "get_market_summary",
    "get_portfolio_summary", "get_technical_analysis",
  ]);
  for (const t of TOOL_SCHEMAS) {
    assert.ok(t.name && t.description && t.inputSchema?.type === "object", t.name);
  }
  assert.equal(MCP_PROTOCOL_VERSION, "2024-11-05");
});

test("no tool can act", () => {
  assert.equal(AUTHORIZES_EXECUTION, false);
  const res = callTool(h(), "get_market_summary", {});
  assert.equal(res.authorizes_execution, false);
  // There is no order, transfer or mutation tool to call.
  for (const n of TOOL_NAMES) assert.match(n, /^get_/);
});

// ── portfolio: supplied, never stored ──────────────────────────────────────
test("portfolio summary is computed from supplied transactions", () => {
  const res = callTool(h(), "get_portfolio_summary", {
    transactions: [{ symbol: "NABIL", side: "BUY", qty: 10, price: 500 }],
    prices: { NABIL: 520 },
  });
  assert.equal(res.ok, true);
  assert.ok(res.data);
  // Said plainly so an assistant cannot imply it looked an account up.
  assert.match(res.note, /no portfolio is stored server-side/);
});

test("the server holds no portfolio between calls", () => {
  const handlers = h();
  callTool(handlers, "get_portfolio_summary", {
    transactions: [{ symbol: "NABIL", side: "BUY", qty: 10, price: 500 }],
  });
  // A second call with nothing supplied must not remember the first.
  const second = callTool(handlers, "get_portfolio_summary", { transactions: [] });
  assert.equal(second.ok, false);
  assert.equal(second.reason, REASON.NO_TRANSACTIONS);
});

test("bad portfolio arguments are refused, not coerced", () => {
  for (const bad of [{}, { transactions: "nope" }, { transactions: null }]) {
    const r = callTool(h(), "get_portfolio_summary", bad);
    assert.equal(r.ok, false);
    assert.ok([REASON.BAD_ARGUMENTS, REASON.NO_TRANSACTIONS].includes(r.reason));
  }
});

// ── market ─────────────────────────────────────────────────────────────────
test("market summary carries the coverage it is based on", () => {
  const res = callTool(h(), "get_market_summary", {});
  assert.equal(res.ok, true);
  // "12 of 586" is a different claim from "the market" and must travel with it.
  assert.equal(res.coverage.listedTotal, 586);
  assert.equal(res.coverage.isFullMarket, false);
  assert.ok(res.as_of);
});

test("an unloaded archive refuses rather than reporting an empty market", () => {
  const res = callTool(createHandlers({}), "get_market_summary", {});
  assert.equal(res.ok, false);
  assert.equal(res.reason, REASON.NO_MARKET_DATA);
  assert.equal(res.data, null);
});

// ── dividends ──────────────────────────────────────────────────────────────
test("dividends filter by symbol and report the total", () => {
  const res = callTool(h(), "get_dividends", { symbol: "nabil" });
  assert.equal(res.data.length, 1);
  assert.equal(res.data[0].bonus, 8);
  assert.equal(res.symbol, "NABIL");
});

test("a missing dividend dataset is a typed refusal, not an empty list", () => {
  // An empty array would read to an assistant as "no dividends announced".
  const res = callTool(createHandlers({}), "get_dividends", {});
  assert.equal(res.ok, false);
  assert.equal(res.reason, REASON.NO_DIVIDEND_DATA);
});

// ── technical analysis ─────────────────────────────────────────────────────
test("technical analysis needs history and says so when it is thin", () => {
  const thin = createHandlers({ ...HOST, entries: [{ symbol: "NABIL", bars: bars(5) }] });
  const res = callTool(thin, "get_technical_analysis", { symbol: "NABIL" });
  assert.equal(res.ok, false);
  assert.equal(res.reason, REASON.INSUFFICIENT_HISTORY);
  assert.match(res.detail, /5 sessions/);
});

test("an unknown symbol is refused by name", () => {
  const res = callTool(h(), "get_technical_analysis", { symbol: "NOSUCH" });
  assert.equal(res.reason, REASON.UNKNOWN_SYMBOL);
  assert.equal(res.detail, "NOSUCH");
});

test("technical analysis returns a score and the sessions behind it", () => {
  const res = callTool(h(), "get_technical_analysis", { symbol: "NABIL" });
  assert.equal(res.ok, true);
  assert.equal(res.data.sessions, 40);
  assert.equal(res.data.symbol, "NABIL");
});

// ── financials ─────────────────────────────────────────────────────────────
test("financials carry the directory's own trust state", () => {
  const res = callTool(h(), "get_company_financials", { symbol: "NABIL" });
  assert.equal(res.ok, true);
  assert.equal(res.data.market_cap, 1e11);
  // Provenance rides along unchanged rather than being asserted here.
  assert.equal(res.directory_state, "LIVE_ENRICHED");
});

test("a symbol with no record is refused", () => {
  assert.equal(callTool(h(), "get_company_financials", { symbol: "ZZZZ" }).reason,
               REASON.UNKNOWN_SYMBOL);
});

// ── dispatch ───────────────────────────────────────────────────────────────
test("an unknown tool is refused, never guessed", () => {
  const res = callTool(h(), "get_everything", {});
  assert.equal(res.reason, REASON.UNKNOWN_TOOL);
  assert.equal(res.detail, "get_everything");
});

test("a throwing handler is contained and leaks no stack", () => {
  const broken = { boom() { throw new Error("/Users/secret/path exploded"); } };
  const res = callTool(broken, "boom", {});
  assert.equal(res.ok, false);
  assert.ok(!/at .*\n/.test(String(res.detail)));
});

test("every refusal carries a reason code and a null payload", () => {
  const res = callTool(createHandlers({}), "get_market_summary", {});
  // An assistant handed `{}` narrates around it and invents the gap.
  assert.ok(res.reason);
  assert.equal(res.data, null);
});
