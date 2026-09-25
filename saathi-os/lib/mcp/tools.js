/**
 * NEPSE MCP tools — the handler layer. PURE, no I/O, no transport.
 *
 * Exposes the exchange data SaathiOS already computes to an MCP client (Claude,
 * ChatGPT, anything speaking the protocol) so a user can ask about their
 * portfolio without copying numbers between tabs.
 *
 * READ-ONLY BY CONSTRUCTION. There is no tool here that places an order, moves
 * money, mutates a portfolio or changes a setting. An assistant that can read
 * your positions is useful; one that can trade them is a different product with
 * a different risk profile, and this is deliberately the first.
 *
 * PORTFOLIO STATE IS SUPPLIED, NOT STORED. SaathiOS keeps portfolios in the
 * viewer's own browser (`lib/nepse/store.js` — localStorage, never leaves the
 * device). So `get_portfolio_summary` takes the holdings as an ARGUMENT rather
 * than reading an account server-side. That is not a workaround: it means this
 * server holds nobody's positions, so there is no portfolio database to leak.
 */

import { portfolioSummary } from "../nepse/accounts.js";
import { marketSummary } from "../nepse/market.js";
import { withAnalytics } from "../nepse/analytics.js";

export const MCP_PROTOCOL_VERSION = "2024-11-05";
export const MCP_SERVER_NAME = "saathios-nepse";
export const MCP_SERVER_VERSION = "1.0.0";

/** Permanent: none of these tools may act. */
export const AUTHORIZES_EXECUTION = false;

const num = { type: "number" };
const str = { type: "string" };

export const TOOL_SCHEMAS = Object.freeze([
  {
    name: "get_portfolio_summary",
    description:
      "Summarise a NEPSE portfolio: value, cost, unrealised P&L per holding and in total. " +
      "Holdings are supplied by the caller — this server stores no portfolios.",
    inputSchema: {
      type: "object",
      properties: {
        transactions: {
          type: "array",
          description: "BUY/SELL/RECEIVABLE transactions.",
          items: {
            type: "object",
            properties: {
              symbol: str, side: str, qty: num, price: num, date: str, account: str,
            },
            required: ["symbol", "side", "qty"],
          },
        },
        prices: { type: "object", description: "symbol -> last traded price." },
      },
      required: ["transactions"],
    },
  },
  {
    name: "get_market_summary",
    description:
      "Exchange-wide state for the last completed session: breadth, top movers, " +
      "sector performance and reported activity, with the coverage it is based on.",
    inputSchema: {
      type: "object",
      properties: { limit: { ...num, description: "movers per list (default 8)" } },
    },
  },
  {
    name: "get_dividends",
    description: "Announced cash and bonus dividends, optionally filtered by symbol.",
    inputSchema: {
      type: "object",
      properties: { symbol: str, limit: num },
    },
  },
  {
    name: "get_technical_analysis",
    description:
      "Indicator readings and a composite score for one symbol. Every reading " +
      "carries a status; an unavailable indicator is reported as unavailable, not as zero.",
    inputSchema: {
      type: "object",
      properties: { symbol: str },
      required: ["symbol"],
    },
  },
  {
    name: "get_company_financials",
    description: "Listing and fundamental reference data for one symbol.",
    inputSchema: {
      type: "object",
      properties: { symbol: str },
      required: ["symbol"],
    },
  },
]);

export const TOOL_NAMES = Object.freeze(TOOL_SCHEMAS.map((t) => t.name));

/** Every tool answers in this envelope, so absence is always legible. */
export function ok(data, meta = {}) {
  return { ok: true, ...meta, data, authorizes_execution: AUTHORIZES_EXECUTION };
}

/**
 * A refusal carries a REASON CODE, never an empty result.
 *
 * An assistant handed `{}` will narrate around it and invent the gap; handed
 * `UNKNOWN_SYMBOL` it can say what actually happened.
 */
export function unavailable(reason, detail) {
  return {
    ok: false, reason, detail: detail || null, data: null,
    authorizes_execution: AUTHORIZES_EXECUTION,
  };
}

export const REASON = Object.freeze({
  UNKNOWN_TOOL: "UNKNOWN_TOOL",
  UNKNOWN_SYMBOL: "UNKNOWN_SYMBOL",
  NO_TRANSACTIONS: "NO_TRANSACTIONS",
  NO_MARKET_DATA: "NO_MARKET_DATA",
  NO_DIVIDEND_DATA: "NO_DIVIDEND_DATA",
  INSUFFICIENT_HISTORY: "INSUFFICIENT_HISTORY",
  BAD_ARGUMENTS: "BAD_ARGUMENTS",
});

