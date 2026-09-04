// NEPSE screener — search + sector filter + multi-column sort + pagination. Pure.
import { withAnalytics } from "./analytics.js";
import { dayChangePct } from "./format.js";

export const PAGE_SIZE = 50;

const SORTABLE = new Set([
  "symbol", "ltp", "change", "score", "rsi", "pe", "pb", "marketCap",
]);

function sortValue(row, key) {
  if (key === "change") return dayChangePct(row.ltp, row.prevClose);
  if (key === "symbol") return row.symbol;
  return row[key];
}

/**
 * @param {Array} stocks raw stocks
 * @param {Object} opts { query, sector, sort:{key,dir}, page, pageSize }
 * @returns { rows, total, page, pages, pageSize }
 */
export function screen(stocks, opts = {}) {
  const rsiBy = opts.rsiBySymbol || {};
  const {
    query = "",
    sector = "",
    sort = { key: "score", dir: "desc" },
    page = 1,
    pageSize = PAGE_SIZE,
  } = opts;

  let rows = stocks.map((s) => withAnalytics(s, rsiBy[s.symbol]));

  const q = String(query).trim().toLowerCase();
  if (q) {
    rows = rows.filter(
      (r) => r.symbol.toLowerCase().includes(q) || r.name.toLowerCase().includes(q),
    );
  }
  if (sector) rows = rows.filter((r) => r.sector === sector);

  const key = SORTABLE.has(sort.key) ? sort.key : "score";
  const dirMul = sort.dir === "asc" ? 1 : -1;
  rows = [...rows].sort((a, b) => {
    const av = sortValue(a, key);
    const bv = sortValue(b, key);
    if (typeof av === "string" || typeof bv === "string") {
      return String(av).localeCompare(String(bv)) * dirMul;
    }
    const an = Number.isFinite(Number(av)) ? Number(av) : -Infinity;
    const bn = Number.isFinite(Number(bv)) ? Number(bv) : -Infinity;
    return (an - bn) * dirMul;
  });

  const total = rows.length;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const p = Math.min(Math.max(1, page), pages);
  const start = (p - 1) * pageSize;
  return { rows: rows.slice(start, start + pageSize), total, page: p, pages, pageSize };
}
