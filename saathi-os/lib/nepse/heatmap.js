// Sector heatmap layout — geometry and colour bucketing only. PURE.
//
// This module answers one question: given today's session rows, what rectangles
// does the UI draw and what colour is each one. It draws nothing itself.
//
// The honesty constraints, all of them about SIZE:
//
//   - A tile's area IS a claim about how much a symbol traded. A symbol whose
//     weight field is null has made no such claim. Coercing it to 0 would give it
//     a zero-area rectangle — visually identical to "not listed" — so the symbol
//     would silently disappear from a market map that claims to show the market.
//     Those symbols go into `unweighted` with a reason, so the UI can say how many
//     tiles it could not size instead of pretending they were not there.
//   - A sector whose members are all unweighable reports FIELD_UNAVAILABLE. An
//     empty sector rectangle would read as "this sector did not trade", which is
//     a statement about the market rather than about our data.
//   - NEUTRAL means exactly flat. A near-flat move is SLIGHT_UP/SLIGHT_DOWN — it
//     has a direction, and washing it to grey throws that direction away.
//   - An unknown change has no colour at all (null bucket), never the flat grey.

import { INDICATOR_STATUS } from "./indicators.js";
import { UNCLASSIFIED } from "./market.js";

/** Fields a tile may be sized by. Both are reported per session by market.js. */
export const WEIGHT_FIELDS = Object.freeze(["turnover", "volume"]);

/** Why a symbol could not be sized. Never merged into a zero-weight tile. */
export const UNWEIGHTED_REASON = {
  WEIGHT_UNAVAILABLE: "WEIGHT_UNAVAILABLE", // field absent/null/blank — no claim made
  WEIGHT_NOT_POSITIVE: "WEIGHT_NOT_POSITIVE", // reported, but zero area is unrenderable
  WEIGHT_FIELD_UNKNOWN: "WEIGHT_FIELD_UNKNOWN", // caller asked to size by a field we do not have
};

/**
 * Symmetric colour buckets. The break points are the same distance either side of
 * zero, so a −4% tile is exactly as dark as a +4% one; an asymmetric scale would
 * make a falling market look calmer (or louder) than a rising one of equal size.
 */
export const HEATMAP_BUCKET = {
  STRONG_DOWN: "STRONG_DOWN",
  DOWN: "DOWN",
  SLIGHT_DOWN: "SLIGHT_DOWN",
  NEUTRAL: "NEUTRAL",
  SLIGHT_UP: "SLIGHT_UP",
  UP: "UP",
  STRONG_UP: "STRONG_UP",
};

/**
 * Break points in percent, applied to |changePct|.
 * `strong` sits at half the ±10% daily circuit, so a genuinely circuit-limited day
 * lands in the top bucket rather than off the end of a scale built for quiet days.
 */
export const BUCKET_BREAKS_PCT = Object.freeze({ moderate: 2, strong: 5 });

/**
 * Bucket for one change, or null when the change is unknown.
 * Rejects null/undefined/"" BEFORE any coercion: Number(null) === 0 would read an
 * absent change as a perfectly flat session, which is the one thing it is not.
 */
export function colourBucket(changePct) {
  if (changePct === null || changePct === undefined || changePct === "") return null;
  if (typeof changePct === "boolean") return null;
  const n = typeof changePct === "number" ? changePct : Number(String(changePct).trim());
  if (!Number.isFinite(n)) return null;

  if (n === 0) return HEATMAP_BUCKET.NEUTRAL; // NEUTRAL is exactly flat, nothing else
  const mag = Math.abs(n);
  const up = n > 0;
  if (mag >= BUCKET_BREAKS_PCT.strong) return up ? HEATMAP_BUCKET.STRONG_UP : HEATMAP_BUCKET.STRONG_DOWN;
  if (mag >= BUCKET_BREAKS_PCT.moderate) return up ? HEATMAP_BUCKET.UP : HEATMAP_BUCKET.DOWN;
  return up ? HEATMAP_BUCKET.SLIGHT_UP : HEATMAP_BUCKET.SLIGHT_DOWN;
}

/** A weight is usable only if it is a real, finite, strictly positive number. */
function readWeight(row, field) {
  const raw = row?.[field];
  if (raw === null || raw === undefined || raw === "") {
    return { weight: null, reason: UNWEIGHTED_REASON.WEIGHT_UNAVAILABLE };
  }
  if (typeof raw === "boolean") return { weight: null, reason: UNWEIGHTED_REASON.WEIGHT_UNAVAILABLE };
  const n = typeof raw === "number" ? raw : Number(String(raw).trim());
  if (!Number.isFinite(n)) return { weight: null, reason: UNWEIGHTED_REASON.WEIGHT_UNAVAILABLE };
  // A reported zero is a fact, but a zero-area tile is indistinguishable from an
  // absent one — so it is declared unsized rather than drawn as nothing.
  if (n <= 0) return { weight: null, reason: UNWEIGHTED_REASON.WEIGHT_NOT_POSITIVE };
  return { weight: n, reason: null };
}

