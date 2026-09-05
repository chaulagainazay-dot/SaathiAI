"use client";
// NEPSE per-viewer store — localStorage only. Guarded so a private window, blocked
// storage, or SSR never throws. Holds portfolios, transactions, and the watchlist.
// This is the ONLY mutable state in the module and it never leaves the browser.

import { PORTFOLIO_COLORS } from "./portfolio.js";

const KEY = "nepse.tracker.v1";

const EMPTY = { portfolios: [], activeId: null, watchlist: [], watchGroups: {} };

function safeRead() {
  if (typeof window === "undefined") return { ...EMPTY };
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return { ...EMPTY };
    const parsed = JSON.parse(raw);
    return { ...EMPTY, ...parsed };
  } catch {
    return { ...EMPTY };
  }
}

function safeWrite(state) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* storage blocked / full — degrade silently */
  }
}

export function loadState() {
  return safeRead();
}

const uid = () => `p_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;

export function createPortfolio(name, colorIndex = 0) {
  const state = safeRead();
  const p = {
    id: uid(),
    name: String(name || "Untitled").trim() || "Untitled",
    color: PORTFOLIO_COLORS[colorIndex % PORTFOLIO_COLORS.length],
    transactions: [],
    createdAt: Date.now(),
  };
  state.portfolios.push(p);
  state.activeId = p.id;
  safeWrite(state);
  return state;
}

export function setActive(id) {
  const state = safeRead();
  if (state.portfolios.some((p) => p.id === id)) state.activeId = id;
  safeWrite(state);
  return state;
}

export function deletePortfolio(id) {
  const state = safeRead();
  state.portfolios = state.portfolios.filter((p) => p.id !== id);
  if (state.activeId === id) state.activeId = state.portfolios[0]?.id || null;
  safeWrite(state);
  return state;
}

export function addTransaction(portfolioId, tx) {
  const state = safeRead();
  const p = state.portfolios.find((x) => x.id === portfolioId);
  if (!p) return state;
  p.transactions.push({ ...tx, id: uid(), addedAt: Date.now() });
  safeWrite(state);
  return state;
}

export function addTransactions(portfolioId, txs) {
  const state = safeRead();
  const p = state.portfolios.find((x) => x.id === portfolioId);
  if (!p) return state;
  for (const tx of txs) p.transactions.push({ ...tx, id: uid(), addedAt: Date.now() });
  safeWrite(state);
  return state;
}

export function removeTransaction(portfolioId, txId) {
  const state = safeRead();
  const p = state.portfolios.find((x) => x.id === portfolioId);
  if (p) p.transactions = p.transactions.filter((t) => t.id !== txId);
  safeWrite(state);
  return state;
}

export function toggleWatch(symbol, group = "All") {
  const state = safeRead();
  const s = String(symbol).toUpperCase();
  if (state.watchlist.includes(s)) {
    state.watchlist = state.watchlist.filter((x) => x !== s);
    Object.keys(state.watchGroups).forEach((g) => {
      state.watchGroups[g] = (state.watchGroups[g] || []).filter((x) => x !== s);
    });
  } else {
    state.watchlist.push(s);
    state.watchGroups[group] = [...(state.watchGroups[group] || []), s];
  }
  safeWrite(state);
  return state;
}

// Round-trip CSV backup (generic, broker-independent) — export/import of the store.
export function exportBackupCSV(state = safeRead()) {
  const lines = ["portfolio,color,symbol,side,qty,price,date"];
  for (const p of state.portfolios) {
    for (const t of p.transactions) {
      lines.push([p.name, p.color, t.symbol, t.side, t.qty, t.price, t.date || ""].join(","));
    }
  }
  return lines.join("\n");
}
