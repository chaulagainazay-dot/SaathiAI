import test from "node:test";
import assert from "node:assert/strict";

import {
  DAY_KIND, calendar, closuresByMonth, isWeekend, statusFor, tradingDays,
} from "./nepse/holidays.js";
import { MATCH, grouped, search } from "./nepse/search.js";

const bars = (dates) => dates.map((d) => ({ date: d, close: 100 }));
// 2026-09-06 is a Sunday. Sun-Thu trade; Fri/Sat are the weekend.
const WEEK = ["2026-09-06", "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"];

// ── trading calendar ───────────────────────────────────────────────────────
test("Friday and Saturday are the NEPSE weekend", () => {
  assert.equal(isWeekend("2026-09-11"), true);   // Friday
  assert.equal(isWeekend("2026-09-12"), true);   // Saturday
  assert.equal(isWeekend("2026-09-13"), false);  // Sunday trades
});

test("session dates are collected from the archive", () => {
  const days = tradingDays([{ bars: bars(WEEK) }, { bars: bars(["2026-09-06"]) }]);
  assert.deepEqual(days, WEEK);
});

test("a silent weekday flanked by sessions is a closure", () => {
  // Wednesday 2026-09-09 removed: the exchange was shut that day.
  const present = WEEK.filter((d) => d !== "2026-09-09");
  const cal = calendar([{ bars: bars(present) }]);
  const wed = cal.days.find((d) => d.date === "2026-09-09");
  assert.equal(wed.kind, DAY_KIND.CLOSED);
  assert.equal(cal.closures.length, 1);
});

test("a silent weekday at the edge of a data gap is UNCONFIRMED, not a closure", () => {
  // The archive cannot tell "the exchange was shut" from "we have no data".
  // Claiming a holiday here would invent a fact about the market.
  const cal = calendar([{ bars: bars(["2026-09-06", "2026-09-07"]) }]);
  const beyond = statusFor(cal, "2026-09-20");
  assert.equal(beyond.kind, DAY_KIND.UNCONFIRMED);
  assert.equal(beyond.outsideArchive, true);
});

test("weekend days are never reported as closures", () => {
  const cal = calendar([{ bars: bars([...WEEK, "2026-09-13"]) }]);
  for (const c of cal.closures) assert.equal(isWeekend(c.date), false);
});

test("a traded day records how many instruments reported", () => {
  const cal = calendar([{ bars: bars(WEEK) }, { bars: bars(WEEK) }]);
  assert.equal(cal.days.find((d) => d.date === "2026-09-07").instruments, 2);
});

test("an empty archive claims no calendar at all", () => {
  const cal = calendar([]);
  assert.deepEqual(cal.days, []);
  assert.equal(cal.span, null);
});

test("closures group by month for a calendar view", () => {
  const present = WEEK.filter((d) => d !== "2026-09-09");
  const groups = closuresByMonth(calendar([{ bars: bars(present) }]));
  assert.equal(groups[0].month, "2026-09");
});

// ── global search ──────────────────────────────────────────────────────────
const STOCKS = [
  { symbol: "NABIL", name: "Nabil Bank Limited", sector: "Commercial Banks" },
  { symbol: "NABILP", name: "Nabil Bank Promoter Share", sector: "Commercial Banks" },
  { symbol: "NBL", name: "Nepal Bank Limited", sector: "Commercial Banks" },
  { symbol: "UPPER", name: "Upper Tamakoshi Hydropower", sector: "Hydro Power" },
];

test("an exact symbol outranks a longer symbol that merely starts with it", () => {
  // NABIL vs NABILP is the case that decides whether search feels broken.
  const hits = search(STOCKS, "NABIL");
  assert.equal(hits[0].symbol, "NABIL");
  assert.equal(hits[0].match, MATCH.EXACT_SYMBOL);
  assert.equal(hits[1].symbol, "NABILP");
});

test("company names are searchable, not just tickers", () => {
  const hits = search(STOCKS, "upper tamakoshi");
  assert.equal(hits[0].symbol, "UPPER");
  assert.equal(hits[0].match, MATCH.NAME_PREFIX);
});

test("a sector term finds its instruments", () => {
  const hits = search(STOCKS, "hydro");
  assert.ok(hits.some((h) => h.symbol === "UPPER"));
});

test("an empty query returns nothing, not the whole exchange", () => {
  // 586 rows in a dropdown is not a search result.
  for (const q of ["", "   ", null, undefined]) {
    assert.deepEqual(search(STOCKS, q), []);
  }
});

test("search is case and whitespace insensitive", () => {
  assert.equal(search(STOCKS, "  nAbIl  ")[0].symbol, "NABIL");
});

test("results are capped", () => {
  assert.equal(search(STOCKS, "bank", { limit: 2 }).length, 2);
});

test("a term matching nothing returns nothing", () => {
  assert.deepEqual(search(STOCKS, "zzzz"), []);
});

test("grouped results separate instruments from sector hits", () => {
  const g = grouped(STOCKS, "NABIL");
  assert.equal(g[0].label, "Instruments");
});