// ── squarified treemap ───────────────────────────────────────────────────────────

/**
 * Worst (largest) aspect ratio in a candidate row laid along `side`.
 * Bruls/Huizing/van Wijk: with the row's areas summing to `sum` across a strip of
 * length `side`, the extreme tiles set the ratio.
 */
function worstRatio(row, side) {
  let sum = 0;
  let max = -Infinity;
  let min = Infinity;
  for (const it of row) {
    sum += it.area;
    if (it.area > max) max = it.area;
    if (it.area < min) min = it.area;
  }
  if (sum <= 0 || side <= 0) return Infinity;
  const s2 = side * side;
  const sum2 = sum * sum;
  return Math.max((s2 * max) / sum2, sum2 / (s2 * min));
}

/** Lay one finished row along the shorter side of `rect`; return the leftover rect. */
function layoutRow(row, rect) {
  const total = row.reduce((a, b) => a + b.area, 0);
  const placed = [];
  if (rect.w <= rect.h) {
    const rowH = total / rect.w;
    let x = rect.x;
    for (const it of row) {
      const w = it.area / rowH;
      placed.push({ ...it.item, x, y: rect.y, w, h: rowH, placed: true });
      x += w;
    }
    return { placed, rest: { x: rect.x, y: rect.y + rowH, w: rect.w, h: rect.h - rowH } };
  }
  const rowW = total / rect.h;
  let y = rect.y;
  for (const it of row) {
    const h = it.area / rowW;
    placed.push({ ...it.item, x: rect.x, y, w: rowW, h, placed: true });
    y += h;
  }
  return { placed, rest: { x: rect.x + rowW, y: rect.y, w: rect.w - rowW, h: rect.h } };
}

/**
 * Squarified treemap layout.
 *
 * @param {Array} items  objects carrying a positive numeric `weight`
 * @param {number} width  container width
 * @param {number} height container height
 * @returns {Array} the input objects, largest first, each with {x,y,w,h,placed}.
 *
 * Items whose weight is not a usable positive number come back LAST with
 * x/y/w/h = null and placed:false. They are not given a zero-size rectangle at the
 * origin: a 0×0 tile at (0,0) is invisible, overlaps whatever is drawn there, and
 * would let a caller believe every item was laid out.
 *
 * Total placed area equals width×height exactly (up to float error), so a caller
 * can verify proportionality rather than trust it.
 */
export function squarify(items, width, height) {
  const list = Array.isArray(items) ? items : [];
  const w = Number(width);
  const h = Number(height);
  // A non-positive container has no interior; laying anything out in it would
  // produce rectangles that are, at best, degenerate lies about area.
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) {
    return list.map((item) => ({ ...item, x: null, y: null, w: null, h: null, placed: false }));
  }

  const sized = [];
  const unsized = [];
  for (const item of list) {
    const { weight } = readWeight(item, "weight");
    if (weight === null) unsized.push({ ...item, x: null, y: null, w: null, h: null, placed: false });
    else sized.push({ item, weight });
  }
  if (!sized.length) return unsized;

  sized.sort((a, b) => b.weight - a.weight);
  const totalWeight = sized.reduce((a, s) => a + s.weight, 0);
  const scale = (w * h) / totalWeight;
  const queue = sized.map((s) => ({ item: s.item, area: s.weight * scale }));

  const out = [];
  let rect = { x: 0, y: 0, w, h };
  let row = [];
  let i = 0;
  while (i < queue.length) {
    const side = Math.min(rect.w, rect.h);
    const next = queue[i];
    // Grow the row while it makes the worst tile squarer; otherwise close it.
    if (row.length === 0 || worstRatio([...row, next], side) <= worstRatio(row, side)) {
      row.push(next);
      i += 1;
      continue;
    }
    const done = layoutRow(row, rect);
    out.push(...done.placed);
    rect = done.rest;
    row = [];
  }
  if (row.length) out.push(...layoutRow(row, rect).placed);

  return [...out, ...unsized];
}

// ── the model the heatmap component consumes ─────────────────────────────────────

