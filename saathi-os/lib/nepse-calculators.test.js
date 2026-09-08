import test from "node:test";
import assert from "node:assert/strict";

import {
  EQUITY_SCHEDULE_2080, INVESTOR, SCHEDULE_STATUS,
  brokerCommission, cgtRate, scheduleFor, transactionCosts,
} from "./nepse/fees.js";
import { capitalGains, rightShareAdjustment, sip, wacc } from "./nepse/calculators.js";
import {
  FY_STATUS, filterByFiscalYear, fiscalYearsIn, groupByFiscalYear,
  adToBs, parseFiscalYear, sortFiscalYears,
} from "./nepse/bs.js";
import { canAdd, compareMatrix, compareSeries, normalize } from "./nepse/compare.js";

const near = (a, b, eps = 0.01) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

// ══ fees ═══════════════════════════════════════════════════════════════════
test("commission is tiered on the WHOLE amount, not marginally", () => {
  // The trap: income-tax intuition says 0.36% of the first 50k plus 0.33% of
  // the rest. NEPSE brokerage does not work that way.
  near(brokerCommission(600_000), 600_000 * 0.0031);
  assert.notEqual(brokerCommission(600_000), 50_000 * 0.0036 + 550_000 * 0.0033);
});

test("each commission band applies at its boundary", () => {
  near(brokerCommission(50_000), 180);
  near(brokerCommission(500_000), 1650);
  near(brokerCommission(2_000_000), 6200);
  near(brokerCommission(10_000_000), 27_000);
  near(brokerCommission(20_000_000), 48_000);
});

test("a tiny trade pays the minimum commission, not a fraction of a rupee", () => {
  assert.equal(brokerCommission(100), EQUITY_SCHEDULE_2080.minCommission);
  assert.equal(brokerCommission(0), 0);
  assert.equal(brokerCommission(-5), 0);
});

test("institutional CGT ignores the holding period", () => {
  // Applying the individual long/short split to an institution understates tax.
  assert.equal(cgtRate(INVESTOR.INSTITUTIONAL, 10), 0.10);
  assert.equal(cgtRate(INVESTOR.INSTITUTIONAL, 5000), 0.10);
});

test("individual CGT turns on the 365-day boundary", () => {
  assert.equal(cgtRate(INVESTOR.INDIVIDUAL, 365), 0.075);   // not yet long-term
  assert.equal(cgtRate(INVESTOR.INDIVIDUAL, 366), 0.05);
});

test("an unknown holding period yields no rate rather than the cheaper one", () => {
  assert.equal(cgtRate(INVESTOR.INDIVIDUAL, null), null);
});

test("the schedule is dated and flagged provisional", () => {
  const s = scheduleFor("2026-09-07");
  assert.equal(s.status, SCHEDULE_STATUS.PROVISIONAL);
  assert.ok(s.effectiveFrom <= "2026-09-07");
  // Policy numbers change; a result must be traceable to the schedule used.
  assert.ok(s.id);
});

test("transaction costs itemise commission, SEBON and DP", () => {
  const c = transactionCosts(100_000);
  near(c.sebon, 15);
  assert.equal(c.dp, 25);
  near(c.total, c.commission + c.sebon + c.dp);
});

// ══ WACC ═══════════════════════════════════════════════════════════════════
test("WACC blends lots and includes purchase costs in the basis", () => {
  const w = wacc([{ qty: 100, price: 500 }, { qty: 50, price: 450 }]);
  assert.equal(w.qty, 150);
  // Excluding entry costs understates the basis and overstates the later gain.
  assert.ok(w.wacc > (100 * 500 + 50 * 450) / 150);
  assert.equal(w.includesCosts, true);
});

test("WACC can exclude costs for comparison with a broker's simpler figure", () => {
  const w = wacc([{ qty: 100, price: 500 }], { includeCosts: false });
  near(w.wacc, 500);
});

