/**
 * NRB foreign-exchange rates — parsing and governance. PURE, no I/O.
 *
 * Nepal Rastra Bank publishes the official daily reference rates through a
 * public JSON API. This module normalises that payload and decides whether a
 * configured endpoint may be called at all — the same fail-closed shape
 * `feed-policy.js` uses for market data, for the same reason: a rate presented
 * without provenance is indistinguishable from a guess.
 *
 * BUY AND SELL ARE NOT INTERCHANGEABLE. NRB publishes both, and they differ by
 * roughly 1%. Showing one labelled simply "rate" is how a remittance estimate
 * comes out wrong in the customer's favour or the bank's. Both are carried, and
 * neither is defaulted to.
 *
 * GOLD AND SILVER ARE NOT HERE. NRB does not publish bullion; those rates come
 * from FENEGOSIDA, a different body with no public API. Inventing them from a
 * spot price and an assumed premium would be fabrication, so the feature
 * reports NO_SOURCE until a real one is configured.
 */

/** The only host these rates may be fetched from. */
export const NRB_HOST = "www.nrb.org.np";
export const NRB_RATES_PATH = "/api/forex/v1/rates";

export const FOREX_STATE = Object.freeze({
  OK: "OK",
  NOT_CONFIGURED: "NOT_CONFIGURED",
  HOST_NOT_ALLOWED: "HOST_NOT_ALLOWED",
  UNREACHABLE: "UNREACHABLE",
  MALFORMED: "MALFORMED",
  EMPTY: "EMPTY",
});

/** Bullion has no configured source; saying so beats inventing a number. */
export const BULLION_STATE = Object.freeze({
  NO_SOURCE: "NO_SOURCE",
});

export function bullionRates() {
  return {
    state: BULLION_STATE.NO_SOURCE,
    detail: "gold and silver are published by FENEGOSIDA, which exposes no public API",
    rates: [],
  };
}

/** Only NRB's own host over HTTPS. */
export function isAllowedForexUrl(raw) {
  try {
    const u = new URL(String(raw));
    if (u.protocol !== "https:") return false;
    return u.hostname.toLowerCase() === NRB_HOST;
  } catch {
    return false;
  }
}

/**
 * Build the rates URL.
 *
 * `page`, `from` and `to` are ALL REQUIRED — the API answers 400 with a
 * validation body when any is missing, and `data.payload` comes back null,
 * which the parser then correctly reports as malformed. Omitting them was a
 * real defect caught by probing the live endpoint rather than by reading docs.
 */
export function buildRatesUrl({ date, page = 1, perPage = 100 } = {}) {
  const d = typeof date === "string" && date.length >= 10
    ? date.slice(0, 10)
    : new Date().toISOString().slice(0, 10);
  return `https://${NRB_HOST}${NRB_RATES_PATH}` +
    `?page=${page}&per_page=${perPage}&from=${d}&to=${d}`;
}

const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/**
 * Normalise one NRB payload.
 *
 * NRB nests the day's rates under `data.payload[].rates[]`, and the shape has
 * changed before. Anything that does not match is MALFORMED rather than
 * partially salvaged: half a currency table read as a whole one is worse than
 * an honest failure.
 */
export function parseNrbRates(payload) {
  const days = payload?.data?.payload;
  if (!Array.isArray(days)) {
    return { state: FOREX_STATE.MALFORMED, detail: "data.payload is not an array", rates: [] };
  }
  if (!days.length) {
    return { state: FOREX_STATE.EMPTY, detail: "no rates published for the requested date", rates: [] };
  }
  const day = days[0];
  const rows = Array.isArray(day?.rates) ? day.rates : null;
  if (!rows) {
    return { state: FOREX_STATE.MALFORMED, detail: "day carries no rates array", rates: [] };
  }

  const rates = [];
  const rejected = [];
  for (const r of rows) {
    const code = String(r?.currency?.iso3 ?? "").toUpperCase();
    const unit = num(r?.currency?.unit);
    const buy = num(r?.buy);
    const sell = num(r?.sell);
    // A currency missing either side is not shown at all: a one-sided rate
    // invites the reader to treat it as both.
    if (!code || unit === null || buy === null || sell === null) {
      rejected.push({ code: code || null, reason: "INCOMPLETE_ROW" });
      continue;
    }
    rates.push({
      code,
      name: r?.currency?.name ?? null,
      unit,
      buy,
      sell,
      // Per-unit figures, since NRB quotes JPY and KRW per 10 units.
      buyPerUnit: buy / unit,
      sellPerUnit: sell / unit,
      spreadPct: buy > 0 ? ((sell - buy) / buy) * 100 : null,
    });
  }
  return {
    state: rates.length ? FOREX_STATE.OK : FOREX_STATE.EMPTY,
    date: day?.date ?? null,
    published: day?.published_on ?? null,
    modified: day?.modified_on ?? null,
    rates,
    rejected,
    source: "Nepal Rastra Bank",
  };
}

/** Convert using the side that actually applies to the direction of trade. */
export function convert(amount, rate, { side = "buy" } = {}) {
  const a = num(amount);
  if (a === null || !rate) return null;
  const per = side === "sell" ? rate.sellPerUnit : rate.buyPerUnit;
  return Number.isFinite(per) ? a * per : null;
}

export const findRate = (rates, code) =>
  (rates || []).find((r) => r.code === String(code || "").toUpperCase()) || null;
