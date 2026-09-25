/**
 * NEPSE multi-account portfolio — account splits, consolidation and honest pricing.
 *
 * The invariants under test are the ones that cost money when they break: shares are
 * matched against the demat that holds them, a transaction with no account is visible
 * rather than absorbed, an unquoted holding is worth "unknown" and not 0, and the
 * consolidated weighted average is genuinely re-derived instead of averaged.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  normalizeAccount, normalizeAccounts, accountIdOf, holdingsByAccount,
  consolidatedHoldings, portfolioSummary, indexPrices,
  UNASSIGNED_ACCOUNT_ID, UNASSIGNED_ACCOUNT, REJECT_REASON, ACCOUNT_REJECT_REASON,
  INDICATOR_STATUS,
} from "./nepse/accounts.js";

const A = "BROKER-A";
const B = "BROKER-B";

/** Two dematsful of NABIL at different sizes and prices, plus an unassigned EBL buy. */
const TXS = [
  { accountId: A, symbol: "NABIL", side: "BUY", qty: 100, price: 500, date: "2024-01-01" },
  { accountId: B, symbol: "NABIL", side: "BUY", qty: 300, price: 700, date: "2024-01-02" },
  { symbol: "EBL", side: "BUY", qty: 50, price: 300, date: "2024-01-03" },
];
const PRICES = { NABIL: 800 };

const find = (rows, id) => rows.find((r) => r.accountId === id);
const holding = (row, symbol) => row.holdings.find((h) => h.symbol === symbol);

// ── account model ────────────────────────────────────────────────────────────────

test("an account is id + label + broker + demat, with absence as null", () => {
  const acc = normalizeAccount({ id: " broker-a ", label: "Nabil Sec", broker: "Nabil", demat: "1301000000000001" });
  assert.deepEqual(acc, { id: "BROKER-A", label: "Nabil Sec", broker: "Nabil", demat: "1301000000000001" });

  const sparse = normalizeAccount({ id: "x", label: "   " });
  assert.equal(sparse.label, null, "blank label is absence, not an empty string");
  assert.equal(sparse.broker, null);
  assert.equal(sparse.demat, null);
  assert.equal(normalizeAccount({ label: "no id" }), null);
});

test("normalizeAccounts refuses duplicates and reserved ids, and always carries UNASSIGNED", () => {
  const { accounts, rejected } = normalizeAccounts([
    { id: "broker-a", broker: "Nabil", demat: "1301000000000001" },
    { id: "  " },
    { id: "BROKER-A", broker: "Nabil again" },
    { id: "broker-c", demat: "1301000000000001" },
    { id: "unassigned" },
    "not-an-account",
  ]);

  assert.deepEqual(accounts.map((a) => a.id), ["BROKER-A", UNASSIGNED_ACCOUNT_ID]);
  assert.deepEqual(rejected.map((r) => r.reason), [
    ACCOUNT_REJECT_REASON.MISSING_ID,
    ACCOUNT_REJECT_REASON.DUPLICATE_ID,
    ACCOUNT_REJECT_REASON.DUPLICATE_DEMAT,
    ACCOUNT_REJECT_REASON.RESERVED_ID,
    ACCOUNT_REJECT_REASON.MALFORMED,
  ]);
  assert.equal(rejected[2].conflictsWith, "BROKER-A", "the demat clash names the account it collides with");
  assert.deepEqual(accounts[1], { ...UNASSIGNED_ACCOUNT });
});

test("a transaction with no accountId resolves to UNASSIGNED, never to an account", () => {
  for (const tx of [{}, { accountId: null }, { accountId: "" }, { accountId: "   " }, {}]) {
    assert.equal(accountIdOf(tx), UNASSIGNED_ACCOUNT_ID);
  }
  assert.equal(accountIdOf({ accountId: " broker-a " }), A);
});

// ── per-account splits ───────────────────────────────────────────────────────────

test("holdings split by account, each with its own weighted average", () => {
  const { accounts } = holdingsByAccount(TXS);
  assert.deepEqual(accounts.map((a) => a.accountId), [A, B, UNASSIGNED_ACCOUNT_ID],
    "UNASSIGNED sorts last: it is a bucket to empty, not a broker");

  assert.equal(holding(find(accounts, A), "NABIL").avgCost, 500);
  assert.equal(holding(find(accounts, A), "NABIL").qty, 100);
  assert.equal(holding(find(accounts, B), "NABIL").avgCost, 700);
  assert.equal(holding(find(accounts, B), "NABIL").qty, 300);
  assert.equal(find(accounts, A).invested, 50000);
  assert.equal(find(accounts, B).invested, 210000);
  assert.equal(holding(find(accounts, A), "NABIL").observations, 1);
});

