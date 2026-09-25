/**
 * Side-by-side instrument comparison. PURE.
 *
 * Two jobs: a normalised return series so differently-priced stocks are
 * visually comparable, and a fundamentals matrix.
 *
 * NORMALISATION IS THE WHOLE POINT OF THE CHART. Plotting a Rs 4,000 share
 * against a Rs 200 one on a shared axis says nothing except which is more
 * expensive. Rebasing every series to its own period start turns it into a
 * comparison of PERFORMANCE, which is the question being asked.
 */

export const MAX_COMPARE = 8;

export const PERIODS = Object.freeze({
  "1W": 5, "1M": 22, "3M": 66, "6M": 132, "1Y": 252, "3Y": 756, "5Y": 1260, ALL: Infinity,
});

/** Trim bars to a period, counted in sessions rather than calendar days. */
export function barsForPeriod(bars = [], period = "1Y") {
  const n = PERIODS[period] ?? PERIODS["1Y"];
  const usable = bars.filter((b) => typeof b?.close === "number" && b.date);
  return n === Infinity ? usable : usable.slice(-n);
}

/**
 * Rebase a series to 0% at its start.
 *
 * A series whose first close is zero or missing is REFUSED, not divided by
 * zero: an Infinity silently plotted as a spike is worse than an absent line.
 */
export function normalize(bars = []) {
  const usable = bars.filter((b) => typeof b?.close === "number");
  if (usable.length < 2) return { ok: false, reason: "INSUFFICIENT_HISTORY", points: [] };
  const base = usable[0].close;
  if (!base) return { ok: false, reason: "ZERO_BASE", points: [] };
  return {
    ok: true,
    base,
    points: usable.map((b) => ({ date: b.date, pct: ((b.close - base) / base) * 100 })),
    returnPct: ((usable[usable.length - 1].close - base) / base) * 100,
  };
}

/** Build the chart series for several symbols over one period. */
export function compareSeries(entries = [], { period = "1Y" } = {}) {
  const series = [];
  const excluded = [];
  for (const e of entries.slice(0, MAX_COMPARE)) {
    const norm = normalize(barsForPeriod(e?.bars || [], period));
    if (!norm.ok) { excluded.push({ symbol: e?.symbol, reason: norm.reason }); continue; }
    series.push({ symbol: e.symbol, points: norm.points, returnPct: norm.returnPct });
  }
  return {
    period, series, excluded,
    // A chart drawn from 3 of 5 requested symbols must say so.
    requested: Math.min(entries.length, MAX_COMPARE),
    plotted: series.length,
  };
}

/** The fundamentals rows a comparison table shows. */
export const COMPARE_FIELDS = Object.freeze([
  { key: "ltp", label: "LTP" },
  { key: "changePct", label: "Day change %" },
  { key: "returnPct", label: "Period return %" },
  { key: "high52", label: "52-week high" },
  { key: "low52", label: "52-week low" },
  { key: "marketCap", label: "Market cap" },
  { key: "sector", label: "Sector" },
  { key: "pe", label: "P/E" },
  { key: "eps", label: "EPS" },
  { key: "bookValue", label: "Book value" },
  { key: "pb", label: "P/B" },
  { key: "dividendYield", label: "Dividend yield %" },
  { key: "latestDividend", label: "Latest dividend" },
  { key: "paidUpCapital", label: "Paid-up capital" },
]);

/**
 * A field-by-symbol matrix.
 *
 * A missing fundamental stays `null` and renders as "—". Substituting zero
 * would put a stock with no published P/E at the top of a "cheapest" sort.
 */
export function compareMatrix(stocks = [], { series = [] } = {}) {
  const picked = stocks.slice(0, MAX_COMPARE);
  const returnBySymbol = new Map(series.map((s) => [s.symbol, s.returnPct]));
  return {
    symbols: picked.map((s) => s.symbol),
    rows: COMPARE_FIELDS.map((f) => ({
      key: f.key,
      label: f.label,
      values: picked.map((s) => {
        if (f.key === "returnPct") return returnBySymbol.get(s.symbol) ?? null;
        const v = s?.[f.key];
        return v === undefined || v === "" ? null : v;
      }),
    })),
  };
}

/** Guard the add-to-comparison action. */
export function canAdd(current = [], symbol) {
  const sym = String(symbol || "").toUpperCase();
  if (!sym) return { ok: false, reason: "NO_SYMBOL" };
  if (current.some((s) => String(s).toUpperCase() === sym)) {
    return { ok: false, reason: "ALREADY_ADDED" };
  }
  if (current.length >= MAX_COMPARE) return { ok: false, reason: "LIMIT_REACHED", limit: MAX_COMPARE };
  return { ok: true, symbol: sym };
}