/**
 * Build the tool handlers over whatever data sources the host can provide.
 *
 * Sources are injected so the handlers stay pure and testable, and so a host
 * that lacks a dataset yields a typed refusal rather than a fabricated answer.
 */
export function createHandlers({ entries = [], dividends = null, directory = null,
                                 stocks = [], listedTotal = null } = {}) {
  const bySymbol = new Map(
    (stocks || []).filter((s) => s?.symbol).map((s) => [String(s.symbol).toUpperCase(), s]),
  );
  const entryFor = (sym) =>
    (entries || []).find((e) => String(e?.symbol).toUpperCase() === sym) || null;

  return {
    get_portfolio_summary(args = {}) {
      const txs = Array.isArray(args.transactions) ? args.transactions : null;
      if (!txs) return unavailable(REASON.BAD_ARGUMENTS, "transactions must be an array");
      if (!txs.length) return unavailable(REASON.NO_TRANSACTIONS, "no transactions supplied");
      const summary = portfolioSummary(txs, args.prices || {});
      return ok(summary, {
        // Said plainly so an assistant does not imply it looked anything up.
        note: "computed from the transactions supplied in this call; no portfolio is stored server-side",
      });
    },

    get_market_summary(args = {}) {
      if (!entries?.length) return unavailable(REASON.NO_MARKET_DATA, "no archive entries loaded");
      const limit = Number.isFinite(args.limit) ? Math.max(1, Math.min(50, args.limit)) : 8;
      const summary = marketSummary(entries, { listedTotal, limit });
      return ok(summary, {
        as_of: summary.asOf,
        basis: summary.basis,
        // Coverage travels with the answer: "12 of 372" is a different claim
        // from "the market", and an assistant must be able to say which it has.
        coverage: summary.coverage,
      });
    },

    get_dividends(args = {}) {
      if (!Array.isArray(dividends)) {
        return unavailable(REASON.NO_DIVIDEND_DATA, "dividend dataset not loaded");
      }
      const sym = args.symbol ? String(args.symbol).toUpperCase() : null;
      let rows = dividends;
      if (sym) rows = rows.filter((d) => String(d.symbol || "").toUpperCase() === sym);
      const limit = Number.isFinite(args.limit) ? Math.max(1, Math.min(500, args.limit)) : 100;
      return ok(rows.slice(0, limit), { total: rows.length, symbol: sym });
    },

    get_technical_analysis(args = {}) {
      const sym = String(args.symbol || "").toUpperCase();
      if (!sym) return unavailable(REASON.BAD_ARGUMENTS, "symbol is required");
      const stock = bySymbol.get(sym);
      const entry = entryFor(sym);
      if (!stock && !entry) return unavailable(REASON.UNKNOWN_SYMBOL, sym);
      const bars = entry?.bars || [];
      if (bars.length < 15) {
        // Thin history is stated, not smoothed over with a number nobody can use.
        return unavailable(REASON.INSUFFICIENT_HISTORY,
          `${sym} has ${bars.length} sessions; indicators need more`);
      }
      const closes = bars.map((b) => b.close).filter((c) => typeof c === "number");
      const analysed = withAnalytics(stock || { symbol: sym }, null);
      return ok({
        symbol: sym,
        sessions: bars.length,
        last_close: closes[closes.length - 1] ?? null,
        score: analysed.score ?? null,
        signal: analysed.signal ?? null,
        evaluation: analysed.evaluation ?? null,
      });
    },

    get_company_financials(args = {}) {
      const sym = String(args.symbol || "").toUpperCase();
      if (!sym) return unavailable(REASON.BAD_ARGUMENTS, "symbol is required");
      const rec = directory?.records?.[sym] || bySymbol.get(sym) || null;
      if (!rec) return unavailable(REASON.UNKNOWN_SYMBOL, sym);
      return ok({
        symbol: sym,
        name: rec.name || rec.company || null,
        sector: rec.sector || null,
        listed_shares: rec.listedShares ?? null,
        paid_up: rec.paidUp ?? null,
        market_cap: rec.marketCap ?? null,
        ltp: rec.ltp ?? null,
      }, {
        // Provenance rides along: the directory's own trust state, unchanged.
        directory_state: directory?.state || null,
      });
    },
  };
}

/** Dispatch one MCP tool call. Unknown names are refused, never guessed. */
export function callTool(handlers, name, args) {
  const fn = handlers?.[name];
  if (typeof fn !== "function") return unavailable(REASON.UNKNOWN_TOOL, name);
  try {
    return fn(args || {});
  } catch (e) {
    // A handler that throws must not take the session down or leak a stack.
    return unavailable(REASON.BAD_ARGUMENTS, String(e?.message || e).slice(0, 200));
  }
}
