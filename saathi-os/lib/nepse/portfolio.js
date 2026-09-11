// NEPSE portfolio math — the correctness core. Pure, side-effect free.
//
// Source of truth is the transaction log; nothing is stored as a separate ledger.
// Weighted-average cost basis. Long-only: a SELL that exceeds the held quantity is
// REJECTED (never produces a negative holding). Bonus / right / IPO shares that are
// allotted but not yet credited are modelled as RECEIVABLE and valued at LTP.
//
// Transaction shape:
//   { symbol, side: "BUY" | "SELL" | "RECEIVABLE", qty, price?, date? }
// priceMap: { [SYMBOL]: ltp }

const EPS = 1e-9;

export function normalizeTx(tx) {
  return {
    symbol: String(tx.symbol || "").toUpperCase(),
    side: String(tx.side || "BUY").toUpperCase(),
    qty: Number(tx.qty) || 0,
    price: Number(tx.price) || 0,
    date: tx.date || null,
  };
}

export function computePortfolio(transactions = [], priceMap = {}) {
  const ordered = [...transactions]
    .map(normalizeTx)
    .sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));

  const book = new Map(); // symbol -> { qty, cost, receivableQty }
  const rejected = [];
  let realizedPnl = 0;

  const ensure = (sym) => {
    if (!book.has(sym)) book.set(sym, { qty: 0, cost: 0, receivableQty: 0 });
    return book.get(sym);
  };

  for (const tx of ordered) {
    if (!tx.symbol || tx.qty <= 0) {
      rejected.push({ tx, reason: "invalid" });
      continue;
    }
    const h = ensure(tx.symbol);
    if (tx.side === "BUY") {
      h.qty += tx.qty;
      h.cost += tx.qty * tx.price;
    } else if (tx.side === "SELL") {
      if (tx.qty > h.qty + EPS) {
        rejected.push({ tx, reason: "oversell", held: h.qty });
        continue;
      }
      const avg = h.qty > 0 ? h.cost / h.qty : 0;
      realizedPnl += (tx.price - avg) * tx.qty;
      h.cost -= avg * tx.qty;
      h.qty -= tx.qty;
      if (h.qty < EPS) { h.qty = 0; h.cost = 0; }
    } else if (tx.side === "RECEIVABLE") {
      h.receivableQty += tx.qty;
    } else {
      rejected.push({ tx, reason: "unknown-side" });
    }
  }

  const holdings = [];
  let invested = 0;
  let value = 0;
  let receivable = 0;

  for (const [symbol, h] of book) {
    const ltp = Number(priceMap[symbol]) || 0;
    const avgCost = h.qty > 0 ? h.cost / h.qty : 0;
    const marketValue = h.qty * ltp;
    const receivableValue = h.receivableQty * ltp;
    const unrealizedPnl = marketValue - h.cost;
    if (h.qty === 0 && h.receivableQty === 0) continue;
    invested += h.cost;
    value += marketValue;
    receivable += receivableValue;
    holdings.push({
      symbol,
      qty: +h.qty.toFixed(4),
      avgCost: +avgCost.toFixed(4),
      invested: +h.cost.toFixed(2),
      ltp,
      marketValue: +marketValue.toFixed(2),
      receivableQty: h.receivableQty,
      receivableValue: +receivableValue.toFixed(2),
      unrealizedPnl: +unrealizedPnl.toFixed(2),
      returnPct: h.cost > 0 ? +((unrealizedPnl / h.cost) * 100).toFixed(2) : 0,
    });
  }

  holdings.sort((a, b) => b.marketValue - a.marketValue);

  return {
    holdings,
    rejected,
    totals: {
      invested: +invested.toFixed(2),
      value: +value.toFixed(2),
      receivable: +receivable.toFixed(2),
      unrealizedPnl: +(value - invested).toFixed(2),
      realizedPnl: +realizedPnl.toFixed(2),
      returnPct: invested > 0 ? +(((value - invested) / invested) * 100).toFixed(2) : 0,
    },
  };
}

export const PORTFOLIO_COLORS = [
  "#1f8a53", "#b83f34", "#9a6d1f", "#3e6bff", "#7f4ee5", "#22bdb0",
  "#e5701f", "#d63b40", "#2aa866", "#6c7a96", "#cc9f37", "#9b6bff",
];
