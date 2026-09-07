/**
 * NEPSE portfolio export — CSV that can be read back in. PURE, no I/O.
 *
 * An export nobody can re-import is a decoy: it looks like data portability and
 * delivers lock-in. So the transaction export writes the exact column names
 * `parseTMS` already reads, and a round-trip test drives export -> import and
 * compares the result. If the importer's vocabulary ever changes, that test
 * fails rather than the feature silently rotting.
 *
 * CSV INJECTION IS THE REAL HAZARD HERE. A cell beginning `=`, `+`, `-` or `@`
 * is a FORMULA to Excel, Sheets and Numbers — `=HYPERLINK(...)` or a DDE payload
 * in a symbol field executes when the user opens their own backup. Every cell is
 * neutralised on the way out; see `neutralize`.
 */

/** Characters that make a spreadsheet treat a cell as a formula. */
const FORMULA_LEAD = /^[=+\-@\t\r]/;

/**
 * Defuse spreadsheet formula injection without corrupting the value.
 *
 * A leading apostrophe is the conventional escape: spreadsheets render the text
 * verbatim and strip the quote, and our own parser sees a value it can still
 * read back. Negative NUMBERS are deliberately exempt — `-42` is arithmetic, not
 * a formula, and quoting it would break the round trip it exists to protect.
 */
export function neutralize(value) {
  if (value === null || value === undefined) return "";
  const s = String(value);
  if (!s) return "";
  if (typeof value === "number") return s;
  if (FORMULA_LEAD.test(s) && !/^-?\d+(\.\d+)?$/.test(s)) return `'${s}`;
  return s;
}

/** One RFC 4180 field: quote when it contains a delimiter, quote or newline. */
export function csvField(value) {
  const s = neutralize(value);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** Rows of objects -> CSV text. Columns are explicit so order is stable. */
export function toCsv(rows, columns) {
  const head = columns.map((c) => csvField(c.header ?? c.key)).join(",");
  const body = (rows || []).map((row) =>
    columns.map((c) => csvField(c.get ? c.get(row) : row[c.key])).join(","),
  );
  // CRLF: what every spreadsheet expects, and what our own parser tolerates.
  return [head, ...body].join("\r\n") + "\r\n";
}

/**
 * Transaction columns, named to match what `parseTMS` reads.
 *
 * `Symbol`, `Transaction Type`, `Quantity`, `Rate` and `Date` are the exact keys
 * that importer picks up, which is what makes the round trip work.
 */
export const TRANSACTION_COLUMNS = Object.freeze([
  { key: "symbol", header: "Symbol" },
  { key: "side", header: "Transaction Type" },
  { key: "qty", header: "Quantity" },
  { key: "price", header: "Rate" },
  { key: "date", header: "Date", get: (t) => t.date || "" },
  { key: "portfolio", header: "Portfolio" },
  { key: "source", header: "Source", get: (t) => t.source || "manual" },
]);

/** Every transaction across every portfolio, re-importable as TMS CSV. */
export function exportTransactions(portfolios = []) {
  const rows = [];
  for (const p of portfolios) {
    for (const tx of p.transactions || []) {
      rows.push({ ...tx, portfolio: p.name || p.id });
    }
  }
  return toCsv(rows, TRANSACTION_COLUMNS);
}

export const HOLDING_COLUMNS = Object.freeze([
  { key: "symbol", header: "Symbol" },
  { key: "qty", header: "Quantity" },
  { key: "wacc", header: "WACC" },
  { key: "cost", header: "Cost" },
  { key: "ltp", header: "LTP" },
  { key: "value", header: "Value" },
  { key: "pnl", header: "Unrealized PnL" },
]);

/** A positions view. Derived, so it is a REPORT, not a backup. */
export function exportHoldings(holdings = []) {
  return toCsv(holdings, HOLDING_COLUMNS);
}

/**
 * Full backup. Transactions are the only thing exported as the restore path,
 * because holdings are DERIVED — restoring a computed position would silently
 * discard the history that produced it and any cost basis it disagreed with.
 */
export function exportPortfolioBundle(state) {
  const portfolios = state?.portfolios || [];
  return {
    filename: `saathios-portfolio-${stamp(state?.exportedAt)}.csv`,
    csv: exportTransactions(portfolios),
    portfolios: portfolios.length,
    transactions: portfolios.reduce((n, p) => n + (p.transactions?.length || 0), 0),
  };
}

function stamp(iso) {
  const s = typeof iso === "string" && iso.length >= 10 ? iso : null;
  return s ? s.slice(0, 10) : "export";
}
