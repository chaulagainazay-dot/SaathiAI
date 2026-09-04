// NEPSE historical price contract — parse, validate, and carry provenance.
// PURE: text in, typed bars out. No I/O, no synthesis.
//
// NEPSE-HIST-2. The qualified research source is an open archive of scraped NEPSE
// daily bars. It is NOT a licensed production feed, and the fields are not equally
// trustworthy — so trust is declared PER FIELD and per row, never per dataset.
//
// Established by auditing 5 symbols / ~15k rows against the source:
//   close     — high confidence; last close matched the live feed exactly on 5/5
//   high/low  — sound (high < low in 0–3 rows per ~3,500)
//   open      — UNRELIABLE before 2018-11-06 (~15–20% of rows fall outside
//               [low, high]); valid after. Hence OPEN_TRUSTED_FROM.
//   adjustment— UNADJUSTED, evidence-confirmed: overnight moves of 20–27% exist
//               while NEPSE runs a ±10% daily circuit, so those are corporate
//               actions left in the raw series.
//   calendar  — some rows fall on Fri/Sat though NEPSE trades Sun–Thu.
//
// Nothing here repairs data. A bad row is flagged and excluded from the fields it
// breaks; it is never rewritten, and a missing session is never invented.

/** The date from which this source's OPEN column is trustworthy. */
export const OPEN_TRUSTED_FROM = "2018-11-06";

/** NEPSE trades Sunday–Thursday. JS getUTCDay(): 0=Sun … 5=Fri, 6=Sat. */
const NON_TRADING_WEEKDAYS = new Set([5, 6]);

/** A daily circuit of ±10% means a larger overnight move is a corporate action. */
export const CIRCUIT_LIMIT_PCT = 10;

export const SOURCE_CLASS = {
  LICENSED_PRODUCTION: "LICENSED_PRODUCTION_CANDIDATE",
  CERTIFIED_RESEARCH: "CERTIFIED_RESEARCH_DATA",
  RESEARCH_ONLY: "RESEARCH_ONLY",
  LICENSE_REQUIRED: "LICENSE_REQUIRED",
  PROVENANCE_INCOMPLETE: "PROVENANCE_INCOMPLETE",
  TERMS_UNSUITABLE: "TERMS_UNSUITABLE",
  REJECTED: "REJECTED",
};

export const ADJUSTMENT = {
  UNADJUSTED: "UNADJUSTED",
  ADJUSTED: "ADJUSTED",
  UNKNOWN: "UNKNOWN",
};

/** Provenance for the one source qualified in this milestone. */
export const NEPSE_RESEARCH_SOURCE = Object.freeze({
  id: "aabishkar2/nepse-data",
  provider: "Aabishkar2/nepse-data (open archive)",
  dataset: "data/company-wise",
  origin: "scraped from public NEPSE portals",
  classification: SOURCE_CLASS.RESEARCH_ONLY,
  license: null, // no LICENSE file — redistribution terms undeclared
  adjustment: ADJUSTMENT.UNADJUSTED,
  adjustmentMethod: "ADJUSTMENT_METHOD_UNVERIFIED",
  revisionMetadata: false, // no publication/revision timestamps -> no universal PIT claim
  openTrustedFrom: OPEN_TRUSTED_FROM,
});

export const ROW_FLAG = {
  OPEN_OUT_OF_RANGE: "OPEN_OUT_OF_RANGE",
  OPEN_ERA_UNTRUSTED: "OPEN_ERA_UNTRUSTED",
  CLOSE_OUT_OF_RANGE: "CLOSE_OUT_OF_RANGE",
  HIGH_BELOW_LOW: "HIGH_BELOW_LOW",
  NON_POSITIVE: "NON_POSITIVE",
  CALENDAR_CONFLICT: "CALENDAR_CONFLICT",
  DUPLICATE_DATE: "DUPLICATE_DATE",
  OUT_OF_ORDER: "OUT_OF_ORDER",
  MISSING_CLOSE: "MISSING_CLOSE",
};

const num = (v) => {
  if (v === undefined || v === null) return null;
  const s = String(v).trim();
  if (!s || s.toLowerCase() === "nan") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
};

const isIsoDate = (s) => /^\d{4}-\d{2}-\d{2}$/.test(String(s || ""));

function weekdayOf(iso) {
  // Parse as UTC so the host timezone can never shift a trading date.
  const d = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? null : d.getUTCDay();
}

/**
 * Parse the source CSV into typed bars with per-row quality flags.
 * Rows are never repaired or invented; unusable ones are flagged and kept out of
 * the series they would corrupt.
 *
 * @returns {{bars: Array, rejected: Array, source: object}}
 */
