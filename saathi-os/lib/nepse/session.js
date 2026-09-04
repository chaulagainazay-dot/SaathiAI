// Session context — derives a REAL previous close, volume, turnover and 52-week
// range from the daily archive, to pair with the live last-traded price. PURE.
//
// Why this exists: the live quote provider returns LTP only, so day change rendered
// as "—" everywhere. The daily archive carries yesterday's official close. Pairing
// today's LTP with yesterday's close is the correct definition of day change — the
// previous close is a settled daily value, not something that moves intraday.
//
// The trap this module is built around: pairing a live price with a STALE close
// silently produces a wrong percentage. So the previous close is only ever taken
// from a bar strictly BEFORE the live session, its date is returned alongside it,
// and a gap beyond `maxStaleDays` is refused rather than quietly used.

/** How far back a "previous close" may sit before it stops being one. */
export const MAX_PREV_CLOSE_STALE_DAYS = 5;

export const SESSION_BASIS = {
  PRIOR_SESSION: "PRIOR_SESSION",       // archive's last bar precedes today — ideal
  STEPPED_BACK: "STEPPED_BACK",         // archive already includes today; used the bar before
  STALE: "STALE",                       // newest usable bar is too old to trust
  UNAVAILABLE: "UNAVAILABLE",           // no usable bar at all
};

const dayMs = 86400000;
const toDate = (iso) => {
  const t = Date.parse(`${iso}T00:00:00Z`);
  return Number.isFinite(t) ? t : null;
};

/**
 * Derive the previous close for a live session.
 *
 * @param bars typed archive bars, oldest → newest (needs {date, close})
 * @param opts.asOfDate ISO date of the LIVE session (defaults to today, UTC)
 * @returns {{previousClose, previousCloseDate, basis, staleDays}}
 */
export function previousCloseFor(bars, { asOfDate = null, maxStaleDays = MAX_PREV_CLOSE_STALE_DAYS } = {}) {
  const usable = (bars || []).filter((b) => b?.trusted?.close !== false && typeof b?.close === "number" && b.date);
  if (!usable.length) {
    return { previousClose: null, previousCloseDate: null, basis: SESSION_BASIS.UNAVAILABLE, staleDays: null };
  }

  const today = asOfDate || new Date().toISOString().slice(0, 10);
  const todayMs = toDate(today);

  // Only bars strictly before the live session can supply a previous close. If the
  // archive already contains today's bar, that bar IS today's close, not the
  // previous one — stepping back is the whole point.
  const prior = usable.filter((b) => {
    const t = toDate(b.date);
    return t !== null && todayMs !== null && t < todayMs;
  });

  if (!prior.length) {
    return { previousClose: null, previousCloseDate: null, basis: SESSION_BASIS.UNAVAILABLE, staleDays: null };
  }

  const bar = prior[prior.length - 1];
  const includesToday = usable[usable.length - 1].date >= today;
  const staleDays = todayMs !== null ? Math.round((todayMs - toDate(bar.date)) / dayMs) : null;

  if (staleDays !== null && staleDays > maxStaleDays) {
    return {
      previousClose: null,
      previousCloseDate: bar.date,
      basis: SESSION_BASIS.STALE,
      staleDays,
    };
  }

  return {
    previousClose: bar.close,
    previousCloseDate: bar.date,
    basis: includesToday ? SESSION_BASIS.STEPPED_BACK : SESSION_BASIS.PRIOR_SESSION,
    staleDays,
  };
}

/** 52-week high/low from the trailing ~252 sessions of trusted closes. */
export function fiftyTwoWeek(bars, { sessions = 252 } = {}) {
  const w = (bars || []).filter((b) => b?.trusted?.close !== false && typeof b?.close === "number").slice(-sessions);
  if (w.length < 20) return { high: null, low: null, sessions: w.length, basis: "INSUFFICIENT_HISTORY" };
  // Use the day's range where it is trusted, otherwise the close — never invent one.
  let high = -Infinity;
  let low = Infinity;
  for (const b of w) {
    const hi = b.trusted?.high && typeof b.high === "number" ? b.high : b.close;
    const lo = b.trusted?.low && typeof b.low === "number" ? b.low : b.close;
    if (hi > high) high = hi;
    if (lo < low) low = lo;
  }
  return {
    high: +high.toFixed(4),
    low: +low.toFixed(4),
    sessions: w.length,
    basis: w.length >= sessions ? "FULL_WINDOW" : "PARTIAL_WINDOW",
  };
}