/**
 * Group session rows into sector blocks sized by turnover (or volume).
 *
 * @param {Array} rows   rows from market.js sessionChanges()
 * @param {{weightBy?: string}} opts
 * @returns {{sectors: Array, unweighted: Array, status: string, ...}}
 *
 * `share` is relative to its container: a sector's share is of total market weight,
 * a tile's share is of its own sector — that is what each level's squarify() call
 * consumes. `overallShare` is kept alongside for labelling a tile against the whole
 * market, so the two can never be confused for one another.
 */
export function heatmapModel(rows, { weightBy = "turnover" } = {}) {
  const list = Array.isArray(rows) ? rows : [];

  if (!WEIGHT_FIELDS.includes(weightBy)) {
    // Sizing by a field we do not carry cannot be approximated by another field —
    // that would silently answer a different question than the caller asked.
    return {
      weightBy,
      sectors: [],
      unweighted: list.map((r) => ({
        symbol: r?.symbol ?? null,
        sector: r?.sector || UNCLASSIFIED,
        reason: UNWEIGHTED_REASON.WEIGHT_FIELD_UNKNOWN,
      })),
      totalWeight: null,
      observations: 0,
      status: INDICATOR_STATUS.FIELD_UNAVAILABLE,
      note: `unknown weight field "${weightBy}" — sizeable fields are ${WEIGHT_FIELDS.join(", ")}`,
    };
  }

  const bySector = new Map();
  const unweighted = [];
  for (const r of list) {
    const sector = r?.sector || UNCLASSIFIED;
    if (!bySector.has(sector)) bySector.set(sector, { members: 0, tiles: [], unsized: 0 });
    const bucketOfSector = bySector.get(sector);
    bucketOfSector.members += 1;

    const { weight, reason } = readWeight(r, weightBy);
    if (weight === null) {
      bucketOfSector.unsized += 1;
      unweighted.push({ symbol: r?.symbol ?? null, sector, reason });
      continue;
    }
    bucketOfSector.tiles.push({
      symbol: r?.symbol ?? null,
      changePct: typeof r?.changePct === "number" && Number.isFinite(r.changePct) ? r.changePct : null,
      weight,
      // An unknown change gets no colour; the tile is still sized, because its size
      // is a fact about turnover and does not depend on the change being known.
      bucket: colourBucket(r?.changePct),
    });
  }

  const sectors = [];
  let totalWeight = 0;
  for (const [, b] of bySector) {
    for (const t of b.tiles) totalWeight += t.weight;
  }

  for (const [sector, b] of bySector) {
    if (!b.tiles.length) {
      // Says "we could not size this sector", never draws it as an empty box that
      // would read as "this sector did not trade".
      sectors.push({
        sector,
        weight: null,
        share: null,
        members: b.members,
        sized: 0,
        unsized: b.unsized,
        tiles: [],
        status: INDICATOR_STATUS.FIELD_UNAVAILABLE,
        note: `no member reported ${weightBy} — sector cannot be sized`,
      });
      continue;
    }
    const weight = b.tiles.reduce((a, t) => a + t.weight, 0);
    const tiles = [...b.tiles]
      .sort((x, y) => y.weight - x.weight)
      .map((t) => ({
        ...t,
        share: t.weight / weight,
        overallShare: totalWeight > 0 ? t.weight / totalWeight : null,
      }));
    sectors.push({
      sector,
      weight,
      share: totalWeight > 0 ? weight / totalWeight : null,
      members: b.members,
      sized: tiles.length,
      unsized: b.unsized,
      tiles,
      status: INDICATOR_STATUS.VALID,
    });
  }

  // Sizeable sectors first, largest first; unsizeable ones keep a stable tail so
  // the UI can list them under the map rather than dropping them.
  sectors.sort((a, b) => {
    if ((a.weight === null) !== (b.weight === null)) return a.weight === null ? 1 : -1;
    if (a.weight === null) return a.sector < b.sector ? -1 : a.sector > b.sector ? 1 : 0;
    return b.weight - a.weight;
  });

  const observations = sectors.reduce((a, s) => a + s.sized, 0);
  const status = list.length === 0
    ? INDICATOR_STATUS.INSUFFICIENT_HISTORY
    : observations === 0
      ? INDICATOR_STATUS.FIELD_UNAVAILABLE
      : INDICATOR_STATUS.VALID;

  return {
    weightBy,
    sectors,
    unweighted,
    totalWeight: observations > 0 ? totalWeight : null,
    observations,
    status,
    ...(status === INDICATOR_STATUS.INSUFFICIENT_HISTORY
      ? { note: "no session rows to lay out" } : {}),
    ...(status === INDICATOR_STATUS.FIELD_UNAVAILABLE
      ? { note: `no row reported ${weightBy} — nothing can be sized` } : {}),
  };
}
