// NEPSE multi-account portfolio — one demat per broker/account. PURE (no I/O, no clock).
//
// Composition, not duplication: every per-holding number (weighted-average cost,
// oversell rejection, receivables, realised P/L) still comes from computePortfolio
// in ./portfolio.js. This module adds only what that function cannot see:
//
//   1. The account dimension. Shares live in ONE demat, so a SELL is matched against
//      that demat's own book — holding 100 in broker A does not let broker B deliver.
//   2. An explicit UNASSIGNED account, so a transaction with no accountId stays
//      visible instead of being folded into whichever account happened to be first.
//   3. Pricing that is allowed to answer "unknown". computePortfolio prices with
//      `Number(priceMap[symbol]) || 0`, which turns a missing quote into a holding
//      worth zero — the exact lie this module exists to prevent. Its price-derived
//      fields (ltp / marketValue / unrealizedPnl / returnPct) are therefore dropped
//      here and recomputed against a null-preserving lookup.
//
// Statuses come from INDICATOR_STATUS; no second vocabulary is invented.

import { computePortfolio } from "./portfolio.js";
import { INDICATOR_STATUS } from "./indicators.js";

export { INDICATOR_STATUS };

const EPS = 1e-9;

const round2 = (n) => +n.toFixed(2);
const round4 = (n) => +n.toFixed(4);

/** The bucket for transactions that name no account. A real id, never a fallback. */
export const UNASSIGNED_ACCOUNT_ID = "UNASSIGNED";

export const UNASSIGNED_ACCOUNT = Object.freeze({
  id: UNASSIGNED_ACCOUNT_ID,
  label: "Unassigned",
  broker: null,
  demat: null,
});

export const TX_SIDE = Object.freeze(["BUY", "SELL", "RECEIVABLE"]);
const SIDES = new Set(TX_SIDE);

export const REJECT_REASON = Object.freeze({
  MALFORMED: "malformed",
  INVALID_SYMBOL: "invalid-symbol",
  INVALID_QTY: "invalid-qty",
  PRICE_UNAVAILABLE: "price-unavailable",
  UNKNOWN_SIDE: "unknown-side",
  OVERSELL: "oversell", // must match portfolio.js, whose rejections pass through
});

export const ACCOUNT_REJECT_REASON = Object.freeze({
  MALFORMED: "malformed",
  MISSING_ID: "missing-id",
  RESERVED_ID: "reserved-id",
  DUPLICATE_ID: "duplicate-id",
  DUPLICATE_DEMAT: "duplicate-demat",
});

/** Trimmed string, or null. "" and whitespace are absence, never an empty label. */
function text(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === "object") return null;
  const s = String(v).trim();
  return s === "" ? null : s;
}

/**
 * A number, or null. Number(null) === 0, Number("") === 0 and Number(true) === 1,
 * so every one of those is refused BEFORE coercion: a missing price must not book a
 * free purchase, and a missing qty must not become a zero-share line.
 */