test("an unassigned transaction is kept in its own account, not merged into the first", () => {
  const { accounts } = holdingsByAccount(TXS);
  const unassigned = find(accounts, UNASSIGNED_ACCOUNT_ID);
  assert.ok(unassigned, "the unassigned bucket exists");
  assert.equal(unassigned.holdings.length, 1);
  assert.equal(holding(unassigned, "EBL").qty, 50);
  assert.equal(holding(find(accounts, A), "EBL"), undefined, "EBL did not leak into the first account");
  assert.equal(find(accounts, A).holdings.length, 1);
});

test("per-account holdings expose no price-derived field, so nothing reads as worth 0", () => {
  const { accounts } = holdingsByAccount(TXS);
  const h = holding(find(accounts, A), "NABIL");
  for (const field of ["ltp", "marketValue", "unrealizedPnl", "returnPct", "receivableValue"]) {
    assert.equal(field in h, false, `${field} must not be carried unpriced`);
  }
});

// ── screening: unknown must never become a number ────────────────────────────────

test("a BUY with no price is rejected, never booked as a free purchase", () => {
  const { accounts, rejected } = holdingsByAccount([
    { accountId: A, symbol: "NABIL", side: "BUY", qty: 100, price: 500 },
    { accountId: A, symbol: "NABIL", side: "BUY", qty: 100 },
    { accountId: A, symbol: "NABIL", side: "BUY", qty: 100, price: null },
    { accountId: A, symbol: "NABIL", side: "BUY", qty: 100, price: "" },
  ]);
  assert.deepEqual(rejected.map((r) => r.reason), Array(3).fill(REJECT_REASON.PRICE_UNAVAILABLE));
  const h = holding(find(accounts, A), "NABIL");
  assert.equal(h.qty, 100, "the priceless lots never entered the book");
  assert.equal(h.avgCost, 500, "and so never dragged the weighted average toward zero");
  assert.equal(find(accounts, A).rejectedCount, 3);
});

test("missing quantity, blank symbol and unknown side are each rejected by reason", () => {
  const { accounts, rejected } = holdingsByAccount([
    { accountId: A, symbol: "NABIL", side: "BUY", qty: null, price: 500 },
    { accountId: A, symbol: "NABIL", side: "BUY", qty: 0, price: 500 },
    { accountId: A, symbol: "  ", side: "BUY", qty: 10, price: 500 },
    { accountId: A, symbol: "NABIL", side: "GIFT", qty: 10, price: 500 },
  ]);
  assert.deepEqual(rejected.map((r) => r.reason), [
    REJECT_REASON.INVALID_QTY, REJECT_REASON.INVALID_QTY,
    REJECT_REASON.INVALID_SYMBOL, REJECT_REASON.UNKNOWN_SIDE,
  ]);
  assert.equal(find(accounts, A).holdings.length, 0);
  assert.ok(find(accounts, A), "an account whose every row failed still appears");
});

test("a RECEIVABLE needs no price and reports an unknown cost basis as null", () => {
  const { accounts } = holdingsByAccount([
    { accountId: A, symbol: "NABIL", side: "RECEIVABLE", qty: 10 },
  ]);
  const h = holding(find(accounts, A), "NABIL");
  assert.equal(h.receivableQty, 10);
  assert.equal(h.qty, 0);
  assert.equal(h.avgCost, null, "bonus stock not yet credited has no average cost, not a cost of 0");
});

// ── consolidation arithmetic ─────────────────────────────────────────────────────

test("consolidation re-derives the weighted average; it is not the mean of the accounts'", () => {
  const { holdings } = consolidatedHoldings(TXS);
  const nabil = holdings.find((h) => h.symbol === "NABIL");

  assert.equal(nabil.qty, 400);
  assert.equal(nabil.invested, 260000);
  assert.equal(nabil.avgCost, 650, "260000 / 400");
  assert.notEqual(nabil.avgCost, 600, "the mean of 500 and 700 ignores the 100 vs 300 share weights");
  assert.equal(nabil.accountCount, 2);
  assert.equal(nabil.observations, 2);

  const breakdown = Object.fromEntries(nabil.accounts.map((a) => [a.accountId, a.avgCost]));
  assert.deepEqual(breakdown, { [A]: 500, [B]: 700 }, "per-account averages survive consolidation");
  assert.deepEqual(holdings.map((h) => h.symbol), ["EBL", "NABIL"]);
});