test("no usable lots yields a null WACC, never zero", () => {
  // A WACC of zero would make every future sale look like pure profit.
  const w = wacc([{ qty: 0, price: 500 }, { qty: -5, price: 100 }]);
  assert.equal(w.wacc, null);
  assert.equal(w.rejected.length, 2);
});

// ══ capital gains ══════════════════════════════════════════════════════════
test("CGT is levied on the gain, not the proceeds", () => {
  const g = capitalGains({ qty: 100, buyPrice: 500, sellPrice: 600, holdingDays: 400 });
  assert.equal(g.cgtRate, 0.05);
  near(g.tax, g.taxableGain * 0.05);
  assert.ok(g.tax < g.sellGross * 0.05);   // not a levy on turnover
});

test("a loss produces no tax and no invented credit", () => {
  const g = capitalGains({ qty: 100, buyPrice: 600, sellPrice: 500, holdingDays: 400 });
  assert.ok(g.gain < 0);
  assert.equal(g.taxableGain, 0);
  assert.equal(g.tax, 0);
  assert.ok(g.netProfit < 0);              // still a real loss
});

test("short-term individual pays more than long-term on the same trade", () => {
  const args = { qty: 100, buyPrice: 500, sellPrice: 600 };
  const short = capitalGains({ ...args, holdingDays: 100 });
  const long = capitalGains({ ...args, holdingDays: 400 });
  assert.ok(short.tax > long.tax);
  assert.equal(short.term, "SHORT");
  assert.equal(long.term, "LONG");
});

test("the holding period can come from dates instead of a day count", () => {
  const g = capitalGains({
    qty: 10, buyPrice: 100, sellPrice: 200,
    buyDate: "2025-01-01", sellDate: "2026-06-01",
  });
  assert.ok(g.holdingDays > 365);
  assert.equal(g.term, "LONG");
});

test("an unknown holding period leaves the tax undetermined and says so", () => {
  const g = capitalGains({ qty: 10, buyPrice: 100, sellPrice: 200 });
  assert.equal(g.cgtRate, null);
  assert.equal(g.tax, null);
  assert.match(g.note, /holding period unknown/);
});

test("both sides of the trade are charged costs", () => {
  const g = capitalGains({ qty: 100, buyPrice: 500, sellPrice: 600, holdingDays: 400 });
  assert.ok(g.buyCosts.total > 0 && g.sellCosts.total > 0);
  assert.ok(g.costBasis > g.buyGross);      // entry costs raise the basis
  assert.ok(g.netProceeds < g.sellGross);   // exit costs reduce proceeds
});

test("invalid input is refused rather than computed", () => {
  for (const bad of [{}, { qty: 0, buyPrice: 1, sellPrice: 2 }, { qty: 1, buyPrice: null, sellPrice: 2 }]) {
    assert.equal(capitalGains(bad).ok, false);
  }
});

test("every result names the schedule it used and its status", () => {
  const g = capitalGains({ qty: 1, buyPrice: 1, sellPrice: 2, holdingDays: 400 });
  assert.equal(g.schedule, EQUITY_SCHEDULE_2080.id);
  assert.equal(g.status, SCHEDULE_STATUS.PROVISIONAL);
});

// ══ right shares ═══════════════════════════════════════════════════════════
test("a 1:2 right at Rs 100 adjusts a Rs 600 share to Rs 433.33", () => {
  const r = rightShareAdjustment({ marketPrice: 600, ratio: 0.5, rightPrice: 100 });
  near(r.adjustedPrice, 433.33);
  near(r.dropPerShare, 166.67);
  // The drop is arithmetic, not a sell-off — the most common misreading on a
  // Nepali portfolio screen.
  assert.match(r.note, /theoretical/);
});

test("a 1:1 right halves toward the issue price", () => {
  const r = rightShareAdjustment({ marketPrice: 500, ratio: 1, rightPrice: 100 });
  near(r.adjustedPrice, 300);
});

