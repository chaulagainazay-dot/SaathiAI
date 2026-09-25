// Demand / supply zones and volume participation. PURE.
//
// A zone is an origin, not an opinion: a tight base of bars that price left in one
// direction with force. Everything reported here is a fact recovered from the bars —
// where the base was, how many bars built it, how hard price left, and how often it
// came back. Nothing is scored, ranked or advised; that judgement belongs upstream.
//
// Three properties are load-bearing:
//
//   1. An unknown field is null, never 0. Number(null) === 0 has already produced a
//      real bug in this codebase (an absent RSI read as maximally oversold); an
//      absent low read as 0 would drop every zone floor to zero and swallow the
//      whole price range. Fields are rejected BEFORE any arithmetic touches them.
//   2. A zone keeps its own arithmetic. `basisBars` and `touches` are separate,
//      recorded facts — a zone tested once and a zone tested five times are
//      different things and are never collapsed into one number here.
//   3. Nothing is approximated. If the bars cannot support an answer the result
//      carries the status that says so, using the same vocabulary as
//      lib/nepse/indicators.js so a caller reads one status language everywhere.
//
// Market-agnostic, like structure.js: NEPSE bars declare per-field trust, exchange
// bars usually do not. No source/dataset stamp is applied for that reason — the
// caller owns provenance; this module owns the maths.

import { INDICATOR_STATUS } from "../nepse/indicators.js";

export const ZONE_KIND = {
  DEMAND: "DEMAND",
  SUPPLY: "SUPPLY",
};

/** Tunables, frozen so a caller cannot mutate the defaults for everybody else. */
export const ZONE_DEFAULTS = Object.freeze({
  minBaseBars: 2,        // one bar is a candle, not a base
  maxBaseBars: 6,        // beyond this it is a range, and the origin is no longer a point
  baseTightPct: 2.5,     // whole base span as % of base mid price
  departureBars: 2,      // bars in the impulse leg, contiguous, straight after the base
  minDeparturePct: 3,    // impulse close measured from the zone edge, as % of base mid
  maxZones: 5,
  staleAfterDays: 7,     // only applied when the caller supplies `asOf`
});

const DAY_MS = 86_400_000;

/**
 * Read one field of a bar, or null.
 *
 * Two traps in one guard. First, null/undefined/"" are rejected before any numeric
 * coercion, because Number(null) === 0 and Number("") === 0 would turn "not reported"
 * into a real observation of zero. Second, `trusted.X === false` is a hard block: the
 * history contract flags fields it caught lying (open outside [low,high], high below
 * low) and a flagged field must not reach the maths. An ABSENT trusted map is not the
 * same claim — it means the caller never declared per-field trust (exchange OHLCV),
 * so it is allowed through rather than silently erasing every non-NEPSE market.
 */