// ── pricing: unknown is null, empty is zero ──────────────────────────────────────

test("summary reports value, cost and unrealised P/L per account and consolidated", () => {
  const s = portfolioSummary(TXS, PRICES);

  const a = find(s.accounts, A);
  assert.equal(a.value, 80000);
  assert.equal(a.investedTotal, 50000);
  assert.equal(a.unrealisedPnl, 30000);
  assert.equal(a.returnPct, 60);
  assert.equal(a.status, INDICATOR_STATUS.VALID);

  const b = find(s.accounts, B);
  assert.equal(b.value, 240000);
  assert.equal(b.unrealisedPnl, 30000);
  assert.equal(b.returnPct, 14.29);

  assert.equal(s.consolidated.value, 320000);
  assert.equal(s.consolidated.value, a.value + b.value, "consolidated value is the sum of the priced accounts");
  assert.equal(s.consolidated.unrealisedPnl, 60000);
  assert.equal(s.consolidated.holdings.find((h) => h.symbol === "NABIL").avgCost, 650);
});

test("an unpriced holding is withheld, not counted as zero, and is counted as unpriced", () => {
  const s = portfolioSummary(TXS, PRICES);
  const ebl = s.consolidated.holdings.find((h) => h.symbol === "EBL");

  assert.equal(ebl.ltp, null);
  assert.equal(ebl.marketValue, null, "no quote means unknown value, never 0");
  assert.equal(ebl.unrealisedPnl, null);
  assert.equal(ebl.returnPct, null);
  assert.equal(ebl.priced, false);
  assert.equal(ebl.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);

  const c = s.consolidated;
  assert.equal(c.holdingCount, 2);
  assert.equal(c.pricedCount, 1);
  assert.equal(c.unpricedCount, 1);
  assert.deepEqual(c.unpricedSymbols, ["EBL"]);
  assert.equal(c.complete, false);
  assert.equal(c.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);

  assert.equal(c.investedTotal, 275000);
  assert.equal(c.investedPriced, 260000);
  assert.equal(c.investedUnpriced, 15000);
  assert.equal(c.unrealisedPnl, 60000,
    "P/L compares the priced value against the priced cost; using the full 275000 cost would invent a 15000 loss");
  assert.equal(c.returnPct, 23.08);

  const unassigned = find(s.accounts, UNASSIGNED_ACCOUNT_ID);
  assert.equal(unassigned.value, null, "an account with nothing quotable has an unknown value");
  assert.equal(unassigned.investedTotal, 15000, "its cost is still known and reported");
});

test("an account holding nothing is worth 0; an account that cannot be quoted is worth null", () => {
  const s = portfolioSummary(
    [{ accountId: A, symbol: "EBL", side: "BUY", qty: 10, price: 300 }],
    {},
    { accounts: [{ id: A }, { id: "BROKER-EMPTY" }] },
  );

  const empty = find(s.accounts, "BROKER-EMPTY");
  assert.equal(empty.value, 0, "no holdings is knowledge, not absence");
  assert.equal(empty.holdingCount, 0);
  assert.equal(empty.status, INDICATOR_STATUS.VALID);
  assert.equal(empty.declared, true);

  const unquotable = find(s.accounts, A);
  assert.equal(unquotable.value, null);
  assert.equal(unquotable.status, INDICATOR_STATUS.FIELD_UNAVAILABLE);
});

test("a zero, blank or null quote is read as unknown, not as a worthless share", () => {
  for (const ltp of [0, null, "", undefined, -5, "n/a"]) {
    const s = portfolioSummary(TXS, { NABIL: ltp });
    const h = find(s.accounts, A).holdings[0];
    assert.equal(h.marketValue, null, `LTP ${String(ltp)} must not value the holding`);
    assert.equal(find(s.accounts, A).value, null);
  }
});

