/**
 * Global instrument search — symbol, company and sector. PURE, no I/O.
 *
 * Ranked rather than filtered: on an exchange where `NABIL` and `NABILP` both
 * exist, and `NBL` is a different bank entirely, substring order decides whether
 * a search box is useful or infuriating. An exact symbol always wins, then
 * symbol prefix, then company prefix, then anything containing the term.
 */

export const MATCH = Object.freeze({
  EXACT_SYMBOL: "EXACT_SYMBOL",
  SYMBOL_PREFIX: "SYMBOL_PREFIX",
  NAME_PREFIX: "NAME_PREFIX",
  SYMBOL_CONTAINS: "SYMBOL_CONTAINS",
  NAME_CONTAINS: "NAME_CONTAINS",
  SECTOR: "SECTOR",
});

const RANK = {
  [MATCH.EXACT_SYMBOL]: 0,
  [MATCH.SYMBOL_PREFIX]: 1,
  [MATCH.NAME_PREFIX]: 2,
  [MATCH.SYMBOL_CONTAINS]: 3,
  [MATCH.NAME_CONTAINS]: 4,
  [MATCH.SECTOR]: 5,
};

export const normalize = (s) => String(s ?? "").trim().toLowerCase();

function classify(stock, q) {
  const sym = normalize(stock.symbol);
  const name = normalize(stock.name || stock.company);
  const sector = normalize(stock.sector);
  if (sym === q) return MATCH.EXACT_SYMBOL;
  if (sym.startsWith(q)) return MATCH.SYMBOL_PREFIX;
  if (name.startsWith(q)) return MATCH.NAME_PREFIX;
  if (sym.includes(q)) return MATCH.SYMBOL_CONTAINS;
  if (name.includes(q)) return MATCH.NAME_CONTAINS;
  if (sector.includes(q)) return MATCH.SECTOR;
  return null;
}

/**
 * @param {Array} stocks  [{symbol, name, sector, ltp, ...}]
 * @param {string} query
 * @param {{limit?:number, sectors?:boolean}} opts
 */
export function search(stocks = [], query = "", { limit = 20 } = {}) {
  const q = normalize(query);
  // An empty query returns nothing rather than the whole exchange: 586 rows
  // dumped into a dropdown is not a search result.
  if (!q) return [];
  const hits = [];
  for (const s of stocks) {
    if (!s?.symbol) continue;
    const kind = classify(s, q);
    if (kind) hits.push({ ...s, match: kind, rank: RANK[kind] });
  }
  hits.sort((a, b) =>
    a.rank - b.rank ||
    String(a.symbol).length - String(b.symbol).length ||
    String(a.symbol).localeCompare(String(b.symbol)),
  );
  return hits.slice(0, Math.max(0, limit));
}

/** Grouped for a search panel with headings. */
export function grouped(stocks, query, opts = {}) {
  const rows = search(stocks, query, { limit: opts.limit ?? 30 });
  const out = new Map();
  for (const r of rows) {
    const key = r.match === MATCH.SECTOR ? "Sector" : "Instruments";
    if (!out.has(key)) out.set(key, []);
    out.get(key).push(r);
  }
  return [...out.entries()].map(([label, items]) => ({ label, items }));
}