/** Last reported session's volume, turnover and derived average traded price. */
export function lastSessionActivity(bars) {
  const usable = (bars || []).filter((b) => typeof b?.close === "number" && b.date);
  if (!usable.length) return { volume: null, turnover: null, averagePrice: null, date: null };
  const b = usable[usable.length - 1];
  const volume = typeof b.volume === "number" && b.volume > 0 ? b.volume : null;
  const turnover = typeof b.turnover === "number" && b.turnover > 0 ? b.turnover : null;
  return {
    date: b.date,
    volume,
    turnover,
    // Only derivable when both sides are reported; never approximated from close.
    averagePrice: volume !== null && turnover !== null ? +(turnover / volume).toFixed(4) : null,
  };
}

/**
 * Change across the last COMPLETED session (its close vs the one before).
 * This is what to show when the market is shut: a live "0.00%" on a holiday reads
 * as a flat trading day, which is not what happened — there was no trading day.
 */
export function lastSessionChange(bars) {
  const usable = (bars || []).filter((b) => b?.trusted?.close !== false && typeof b?.close === "number" && b.date);
  if (usable.length < 2) return { change: null, changePct: null, available: false, date: null, priorDate: null };
  const last = usable[usable.length - 1];
  const prior = usable[usable.length - 2];
  if (!prior.close) return { change: null, changePct: null, available: false, date: last.date, priorDate: prior.date };
  const change = +(last.close - prior.close).toFixed(4);
  return {
    change,
    changePct: +((change / prior.close) * 100).toFixed(2),
    available: true,
    date: last.date,
    priorDate: prior.date,
  };
}

/**
 * Assemble everything the live surfaces need for one symbol.
 * Every field carries where it came from, so a UI can show a real day change
 * without ever implying the archive supplied the live price.
 */
export function sessionContext(bars, { asOfDate = null } = {}) {
  const prev = previousCloseFor(bars, { asOfDate });
  const range = fiftyTwoWeek(bars);
  const activity = lastSessionActivity(bars);
  const lastChange = lastSessionChange(bars);
  return {
    lastSessionChange: lastChange.change,
    lastSessionChangePct: lastChange.changePct,
    lastSessionChangeFrom: lastChange.priorDate,
    previousClose: prev.previousClose,
    previousCloseDate: prev.previousCloseDate,
    previousCloseBasis: prev.basis,
    previousCloseStaleDays: prev.staleDays,
    fiftyTwoWeekHigh: range.high,
    fiftyTwoWeekLow: range.low,
    fiftyTwoWeekBasis: range.basis,
    fiftyTwoWeekSessions: range.sessions,
    lastSessionDate: activity.date,
    lastSessionVolume: activity.volume,
    lastSessionTurnover: activity.turnover,
    lastSessionAveragePrice: activity.averagePrice,
  };
}

/** Day change from a LIVE price against a derived previous close. */
export function dayChange(livePrice, ctx) {
  if (typeof livePrice !== "number" || ctx?.previousClose === null || ctx?.previousClose === undefined) {
    return { change: null, changePct: null, available: false, reason: ctx?.previousCloseBasis || "UNAVAILABLE" };
  }
  const prev = ctx.previousClose;
  if (!prev) return { change: null, changePct: null, available: false, reason: "ZERO_PREVIOUS_CLOSE" };
  const change = +(livePrice - prev).toFixed(4);
  return {
    change,
    changePct: +((change / prev) * 100).toFixed(2),
    available: true,
    against: ctx.previousCloseDate,
    basis: ctx.previousCloseBasis,
  };
}