function numberOrNull(v) {
  if (v === null || v === undefined || v === "" || typeof v === "boolean") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

// ── account model ────────────────────────────────────────────────────────────────

/** One account = one demat at one broker. Returns null when it has no identity. */
export function normalizeAccount(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const id = text(raw.id);
  if (id === null) return null;
  return {
    id: id.toUpperCase(),
    label: text(raw.label),
    broker: text(raw.broker),
    demat: text(raw.demat),
  };
}

/**
 * Normalise a declared account list. Duplicates are rejected rather than merged: two
 * rows sharing an id — or a demat — would double-count the same holdings.
 * UNASSIGNED is appended by construction so no caller can forget the bucket exists.
 */
export function normalizeAccounts(raw) {
  const list = Array.isArray(raw) ? raw : raw ? [raw] : [];
  const accounts = [];
  const rejected = [];
  const seenId = new Set();
  const seenDemat = new Map();

  for (const entry of list) {
    const account = normalizeAccount(entry);
    if (!account) {
      const malformed = !entry || typeof entry !== "object" || Array.isArray(entry);
      rejected.push({
        entry,
        reason: malformed ? ACCOUNT_REJECT_REASON.MALFORMED : ACCOUNT_REJECT_REASON.MISSING_ID,
      });
      continue;
    }
    if (account.id === UNASSIGNED_ACCOUNT_ID) {
      rejected.push({ entry, reason: ACCOUNT_REJECT_REASON.RESERVED_ID });
      continue;
    }
    if (seenId.has(account.id)) {
      rejected.push({ entry, reason: ACCOUNT_REJECT_REASON.DUPLICATE_ID });
      continue;
    }
    if (account.demat !== null && seenDemat.has(account.demat)) {
      rejected.push({
        entry,
        reason: ACCOUNT_REJECT_REASON.DUPLICATE_DEMAT,
        conflictsWith: seenDemat.get(account.demat),
      });
      continue;
    }
    seenId.add(account.id);
    if (account.demat !== null) seenDemat.set(account.demat, account.id);
    accounts.push(account);
  }

  accounts.push({ ...UNASSIGNED_ACCOUNT });
  return { accounts, rejected };
}

/** Which account a transaction belongs to. Absent means UNASSIGNED, never "the first". */
export function accountIdOf(tx) {
  const id = text(tx && typeof tx === "object" ? tx.accountId : null);
  return id === null ? UNASSIGNED_ACCOUNT_ID : id.toUpperCase();
}

// ── transaction screening ────────────────────────────────────────────────────────

/**
 * Reject what computePortfolio would silently coerce. Its normalizeTx does
 * `Number(tx.price) || 0`, so a BUY with a missing price books as a gift and drags
 * the weighted average down for every later share. Returns a reason, or null if clean.
 */
function screenTransaction(tx) {
  if (!tx || typeof tx !== "object" || Array.isArray(tx)) return REJECT_REASON.MALFORMED;
  if (text(tx.symbol) === null) return REJECT_REASON.INVALID_SYMBOL;
  const side = (text(tx.side) || "BUY").toUpperCase(); // portfolio.js defaults to BUY
  if (!SIDES.has(side)) return REJECT_REASON.UNKNOWN_SIDE;
  const qty = numberOrNull(tx.qty);
  if (qty === null || qty <= 0) return REJECT_REASON.INVALID_QTY;
  if (side !== "RECEIVABLE") {
    // RECEIVABLE is allotted-not-credited stock and carries no cost; BUY/SELL must
    // state a price. An explicit 0 is allowed (it was asserted), a missing one is not.
    const price = numberOrNull(tx.price);
    if (price === null || price < 0) return REJECT_REASON.PRICE_UNAVAILABLE;
  }
  return null;
}

// ── per-account books ────────────────────────────────────────────────────────────

/** UNASSIGNED sorts last: it is a bucket to be emptied, not a broker. */
function byAccountId(a, b) {
  if (a === b) return 0;
  if (a === UNASSIGNED_ACCOUNT_ID) return 1;
  if (b === UNASSIGNED_ACCOUNT_ID) return -1;
  return a < b ? -1 : 1;
}

/**
 * Split a transaction log into one book per account.
 * @param {Array} transactions each { symbol, side, qty, price, date, accountId? }
 * @returns {{accounts: Array, rejected: Array}} holdings carry no price-derived field
 */
export function holdingsByAccount(transactions = []) {
  const list = Array.isArray(transactions) ? transactions : [];
  const groups = new Map();
  const rejected = [];

  for (const tx of list) {
    const accountId = accountIdOf(tx);
    // The group is created even for a doomed transaction: an account whose every row
    // is bad must still surface as an account with problems, not vanish.
    if (!groups.has(accountId)) groups.set(accountId, []);
    const reason = screenTransaction(tx);
    if (reason) {
      rejected.push({ accountId, symbol: text(tx?.symbol)?.toUpperCase() ?? null, tx, reason });
      continue;
    }
    groups.get(accountId).push(tx);
  }

  const accounts = [];
  for (const accountId of [...groups.keys()].sort(byAccountId)) {
    const txs = groups.get(accountId);
    // Empty priceMap on purpose — pricing happens in portfolioSummary, where a
    // missing quote can stay null instead of collapsing to 0.
    const book = computePortfolio(txs, {});

    const bookRejected = book.rejected.map((r) => ({
      accountId,
      symbol: r.tx.symbol || null,
      tx: r.tx,
      reason: r.reason,
      ...(r.held === undefined ? {} : { held: r.held }),
    }));
    rejected.push(...bookRejected);

    // Observations = accepted transactions behind each symbol's numbers.
    const observations = new Map();
    for (const tx of txs) {
      const s = String(tx.symbol).trim().toUpperCase();
      observations.set(s, (observations.get(s) || 0) + 1);
    }
    for (const r of book.rejected) {
      const s = r.tx.symbol;
      if (observations.has(s)) observations.set(s, observations.get(s) - 1);
    }

    const holdings = book.holdings
      .map((h) => ({
        accountId,
        symbol: h.symbol,
        qty: h.qty,
        // A receivable-only line has no cost basis yet. Reporting avgCost 0 would read
        // as "acquired free" instead of "not yet known".
        avgCost: h.qty > EPS ? h.avgCost : null,
        invested: h.invested,
        receivableQty: h.receivableQty,
        observations: observations.get(h.symbol) ?? 0,
      }))
      .sort((a, b) => (a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0));

    accounts.push({
      accountId,
      holdings,
      invested: book.totals.invested,
      realizedPnl: book.totals.realizedPnl,
      transactionCount: txs.length - book.rejected.length,
      rejectedCount: 0,
      rejected: [],
    });
  }

  // Screening rejections happened before any book existed, so each account's own list
  // is assembled once here — a screened-out row must be as visible as an oversell.
  for (const account of accounts) {
    account.rejected = rejected.filter((r) => r.accountId === account.accountId);
    account.rejectedCount = account.rejected.length;
  }

  return { accounts, rejected };
}

// ── consolidation ────────────────────────────────────────────────────────────────

function consolidateFrom(accounts) {
  const merged = new Map();
  for (const account of accounts) {
    for (const h of account.holdings) {
      if (!merged.has(h.symbol)) {
        merged.set(h.symbol, {
          symbol: h.symbol, qty: 0, invested: 0, receivableQty: 0, observations: 0, accounts: [],
        });
      }
      const m = merged.get(h.symbol);
      m.qty += h.qty;
      m.invested += h.invested;
      m.receivableQty += h.receivableQty;
      m.observations += h.observations;
      m.accounts.push(h);
    }
  }

  return [...merged.values()]
    .map((m) => ({
      symbol: m.symbol,
      qty: round4(m.qty),
      // Total cost over total quantity across every demat. NOT the mean of the
      // per-account averages: that mean ignores how many shares sit behind each one
      // and is a different (wrong) number whenever the accounts hold unequal size.
      avgCost: m.qty > EPS ? round4(m.invested / m.qty) : null,
      invested: round2(m.invested),
      receivableQty: m.receivableQty,
      observations: m.observations,
      accountCount: m.accounts.length,
      accounts: m.accounts, // per-account breakdown retained, with its own avgCost
    }))
    .sort((a, b) => (a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0));
}

/** The same symbol across accounts merged, with the per-account breakdown kept. */
export function consolidatedHoldings(transactions = []) {
  const { accounts, rejected } = holdingsByAccount(transactions);
  return { holdings: consolidateFrom(accounts), accounts, rejected };
}

// ── pricing ──────────────────────────────────────────────────────────────────────

const PRICE_CONFLICT = Symbol("price-conflict");

/**
 * Case-folded price lookup. A quote of 0 or below is not a price on NEPSE — it is the
 * fingerprint of Number(null), so it is read as "unknown", not as a worthless share.
 */
export function indexPrices(prices) {
  const index = new Map();
  if (!prices || typeof prices !== "object") return index;
  for (const [key, raw] of Object.entries(prices)) {
    const symbol = text(key);
    if (symbol === null) continue;
    const upper = symbol.toUpperCase();
    const n = numberOrNull(raw);
    const value = n !== null && n > 0 ? n : null;
    if (!index.has(upper)) { index.set(upper, value); continue; }
    const prev = index.get(upper);
    if (prev === PRICE_CONFLICT || value === null) continue;
    if (prev === null) { index.set(upper, value); continue; }
    // Two spellings of one symbol quoting different numbers means two feeds were
    // merged; picking a winner would price the position on a coin flip.
    if (prev !== value) index.set(upper, PRICE_CONFLICT);
  }
  return index;
}

function lookupPrice(index, symbol) {
  const v = index.get(symbol);
  if (v === undefined || v === null) return { ltp: null, status: INDICATOR_STATUS.FIELD_UNAVAILABLE };
  if (v === PRICE_CONFLICT) return { ltp: null, status: INDICATOR_STATUS.DATA_CONFLICT };
  return { ltp: v, status: INDICATOR_STATUS.VALID };
}

function priceHolding(holding, index) {
  const { ltp, status } = lookupPrice(index, holding.symbol);
  if (ltp === null) {
    return {
      ...holding,
      ltp: null,
      marketValue: null,
      receivableValue: null,
      unrealisedPnl: null,
      returnPct: null,
      priced: false,
      status,
      note: "no usable LTP; value withheld rather than counted as 0",
    };
  }
  const marketValue = holding.qty * ltp;
  const unrealisedPnl = marketValue - holding.invested;
  return {
    ...holding,
    ltp,
    marketValue: round2(marketValue),
    receivableValue: round2(holding.receivableQty * ltp),
    unrealisedPnl: round2(unrealisedPnl),
    // Bonus stock costs nothing, so its return is undefined rather than 0%.
    returnPct: holding.invested > EPS ? round2((unrealisedPnl / holding.invested) * 100) : null,
    priced: true,
    status: INDICATOR_STATUS.VALID,
  };
}

/**
 * Totals over already-priced holdings. Cost is split priced/unpriced because the
 * value figure only covers the priced ones: subtracting the FULL cost from a PARTIAL
 * value invents a loss the size of whatever could not be quoted.
 */
function totalize(holdings) {
  let value = 0;
  let receivableValue = 0;
  let investedTotal = 0;
  let investedPriced = 0;
  let pricedCount = 0;
  let unpricedCount = 0;

  for (const h of holdings) {
    investedTotal += h.invested;
    if (h.priced) {
      pricedCount += 1;
      value += h.marketValue;
      receivableValue += h.receivableValue;
      investedPriced += h.invested;
    } else {
      unpricedCount += 1;
    }
  }

  // An account holding nothing is worth 0 — that is knowledge. An account whose
  // holdings cannot be quoted is worth an unknown amount — that is null.
  const valued = holdings.length === 0 || pricedCount > 0;
  const unrealisedPnl = value - investedPriced;

  return {
    holdingCount: holdings.length,
    pricedCount,
    unpricedCount,
    investedTotal: round2(investedTotal),
    investedPriced: round2(investedPriced),
    investedUnpriced: round2(investedTotal - investedPriced),
    value: valued ? round2(value) : null,
    receivableValue: valued ? round2(receivableValue) : null,
    unrealisedPnl: valued ? round2(unrealisedPnl) : null,
    returnPct: valued && investedPriced > EPS ? round2((unrealisedPnl / investedPriced) * 100) : null,
    complete: unpricedCount === 0,
    status: unpricedCount === 0 ? INDICATOR_STATUS.VALID : INDICATOR_STATUS.FIELD_UNAVAILABLE,
  };
}

/**
 * Value, cost and unrealised P/L per account AND consolidated.
 * @param {Array} transactions transaction log, each optionally carrying accountId
 * @param {Object} prices { [SYMBOL]: ltp } — a symbol may legitimately be absent
 * @param {Object} [options] { accounts } declared account list (see normalizeAccounts)
 */
export function portfolioSummary(transactions = [], prices = {}, options = {}) {
  const index = indexPrices(prices);
  const { accounts: books, rejected } = holdingsByAccount(transactions);
  const consolidatedRaw = consolidateFrom(books);

  const declared = options.accounts === undefined ? null : normalizeAccounts(options.accounts).accounts;
  const declaredById = new Map((declared || []).map((a) => [a.id, a]));

  const accounts = books.map((book) => {
    const holdings = book.holdings.map((h) => priceHolding(h, index));
    return {
      accountId: book.accountId,
      account: declaredById.get(book.accountId) ?? null,
      // null = no list was supplied, so "declared" is not a question that was asked.
      declared: declared === null ? null : declaredById.has(book.accountId),
      holdings,
      realizedPnl: book.realizedPnl,
      transactionCount: book.transactionCount,
      rejectedCount: book.rejectedCount,
      rejected: book.rejected,
      ...totalize(holdings),
    };
  });

  // Declared accounts with no transactions are real and empty; showing them keeps the
  // account list honest instead of implying the person only holds where they traded.
  for (const account of declared || []) {
    if (account.id === UNASSIGNED_ACCOUNT_ID) continue;
    if (accounts.some((a) => a.accountId === account.id)) continue;
    accounts.push({
      accountId: account.id,
      account,
      declared: true,
      holdings: [],
      realizedPnl: 0,
      transactionCount: 0,
      rejectedCount: 0,
      rejected: [],
      ...totalize([]),
    });
  }
  accounts.sort((a, b) => byAccountId(a.accountId, b.accountId));

  const consolidatedHoldingsPriced = consolidatedRaw.map((h) => priceHolding(h, index));
  const consolidated = {
    holdings: consolidatedHoldingsPriced,
    accountCount: accounts.length,
    realizedPnl: round2(books.reduce((sum, b) => sum + b.realizedPnl, 0)),
    unpricedSymbols: consolidatedHoldingsPriced.filter((h) => !h.priced).map((h) => h.symbol),
    ...totalize(consolidatedHoldingsPriced),
  };

  return {
    accounts,
    consolidated,
    rejected,
    rejectedCount: rejected.length,
    unassignedTransactionCount: rejected.filter((r) => r.accountId === UNASSIGNED_ACCOUNT_ID).length
      + (books.find((b) => b.accountId === UNASSIGNED_ACCOUNT_ID)?.transactionCount ?? 0),
  };
}
