/**
 * NEPSE investor calculators — WACC, capital-gains tax, right shares, SIP. PURE.
 *
 * Every result carries the fee schedule it used and its PROVISIONAL status. The
 * arithmetic is exact; the rates are policy that changes, and a number presented
 * without the schedule behind it invites someone to file it as tax.
 *
 * NOTHING HERE ROUNDS TO A FRIENDLY FIGURE. Costs are returned at full precision
 * and the caller formats. Rounding inside a calculator is how a Rs 3 discrepancy
 * against a broker note becomes unexplainable.
 */

import {
  EQUITY_SCHEDULE_2080, INVESTOR, LONG_TERM_DAYS,
  cgtRate, scheduleFor, transactionCosts,
} from "./fees.js";

export { INVESTOR, LONG_TERM_DAYS };

/**
 * Coerce to a finite number, or null.
 *
 * `Number(null)` is 0, `Number("")` is 0 and `Number(false)` is 0 — all finite.
 * A bare `Number.isFinite` check therefore accepts every one of them as a
 * legitimate zero price, quantity or holding period. Absence is rejected BEFORE
 * coercion, which is the only order that works.
 */
const n = (v) => {
  if (v === null || v === undefined || v === "" || typeof v === "boolean") return null;
  const x = Number(v);
  return Number.isFinite(x) ? x : null;
};

/**
 * Weighted average cost per share across purchase lots.
 *
 * PURCHASE COSTS ARE PART OF THE BASIS. Commission, SEBON fee and DP charge on
 * the way IN raise what the shares actually cost you, so excluding them
 * overstates the eventual gain and the tax on it. `includeCosts: false` is
 * offered for comparison against a broker's simpler figure, not as the default.
 */
export function wacc(lots = [], { includeCosts = true, schedule = EQUITY_SCHEDULE_2080 } = {}) {
  let qty = 0;
  let cost = 0;
  const rejected = [];
  for (const lot of lots) {
    const q = n(lot?.qty);
    const p = n(lot?.price);
    if (q === null || p === null || q <= 0 || p < 0) {
      rejected.push({ lot, reason: "INVALID_LOT" });
      continue;
    }
    const gross = q * p;
    const fees = includeCosts
      ? transactionCosts(gross, { scrips: 1, schedule }).total
      : 0;
    qty += q;
    cost += gross + fees;
  }
  if (qty <= 0) {
    // No usable lots means no cost basis — not a WACC of zero, which would
    // make every future sale look like pure profit.
    return { qty: 0, totalCost: 0, wacc: null, rejected, schedule: schedule.id,
             status: schedule.status };
  }
  return {
    qty, totalCost: cost, wacc: cost / qty, rejected,
    schedule: schedule.id, status: schedule.status, includesCosts: includeCosts,
  };
}

/**
 * Capital gains on a sale, with every cost line itemised.
 *
 * CGT IS LEVIED ON THE GAIN, NOT THE PROCEEDS. The taxable gain is net sale
 * proceeds minus the cost basis; selling at a loss produces no tax, and this
 * returns zero tax rather than a negative "credit" nobody can claim.
 */
export function capitalGains({
  qty, buyPrice, sellPrice, investor = INVESTOR.INDIVIDUAL,
  holdingDays = null, buyDate = null, sellDate = null,
  waccOverride = null, schedule = null,
} = {}) {
  const sched = schedule || scheduleFor(sellDate || buyDate);
  const q = n(qty);
  const bp = waccOverride !== null ? n(waccOverride) : n(buyPrice);
  const sp = n(sellPrice);
  if (q === null || q <= 0 || bp === null || sp === null) {
    return { ok: false, reason: "INVALID_INPUT", schedule: sched.id, status: sched.status };
  }

  const days = holdingDays !== null ? n(holdingDays) : daysBetween(buyDate, sellDate);
  const rate = cgtRate(investor, days, sched);

  const buyGross = q * bp;
  const sellGross = q * sp;
  const buyCosts = transactionCosts(buyGross, { schedule: sched });
  const sellCosts = transactionCosts(sellGross, { schedule: sched });

  const costBasis = buyGross + buyCosts.total;
  const netProceeds = sellGross - sellCosts.total;
  const gain = netProceeds - costBasis;

  // A loss is a loss. No tax, and no invented refund.
  const taxable = gain > 0 ? gain : 0;
  const tax = rate === null ? null : taxable * rate;
  const netProfit = tax === null ? null : gain - tax;

  return {
    ok: true,
    schedule: sched.id,
    status: sched.status,
    investor,
    holdingDays: days,
    term: days === null ? null : (days > LONG_TERM_DAYS ? "LONG" : "SHORT"),
    cgtRate: rate,
    buyGross, sellGross, buyCosts, sellCosts,
    costBasis, effectiveWacc: costBasis / q,
    netProceeds, gain, taxableGain: taxable, tax, netProfit,
    roiPct: costBasis > 0 && netProfit !== null ? (netProfit / costBasis) * 100 : null,
    // The holding period drives the rate, so an unknown date is an unknown tax
    // rather than a default that happens to be the cheaper one.
    note: rate === null ? "holding period unknown — CGT rate not determined" : null,
  };
}

