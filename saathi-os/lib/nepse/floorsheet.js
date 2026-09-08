// Floorsheet — real per-broker trade data. PURE.
//
// This replaces `brokersForStock()`, which derived every quantity from the sum of
// a symbol's character codes. It looked plausible and was entirely invented: the
// same symbol always produced the same "broker activity" regardless of what
// actually traded. The floorsheet is the exchange's own record of who bought what
// from whom, so these numbers are counted, not generated.
//
// Broker NAMES are a separate problem: the floorsheet carries numeric codes, and
// this build only knows a handful of them. An unknown code is shown as a code —
// never given a name that might belong to a different firm.

const num = (v) => {
  const s = String(v ?? "").trim();
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
};

/**
 * Parse a floorsheet CSV into typed trades.
 * Fields are located by header name; a row missing a quantity, rate or either
 * broker is dropped rather than defaulted, since a zero would understate one
 * broker and a guess would misattribute a trade.
 */
export function parseFloorsheet(text, { symbol = null, maxRows = 500_000 } = {}) {
  const lines = String(text || "").split(/\r?\n/);
  if (lines.length < 2) return { trades: [], date: null, rejected: 0 };

  const header = lines[0].split(",").map((h) => h.trim().toLowerCase());
  const at = (n) => header.indexOf(n);
  const iSym = at("symbol");
  const iBuy = at("buyer");
  const iSell = at("seller");
  const iQty = at("quantity");
  const iRate = at("rate");
  const iAmt = at("amount");
  const iDate = at("date");
  if (iSym < 0 || iBuy < 0 || iSell < 0 || iQty < 0) {
    return { trades: [], date: null, rejected: 0 };
  }

  const want = symbol ? String(symbol).toUpperCase() : null;
  const trades = [];
  let rejected = 0;
  let date = null;

  for (let i = 1; i < lines.length && trades.length < maxRows; i += 1) {
    const line = lines[i];
    if (!line.trim()) continue;
    const c = line.split(",");
    const sym = String(c[iSym] || "").trim().toUpperCase();
    if (!sym) { rejected += 1; continue; }
    if (want && sym !== want) continue;

    const qty = num(c[iQty]);
    const rate = iRate >= 0 ? num(c[iRate]) : null;
    const buyer = String(c[iBuy] || "").trim();
    const seller = String(c[iSell] || "").trim();
    if (qty === null || qty <= 0 || !buyer || !seller) { rejected += 1; continue; }

    // Prefer the reported amount; fall back to qty × rate only when both exist.
    const reported = iAmt >= 0 ? num(c[iAmt]) : null;
    const amount = reported !== null ? reported : (rate !== null ? +(qty * rate).toFixed(2) : null);
    if (amount === null) { rejected += 1; continue; }

    if (!date && iDate >= 0) {
      const d = String(c[iDate] || "").trim();
      if (/^\d{4}-\d{2}-\d{2}$/.test(d)) date = d;
    }
    trades.push({ symbol: sym, buyer, seller, quantity: qty, rate, amount });
  }
  return { trades, date, rejected };
}

/**
 * Aggregate trades per broker.
 * A broker that only sold has bought: 0 — that is a counted zero, not a missing
 * value, and is the one place a zero here is truthful.
 */
export function brokerActivity(trades, { names = new Map() } = {}) {
  const acc = new Map();
  const touch = (code) => {
    if (!acc.has(code)) {
      acc.set(code, {
        code,
        name: names.get(Number(code)) || names.get(code) || null,
        buyQty: 0, buyAmount: 0, sellQty: 0, sellAmount: 0, trades: 0,
      });
    }
    return acc.get(code);
  };

  for (const t of trades) {
    const b = touch(t.buyer);
    b.buyQty += t.quantity;
    b.buyAmount += t.amount;
    b.trades += 1;
    const s = touch(t.seller);
    s.sellQty += t.quantity;
    s.sellAmount += t.amount;
    // A broker on both sides of one trade is counted once per side it took.
    if (t.seller !== t.buyer) s.trades += 1;
  }

  return [...acc.values()].map((b) => ({
    ...b,
    buyAmount: +b.buyAmount.toFixed(2),
    sellAmount: +b.sellAmount.toFixed(2),
    total: +(b.buyAmount + b.sellAmount).toFixed(2),
    net: +(b.buyAmount - b.sellAmount).toFixed(2),
  })).sort((a, b) => b.total - a.total).map((b, i) => ({ ...b, rank: i + 1 }));
}

/** Session totals straight from the trades — turnover here is counted, not summed from closes. */
export function floorsheetTotals(trades) {
  let quantity = 0;
  let amount = 0;
  const symbols = new Set();
  for (const t of trades) {
    quantity += t.quantity;
    amount += t.amount;
    symbols.add(t.symbol);
  }
  return {
    trades: trades.length,
    quantity,
    amount: +amount.toFixed(2),
    symbols: symbols.size,
  };
}

/** The most-traded symbols by counted turnover. */
export function symbolActivity(trades, limit = 10) {
  const acc = new Map();
  for (const t of trades) {
    const a = acc.get(t.symbol) || { symbol: t.symbol, quantity: 0, amount: 0, trades: 0 };
    a.quantity += t.quantity;
    a.amount += t.amount;
    a.trades += 1;
    acc.set(t.symbol, a);
  }
  return [...acc.values()]
    .map((a) => ({ ...a, amount: +a.amount.toFixed(2) }))
    .sort((a, b) => b.amount - a.amount)
    .slice(0, limit);
}
