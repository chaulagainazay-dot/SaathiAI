/**
 * Session context — a real previous close, and the traps around it.
 *
 * The load-bearing assertions: a live price is never paired with the SAME session's
 * close, never with a stale one, and an unavailable previous close stays null rather
 * than producing a confident 0.00%.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {
  previousCloseFor, fiftyTwoWeek, lastSessionActivity, sessionContext, dayChange,
  SESSION_BASIS, MAX_PREV_CLOSE_STALE_DAYS,
} from "./nepse/session.js";

const bar = (date, close, extra = {}) => ({
  date, close, high: close + 1, low: close - 1, volume: 1000, turnover: 1000 * close,
  trusted: { close: true, high: true, low: true, volume: true }, ...extra,
});

test("previous close comes from the bar before the live session", () => {
  const bars = [bar("2026-09-02", 537.5), bar("2026-09-03", 539)];
  const r = previousCloseFor(bars, { asOfDate: "2026-09-04" });
  assert.equal(r.previousClose, 539);
  assert.equal(r.previousCloseDate, "2026-09-03");
  assert.equal(r.basis, SESSION_BASIS.PRIOR_SESSION);
});

test("when the archive already holds today, it steps back — today's close is not the previous one", () => {
  const bars = [bar("2026-09-03", 539), bar("2026-09-04", 545)];
  const r = previousCloseFor(bars, { asOfDate: "2026-09-04" });
  assert.equal(r.previousClose, 539, "must not use today's own close");
  assert.equal(r.previousCloseDate, "2026-09-03");
  assert.equal(r.basis, SESSION_BASIS.STEPPED_BACK);
});

test("a stale archive refuses to supply a previous close", () => {
  const bars = [bar("2026-08-01", 500)];
  const r = previousCloseFor(bars, { asOfDate: "2026-09-04" });
  assert.equal(r.previousClose, null);
  assert.equal(r.basis, SESSION_BASIS.STALE);
  assert.ok(r.staleDays > MAX_PREV_CLOSE_STALE_DAYS);
});

test("no prior bar yields UNAVAILABLE, never a guess", () => {
  assert.equal(previousCloseFor([], { asOfDate: "2026-09-04" }).basis, SESSION_BASIS.UNAVAILABLE);
  const onlyToday = [bar("2026-09-04", 545)];
  assert.equal(previousCloseFor(onlyToday, { asOfDate: "2026-09-04" }).previousClose, null);
});

test("day change is computed from the live price against the derived close", () => {
  const bars = [bar("2026-09-02", 537.5), bar("2026-09-03", 539)];
  const ctx = sessionContext(bars, { asOfDate: "2026-09-04" });
  const d = dayChange(545, ctx);
  assert.equal(d.available, true);
  assert.equal(d.change, 6);
  assert.equal(d.changePct, 1.11);
  assert.equal(d.against, "2026-09-03");
});

test("an unavailable previous close yields null, never 0.00%", () => {
  const ctx = sessionContext([bar("2026-08-01", 500)], { asOfDate: "2026-09-04" });
  const d = dayChange(545, ctx);
  assert.equal(d.available, false);
  assert.equal(d.changePct, null);
  assert.equal(d.change, null);
});

test("52-week range uses trusted highs/lows and reports its window", () => {
  const bars = Array.from({ length: 260 }, (_, i) => bar(`2026-01-01`, 100 + (i % 50)));
  const r = fiftyTwoWeek(bars);
  assert.equal(r.basis, "FULL_WINDOW");
  assert.ok(r.high > r.low);
  const short = fiftyTwoWeek([bar("2026-09-03", 100)]);
  assert.equal(short.basis, "INSUFFICIENT_HISTORY");
  assert.equal(short.high, null);
});

test("52-week range falls back to close when the range is untrusted, never invents one", () => {
  const bars = Array.from({ length: 30 }, () =>
    ({ date: "2026-09-03", close: 100, high: 999, low: 1, trusted: { close: true, high: false, low: false } }));
  const r = fiftyTwoWeek(bars);
  assert.equal(r.high, 100, "untrusted high must not become the 52w high");
  assert.equal(r.low, 100);
});

test("average traded price is derived only when both volume and turnover exist", () => {
  const a = lastSessionActivity([bar("2026-09-03", 500, { volume: 100, turnover: 50000 })]);
  assert.equal(a.averagePrice, 500);
  const b = lastSessionActivity([bar("2026-09-03", 500, { volume: null, turnover: 50000 })]);
  assert.equal(b.averagePrice, null, "never approximated from close");
});

test("session context carries provenance for every derived field", () => {
  const ctx = sessionContext([bar("2026-09-02", 537.5), bar("2026-09-03", 539)], { asOfDate: "2026-09-04" });
  for (const k of ["previousCloseDate", "previousCloseBasis", "fiftyTwoWeekBasis", "lastSessionDate"]) {
    assert.ok(k in ctx, `missing provenance field ${k}`);
  }
});

test("a day change is refused when the PRICE is not live", async () => {
  const { liveDayChange } = await import("./nepse/use-indicators.js");
  const entry = { session: { previousClose: 539, previousCloseDate: "2026-09-03" } };
  const live = liveDayChange(539, entry, true);
  assert.equal(live.available, true);
  // snapshot price + real previous close = a confidently wrong percentage
  const stale = liveDayChange(512, entry, false);
  assert.equal(stale.available, false);
  assert.equal(stale.reason, "PRICE_NOT_LIVE");
  assert.equal(stale.changePct, null);
});