test("price keys are case-folded, and two spellings that disagree price nothing", () => {
  const priced = portfolioSummary(TXS, { nabil: 800 });
  assert.equal(find(priced.accounts, A).value, 80000);

  const conflicted = portfolioSummary(TXS, { nabil: 800, NABIL: 900 });
  const h = find(conflicted.accounts, A).holdings[0];
  assert.equal(h.marketValue, null);
  assert.equal(h.status, INDICATOR_STATUS.DATA_CONFLICT);

  assert.equal(indexPrices({ NABIL: null, nabil: 800 }).get("NABIL"), 800,
    "one key saying nothing does not veto another key saying 800");
});

test("an undeclared account is flagged rather than dropped", () => {
  const s = portfolioSummary(TXS, PRICES, { accounts: [{ id: A, broker: "Nabil" }] });
  assert.equal(find(s.accounts, A).declared, true);
  assert.equal(find(s.accounts, A).account.broker, "Nabil");
  assert.equal(find(s.accounts, B).declared, false);
  assert.equal(find(s.accounts, B).value, 240000, "and still contributes its value");
  assert.equal(s.consolidated.value, 320000);
});

// ── oversell ─────────────────────────────────────────────────────────────────────

test("a sell larger than the account holds is flagged and leaves the position intact", () => {
  const { accounts, rejected } = holdingsByAccount([
    { accountId: A, symbol: "NABIL", side: "BUY", qty: 100, price: 500, date: "2024-01-01" },
    { accountId: A, symbol: "NABIL", side: "SELL", qty: 150, price: 900, date: "2024-01-02" },
  ]);
  assert.equal(rejected.length, 1);
  assert.equal(rejected[0].reason, REJECT_REASON.OVERSELL);
  assert.equal(rejected[0].accountId, A);
  assert.equal(rejected[0].held, 100);

  const h = holding(find(accounts, A), "NABIL");
  assert.equal(h.qty, 100, "the holding is unchanged, and never negative");
  assert.ok(h.qty >= 0);
  assert.equal(find(accounts, A).realizedPnl, 0, "a refused sell realises nothing");
});

test("shares in one demat cannot settle a sell from another", () => {
  const s = portfolioSummary([
    { accountId: A, symbol: "NABIL", side: "BUY", qty: 100, price: 500, date: "2024-01-01" },
    { accountId: B, symbol: "NABIL", side: "SELL", qty: 100, price: 900, date: "2024-01-02" },
  ], PRICES);

  assert.equal(s.rejectedCount, 1);
  assert.equal(s.rejected[0].reason, REJECT_REASON.OVERSELL);
  assert.equal(s.rejected[0].accountId, B, "the sell is refused in B even though A holds 100");
  assert.equal(s.rejected[0].held, 0);

  assert.equal(find(s.accounts, B).holdings.length, 0);
  assert.equal(find(s.accounts, B).value, 0);
  assert.equal(s.consolidated.holdings.find((h) => h.symbol === "NABIL").qty, 100,
    "consolidation must not net a refused sell against the other demat");
  assert.equal(s.consolidated.value, 80000);
});

test("a legitimate partial sell reduces one account only", () => {
  const s = portfolioSummary([
    ...TXS,
    { accountId: A, symbol: "NABIL", side: "SELL", qty: 40, price: 900, date: "2024-01-04" },
  ], PRICES);

  const a = find(s.accounts, A);
  assert.equal(holding(a, "NABIL").qty, 60);
  assert.equal(holding(a, "NABIL").avgCost, 500, "weighted average cost survives a partial sell");
  assert.equal(a.realizedPnl, 16000, "(900 - 500) * 40");
  assert.equal(holding(find(s.accounts, B), "NABIL").qty, 300, "B is untouched");
  assert.equal(s.consolidated.realizedPnl, 16000);
  const nabil = s.consolidated.holdings.find((h) => h.symbol === "NABIL");
  assert.equal(nabil.qty, 360);
  assert.equal(nabil.invested, 240000);
  assert.equal(nabil.avgCost, 666.6667,
    "240000 / 360: selling the cheap A shares lifts the consolidated average away from the 650 it was before");
});

// ── purity ───────────────────────────────────────────────────────────────────────

test("pure: repeated calls agree and the input log is not mutated", () => {
  const input = JSON.parse(JSON.stringify(TXS));
  const first = portfolioSummary(input, PRICES);
  const second = portfolioSummary(input, PRICES);
  assert.deepEqual(JSON.parse(JSON.stringify(first)), JSON.parse(JSON.stringify(second)));
  assert.deepEqual(input, TXS, "transactions are read, never rewritten");
});
