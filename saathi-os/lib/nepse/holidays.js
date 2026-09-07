/**
 * NEPSE trading calendar — DERIVED from the archive, not declared. PURE.
 *
 * A hardcoded holiday list is wrong within a year: Nepal's calendar moves with
 * the Bikram Sambat year, festival dates shift, and NEPSE adds unscheduled
 * closures. So nothing here is typed in. A closure is INFERRED: a day the
 * exchange should have traded and no instrument recorded a session.
 *
 * That inversion is the honest one — it reports what the market actually did
 * rather than what a stale table said it would do — but it has a real limit,
 * stated rather than hidden: the archive cannot distinguish "the exchange was
 * shut" from "we have no data for that day". Both surface as UNCONFIRMED unless
 * a neighbouring session proves the archive was otherwise healthy. Callers get
 * the confidence, not just the verdict.
 */

/** NEPSE trades Sunday–Thursday. Friday and Saturday are the weekend. */
export const TRADING_WEEKDAYS = Object.freeze([0, 1, 2, 3, 4]); // Sun..Thu
export const WEEKEND_WEEKDAYS = Object.freeze([5, 6]);          // Fri, Sat

export const DAY_KIND = Object.freeze({
  TRADED: "TRADED",
  WEEKEND: "WEEKEND",
  /** A trading weekday with no session anywhere in the archive. */
  CLOSED: "CLOSED",
  /** A gap we cannot attribute — closure or missing data, unresolved. */
  UNCONFIRMED: "UNCONFIRMED",
});

const DAY_MS = 86400000;

/** `YYYY-MM-DD` -> UTC epoch ms. Returns null on anything unparseable. */
export function dayEpoch(iso) {
  if (typeof iso !== "string" || iso.length < 10) return null;
  const y = Number(iso.slice(0, 4));
  const m = Number(iso.slice(5, 7));
  const d = Number(iso.slice(8, 10));
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return null;
  const t = Date.UTC(y, m - 1, d);
  return Number.isFinite(t) ? t : null;
}

export const isoOf = (epoch) => new Date(epoch).toISOString().slice(0, 10);
export const weekdayOf = (iso) => {
  const e = dayEpoch(iso);
  return e === null ? null : new Date(e).getUTCDay();
};
export const isWeekend = (iso) => WEEKEND_WEEKDAYS.includes(weekdayOf(iso));

/** Every distinct session date in the archive, ascending. */
export function tradingDays(entries = []) {
  const seen = new Set();
  for (const e of entries) {
    for (const b of e?.bars || []) {
      if (b?.date && dayEpoch(b.date) !== null) seen.add(b.date.slice(0, 10));
    }
  }
  return [...seen].sort();
}

/**
 * Classify every calendar day across the archive's span.
 *
 * `minTradedFor` is the confidence gate: a weekday with no sessions is only
 * called CLOSED when the archive is dense enough around it to be trusted. One
 * company reporting is not evidence the exchange was open, and zero companies
 * reporting in a sparse archive is not evidence it was shut.
 */
export function calendar(entries = [], { minTradedFor = 1 } = {}) {
  const perDay = new Map();
  for (const e of entries) {
    for (const b of e?.bars || []) {
      if (!b?.date) continue;
      const d = b.date.slice(0, 10);
      if (dayEpoch(d) === null) continue;
      perDay.set(d, (perDay.get(d) || 0) + 1);
    }
  }
  const days = [...perDay.keys()].sort();
  if (!days.length) return { days: [], closures: [], span: null, coverage: 0 };

  const first = dayEpoch(days[0]);
  const last = dayEpoch(days[days.length - 1]);
  const out = [];
  for (let t = first; t <= last; t += DAY_MS) {
    const iso = isoOf(t);
    const count = perDay.get(iso) || 0;
    let kind;
    if (isWeekend(iso)) kind = DAY_KIND.WEEKEND;
    else if (count >= minTradedFor) kind = DAY_KIND.TRADED;
    else kind = neighbourTraded(perDay, t) ? DAY_KIND.CLOSED : DAY_KIND.UNCONFIRMED;
    out.push({ date: iso, weekday: weekdayOf(iso), kind, instruments: count });
  }
  return {
    days: out,
    closures: out.filter((d) => d.kind === DAY_KIND.CLOSED),
    span: { from: days[0], to: days[days.length - 1] },
    coverage: days.length,
  };
}

/**
 * Did the archive record sessions either side of this day?
 *
 * This is what separates "the exchange was shut" from "our data stops here". A
 * silent day flanked by busy ones is a closure; a silent day at the edge of a
 * gap is simply unknown, and saying so is the whole point.
 */
function neighbourTraded(perDay, epoch) {
  const before = [1, 2, 3, 4].some((n) => (perDay.get(isoOf(epoch - n * DAY_MS)) || 0) > 0);
  const after = [1, 2, 3, 4].some((n) => (perDay.get(isoOf(epoch + n * DAY_MS)) || 0) > 0);
  return before && after;
}

/** Was the exchange open on this date, as far as the archive can show? */
export function statusFor(cal, iso) {
  const hit = (cal?.days || []).find((d) => d.date === iso);
  if (hit) return hit;
  // Outside the archive's span nothing is claimed — a weekend is still a
  // weekend, but a weekday is genuinely unknown rather than assumed open.
  return {
    date: iso,
    weekday: weekdayOf(iso),
    kind: isWeekend(iso) ? DAY_KIND.WEEKEND : DAY_KIND.UNCONFIRMED,
    instruments: 0,
    outsideArchive: true,
  };
}

/** Closures grouped by month, for a calendar view. */
export function closuresByMonth(cal) {
  const groups = new Map();
  for (const c of cal?.closures || []) {
    const key = c.date.slice(0, 7);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  }
  return [...groups.entries()].sort().map(([month, days]) => ({ month, days }));
}
