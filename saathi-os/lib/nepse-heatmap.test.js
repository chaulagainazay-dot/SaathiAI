// Sector heatmap — layout geometry and colour bucketing.
//
// A treemap makes a visual claim about proportion, so the tests that matter are
// the geometric ones: rectangles must not overlap, must not escape the container,
// and their AREAS must be proportional to weight. A tile that is merely in roughly
// the right place still lies about how much of the market it is.

import test from "node:test";
import assert from "node:assert/strict";
import {
  squarify, heatmapModel, colourBucket,
  HEATMAP_BUCKET, BUCKET_BREAKS_PCT, UNWEIGHTED_REASON, WEIGHT_FIELDS,
} from "./nepse/heatmap.js";

const row = (symbol, sector, changePct, turnover, volume = null) =>
  ({ symbol, sector, changePct, turnover, volume });

const overlaps = (a, b) =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

test("an absent change is not a flat session", () => {
  for (const empty of [null, undefined, ""]) {
    assert.equal(colourBucket(empty), null, `${empty} must not bucket as NEUTRAL`);
  }
  assert.equal(colourBucket(0), HEATMAP_BUCKET.NEUTRAL);
});

test("colour buckets are symmetric about zero", () => {
  const { moderate, strong } = BUCKET_BREAKS_PCT;
  const pairs = [[0.5, 1], [moderate + 1, moderate + 1], [strong + 1, strong + 1]];
  for (const [up] of pairs) {
    const u = colourBucket(up);
    const d = colourBucket(-up);
    assert.notEqual(u, d, `${up} and -${up} must differ in direction`);
    // Same distance from zero → same intensity tier on both sides. The bare
    // UP/DOWN tier has no prefix, so strip the direction word itself.
    const tier = (b) => b.replace(/UP$/, "").replace(/DOWN$/, "").replace(/_$/, "");
    assert.equal(tier(u), tier(d), `${up}% and -${up}% must sit in matching tiers`);
  }
  assert.equal(colourBucket(strong + 3), HEATMAP_BUCKET.STRONG_UP);
  assert.equal(colourBucket(-(strong + 3)), HEATMAP_BUCKET.STRONG_DOWN);
});

test("a non-numeric change buckets as unknown rather than throwing", () => {
  assert.equal(colourBucket("not a number"), null);
  assert.equal(colourBucket(true), null);
  assert.equal(colourBucket(NaN), null);
  assert.equal(colourBucket(Infinity), null);
});

test("squarified rectangles never overlap and never leave the container", () => {
  const items = [
    { id: "a", weight: 500 }, { id: "b", weight: 250 }, { id: "c", weight: 120 },
    { id: "d", weight: 80 }, { id: "e", weight: 40 }, { id: "f", weight: 10 },
  ];
  const out = squarify(items, 800, 400).filter((r) => r.placed !== false);
  assert.equal(out.length, 6);
  for (const r of out) {
    assert.ok(r.w > 0 && r.h > 0, `${r.id} has no area`);
    assert.ok(r.x >= -1e-6 && r.y >= -1e-6, `${r.id} starts outside the container`);
    assert.ok(r.x + r.w <= 800 + 1e-6, `${r.id} overflows the width`);
    assert.ok(r.y + r.h <= 400 + 1e-6, `${r.id} overflows the height`);
  }
  for (let i = 0; i < out.length; i += 1) {
    for (let j = i + 1; j < out.length; j += 1) {
      assert.ok(!overlaps(out[i], out[j]), `${out[i].id} overlaps ${out[j].id}`);
    }
  }
});

test("tile area is proportional to weight", () => {
  const items = [{ id: "a", weight: 600 }, { id: "b", weight: 300 }, { id: "c", weight: 100 }];
  const W = 600, H = 400;
  const out = squarify(items, W, H);
  const total = 1000;
  for (const r of out) {
    const expected = (r.weight / total) * W * H;
    const actual = r.w * r.h;
    // Proportionality is the claim the picture makes; 1% is generous slack.
    assert.ok(Math.abs(actual - expected) / expected < 0.01,
      `${r.id}: area ${actual.toFixed(1)} vs expected ${expected.toFixed(1)}`);
  }
  // And together they fill the container.
  const covered = out.reduce((a, r) => a + r.w * r.h, 0);
  assert.ok(Math.abs(covered - W * H) / (W * H) < 0.01);
});

test("a single item fills the whole container", () => {
  const [only] = squarify([{ id: "solo", weight: 7 }], 300, 200);
  assert.equal(only.x, 0);
  assert.equal(only.y, 0);
  assert.ok(Math.abs(only.w - 300) < 1e-6);
  assert.ok(Math.abs(only.h - 200) < 1e-6);
});

test("an item with no weight is not laid out as a zero-area tile", () => {
  const out = squarify([{ id: "a", weight: 100 }, { id: "ghost", weight: null }], 400, 300);
  const ghost = out.find((r) => r.id === "ghost");
  assert.equal(ghost.placed, false);
  assert.equal(ghost.w, null);
  // The real tile still gets the full container — the ghost took no space.
  const real = out.find((r) => r.id === "a");
  assert.ok(Math.abs(real.w * real.h - 400 * 300) / (400 * 300) < 0.01);
});