test("bonus shares dilute without contributing capital", () => {
  const withBonus = rightShareAdjustment({ marketPrice: 600, ratio: 0.5, rightPrice: 100, bonusPct: 10 });
  const without = rightShareAdjustment({ marketPrice: 600, ratio: 0.5, rightPrice: 100 });
  assert.ok(withBonus.adjustedPrice < without.adjustedPrice);
});

test("a right worth less than its issue price has no value", () => {
  const r = rightShareAdjustment({ marketPrice: 105, ratio: 1, rightPrice: 100 });
  assert.ok(r.valueOfRight >= 0);
});

// ══ SIP ════════════════════════════════════════════════════════════════════
test("SIP contributions are invested at the start of the period", () => {
  // An ordinary annuity understates a standing instruction, which pays first.
  const s = sip({ monthly: 5000, years: 10, annualReturnPct: 12 });
  assert.equal(s.invested, 600_000);
  assert.ok(s.futureValue > 1_150_000);
  near(s.futureValue, 1_161_695, 50);
});

test("SIP with zero return returns exactly what was paid in", () => {
  const s = sip({ monthly: 1000, years: 2, annualReturnPct: 0 });
  assert.equal(s.invested, 24_000);
  near(s.futureValue, 24_000);
  near(s.gain, 0);
});

test("SIP yields a year-by-year schedule", () => {
  const s = sip({ monthly: 1000, years: 3, annualReturnPct: 10 });
  assert.equal(s.schedule.length, 3);
  assert.deepEqual(s.schedule.map((r) => r.year), [1, 2, 3]);
});

test("SIP is labelled a projection, not a forecast", () => {
  assert.match(sip({ monthly: 1, years: 1, annualReturnPct: 1 }).note, /not a prediction/);
});

test("invalid SIP input is refused", () => {
  for (const bad of [{}, { monthly: 0, years: 1, annualReturnPct: 1 }, { monthly: 1, years: -1, annualReturnPct: 1 }]) {
    assert.equal(sip(bad).ok, false);
  }
});

// ══ B.S. fiscal years ══════════════════════════════════════════════════════
test("fiscal-year labels parse in every published spelling", () => {
  for (const l of ["2081/82", "2081-82", "2081/2082", " 2081 / 82 "]) {
    const p = parseFiscalYear(l);
    assert.equal(p.status, FY_STATUS.VALID, l);
    assert.equal(p.label, "2081/82");      // one canonical spelling
  }
});

test("a non-consecutive fiscal year is rejected, not sorted into the middle", () => {
  assert.equal(parseFiscalYear("2081/85").status, FY_STATUS.INCONSISTENT);
  assert.equal(parseFiscalYear("garbage").status, FY_STATUS.UNPARSEABLE);
});

test("fiscal years sort newest first with unparseable labels last", () => {
  assert.deepEqual(
    sortFiscalYears(["2079/80", "junk", "2081/82", "2080/81"]),
    ["2081/82", "2080/81", "2079/80", "junk"],
  );
});

test("filtering by fiscal year excludes rows whose year cannot be read", () => {
  const rows = [
    { symbol: "A", fiscalYear: "2081/82" },
    { symbol: "B", fiscalYear: "2081-82" },
    { symbol: "C", fiscalYear: "???" },
  ];
  // A dividend of unknown year shown under 2081/82 is a false statement.
  assert.deepEqual(filterByFiscalYear(rows, "2081/82").map((r) => r.symbol), ["A", "B"]);
});

test("grouping surfaces unparseable rows rather than dropping them", () => {
  const { groups, unknown } = groupByFiscalYear([
    { fiscalYear: "2081/82" }, { fiscalYear: "2080/81" }, { fiscalYear: "" },
  ]);
  assert.deepEqual(groups.map((g) => g.fiscalYear), ["2081/82", "2080/81"]);
  assert.equal(unknown.length, 1);
});

test("distinct fiscal years are listed newest first", () => {
  assert.deepEqual(
    fiscalYearsIn([{ fiscalYear: "2080/81" }, { fiscalYear: "2081/82" }, { fiscalYear: "2081-82" }]),
    ["2081/82", "2080/81"],
  );
});

