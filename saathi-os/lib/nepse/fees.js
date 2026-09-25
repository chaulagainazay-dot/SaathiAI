/**
 * NEPSE transaction costs and capital-gains tax — a VERSIONED, DATED schedule.
 *
 * These are policy numbers, not physics. SEBON and the Inland Revenue Department
 * change them; broker commission bands have been revised more than once. A rate
 * hardcoded as an eternal constant silently produces wrong tax on every trade
 * the day after it changes, and nobody notices because the arithmetic still
 * "works".
 *
 * So every schedule carries an `effectiveFrom`, a `source` and a `status`, the
 * calculator picks the one in force for the trade's date, and results carry the
 * schedule they used.
 *
 * PROVISIONAL, DELIBERATELY. The repository already tracks
 * `NEPSE_COST_POLICY_UNVERIFIED` as an open blocker — tick and lot values are
 * provisional and the cost policy has not been verified against a primary
 * source. These figures inherit that status: they are the published rates as
 * commonly applied, they are NOT operator-verified, and every result says so.
 * Treat the output as an estimate to check against a broker note, not as a tax
 * filing.
 */

export const SCHEDULE_STATUS = Object.freeze({
  /** Published and widely applied, but not verified here against a primary source. */
  PROVISIONAL: "PROVISIONAL",
  /** An operator has checked it against SEBON/IRD/broker documentation. */
  OPERATOR_VERIFIED: "OPERATOR_VERIFIED",
});

export const INVESTOR = Object.freeze({
  INDIVIDUAL: "INDIVIDUAL",
  INSTITUTIONAL: "INSTITUTIONAL",
});

/** Nepal's long-term threshold for listed shares. */
export const LONG_TERM_DAYS = 365;

/**
 * Broker commission is TIERED ON THE WHOLE TRANSACTION, not marginal.
 *
 * That distinction matters and is easy to get wrong: a Rs 600,000 trade is
 * charged 0.31% of the entire amount, not 0.36% of the first 50k plus 0.33% of
 * the next band. Income-tax intuition leads people to the marginal reading; it
 * is not how NEPSE brokerage works.
 */
export const EQUITY_SCHEDULE_2080 = Object.freeze({
  id: "nepse-equity/2080",
  effectiveFrom: "2023-07-17",
  status: SCHEDULE_STATUS.PROVISIONAL,
  source: "SEBON / NEPSE published brokerage bands; not verified here",
  currency: "NPR",
  commissionTiers: Object.freeze([
    { upTo: 50_000, rate: 0.0036 },
    { upTo: 500_000, rate: 0.0033 },
    { upTo: 2_000_000, rate: 0.0031 },
    { upTo: 10_000_000, rate: 0.0027 },
    { upTo: Infinity, rate: 0.0024 },
  ]),
  minCommission: 10,
  sebonFeeRate: 0.00015,        // 0.015% of transaction value
  dpChargePerScrip: 25,         // flat, per scrip per settlement
  cgt: Object.freeze({
    INDIVIDUAL_LONG: 0.05,
    INDIVIDUAL_SHORT: 0.075,
    INSTITUTIONAL: 0.10,
  }),
});

export const SCHEDULES = Object.freeze([EQUITY_SCHEDULE_2080]);

/**
 * The schedule in force on a date. Falls back to the earliest known one.
 *
 * A trade older than every schedule is charged the earliest rather than
 * refused — but the result reports which schedule was used, so an out-of-range
 * date is visible rather than silently assumed correct.
 */
export function scheduleFor(date, schedules = SCHEDULES) {
  const sorted = [...schedules].sort((a, b) => a.effectiveFrom.localeCompare(b.effectiveFrom));
  const iso = typeof date === "string" && date.length >= 10 ? date.slice(0, 10) : null;
  if (!iso) return sorted[sorted.length - 1];
  let chosen = sorted[0];
  for (const s of sorted) if (s.effectiveFrom <= iso) chosen = s;
  return chosen;
}

/** Whole-amount tiered commission, floored at the minimum. */
export function brokerCommission(amount, schedule = EQUITY_SCHEDULE_2080) {
  const a = Number(amount);
  if (!Number.isFinite(a) || a <= 0) return 0;
  const tier = schedule.commissionTiers.find((t) => a <= t.upTo)
    || schedule.commissionTiers[schedule.commissionTiers.length - 1];
  return Math.max(schedule.minCommission, a * tier.rate);
}

export function sebonFee(amount, schedule = EQUITY_SCHEDULE_2080) {
  const a = Number(amount);
  return Number.isFinite(a) && a > 0 ? a * schedule.sebonFeeRate : 0;
}

export function dpCharge(scrips = 1, schedule = EQUITY_SCHEDULE_2080) {
  const n = Number(scrips);
  return Number.isFinite(n) && n > 0 ? n * schedule.dpChargePerScrip : 0;
}

/**
 * The CGT rate for this investor and holding period.
 *
 * Institutional is a flat rate — holding period does not apply to it, and
 * quietly using the individual long/short split for an institution would
 * understate the tax.
 */
export function cgtRate(investor, holdingDays, schedule = EQUITY_SCHEDULE_2080) {
  if (investor === INVESTOR.INSTITUTIONAL) return schedule.cgt.INSTITUTIONAL;
  // `Number(null)` is 0 and 0 is finite, so a bare isFinite check lets an
  // UNKNOWN holding period through as "zero days held" and quietly returns the
  // short-term rate. Absence is checked before coercion, never after.
  if (holdingDays === null || holdingDays === undefined || holdingDays === "") return null;
  const d = Number(holdingDays);
  if (!Number.isFinite(d)) return null;   // unknown period -> no rate invented
  return d > LONG_TERM_DAYS ? schedule.cgt.INDIVIDUAL_LONG : schedule.cgt.INDIVIDUAL_SHORT;
}

/** All costs on one side of a trade. */
export function transactionCosts(amount, { scrips = 1, schedule = EQUITY_SCHEDULE_2080 } = {}) {
  const commission = brokerCommission(amount, schedule);
  const sebon = sebonFee(amount, schedule);
  const dp = dpCharge(scrips, schedule);
  return { commission, sebon, dp, total: commission + sebon + dp };
}
