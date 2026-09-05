// NEPSE index / sub-index parsing.
//
// The tests that matter: the upstream duplicate-row defect must not make a value
// depend on file ordering, schema drift must not shift a column, and a market-wide
// variant must never be presented as a sector.

import test from "node:test";
import assert from "node:assert/strict";
import {
  parseIndexCsv, pickIndex, indexChanges, sectorIndices, marketIndices,
  indexSeries, indexKey, MAIN_INDEX, INDEX_META, KNOWN_MISSING_SECTORS,
  NEPSE_INDEX_SOURCE,
} from "./nepse/indices.js";

const CURRENT = `timestamp,open,high,low,close,volume,symbol,date_unix,date
1788393600.0,1430.19,1433.23,1426.21,1430.65,316934030.0,Banking_index,1788393600.0,2026-09-03
1788393600.0,5391.71,5439.21,5388.42,5434.72,183062960.0,Development%20Bank_index,1788393600.0,2026-09-03
1788393600.0,2536.98,2544.98,2533.41,2542.77,3465201042.0,NEPSE_index,1788393600.0,2026-09-03
1788393600.0,174.16,174.6,173.7,174.35,0.0,Float_index,1788393600.0,2026-09-03`;

const PRIOR = `timestamp,open,high,low,close,volume,symbol,date_unix,date
1788307200.0,1425.17,1428.55,1416.48,1427.15,310133867.0,Banking_index,1788307200.0,2026-09-02
1788307200.0,5300.0,5400.0,5290.0,5390.0,180000000.0,Development%20Bank_index,1788307200.0,2026-09-02
1788307200.0,2530.0,2545.0,2528.0,2538.0,3400000000.0,NEPSE_index,1788307200.0,2026-09-02`;

test("percent-encoded symbols decode and lose the _index suffix", () => {
  assert.equal(indexKey("Development%20Bank_index"), "Development Bank");
  assert.equal(indexKey("NEPSE_index"), "NEPSE");
  assert.equal(indexKey("Sen.%20Float_index"), "Sen. Float");
});

test("a daily file parses into typed rows carrying its date", () => {
  const { rows, date } = parseIndexCsv(CURRENT);
  assert.equal(date, "2026-09-03");
  assert.equal(rows.length, 4);
  const nepse = pickIndex(rows, MAIN_INDEX);
  assert.equal(nepse.close, 2542.77);
  assert.equal(nepse.volume, 3465201042);
  assert.equal(nepse.kind, "MARKET");
});

test("fields are located by header name, so column order cannot shift a value", () => {
  // The older upstream layout: no timestamp, different order.
  const OLD = `open,high,low,close,volume,symbol,date
2301.95,2338.37,2301.95,2309.72,236887633.1,Others_index,2025-06-16`;
  const { rows } = parseIndexCsv(OLD);
  assert.equal(rows[0].index, "Others");
  assert.equal(rows[0].close, 2309.72);
  assert.equal(rows[0].open, 2301.95);
  assert.equal(rows[0].date, "2025-06-16");
});

test("a duplicated row resolves deterministically to the last one", () => {
  const DUP = `${CURRENT}
1788393600.0,1430.19,1433.23,1426.21,1442.05,316934030.0,Banking_index,1788393600.0,2026-09-03`;
  const { rows } = parseIndexCsv(DUP);
  assert.equal(pickIndex(rows, "Banking").close, 1442.05);
  // and only one Banking row survives
  assert.equal(rows.filter((r) => r.index === "Banking").length, 1);
});

test("a CONFLICTING duplicate is recorded, never silently swallowed", () => {
  const DUP = `${CURRENT}
1788393600.0,1430.19,1433.23,1426.21,1442.05,316934030.0,Banking_index,1788393600.0,2026-09-03`;
  const { conflicts } = parseIndexCsv(DUP);
  assert.equal(conflicts.length, 1);
  assert.equal(conflicts[0].index, "Banking");
  assert.deepEqual(conflicts[0].values, [1430.65, 1442.05]);
});

test("an identical duplicate is not reported as a conflict", () => {
  const DUP = `${CURRENT}
1788393600.0,1430.19,1433.23,1426.21,1430.65,316934030.0,Banking_index,1788393600.0,2026-09-03`;
  assert.equal(parseIndexCsv(DUP).conflicts.length, 0);
});

test("index change is computed against the prior session", () => {
  const cur = parseIndexCsv(CURRENT).rows;
  const prev = parseIndexCsv(PRIOR).rows;
  const ch = indexChanges(cur, prev);
  const nepse = ch.find((r) => r.index === "NEPSE");
  assert.equal(nepse.previousClose, 2538);
  assert.equal(nepse.changePct, 0.19);
  assert.equal(nepse.available, true);
});

test("an index absent from the prior session yields null, not zero", () => {
  const cur = parseIndexCsv(CURRENT).rows;
  const prev = parseIndexCsv(PRIOR).rows;
  const float = indexChanges(cur, prev).find((r) => r.index === "Float");
  assert.equal(float.changePct, null);
  assert.equal(float.change, null);
  assert.equal(float.available, false);
  assert.equal(float.reason, "NO_PRIOR_SESSION");
});

test("market-wide indices are never listed among the sectors", () => {
  const ch = indexChanges(parseIndexCsv(CURRENT).rows, parseIndexCsv(PRIOR).rows);
  const secs = sectorIndices(ch).map((r) => r.index);
  assert.ok(!secs.includes("NEPSE"));
  assert.ok(!secs.includes("Float"));
  assert.deepEqual(secs, ["Development Bank", "Banking"]); // sorted best-first
  assert.deepEqual(marketIndices(ch).map((r) => r.index), ["NEPSE", "Float"]);
});

test("every mapped index declares whether it is a sector or the market", () => {
  for (const [key, meta] of Object.entries(INDEX_META)) {
    assert.ok(["SECTOR", "MARKET"].includes(meta.kind), `${key} has kind ${meta.kind}`);
    assert.ok(meta.label.length > 0);
  }
});

test("a sector this source does not publish is named, not silently absent", () => {
  assert.ok(KNOWN_MISSING_SECTORS.includes("Manufacturing & Processing"));
});

test("a series is ordered oldest to newest regardless of fetch order", () => {
  const days = [
    { date: "2026-09-03", rows: parseIndexCsv(CURRENT).rows },
    { date: "2026-09-02", rows: parseIndexCsv(PRIOR).rows },
  ];
  const s = indexSeries(days, MAIN_INDEX);
  assert.deepEqual(s.map((p) => p.date), ["2026-09-02", "2026-09-03"]);
  assert.equal(s[1].close, 2542.77);
});

test("the source declares its licence and that prices are adjusted", () => {
  assert.equal(NEPSE_INDEX_SOURCE.license, "MIT");
  assert.equal(NEPSE_INDEX_SOURCE.adjustment, "ADJUSTED");
  assert.equal(NEPSE_INDEX_SOURCE.classification, "RESEARCH_ONLY");
});

test("a malformed or empty body yields no rows rather than throwing", () => {
  assert.deepEqual(parseIndexCsv("").rows, []);
  assert.deepEqual(parseIndexCsv("<!doctype html><html>404</html>").rows, []);
  assert.deepEqual(parseIndexCsv("a,b,c\n1,2,3").rows, []);
});
