/**
 * Bikram Sambat fiscal years for NEPSE disclosures. PURE.
 *
 * Dividends, IPOs and financial reports are published against a B.S. fiscal
 * year — "2081/82" — not a Gregorian one. Filtering those by A.D. year gives
 * wrong answers at both ends, because Nepal's fiscal year runs mid-July to
 * mid-July and the B.S. year rolls over inside it.
 *
 * DELIBERATE SCOPE. This does NOT implement a full B.S.↔A.D. calendar. That
 * needs a per-year table of month lengths (Nepali months vary between 29 and 32
 * days and are fixed by almanac, not formula), and a converter built on an
 * approximation is worse than none: it produces plausible dates that are one or
 * two days wrong, which nobody catches. What is implemented is fiscal-year
 * LABEL handling — parsing, ordering, comparison and grouping — which is what
 * the dividend and IPO screens actually need. Conversion is marked
 * NOT_IMPLEMENTED rather than approximated.
 */

/** `2081/82`, `2081/2082`, `2081-82` all mean the same fiscal year. */
const FY_PATTERN = /^(\d{4})\s*[/\-]\s*(\d{2,4})$/;

export const FY_STATUS = Object.freeze({
  VALID: "VALID",
  UNPARSEABLE: "UNPARSEABLE",
  INCONSISTENT: "INCONSISTENT",
});

/**
 * Parse a fiscal-year label into a comparable form.
 *
 * The second half must be the year after the first. `2081/85` is not a fiscal
 * year, and accepting it would let a typo sort into the middle of a list.
 */
export function parseFiscalYear(raw) {
  const s = String(raw ?? "").trim();
  const m = FY_PATTERN.exec(s);
  if (!m) return { status: FY_STATUS.UNPARSEABLE, input: raw, start: null, label: null };
  const start = Number(m[1]);
  const tail = m[2];
  const end = tail.length === 2 ? Math.floor(start / 100) * 100 + Number(tail) : Number(tail);
  if (end !== start + 1) {
    return { status: FY_STATUS.INCONSISTENT, input: raw, start, end, label: null };
  }
  return {
    status: FY_STATUS.VALID,
    input: raw,
    start,
    end,
    // One canonical spelling, so grouping does not split "2081/82" from "2081-82".
    label: `${start}/${String(end).slice(-2)}`,
    sortKey: start,
  };
}

export const isValidFiscalYear = (raw) => parseFiscalYear(raw).status === FY_STATUS.VALID;

/** Canonical label, or null when it cannot be trusted. */
export function fiscalYearLabel(raw) {
  const p = parseFiscalYear(raw);
  return p.status === FY_STATUS.VALID ? p.label : null;
}

/** Newest first. Unparseable labels sort last rather than silently vanishing. */
export function sortFiscalYears(labels = []) {
  const parsed = labels.map(parseFiscalYear);
  const valid = parsed.filter((p) => p.status === FY_STATUS.VALID);
  const rest = parsed.filter((p) => p.status !== FY_STATUS.VALID);
  valid.sort((a, b) => b.sortKey - a.sortKey);
  return [...valid.map((p) => p.label), ...rest.map((p) => String(p.input))];
}

/** Distinct fiscal years present in a dataset, newest first. */
export function fiscalYearsIn(rows = [], key = "fiscalYear") {
  const seen = new Set();
  for (const r of rows) {
    const label = fiscalYearLabel(r?.[key]);
    if (label) seen.add(label);
  }
  return sortFiscalYears([...seen]);
}

/**
 * Filter rows to one fiscal year.
 *
 * Rows whose label cannot be parsed are EXCLUDED rather than kept "just in
 * case": a dividend of unknown year shown under 2081/82 is a false statement
 * about when it was declared.
 */
export function filterByFiscalYear(rows = [], label, key = "fiscalYear") {
  const want = fiscalYearLabel(label);
  if (!want) return [];
  return rows.filter((r) => fiscalYearLabel(r?.[key]) === want);
}

/** Group rows by fiscal year, newest first, with unparseable rows reported. */
export function groupByFiscalYear(rows = [], key = "fiscalYear") {
  const groups = new Map();
  const unknown = [];
  for (const r of rows) {
    const label = fiscalYearLabel(r?.[key]);
    if (!label) { unknown.push(r); continue; }
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(r);
  }
  const ordered = sortFiscalYears([...groups.keys()])
    .map((label) => ({ fiscalYear: label, rows: groups.get(label) }));
  // Surfaced, not dropped: an unexplained gap in a table is worse than a
  // labelled "unknown fiscal year" bucket.
  return { groups: ordered, unknown };
}

/**
 * A.D.↔B.S. date conversion is NOT implemented, on purpose.
 *
 * Nepali month lengths vary by year and are fixed by almanac, not by formula.
 * A converter built on an approximation returns dates that are plausibly one or
 * two days wrong — the worst kind of wrong, because nobody audits a date that
 * looks reasonable. Callers get an explicit refusal and can supply a real
 * conversion table when one is available.
 */
export const CONVERSION_STATUS = "NOT_IMPLEMENTED";

export function adToBs() {
  return { ok: false, reason: CONVERSION_STATUS,
           detail: "B.S. date conversion needs a per-year month-length table" };
}

export function bsToAd() {
  return { ok: false, reason: CONVERSION_STATUS,
           detail: "B.S. date conversion needs a per-year month-length table" };
}
