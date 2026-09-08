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

// ── NEPSE-COMPLETE-1: brokers, IPO pipeline, sector map ──────────────────────

import {
  parseTopBrokers, parseExistingIssues, parseSectorMap, canonicalSector,
  CANONICAL_SECTORS,
} from "./extract/sharesansar.js";

const BROKER_HEADERS = SHARESANSAR_PAGES.topBrokers.headers.join("\n");
const BROKER_ROWS = [
  "1\t58\tNaasa Securities Co. Ltd.\t248,671,555.77\t205,792,999.40\t454,464,555.17\t42,878,556.37\t33,631,081.00",
  "2\t49\tOnline Securities Limited\t141,687,670.30\t116,250,257.40\t257,937,927.70\t25,437,412.90\t10,145,754.40",
].join("\n");

const IPO_HEADERS = SHARESANSAR_PAGES.existingIssues.headers.join("\n");
const IPO_ROWS = [
  "1\tBENI\tBeni Hydropower Project Limited\t863,200.00\t100.00\t2026-09-07\t2026-09-10\t2026-09-21\t\tNMB Capital Limited\tComing Soon\t",
  "2\tMEPDL\tMount Everest Power Development Limited\t1,427,600.00\t100.00\t2026-06-17\t2026-06-22\t2026-07-01\t2026-08-11\tNIMB Ace Capital Limited\tClosed\t",
].join("\n");

test("broker rankings parse with numbers, names and session totals", () => {
  const r = parseTopBrokers(BROKER_ROWS, BROKER_HEADERS, { title: "Top Brokers" });
  assert.equal(r.ok, true);
  assert.equal(r.rows.length, 2);
  assert.equal(r.rows[0].code, 58);
  assert.equal(r.rows[0].name, "Naasa Securities Co. Ltd.");
  assert.equal(r.rows[0].buyAmount, 248671555.77);
  assert.equal(r.rows[1].code, 49);
  assert.equal(r.rows[1].name, "Online Securities Limited");
});

test("a broker row without a number or a name is rejected", () => {
  const bad = "3\t\tNo Number Ltd\t1\t1\t2\t0\t0\n4\t77\t\t1\t1\t2\t0\t0";
  const r = parseTopBrokers(bad, BROKER_HEADERS, {});
  assert.equal(r.rows.length, 0);
  assert.equal(r.rejected.length, 2);
});

test("brokers refuse a changed layout", () => {
  const moved = [...SHARESANSAR_PAGES.topBrokers.headers];
  [moved[3], moved[4]] = [moved[4], moved[3]];
  assert.equal(parseTopBrokers(BROKER_ROWS, moved.join("\n"), {}).reason, "COLUMN_MOVED");
});

test("the IPO pipeline parses, leaving unset dates null", () => {
  const r = parseExistingIssues(IPO_ROWS, IPO_HEADERS, { title: "Existing Issues" });
  assert.equal(r.ok, true);
  const beni = r.rows[0];
  assert.equal(beni.symbol, "BENI");
  assert.equal(beni.units, 863200);
  assert.equal(beni.pricePerUnit, 100);
  assert.equal(beni.opensOn, "2026-09-07");
  assert.equal(beni.listedOn, null);      // not yet listed — null, not a guess
  assert.equal(beni.issueManager, "NMB Capital Limited");
  assert.equal(beni.status, "Coming Soon");
  assert.equal(r.rows[1].listedOn, "2026-08-11");
});

test("only headings in the known vocabulary become sectors", () => {
  assert.equal(canonicalSector("Commercial Bank"), "Commercial Bank");
  assert.equal(canonicalSector("commercial  bank"), "Commercial Bank");
  assert.equal(canonicalSector("NEPSE  Calendar"), null);
  assert.equal(canonicalSector("Some New Sector"), null);
  assert.ok(CANONICAL_SECTORS.includes("Manufacturing and Processing"));
});

const secBlock = (rows) =>
  ["S.No\tSymbol\tOpen\tHigh\tLow\tLTP\tPrev. Closing\tVolume\tPts Change\t% Change", ...rows].join("\n");
const TWO_SECTORS = ["Commercial Bank", "Hydropower", "NEPSE  Calendar"].join("\n");
const FOUR_BLOCKS = [
  secBlock(["1\tNABIL\t1\t1\t1\t539.00\t537.50\t100\t1.5\t0.28"]),
  secBlock(["1\tEBL\t1\t1\t1\t716.10\t715.00\t100\t1.1\t0.15"]),
  secBlock(["1\tCKHL\t1\t1\t1\t615.00\t566.60\t100\t48.4\t8.56"]),
  secBlock(["1\tRHPC\t1\t1\t1\t840.00\t776.00\t100\t64\t8.25"]),
].join("\n\n");

test("sector map pairs headings to blocks by order and drops non-sector headings", () => {
  const r = parseSectorMap(TWO_SECTORS, FOUR_BLOCKS, { observedOn: "2026-09-03" });
  assert.equal(r.ok, true);
  assert.deepEqual(r.sectors, ["Commercial Bank", "Hydropower"]);
  assert.deepEqual(r.dropped, ["NEPSE  Calendar"]);
  assert.equal(r.map.NABIL.sector, "Commercial Bank");
  assert.equal(r.map.EBL.sector, "Commercial Bank");
  assert.equal(r.map.CKHL.sector, "Hydropower");
  assert.equal(r.map.RHPC.sector, "Hydropower");
  assert.equal(r.map.NABIL.observedOn, "2026-09-03");
  assert.equal(r.covered, 4);
});

test("a block count that does not match the sectors is REFUSED, not mislabelled", () => {
  const threeBlocks = FOUR_BLOCKS.split("\n\n").slice(0, 3).join("\n\n");
  const r = parseSectorMap(TWO_SECTORS, threeBlocks, {});
  assert.equal(r.ok, false);
  assert.equal(r.reason, "PAIRING_MISMATCH");
  assert.deepEqual(r.map, {});
  assert.ok(r.detail.includes("4 blocks") || r.detail.includes("found 3"));
});

test("no recognised heading means no map, rather than an unlabelled one", () => {
  const r = parseSectorMap("NEPSE  Calendar\nAnalysis", FOUR_BLOCKS, {});
  assert.equal(r.ok, false);
  assert.equal(r.reason, "NO_SECTORS");
});

test("an error page yields no sector map", () => {
  const r = parseSectorMap(TWO_SECTORS, FOUR_BLOCKS, { title: "400 - Page Not Found" });
  assert.equal(r.ok, false);
  assert.equal(r.reason, "ERROR_PAGE");
});

test("a header row inside a block never becomes a symbol", () => {
  const r = parseSectorMap(TWO_SECTORS, FOUR_BLOCKS, {});
  assert.equal(r.map.SYMBOL, undefined);
  assert.equal(Object.keys(r.map).length, 4);
});