function field(bar, name) {
  if (!bar || typeof bar !== "object") return null;
  if (bar.trusted && bar.trusted[name] === false) return null;
  const v = bar[name];
  if (v === null || v === undefined || v === "") return null;
  // Strings are refused rather than parsed: a parser here would be a second, divergent
  // copy of the one in history.js, and the two would drift.
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Whole calendar days between two ISO dates, or null if either is unparseable. */
function daysBetween(fromIso, toIso) {
  const a = Date.parse(`${String(fromIso)}T00:00:00Z`);
  const b = Date.parse(`${String(toIso)}T00:00:00Z`);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  return Math.round((b - a) / DAY_MS);
}

const round = (n, dp = 4) => +n.toFixed(dp);

/** The envelope every zone query returns — status and observation count included. */
function zoneResult(kind, zones, status, meta = {}) {
  return {
    analysis: "zones",
    kind,
    zones,
    status,
    asOf: meta.asOf ?? null,
    observations: meta.observations ?? 0,
    lookback: meta.lookback ?? null,
    ...(meta.detail ? { detail: meta.detail } : {}),
    ...(meta.note ? { note: meta.note } : {}),
  };
}

// ── zone discovery ────────────────────────────────────────────────────────────────

/**
 * Does bars[start..end] form a tight base, and what are its edges?
 * Every bar must contribute a usable high AND low: a base whose span is measured
 * from bars we cannot see is not a base, it is a guess.
 */
function baseAt(bars, start, end, tightPct) {
  let high = -Infinity;
  let low = Infinity;
  let lastClose = null;
  for (let i = start; i <= end; i += 1) {
    const h = field(bars[i], "high");
    const l = field(bars[i], "low");
    if (h === null || l === null) return null;
    if (h < l) return null; // a flagged-through inverted bar would invert the zone
    if (h > high) high = h;
    if (l < low) low = l;
    lastClose = field(bars[i], "close");
  }
  if (lastClose === null) return null; // the departure is measured against this close
  const mid = (high + low) / 2;
  if (!(mid > 0)) return null; // a non-positive mid makes every percentage meaningless
  const spanPct = ((high - low) / mid) * 100;
  if (spanPct > tightPct) return null;
  return { high, low, mid, lastClose, spanPct: round(spanPct, 3) };
}

/**
 * The impulse leg immediately after the base: `n` contiguous bars whose closes move
 * monotonically in `dir` and finish a real distance beyond the zone edge.
 *
 * Measured close-to-close on purpose. Wicks are the least trustworthy part of this
 * source, and a leg proven by closes cannot be manufactured by one long shadow.
 */
function departureAfter(bars, endIndex, dir, base, { departureBars, minDeparturePct }) {
  const last = endIndex + departureBars;
  if (departureBars < 1 || last >= bars.length) return null;

  let prev = base.lastClose;
  for (let i = endIndex + 1; i <= last; i += 1) {
    const c = field(bars[i], "close");
    if (c === null) return null;
    if ((c - prev) * dir <= 0) return null; // a stall or a pullback is not an impulse
    prev = c;
  }

  // Distance from the far edge of the zone, so a wide base cannot borrow strength
  // from its own thickness.
  const edge = dir > 0 ? base.high : base.low;
  const strengthPct = ((prev - edge) / base.mid) * 100 * dir;
  if (strengthPct < minDeparturePct) return null;
  return { endIndex: last, strengthPct: round(strengthPct, 2), legEndClose: prev };
}

/**
 * Count returns into a formed zone, oldest → newest, starting after the impulse.
 *
 * A stay of several bars inside the zone is ONE touch: touches count re-entries, not
 * bar-days, otherwise a slow drift through a zone would out-score five sharp tests.
 * Bars whose high or low is unusable are counted as unobservable rather than assumed
 * to be outside — an unseen bar is not evidence of an untouched zone.
 */
function countTouches(bars, fromIndex, low, high, dir) {
  let touches = 0;
  let inside = false;
  let unobservable = 0;
  let lastTouchAt = null;
  let broken = false;
  let brokenAt = null;

  for (let i = fromIndex; i < bars.length; i += 1) {
    const bar = bars[i];
    const c = field(bar, "close");
    // A demand zone is broken by a CLOSE below its floor (mirror for supply). Beyond
    // that the zone is history, and later visits are not tests of a live level.
    if (c !== null && ((dir > 0 && c < low) || (dir < 0 && c > high))) {
      broken = true;
      brokenAt = bar?.date ?? null;
      break;
    }
    const h = field(bar, "high");
    const l = field(bar, "low");
    if (h === null || l === null) {
      unobservable += 1;
      continue; // leave `inside` untouched: we cannot claim price left or entered
    }
    const overlaps = l <= high && h >= low;
    if (overlaps && !inside) {
      touches += 1;
      lastTouchAt = bar?.date ?? null;
    } else if (overlaps) {
      lastTouchAt = bar?.date ?? null;
    }
    inside = overlaps;
  }
  return { touches, unobservable, lastTouchAt, broken, brokenAt };
}

function scanZones(bars, dir, options = {}) {
  const kind = dir > 0 ? ZONE_KIND.DEMAND : ZONE_KIND.SUPPLY;
  const o = { ...ZONE_DEFAULTS, ...options };
  const series = Array.isArray(bars) ? bars : [];
  const asOf = series.length ? (series[series.length - 1]?.date ?? null) : null;

  // Zones are built from the day's range. Without a trusted high and low there is no
  // zone to report — close-only bars are refused, never widened into a fake box.
  const rangeBars = series.filter(
    (b) => field(b, "high") !== null && field(b, "low") !== null,
  ).length;

  const minBars = o.minBaseBars + o.departureBars;
  if (rangeBars === 0) {
    return zoneResult(kind, [], INDICATOR_STATUS.FIELD_UNAVAILABLE, {
      asOf, observations: 0, lookback: minBars,
      note: "zones need trusted high and low; a close-only series has no base to measure",
    });
  }
  if (series.length < minBars || rangeBars < o.minBaseBars) {
    return zoneResult(kind, [], INDICATOR_STATUS.INSUFFICIENT_HISTORY, {
      asOf, observations: rangeBars, lookback: minBars,
      note: `needs ${minBars} bars (${o.minBaseBars} base + ${o.departureBars} departure), has ${series.length}`,
    });
  }

  const found = [];
  let i = 0;
  while (i + o.minBaseBars + o.departureBars - 1 < series.length) {
    let hit = null;
    // Longest base first: a 5-bar base that also contains a tight 2-bar window is one
    // zone with five bars behind it, not two overlapping zones.
    for (let n = o.maxBaseBars; n >= o.minBaseBars && !hit; n -= 1) {
      const end = i + n - 1;
      if (end + o.departureBars >= series.length) continue;
      const base = baseAt(series, i, end, o.baseTightPct);
      if (!base) continue;
      const dep = departureAfter(series, end, dir, base, o);
      if (!dep) continue;
      hit = { n, end, base, dep };
    }

    if (!hit) { i += 1; continue; }

    const { touches, unobservable, lastTouchAt, broken, brokenAt } =
      countTouches(series, hit.dep.endIndex + 1, hit.base.low, hit.base.high, dir);

    found.push({
      kind,
      low: round(hit.base.low),
      high: round(hit.base.high),
      formedAt: series[hit.end]?.date ?? null,
      basisBars: hit.n,
      departureStrength: hit.dep.strengthPct,
      departureBars: o.departureBars,
      departureAt: series[hit.dep.endIndex]?.date ?? null,
      baseSpanPct: hit.base.spanPct,
      // touches and basisBars stay side by side, unweighted: how the two combine is
      // the caller's judgement, and flattening them here would destroy the evidence.
      touches,
      lastTouchAt,
      unobservableBars: unobservable,
      barsSinceFormation: series.length - 1 - hit.end,
      broken,
      brokenAt,
      status: INDICATOR_STATUS.VALID,
    });

    // Resume past the impulse: bars inside a leg cannot also be the base of the next
    // zone, and allowing that produced near-duplicate zones one bar apart.
    i = hit.dep.endIndex + 1;
  }

  // Keep the most recent when there are more than asked for — an old zone matters
  // less than a fresh one — but preserve formation order so the caller can read it.
  const truncated = found.length > o.maxZones;
  const zones = truncated ? found.slice(found.length - o.maxZones) : found;

  // DATA_STALE is only claimable when the caller supplies the reference date; this
  // module never reads the clock, so without `asOf` staleness is simply unknown.
  let status = INDICATOR_STATUS.VALID;
  let note;
  const age = o.asOf && asOf ? daysBetween(asOf, o.asOf) : null;
  if (age !== null && age > o.staleAfterDays) {
    status = INDICATOR_STATUS.DATA_STALE;
    note = `last bar ${asOf} is ${age} days before ${o.asOf}`;
    for (const z of zones) z.status = INDICATOR_STATUS.DATA_STALE;
  }

  return zoneResult(kind, zones, status, {
    asOf,
    observations: rangeBars,
    lookback: minBars,
    ...(truncated ? { detail: { discovered: found.length, returned: zones.length } } : {}),
    ...(note ? { note } : {}),
  });
}

/** Drop-base-rally / rally-base-rally origins: bases price left upward. */
export function demandZones(bars, opts = {}) {
  return scanZones(bars, 1, opts);
}

/** Rally-base-drop / drop-base-drop origins: bases price left downward. */
export function supplyZones(bars, opts = {}) {
  return scanZones(bars, -1, opts);
}

/** Both sides in one pass, for callers that want the whole map. */
export function priceZones(bars, opts = {}) {
  return { demand: demandZones(bars, opts), supply: supplyZones(bars, opts) };
}

// ── volume participation ──────────────────────────────────────────────────────────

function volumeResult(value, status, meta = {}) {
  return {
    indicator: "volumeRatio",
    value,
    status,
    asOf: meta.asOf ?? null,
    lookback: meta.lookback ?? null,
    observations: meta.observations ?? 0,
    ...(meta.index !== undefined ? { index: meta.index } : {}),
    ...(meta.detail ? { detail: meta.detail } : {}),
    ...(meta.note ? { note: meta.note } : {}),
  };
}

/**
 * Latest volume against the average of the `period` bars before it, at index `i`.
 *
 * The whole reason this is not a one-liner: an absent volume is not a quiet day. A
 * missing numerator makes the ratio unanswerable (FIELD_UNAVAILABLE), and a missing
 * bar in the baseline shortens the sample rather than being averaged in as zero,
 * which would inflate every ratio computed over a gappy series.
 */
function ratioAt(bars, i, period) {
  const series = Array.isArray(bars) ? bars : [];
  const bar = series[i];
  const asOf = bar?.date ?? null;
  const base = { asOf, lookback: period, index: i };

  if (!bar) {
    return volumeResult(null, INDICATOR_STATUS.INSUFFICIENT_HISTORY, {
      ...base, observations: 0, note: "no bar at this index",
    });
  }
  if (!(period >= 1)) {
    return volumeResult(null, INDICATOR_STATUS.INSUFFICIENT_HISTORY, {
      ...base, observations: 0, note: "period must be at least 1",
    });
  }

  const latest = field(bar, "volume");
  if (latest === null) {
    return volumeResult(null, INDICATOR_STATUS.FIELD_UNAVAILABLE, {
      ...base, observations: 0,
      note: "volume is absent or untrusted on this bar; an unreported volume is not zero volume",
    });
  }

  if (i < period) {
    return volumeResult(null, INDICATOR_STATUS.INSUFFICIENT_HISTORY, {
      ...base, observations: i,
      note: `needs ${period} prior bars, has ${i}`,
      detail: { latest },
    });
  }

  let sum = 0;
  let n = 0;
  for (let j = i - period; j < i; j += 1) {
    const v = field(series[j], "volume");
    if (v === null) continue; // skipped, never counted as a zero observation
    sum += v;
    n += 1;
  }

  if (n === 0) {
    return volumeResult(null, INDICATOR_STATUS.FIELD_UNAVAILABLE, {
      ...base, observations: 0,
      note: "no usable volume in the baseline window",
      detail: { latest },
    });
  }
  if (n < period) {
    return volumeResult(null, INDICATOR_STATUS.INSUFFICIENT_HISTORY, {
      ...base, observations: n,
      note: `needs ${period} baseline volumes, has ${n}; the gap is not averaged over`,
      detail: { latest },
    });
  }

  const average = sum / n;
  if (average === 0) {
    // Every baseline bar genuinely traded zero. The average is known; the RATIO is
    // not — dividing gives Infinity or NaN, and neither is a fact about this stock.
    return volumeResult(null, INDICATOR_STATUS.FIELD_UNAVAILABLE, {
      ...base, observations: n,
      note: "baseline average volume is 0; a ratio against no baseline does not exist",
      detail: { latest, average: 0 },
    });
  }

  return volumeResult(round(latest / average), INDICATOR_STATUS.VALID, {
    ...base, observations: n,
    detail: { latest, average: round(average, 2) },
  });
}

/** Latest volume vs the average of the prior `period` bars. Typed, never a bare number. */
export function volumeRatio(bars, { period = 20 } = {}) {
  const series = Array.isArray(bars) ? bars : [];
  if (!series.length) {
    return volumeResult(null, INDICATOR_STATUS.INSUFFICIENT_HISTORY, {
      lookback: period, observations: 0, note: "no bars",
    });
  }
  return ratioAt(series, series.length - 1, period);
}

/**
 * The same ratio for every bar, index-aligned with `bars`.
 *
 * One entry per input bar, including the ones that cannot be computed — dropping them
 * would silently shift the series against the price series a caller plots it beside.
 */
export function relativeVolumeSeries(bars, { period = 20 } = {}) {
  const series = Array.isArray(bars) ? bars : [];
  return series.map((_, i) => ratioAt(series, i, period));
}
