// Typed extractors for ShareSansar tables. PURE.
//
// Scraping a table by column POSITION is the fragile part of any extractor: the
// day the site inserts a column, every field shifts one place and the parser keeps
// returning confident, wrong numbers. Nothing about the output looks broken. So
// the central guarantee here is not the parsing — it is the REFUSAL:
//
//   Every extractor is handed the table's own header row and verifies it against
//   the layout it was written for. A mismatch returns no rows and says which
//   header moved. A wrong number is worse than no number.
//
// Everything returned carries its source and the session it describes, and page
// text is treated as untrusted throughout.

export const SHARESANSAR_SOURCE = Object.freeze({
  id: "sharesansar.com",
  label: "ShareSansar",
  host: "www.sharesansar.com",
  classification: "RESEARCH_ONLY",
  // Scraped from rendered HTML, not an API. It carries no licence grant and the
  // layout can change without notice — hence the header check on every parse.
  access: "SCRAPED_PUBLIC_PAGE",
  adjustment: "UNKNOWN",
});

/** Each page: where it lives, what to select, and the exact layout expected. */
export const SHARESANSAR_PAGES = Object.freeze({
  todayPrices: {
    url: "https://www.sharesansar.com/today-share-price",
    rowSelector: "#headFixed tbody tr",
    headerSelector: "#headFixed thead th",
    headers: ["S.No", "Symbol", "Conf.", "Open", "High", "Low", "Close", "LTP",
      "Close - LTP", "Close - LTP %", "VWAP", "Vol", "Prev. Close", "Turnover",
      "Trans.", "Diff", "Range", "Diff %", "Range %", "VWAP %",
      "120 Days", "180 Days", "52 Weeks High", "52 Weeks Low"],
  },
  proposedDividends: {
    url: "https://www.sharesansar.com/proposed-dividend",
    rowSelector: "#myTableLD tbody tr",
    headerSelector: "#myTableLD thead th",
    headers: ["S.N.", "Symbol", "Company", "Bonus (%)", "Cash (%)", "Total (%)",
      "Announcement Date", "Book Closure Date", "Distribution Date",
      "Bonus Listing Date", "Fiscal Year", "LTP", "As Of:"],
  },
});

const SYMBOL_RE = /^[A-Z0-9][A-Z0-9/.-]{0,15}$/;

/**
 * A ShareSansar 404 answers with HTTP 200 and a page titled "400 - Page Not
 * Found". A soft error that parses to zero rows looks exactly like a quiet day,
 * so it is detected explicitly rather than inferred from emptiness.
 */
export function looksLikeErrorPage(title) {
  return /\b(40\d|page not found|not found|error)\b/i.test(String(title || ""));
}

/** Rendered rows arrive newline-separated, cells tab-separated. */
export function splitRows(text) {
  return String(text || "")
    .split("\n")
    .map((line) => line.split("\t").map((c) => c.trim()))
    .filter((cells) => cells.some((c) => c.length));
}

/** Header text arrives one per line from the header selector. */
export function splitHeaders(text) {
  return String(text || "")
    .split("\n")
    .flatMap((l) => l.split("\t"))
    .map((h) => h.trim())
    .filter(Boolean);
}

/**
 * Verify the live header against the layout an extractor was written for.
 * Compared by normalized text and by POSITION — a column that merely moved is the
 * exact failure this guards against, so an unordered set comparison would miss it.
 */
export function verifyHeaders(observed, expected) {
  // Punctuation becomes a space rather than vanishing, so "S.No" and "S No"
  // normalize alike; dropping the dot outright would fuse them into "sno" and
  // make the two spellings differ.
  const norm = (h) => String(h || "").toLowerCase().replace(/[.:()%]/g, " ").replace(/\s+/g, " ").trim();
  const got = observed.map(norm);
  const want = expected.map(norm);
  if (!got.length) return { ok: false, reason: "NO_HEADERS", detail: "the table exposed no header row" };
  if (got.length !== want.length) {
    return {
      ok: false, reason: "COLUMN_COUNT_CHANGED",
      detail: `expected ${want.length} columns, found ${got.length}`,
    };
  }
  for (let i = 0; i < want.length; i += 1) {
    if (got[i] !== want[i]) {
      return {
        ok: false, reason: "COLUMN_MOVED",
        detail: `column ${i + 1} is "${observed[i]}", expected "${expected[i]}"`,
      };
    }
  }
  return { ok: true };
}

/**
 * Parse a ShareSansar number: thousands separators, and the several ways the site
 * writes "nothing". Absent stays null — never 0, which would read as a real zero
 * volume or a flat price.
 */