test("a degenerate container places nothing rather than inventing geometry", () => {
  for (const [w, h] of [[0, 100], [100, 0], [-5, 10], [NaN, 10]]) {
    const out = squarify([{ id: "a", weight: 1 }], w, h);
    assert.equal(out[0].placed, false);
    assert.equal(out[0].x, null);
  }
});

test("an empty list lays out nothing without throwing", () => {
  assert.deepEqual(squarify([], 100, 100), []);
  assert.deepEqual(squarify(null, 100, 100), []);
});

test("the model groups by sector and reports each sector's share", () => {
  const m = heatmapModel([
    row("NABIL", "Commercial Bank", 0.28, 11650487),
    row("EBL", "Commercial Bank", 0.15, 12354209),
    row("RSML", "Manufacturing", 5.01, 409088927),
  ]);
  assert.equal(m.sectors.length, 2);
  const banks = m.sectors.find((s) => s.sector === "Commercial Bank");
  const mfg = m.sectors.find((s) => s.sector === "Manufacturing");
  assert.equal(banks.tiles.length, 2);
  assert.ok(mfg.weight > banks.weight);
  const shareSum = m.sectors.reduce((a, s) => a + s.share, 0);
  assert.ok(Math.abs(shareSum - 1) < 1e-6, "sector shares must sum to 1");
});

test("a symbol with no turnover goes to `unweighted`, never a zero-size tile", () => {
  const m = heatmapModel([
    row("NABIL", "Commercial Bank", 0.28, 11650487),
    row("QUIET", "Commercial Bank", 0.00, null),
  ]);
  const sized = m.sectors.flatMap((s) => s.tiles).map((t) => t.symbol);
  assert.ok(!sized.includes("QUIET"), "an unweighable symbol must not be sized");
  assert.equal(m.unweighted.length, 1);
  assert.equal(m.unweighted[0].symbol, "QUIET");
  assert.equal(m.unweighted[0].reason, UNWEIGHTED_REASON.WEIGHT_UNAVAILABLE);
});

test("a reported zero turnover is distinguished from an absent one", () => {
  const m = heatmapModel([
    row("A", "S", 1, 100),
    row("ZERO", "S", 0, 0),
    row("NONE", "S", 0, null),
  ]);
  const reasons = Object.fromEntries(m.unweighted.map((u) => [u.symbol, u.reason]));
  assert.equal(reasons.ZERO, UNWEIGHTED_REASON.WEIGHT_NOT_POSITIVE);
  assert.equal(reasons.NONE, UNWEIGHTED_REASON.WEIGHT_UNAVAILABLE);
});

test("weighting by volume is supported, and an unknown field is refused", () => {
  assert.ok(WEIGHT_FIELDS.includes("volume"));
  const rows = [row("A", "S", 1, null, 500), row("B", "S", -1, null, 250)];
  const byVol = heatmapModel(rows, { weightBy: "volume" });
  assert.equal(byVol.sectors[0].tiles.length, 2);

  const bogus = heatmapModel(rows, { weightBy: "marketCap" });
  assert.equal(bogus.sectors.length, 0);
  assert.equal(bogus.unweighted.length, 2);
  assert.equal(bogus.unweighted[0].reason, UNWEIGHTED_REASON.WEIGHT_FIELD_UNKNOWN);
});

test("a sector whose every member is unweighable says so instead of vanishing", () => {
  const m = heatmapModel([row("A", "Ghosts", 1, null), row("B", "Ghosts", -1, null)]);
  // The sector is KEPT with a status rather than dropped: "we could not size this
  // sector" and "this sector does not exist" are different claims, and a heatmap
  // that silently omits a whole sector misrepresents the market it draws.
  assert.equal(m.sectors.length, 1);
  const ghosts = m.sectors[0];
  assert.equal(ghosts.sector, "Ghosts");
  assert.equal(ghosts.weight, null);          // null, never 0
  assert.equal(ghosts.share, null);
  assert.deepEqual(ghosts.tiles, []);
  assert.equal(ghosts.members, 2);
  assert.equal(ghosts.unsized, 2);
  assert.ok(ghosts.status && ghosts.status !== "OK");
  assert.equal(m.unweighted.length, 2);
});

test("each tile carries its own colour bucket", () => {
  const m = heatmapModel([row("UP", "S", 6.1, 100), row("DOWN", "S", -6.1, 100)]);
  const tiles = Object.fromEntries(m.sectors[0].tiles.map((t) => [t.symbol, t.bucket]));
  assert.equal(tiles.UP, HEATMAP_BUCKET.STRONG_UP);
  assert.equal(tiles.DOWN, HEATMAP_BUCKET.STRONG_DOWN);
});

test("no rows yields an empty model rather than throwing", () => {
  const m = heatmapModel([]);
  assert.deepEqual(m.sectors, []);
  assert.deepEqual(m.unweighted, []);
  assert.deepEqual(heatmapModel(null).sectors, []);
});
