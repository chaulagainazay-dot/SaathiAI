// Typed ShareSansar extractors.
//
// The tests that carry the weight are the refusals. Positional table scraping
// fails silently when a site inserts or moves a column — the parser keeps
// returning confident, wrong numbers — so most of what follows checks that a
// changed layout produces NO rows and a named reason.

import test from "node:test";
import assert from "node:assert/strict";
import {
  parseTodayPrices, parseProposedDividends, verifyHeaders, splitRows, splitHeaders,
  parseNum, parseIsoDate, looksLikeErrorPage, SHARESANSAR_PAGES, SHARESANSAR_SOURCE,
} from "./extract/sharesansar.js";

const PRICE_HEADERS = SHARESANSAR_PAGES.todayPrices.headers.join("\n");
const PRICE_ROWS = [
  "1\tACLBSL\t35.65\t900.00\t900.00\t880.00\t894.90\t894.90\t0.00\t0.00\t884.30\t804.00\t894.80\t710,976.00\t18\t0.10\t20.00\t0.01\t2.27\t1.18\t953.50\t956.47\t1,095.00\t827.90",
  "2\tADBL\t28.90\t299.00\t299.80\t296.00\t297.00\t297.00\t0.00\t0.00\t297.64\t9,898.00\t296.60\t2,946,015.50\t93\t0.40\t3.80\t0.13\t1.28\t-0.21\t311.29\t306.90\t340.00\t285.20",
].join("\n");

const DIV_HEADERS = SHARESANSAR_PAGES.proposedDividends.headers.join("\n");
const DIV_ROWS = [
  "1\tNBF2\tNabil Balanced Fund - 2\t\t3.5\t3.5\t2026-09-04\t2026-09-23\t\t\t2082/2083\t9.80\t2026-09-03",
  "2\tNBF3\tNabil Balanced Fund III\t\t2.5\t2.5\t2026-09-04\t2026-09-23\t\t\t2082/2083\t9.54\t2026-09-03",
].join("\n");

test("rows split on newlines and cells on tabs", () => {
  const rows = splitRows("a\tb\tc\nd\te\tf");
  assert.deepEqual(rows, [["a", "b", "c"], ["d", "e", "f"]]);
});

test("numbers lose their thousands separators; absent stays null, never zero", () => {
  assert.equal(parseNum("2,946,015.50"), 2946015.5);
  assert.equal(parseNum("18"), 18);
  for (const empty of ["", "-", "--", "N/A", null, undefined]) {
    assert.equal(parseNum(empty), null, `${empty} must be null, not 0`);
  }
});

test("only ISO dates are dates; Bikram Sambat is not silently converted", () => {
  assert.equal(parseIsoDate("2026-09-23"), "2026-09-23");
  assert.equal(parseIsoDate("2083-06-07"), "2083-06-07"); // shape-valid, kept verbatim
  assert.equal(parseIsoDate("2082/2083"), null);
  assert.equal(parseIsoDate(""), null);
});

test("a soft 404 is recognised from its title, not inferred from empty rows", () => {
  assert.equal(looksLikeErrorPage("400 - Page Not Found - || ShareSansar ||"), true);
  assert.equal(looksLikeErrorPage("Nabil Bank Limited - || ShareSansar ||"), false);
});

test("today prices parse with every field the page carries", () => {
  const r = parseTodayPrices(PRICE_ROWS, PRICE_HEADERS, { title: "Today Share Price" });
  assert.equal(r.ok, true);
  assert.equal(r.rows.length, 2);
  const a = r.rows[0];
  assert.equal(a.symbol, "ACLBSL");
  assert.equal(a.open, 900);
  assert.equal(a.close, 894.9);
  assert.equal(a.previousClose, 894.8);
  assert.equal(a.vwap, 884.3);
  assert.equal(a.volume, 804);
  assert.equal(a.turnover, 710976);
  assert.equal(a.transactions, 18);
  assert.equal(a.fiftyTwoWeekHigh, 1095);
  assert.equal(a.fiftyTwoWeekLow, 827.9);
});

test("day change is computed against the page's own previous close", () => {
  const r = parseTodayPrices(PRICE_ROWS, PRICE_HEADERS, {});
  assert.equal(r.rows[0].change, 0.1);
  assert.equal(r.rows[0].changePct, 0.01);
  assert.equal(r.rows[1].change, 0.4);
});