test("B.S. date conversion refuses rather than approximating", () => {
  // Nepali month lengths are fixed by almanac, not formula. An approximate
  // converter returns dates that are plausibly wrong, which nobody audits.
  assert.equal(adToBs("2026-09-07").ok, false);
  assert.equal(adToBs().reason, "NOT_IMPLEMENTED");
});

// ══ compare ════════════════════════════════════════════════════════════════
const bars = (closes) => closes.map((c, i) => ({ date: `2026-01-${String(i + 1).padStart(2, "0")}`, close: c }));

test("series are rebased so differently-priced stocks are comparable", () => {
  // Plotting Rs 4,000 against Rs 200 says only which is dearer.
  const n = normalize(bars([100, 110, 120]));
  assert.equal(n.points[0].pct, 0);
  near(n.returnPct, 20);
});

test("a zero base is refused rather than plotted as a spike", () => {
  assert.equal(normalize(bars([0, 100])).reason, "ZERO_BASE");
  assert.equal(normalize(bars([100])).reason, "INSUFFICIENT_HISTORY");
});

test("a chart drawn from fewer symbols than requested says so", () => {
  const out = compareSeries([
    { symbol: "A", bars: bars([100, 120]) },
    { symbol: "B", bars: bars([0, 50]) },
  ]);
  assert.equal(out.plotted, 1);
  assert.equal(out.excluded[0].symbol, "B");
});

test("comparison is capped at eight instruments", () => {
  const many = Array.from({ length: 12 }, (_, i) => ({ symbol: `S${i}`, bars: bars([100, 110]) }));
  assert.equal(compareSeries(many).plotted, 8);
  assert.equal(canAdd(Array.from({ length: 8 }, (_, i) => `S${i}`), "NEW").reason, "LIMIT_REACHED");
});

test("adding a duplicate or empty symbol is refused", () => {
  assert.equal(canAdd(["NABIL"], "nabil").reason, "ALREADY_ADDED");
  assert.equal(canAdd([], "").reason, "NO_SYMBOL");
  assert.equal(canAdd([], "UPPER").ok, true);
});

test("a missing fundamental stays null so it cannot top a sort", () => {
  const m = compareMatrix([{ symbol: "A", pe: 12 }, { symbol: "B" }]);
  const pe = m.rows.find((r) => r.key === "pe");
  assert.deepEqual(pe.values, [12, null]);   // not [12, 0]
});

test("period return in the matrix comes from the plotted series", () => {
  const series = compareSeries([{ symbol: "A", bars: bars([100, 150]) }]);
  const m = compareMatrix([{ symbol: "A" }], { series: series.series });
  near(m.rows.find((r) => r.key === "returnPct").values[0], 50);
});


// ══ the coercion trap ══════════════════════════════════════════════════════
test("null and empty string are absence, not zero", () => {
  // `Number(null)` is 0 and 0 is finite, so a bare isFinite check accepts every
  // one of these as a legitimate zero. This caught a real defect: an unknown
  // holding period was silently getting the short-term CGT rate.
  for (const absent of [null, undefined, ""]) {
    assert.equal(cgtRate(INVESTOR.INDIVIDUAL, absent), null, String(absent));
    assert.equal(capitalGains({ qty: 1, buyPrice: absent, sellPrice: 2 }).ok, false);
    assert.equal(capitalGains({ qty: absent, buyPrice: 1, sellPrice: 2 }).ok, false);
  }
});

test("a boolean is never accepted as a price or quantity", () => {
  // `Number(true)` is 1 — a quantity of one share from a checkbox.
  assert.equal(capitalGains({ qty: true, buyPrice: 1, sellPrice: 2 }).ok, false);
  assert.equal(wacc([{ qty: true, price: 500 }]).wacc, null);
});

test("a genuine zero is still distinguishable from absence", () => {
  // 0 days held is a real same-day trade and must get the short-term rate.
  assert.equal(cgtRate(INVESTOR.INDIVIDUAL, 0), 0.075);
});