export function parseHistoryCsv(text, { symbol = "", maxRows = 20000 } = {}) {
  const lines = String(text || "").split(/\r?\n/).filter((l) => l.trim().length);
  if (!lines.length) return { bars: [], rejected: [], source: NEPSE_RESEARCH_SOURCE };

  const header = lines[0].split(",").map((h) => h.trim().toLowerCase());
  const idx = (name) => header.indexOf(name);
  const iDate = idx("published_date");
  const iOpen = idx("open");
  const iHigh = idx("high");
  const iLow = idx("low");
  const iClose = idx("close");
  const iQty = idx("traded_quantity");
  const iAmt = idx("traded_amount");
  if (iDate < 0 || iClose < 0) return { bars: [], rejected: [], source: NEPSE_RESEARCH_SOURCE };

  const bars = [];
  const rejected = [];
  const seen = new Set();
  let prevDate = "";

  for (let i = 1; i < lines.length && bars.length < maxRows; i += 1) {
    const c = lines[i].split(",");
    const date = String(c[iDate] || "").trim();
    if (!isIsoDate(date)) { rejected.push({ line: i, date, reason: "BAD_DATE" }); continue; }

    const flags = [];
    if (seen.has(date)) flags.push(ROW_FLAG.DUPLICATE_DATE);
    seen.add(date);
    if (prevDate && date < prevDate) flags.push(ROW_FLAG.OUT_OF_ORDER);
    prevDate = date;

    const wd = weekdayOf(date);
    if (wd !== null && NON_TRADING_WEEKDAYS.has(wd)) flags.push(ROW_FLAG.CALENDAR_CONFLICT);

    const open = iOpen >= 0 ? num(c[iOpen]) : null;
    const high = iHigh >= 0 ? num(c[iHigh]) : null;
    const low = iLow >= 0 ? num(c[iLow]) : null;
    const close = num(c[iClose]);
    const volume = iQty >= 0 ? num(c[iQty]) : null;
    const turnover = iAmt >= 0 ? num(c[iAmt]) : null;

    if (close === null) { rejected.push({ line: i, date, reason: ROW_FLAG.MISSING_CLOSE }); continue; }
    if ([open, high, low, close].some((x) => x !== null && x <= 0)) flags.push(ROW_FLAG.NON_POSITIVE);
    if (high !== null && low !== null && high < low) flags.push(ROW_FLAG.HIGH_BELOW_LOW);
    if (high !== null && low !== null && (close < low || close > high)) flags.push(ROW_FLAG.CLOSE_OUT_OF_RANGE);

    // OPEN: distrust the whole pre-2018-11-06 era, and any row where it is
    // outside the day's range. Never repair it — mark it unusable.
    let openTrusted = open !== null;
    if (date < OPEN_TRUSTED_FROM) { openTrusted = false; flags.push(ROW_FLAG.OPEN_ERA_UNTRUSTED); }
    if (open !== null && high !== null && low !== null && (open < low || open > high)) {
      openTrusted = false;
      flags.push(ROW_FLAG.OPEN_OUT_OF_RANGE);
    }

    const closeUsable = !flags.includes(ROW_FLAG.NON_POSITIVE);
    const rangeUsable =
      high !== null && low !== null &&
      !flags.includes(ROW_FLAG.HIGH_BELOW_LOW) &&
      !flags.includes(ROW_FLAG.NON_POSITIVE);

    bars.push({
      symbol: String(symbol || "").toUpperCase(),
      date,
      open, high, low, close, volume, turnover,
      // Per-field trust — the whole point of this contract.
      trusted: { close: closeUsable, high: rangeUsable, low: rangeUsable, open: openTrusted, volume: volume !== null },
      flags,
      source: NEPSE_RESEARCH_SOURCE.id,
      adjustment: NEPSE_RESEARCH_SOURCE.adjustment,
    });
  }

  return { bars, rejected, source: NEPSE_RESEARCH_SOURCE };
}

/** Closes usable for indicators, oldest → newest. Bad rows drop out, never repaired. */
export function closeSeries(bars) {
  return bars.filter((b) => b.trusted.close).map((b) => b.close);
}

/**
 * Corporate actions visible as an unadjusted overnight gap beyond the circuit.
 * On an UNADJUSTED series these break every indicator that spans them, so they are
 * reported rather than smoothed away.
 */
export function corporateActionGaps(bars, limitPct = CIRCUIT_LIMIT_PCT) {
  const out = [];
  const usable = bars.filter((b) => b.trusted.close);
  for (let i = 1; i < usable.length; i += 1) {
    const prev = usable[i - 1].close;
    const cur = usable[i].close;
    if (!prev) continue;
    const pct = ((cur - prev) / prev) * 100;
    if (Math.abs(pct) > limitPct * 2) {
      out.push({ date: usable[i].date, from: prev, to: cur, pct: +pct.toFixed(2) });
    }
  }
  return out;
}

/** Dataset-level quality report — evidence for the certification verdict. */
export function historyQuality(bars, rejected = []) {
  const count = (f) => bars.filter((b) => b.flags.includes(f)).length;
  const gaps = corporateActionGaps(bars);
  return {
    rows: bars.length,
    rejected: rejected.length,
    firstDate: bars[0]?.date ?? null,
    lastDate: bars[bars.length - 1]?.date ?? null,
    usableCloses: closeSeries(bars).length,
    openUntrusted: bars.filter((b) => !b.trusted.open).length,
    flags: {
      OPEN_OUT_OF_RANGE: count(ROW_FLAG.OPEN_OUT_OF_RANGE),
      OPEN_ERA_UNTRUSTED: count(ROW_FLAG.OPEN_ERA_UNTRUSTED),
      CLOSE_OUT_OF_RANGE: count(ROW_FLAG.CLOSE_OUT_OF_RANGE),
      HIGH_BELOW_LOW: count(ROW_FLAG.HIGH_BELOW_LOW),
      CALENDAR_CONFLICT: count(ROW_FLAG.CALENDAR_CONFLICT),
      DUPLICATE_DATE: count(ROW_FLAG.DUPLICATE_DATE),
      OUT_OF_ORDER: count(ROW_FLAG.OUT_OF_ORDER),
      NON_POSITIVE: count(ROW_FLAG.NON_POSITIVE),
    },
    corporateActionGaps: gaps.length,
    adjustment: NEPSE_RESEARCH_SOURCE.adjustment,
    classification: NEPSE_RESEARCH_SOURCE.classification,
  };
}