export function parseNum(v) {
  const s = String(v ?? "").trim().replace(/,/g, "");
  if (!s || s === "-" || s === "--" || s === "N/A" || s === "NaN") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

/** ISO date or null. The site also emits Bikram Sambat, which is left as text. */
export function parseIsoDate(v) {
  const s = String(v ?? "").trim();
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : null;
}

const guard = (headerText, page, title) => {
  if (looksLikeErrorPage(title)) {
    return { ok: false, reason: "ERROR_PAGE", detail: `the page returned "${title}"` };
  }
  const v = verifyHeaders(splitHeaders(headerText), page.headers);
  return v.ok ? { ok: true } : { ok: false, ...v };
};

const fail = (page, g) => ({
  ok: false,
  reason: g.reason,
  detail: g.detail,
  rows: [],
  source: SHARESANSAR_SOURCE,
  url: page.url,
});

/**
 * The full daily price table: OHLC, VWAP, volume, turnover, transactions, the
 * PREVIOUS CLOSE and the 52-week range — every field on one page.
 */
export function parseTodayPrices(rowText, headerText, { title = "" } = {}) {
  const page = SHARESANSAR_PAGES.todayPrices;
  const g = guard(headerText, page, title);
  if (!g.ok) return fail(page, g);

  const rows = [];
  const rejected = [];
  for (const c of splitRows(rowText)) {
    if (c.length !== page.headers.length) { rejected.push({ cells: c.length, reason: "CELL_COUNT" }); continue; }
    const symbol = c[1].toUpperCase();
    if (!SYMBOL_RE.test(symbol)) { rejected.push({ symbol: c[1], reason: "BAD_SYMBOL" }); continue; }
    const close = parseNum(c[6]);
    if (close === null) { rejected.push({ symbol, reason: "NO_CLOSE" }); continue; }

    const previousClose = parseNum(c[12]);
    const change = previousClose !== null && previousClose !== 0 ? +(close - previousClose).toFixed(4) : null;
    rows.push({
      symbol,
      open: parseNum(c[3]),
      high: parseNum(c[4]),
      low: parseNum(c[5]),
      close,
      ltp: parseNum(c[7]),
      vwap: parseNum(c[10]),
      volume: parseNum(c[11]),
      previousClose,
      turnover: parseNum(c[13]),
      transactions: parseNum(c[14]),
      fiftyTwoWeekHigh: parseNum(c[22]),
      fiftyTwoWeekLow: parseNum(c[23]),
      change,
      // Derived only where a real previous close exists — never against zero.
      changePct: change !== null ? +((change / previousClose) * 100).toFixed(2) : null,
      source: SHARESANSAR_SOURCE.id,
    });
  }
  return { ok: true, rows, rejected, source: SHARESANSAR_SOURCE, url: page.url };
}

/** Announced dividends: bonus, cash, book closure and the fiscal year. */
export function parseProposedDividends(rowText, headerText, { title = "" } = {}) {
  const page = SHARESANSAR_PAGES.proposedDividends;
  const g = guard(headerText, page, title);
  if (!g.ok) return fail(page, g);

  const rows = [];
  const rejected = [];
  for (const c of splitRows(rowText)) {
    if (c.length !== page.headers.length) { rejected.push({ cells: c.length, reason: "CELL_COUNT" }); continue; }
    const symbol = c[1].toUpperCase();
    if (!SYMBOL_RE.test(symbol)) { rejected.push({ symbol: c[1], reason: "BAD_SYMBOL" }); continue; }
    const bonus = parseNum(c[3]);
    const cash = parseNum(c[4]);
    // A dividend with neither a bonus nor a cash component says nothing.
    if (bonus === null && cash === null) { rejected.push({ symbol, reason: "NO_DIVIDEND" }); continue; }
    rows.push({
      symbol,
      company: c[2] || null,
      bonusPct: bonus,
      cashPct: cash,
      totalPct: parseNum(c[5]),
      announcedOn: parseIsoDate(c[6]),
      bookClosureOn: parseIsoDate(c[7]),
      distributionOn: parseIsoDate(c[8]),
      bonusListingOn: parseIsoDate(c[9]),
      // Bikram Sambat, kept verbatim — converting calendars is its own hazard.
      fiscalYearBs: c[10] || null,
      ltp: parseNum(c[11]),
      asOf: parseIsoDate(c[12]),
      source: SHARESANSAR_SOURCE.id,
    });
  }
  return { ok: true, rows, rejected, source: SHARESANSAR_SOURCE, url: page.url };
}
