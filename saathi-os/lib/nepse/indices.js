// NEPSE index and sub-indices — parsing and provenance. PURE.
//
// This is the number the market page could not previously show. The per-company
// archive cannot yield an index, so the page rendered "—" rather than synthesize
// one. This module reads the PUBLISHED index series instead, so the figure on the
// page is NEPSE's, not ours.
//
// Two defects in the upstream data are handled here rather than downstream:
//
//   1. DUPLICATE ROWS. Roughly one file in fifteen repeats every index, and some
//      repeats DISAGREE (Banking_index appears as both 1442 and 1442.05 on
//      2026-07-07). Silently taking whichever row parsed last would make the value
//      depend on file ordering. The last row wins deterministically AND the
//      conflict is recorded, so a UI can show that the source contradicted itself.
//   2. SCHEMA DRIFT. Older files omit `timestamp`/`date_unix` and order columns
//      differently, so every field is located by HEADER NAME, never by position.
//
// Symbols arrive percent-encoded ("Development%20Bank_index").

export const NEPSE_INDEX_SOURCE = Object.freeze({
  id: "socrateai/nepse-open-data",
  label: "NEPSE Open Data (SocrateAI)",
  license: "MIT",
  classification: "RESEARCH_ONLY",
  adjustment: "ADJUSTED",
  host: "raw.githubusercontent.com",
});

/** The whole-market index. Not a sector. */
export const MAIN_INDEX = "NEPSE";

/**
 * Index symbol → display name, and whether it is a SECTOR index or a market-wide
 * variant. Float/Sensitive/Sen. Float track subsets of the whole market, so
 * listing them beside sectors would double-count the market as a sector.
 */
export const INDEX_META = Object.freeze({
  NEPSE: { label: "NEPSE", kind: "MARKET" },
  Float: { label: "Float", kind: "MARKET" },
  Sensitive: { label: "Sensitive", kind: "MARKET" },
  "Sen. Float": { label: "Sensitive Float", kind: "MARKET" },
  Banking: { label: "Commercial Banks", kind: "SECTOR" },
  "Development Bank": { label: "Development Banks", kind: "SECTOR" },
  Finance: { label: "Finance", kind: "SECTOR" },
  Microfinance: { label: "Microfinance", kind: "SECTOR" },
  "Hotels and Tourism": { label: "Hotels & Tourism", kind: "SECTOR" },
  HydroPower: { label: "Hydropower", kind: "SECTOR" },
  "Life Insurance": { label: "Life Insurance", kind: "SECTOR" },
  "Non Life Insurance": { label: "Non-Life Insurance", kind: "SECTOR" },
  Investment: { label: "Investment", kind: "SECTOR" },
  Trading: { label: "Trading", kind: "SECTOR" },
  "Mutual Fund": { label: "Mutual Fund", kind: "SECTOR" },
  Others: { label: "Others", kind: "SECTOR" },
});

/**
 * NEPSE publishes a Manufacturing & Processing sub-index; this source does not
 * carry it. Named so the gap is visible instead of looking like a sector that
 * simply did not move.
 */
export const KNOWN_MISSING_SECTORS = Object.freeze(["Manufacturing & Processing"]);

const num = (v) => {
  const s = String(v ?? "").trim();
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
};

/** Strip the `_index` suffix and percent-encoding from a raw symbol. */
export function indexKey(raw) {
  let s = String(raw || "").trim();
  try { s = decodeURIComponent(s); } catch { /* keep the raw form */ }
  return s.replace(/_index$/i, "").trim();
}

/**
 * Parse one daily index file.
 * @returns {{rows, conflicts, date}} rows keyed by index name, newest row winning
 */
export function parseIndexCsv(text, { date = null } = {}) {
  const lines = String(text || "").split(/\r?\n/).filter((l) => l.trim().length);
  if (lines.length < 2) return { rows: [], conflicts: [], date };

  const header = lines[0].split(",").map((h) => h.trim().toLowerCase());
  const at = (name) => header.indexOf(name);
  const iSym = at("symbol");
  const iClose = at("close");
  if (iSym < 0 || iClose < 0) return { rows: [], conflicts: [], date };
  const iOpen = at("open");
  const iHigh = at("high");
  const iLow = at("low");
  const iVol = at("volume");
  const iDate = at("date");

  const byKey = new Map();
  const conflicts = [];
  let fileDate = date;

  for (const line of lines.slice(1)) {
    const c = line.split(",");
    const key = indexKey(c[iSym]);
    if (!key) continue;
    const close = num(c[iClose]);
    if (close === null) continue;
    if (iDate >= 0 && !fileDate) {
      const d = String(c[iDate] || "").trim();
      if (/^\d{4}-\d{2}-\d{2}$/.test(d)) fileDate = d;
    }
    const prior = byKey.get(key);
    // Last row wins, but a disagreement is never swallowed.
    if (prior && prior.close !== close) {
      conflicts.push({ index: key, date: fileDate, values: [prior.close, close] });
    }
    byKey.set(key, {
      index: key,
      label: INDEX_META[key]?.label || key,
      kind: INDEX_META[key]?.kind || "UNKNOWN",
      close,
      open: iOpen >= 0 ? num(c[iOpen]) : null,
      high: iHigh >= 0 ? num(c[iHigh]) : null,
      low: iLow >= 0 ? num(c[iLow]) : null,
      // For NEPSE this column is the session's total traded VALUE in rupees.
      volume: iVol >= 0 ? num(c[iVol]) : null,
    });
  }

  const rows = [...byKey.values()].map((r) => ({ ...r, date: fileDate }));
  return { rows, conflicts, date: fileDate };
}

/** Look up one index in a parsed day. */
export function pickIndex(rows, key = MAIN_INDEX) {
  return rows.find((r) => r.index === key) || null;
}

/**
 * Change for every index between two parsed sessions.
 * An index present in only one of the two sessions yields a null change rather
 * than being compared against nothing.
 */
export function indexChanges(current, previous) {
  const prev = new Map((previous || []).map((r) => [r.index, r]));
  return (current || []).map((r) => {
    const p = prev.get(r.index);
    if (!p || !p.close) {
      return { ...r, previousClose: p?.close ?? null, change: null, changePct: null,
               available: false, reason: p ? "ZERO_PREVIOUS_CLOSE" : "NO_PRIOR_SESSION" };
    }
    const change = +(r.close - p.close).toFixed(4);
    return {
      ...r,
      previousClose: p.close,
      previousDate: p.date,
      change,
      changePct: +((change / p.close) * 100).toFixed(2),
      available: true,
    };
  });
}

/** Sector indices only — market-wide variants are not sectors. */
export function sectorIndices(changes) {
  return (changes || [])
    .filter((r) => r.kind === "SECTOR")
    .sort((a, b) => (b.changePct ?? -Infinity) - (a.changePct ?? -Infinity));
}

/** Market-wide indices (NEPSE, Float, Sensitive, Sensitive Float). */
export function marketIndices(changes) {
  const order = ["NEPSE", "Sensitive", "Float", "Sen. Float"];
  return (changes || [])
    .filter((r) => r.kind === "MARKET")
    .sort((a, b) => order.indexOf(a.index) - order.indexOf(b.index));
}

/** A close-only series for one index, oldest → newest, for charting. */
export function indexSeries(days, key = MAIN_INDEX) {
  const out = [];
  for (const day of days || []) {
    const row = pickIndex(day.rows, key);
    if (row && day.date) out.push({ date: day.date, close: row.close });
  }
  return out.sort((a, b) => a.date.localeCompare(b.date));
}