test("a moved column is REFUSED — no rows, and the column is named", () => {
  const moved = [...SHARESANSAR_PAGES.todayPrices.headers];
  [moved[6], moved[7]] = [moved[7], moved[6]];   // Close and LTP swap places
  const r = parseTodayPrices(PRICE_ROWS, moved.join("\n"), {});
  assert.equal(r.ok, false);
  assert.equal(r.reason, "COLUMN_MOVED");
  assert.equal(r.rows.length, 0);
  assert.ok(r.detail.includes("column 7"));
});

test("an inserted column is refused rather than shifting every field by one", () => {
  const grown = [...SHARESANSAR_PAGES.todayPrices.headers];
  grown.splice(3, 0, "New Column");
  const r = parseTodayPrices(PRICE_ROWS, grown.join("\n"), {});
  assert.equal(r.ok, false);
  assert.equal(r.reason, "COLUMN_COUNT_CHANGED");
  assert.equal(r.rows.length, 0);
});

test("an error page is refused even when the row text would parse", () => {
  const r = parseTodayPrices(PRICE_ROWS, PRICE_HEADERS, { title: "400 - Page Not Found" });
  assert.equal(r.ok, false);
  assert.equal(r.reason, "ERROR_PAGE");
  assert.equal(r.rows.length, 0);
});

test("a missing header row is refused rather than parsed positionally on trust", () => {
  const r = parseTodayPrices(PRICE_ROWS, "", {});
  assert.equal(r.ok, false);
  assert.equal(r.reason, "NO_HEADERS");
});

test("header comparison ignores case, spacing and punctuation but not order", () => {
  assert.equal(verifyHeaders(["S.No", "Symbol"], ["s no", "symbol"]).ok, true);
  assert.equal(verifyHeaders(["Symbol", "S.No"], ["S.No", "Symbol"]).reason, "COLUMN_MOVED");
});

test("a row with the wrong number of cells is rejected, not padded", () => {
  const short = "1\tACLBSL\t35.65\t900.00";
  const r = parseTodayPrices(`${PRICE_ROWS}\n${short}`, PRICE_HEADERS, {});
  assert.equal(r.rows.length, 2);
  assert.equal(r.rejected[0].reason, "CELL_COUNT");
});

test("proposed dividends parse, keeping the Bikram Sambat year verbatim", () => {
  const r = parseProposedDividends(DIV_ROWS, DIV_HEADERS, { title: "Proposed Dividend" });
  assert.equal(r.ok, true);
  assert.equal(r.rows.length, 2);
  const d = r.rows[0];
  assert.equal(d.symbol, "NBF2");
  assert.equal(d.cashPct, 3.5);
  assert.equal(d.bonusPct, null);       // blank cell, not a zero bonus
  assert.equal(d.totalPct, 3.5);
  assert.equal(d.bookClosureOn, "2026-09-23");
  assert.equal(d.fiscalYearBs, "2082/2083");
  assert.equal(d.distributionOn, null);
});

test("a dividend row with neither bonus nor cash is rejected as saying nothing", () => {
  const blank = "3\tXYZ\tSome Co\t\t\t\t2026-09-04\t2026-09-23\t\t\t2082/2083\t10.00\t2026-09-03";
  const r = parseProposedDividends(blank, DIV_HEADERS, {});
  assert.equal(r.rows.length, 0);
  assert.equal(r.rejected[0].reason, "NO_DIVIDEND");
});

test("dividends refuse a changed layout too", () => {
  const moved = [...SHARESANSAR_PAGES.proposedDividends.headers];
  [moved[3], moved[4]] = [moved[4], moved[3]];   // Bonus and Cash swap
  const r = parseProposedDividends(DIV_ROWS, moved.join("\n"), {});
  assert.equal(r.ok, false);
  assert.equal(r.reason, "COLUMN_MOVED");
});

test("the source declares it is a scraped page, not a licensed API", () => {
  assert.equal(SHARESANSAR_SOURCE.access, "SCRAPED_PUBLIC_PAGE");
  assert.equal(SHARESANSAR_SOURCE.classification, "RESEARCH_ONLY");
  assert.equal(SHARESANSAR_SOURCE.adjustment, "UNKNOWN");
});

test("headers arriving one-per-line or tab-joined both split correctly", () => {
  assert.deepEqual(splitHeaders("A\nB\nC"), ["A", "B", "C"]);
  assert.deepEqual(splitHeaders("A\tB\tC"), ["A", "B", "C"]);
});
