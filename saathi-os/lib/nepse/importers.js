// NEPSE import parsers — file-based onboarding, no live brokerage connection.
// Pure functions: text in, normalized transactions out. No network, no side effects.
//
// Supported (as the teardown documents):
//   Meroshare  — CSV holdings export (CDSC demat balances)  -> BUY lots at last price
//   TMS        — broker Trade Management System export (CSV) -> BUY/SELL per trade
//   Nepal Share— third-party portfolio export (CSV or TSV)   -> BUY lots at WACC

function detectDelimiter(text) {
  const first = String(text).split(/\r?\n/).find((l) => l.trim().length) || "";
  const tabs = (first.match(/\t/g) || []).length;
  const commas = (first.match(/,/g) || []).length;
  return tabs > commas ? "\t" : ",";
}

// Minimal CSV/TSV field splitter (handles simple double-quoted fields).
function splitLine(line, delim) {
  const out = [];
  let cur = "";
  let inQ = false;
  for (let i = 0; i < line.length; i += 1) {
    const c = line[i];
    if (c === '"') {
      if (inQ && line[i + 1] === '"') { cur += '"'; i += 1; } else inQ = !inQ;
    } else if (c === delim && !inQ) {
      out.push(cur); cur = "";
    } else {
      cur += c;
    }
  }
  out.push(cur);
  return out.map((s) => s.trim());
}

export function parseTable(text) {
  const delim = detectDelimiter(text);
  const lines = String(text).split(/\r?\n/).filter((l) => l.trim().length);
  if (!lines.length) return { headers: [], rows: [] };
  const headers = splitLine(lines[0], delim).map((h) => h.toLowerCase().replace(/[^a-z0-9]/g, ""));
  const rows = lines.slice(1).map((l) => {
    const cells = splitLine(l, delim);
    const obj = {};
    headers.forEach((h, i) => { obj[h] = cells[i] ?? ""; });
    return obj;
  });
  return { headers, rows };
}

// Pick the first present key from a list of candidates.
function pick(row, ...keys) {
  for (const k of keys) if (row[k] !== undefined && row[k] !== "") return row[k];
  return "";
}

const num = (v) => {
  const n = Number(String(v).replace(/[^0-9.\-]/g, ""));
  return Number.isFinite(n) ? n : 0;
};

export function parseMeroshare(text) {
  const { rows } = parseTable(text);
  const out = [];
  for (const r of rows) {
    const symbol = String(pick(r, "scrip", "symbol", "stocksymbol", "company")).toUpperCase();
    const qty = num(pick(r, "currentbalance", "balance", "quantity", "totalqty"));
    const price = num(pick(r, "previousclosingprice", "lastprice", "ltp", "rate", "price"));
    if (symbol && qty > 0) out.push({ symbol, side: "BUY", qty, price, date: null, source: "meroshare" });
  }
  return out;
}

export function parseTMS(text) {
  const { rows } = parseTable(text);
  const out = [];
  for (const r of rows) {
    const symbol = String(pick(r, "symbol", "scrip", "stocksymbol")).toUpperCase();
    const rawSide = String(pick(r, "transactiontype", "type", "buysell", "side")).toUpperCase();
    const side = /SELL|S\b/.test(rawSide) ? "SELL" : "BUY";
    const qty = num(pick(r, "quantity", "qty", "unit", "kitta"));
    const price = num(pick(r, "rate", "price", "amount"));
    const date = pick(r, "date", "transactiondate", "tradedate") || null;
    if (symbol && qty > 0) out.push({ symbol, side, qty, price, date, source: "tms" });
  }
  return out;
}

export function parseNepalShare(text) {
  const { rows } = parseTable(text);
  const out = [];
  for (const r of rows) {
    const symbol = String(pick(r, "symbol", "scrip", "stock", "company")).toUpperCase();
    const qty = num(pick(r, "quantity", "qty", "units", "kitta", "balance"));
    const price = num(pick(r, "wacc", "purchaseprice", "costprice", "rate", "price"));
    if (symbol && qty > 0) out.push({ symbol, side: "BUY", qty, price, date: null, source: "nepalshare" });
  }
  return out;
}

export const IMPORTERS = {
  meroshare: parseMeroshare,
  tms: parseTMS,
  nepalshare: parseNepalShare,
};

export function importTransactions(source, text) {
  const fn = IMPORTERS[source];
  if (!fn) throw new Error(`unknown import source: ${source}`);
  return fn(text);
}