export function daysBetween(from, to) {
  const a = dayMs(from);
  const b = dayMs(to);
  if (a === null || b === null) return null;
  return Math.round((b - a) / 86400000);
}

function dayMs(iso) {
  if (typeof iso !== "string" || iso.length < 10) return null;
  const t = Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
  return Number.isFinite(t) ? t : null;
}

/**
 * Theoretical price after a rights issue, and the value of the right itself.
 *
 * The adjusted price is the blended cost of old and new shares. This is why a
 * share "falls" on its ex-right date without anyone losing money — the drop is
 * arithmetic, not a sell-off, and showing it as a loss is the single most common
 * misreading on a Nepali portfolio screen.
 */
export function rightShareAdjustment({ marketPrice, ratio, rightPrice = 100, bonusPct = 0 } = {}) {
  const mp = n(marketPrice);
  const r = n(ratio);          // e.g. 0.5 for 1:2, 1 for 1:1
  const rp = n(rightPrice);
  const bonus = n(bonusPct) ?? 0;
  if (mp === null || r === null || rp === null || mp <= 0 || r < 0) {
    return { ok: false, reason: "INVALID_INPUT" };
  }
  const bonusRatio = bonus / 100;
  const totalShares = 1 + r + bonusRatio;
  // Bonus shares are issued free: they dilute without contributing capital.
  const totalValue = mp + r * rp;
  const adjusted = totalValue / totalShares;
  return {
    ok: true,
    marketPrice: mp, ratio: r, rightPrice: rp, bonusPct: bonus,
    adjustedPrice: adjusted,
    valueOfRight: Math.max(0, adjusted - rp),
    sharesPerOld: totalShares,
    dropPerShare: mp - adjusted,
    note: "theoretical ex-right price; the market sets the actual open",
  };
}

/**
 * SIP compounding with a periodic contribution.
 *
 * Contributions are applied at the START of each period (an annuity-due), which
 * is what a standing instruction actually does — money leaves your account and
 * is invested, then the period's return applies to it. Treating it as an
 * ordinary annuity silently understates the final value.
 */
export function sip({ monthly, years, annualReturnPct, periodsPerYear = 12 } = {}) {
  const c = n(monthly);
  const y = n(years);
  const ar = n(annualReturnPct);
  const pp = n(periodsPerYear);
  if (c === null || y === null || ar === null || c <= 0 || y <= 0 || !pp || pp <= 0) {
    return { ok: false, reason: "INVALID_INPUT" };
  }
  const periods = Math.round(y * pp);
  const r = ar / 100 / pp;
  let value = 0;
  const schedule = [];
  for (let i = 1; i <= periods; i += 1) {
    value = (value + c) * (1 + r);        // contribute, then grow
    if (i % pp === 0) {
      schedule.push({ year: i / pp, invested: c * i, value });
    }
  }
  const invested = c * periods;
  return {
    ok: true,
    periods, periodsPerYear: pp, ratePerPeriod: r,
    invested, futureValue: value, gain: value - invested,
    multiple: invested > 0 ? value / invested : null,
    schedule,
    // Stated so a projection is never mistaken for a forecast.
    note: "compounding projection at a constant assumed return; not a prediction",
  };
}
