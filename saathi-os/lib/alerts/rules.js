// Price alert rules — EVALUATION ONLY. PURE.
//
// This module decides whether an alert SHOULD fire. It does not deliver one: no
// push, no service worker, no I/O, no Date.now(). `now` and `lastFiredAt` arrive
// as arguments precisely so the same evaluation replays identically in a test, a
// backfill and a live tick.
//
// Three rules shape everything below:
//
//   1. "DID NOT FIRE" AND "COULD NOT TELL" ARE DIFFERENT ANSWERS. A rule whose
//      price is missing, whose indicator is not VALID, or whose strategy is
//      unreadable returns status NOT_EVALUABLE with fired=false. A caller that
//      reads fired=false as "the condition is false" would let a user believe the
//      market was checked and found quiet when it was never checked at all — the
//      exact failure this file exists to prevent. `cause` says which reading
//      blocked it, in the indicator vocabulary.
//
//   2. NO COERCION. Every operand is rejected as unusable BEFORE any arithmetic:
//      Number(null) === 0, Number("") === 0 and Number(" 70 ") === 70, so an
//      absent price would otherwise arrive at a `priceBelow 100` comparator as a
//      confidently-below 0 and fire a false alarm.
//
//   3. A BROKEN RULE FAILS WHEN IT IS SAVED. validateRule rejects unknown kinds,
//      non-numeric thresholds, malformed crossing operands and negative cooldowns,
//      so a rule cannot sit in the store looking armed while it can never fire.

import { INDICATOR_STATUS } from "../nepse/indicators.js";
import {
  CONDITION_OP, NODE_TYPE, STRATEGY_STATUS,
  validateStrategy, evaluateStrategy,
} from "../strategy/conditions.js";

export const ALERT_KIND = {
  PRICE_ABOVE: "priceAbove",
  PRICE_BELOW: "priceBelow",
  PERCENT_CHANGE_ABOVE: "percentChangeAbove",
  PERCENT_CHANGE_BELOW: "percentChangeBelow",
  VOLUME_RATIO_ABOVE: "volumeRatioAbove",
  INDICATOR_CROSSING: "indicatorCrossing",
  STRATEGY: "strategy",
};

/**
 * Outcome status. Deliberately three values and not more: the delivery layer only
 * ever asks "send, hold, or admit we don't know". WHY it could not be told is
 * carried separately in `cause`, in the indicator vocabulary.
 */
export const ALERT_STATUS = {
  VALID: "VALID",                 // the condition was actually evaluated; `fired` is the answer
  NOT_EVALUABLE: "NOT_EVALUABLE", // no answer exists — never report this as "did not fire"
  COOLDOWN: "COOLDOWN",           // the condition IS true; suppressed because it fired recently
};

/** Why a result is NOT_EVALUABLE. Reuses the indicator vocabulary verbatim. */
export const ALERT_CAUSE = {
  ...INDICATOR_STATUS,
  INVALID_STRATEGY: STRATEGY_STATUS.INVALID_STRATEGY,
  INVALID_RULE: "INVALID_RULE",
};

export const CROSS_DIRECTION = { ABOVE: "above", BELOW: "below" };

export const RULE_ERROR = {
  MISSING_RULE: "MISSING_RULE",
  MISSING_ID: "MISSING_ID",
  UNKNOWN_KIND: "UNKNOWN_KIND",
  MISSING_SYMBOL: "MISSING_SYMBOL",
  MISSING_THRESHOLD: "MISSING_THRESHOLD",
  INVALID_THRESHOLD: "INVALID_THRESHOLD",
  INVALID_COOLDOWN: "INVALID_COOLDOWN",
  UNKNOWN_DIRECTION: "UNKNOWN_DIRECTION",
  INVALID_OPERAND: "INVALID_OPERAND",
  MISSING_STRATEGY_ID: "MISSING_STRATEGY_ID",
};

/** Kinds that compare one observed number against one saved number. */
const THRESHOLD_KINDS = new Set([
  ALERT_KIND.PRICE_ABOVE,
  ALERT_KIND.PRICE_BELOW,
  ALERT_KIND.PERCENT_CHANGE_ABOVE,
  ALERT_KIND.PERCENT_CHANGE_BELOW,
  ALERT_KIND.VOLUME_RATIO_ABOVE,
]);

const KINDS = new Set(Object.values(ALERT_KIND));
const DIRECTIONS = new Set(Object.values(CROSS_DIRECTION));

/** True only for a real, finite JS number — strings, null and NaN never qualify. */
const isFiniteNumber = (v) => typeof v === "number" && Number.isFinite(v);

const isPlainObject = (v) => typeof v === "object" && v !== null && !Array.isArray(v);

const nonEmptyString = (v) => typeof v === "string" && v.trim() !== "";

/** Published values are rounded; see round4's use in `observed` for why it matters. */
const round4 = (n) => +n.toFixed(4);

// ── validation (save time; evaluation re-runs it and refuses to guess) ───────────

/** The crossing leaf as a strategy condition, so one crossing semantic exists. */
function crossingNode(rule) {
  return {
    type: NODE_TYPE.CONDITION,
    left: rule.left,
    op: rule.direction === CROSS_DIRECTION.BELOW
      ? CONDITION_OP.CROSSES_BELOW
      : CONDITION_OP.CROSSES_ABOVE,
    right: rule.right,
  };
}

function validateCrossing(rule, errors) {
  if (!DIRECTIONS.has(rule.direction)) {
    errors.push({
      code: RULE_ERROR.UNKNOWN_DIRECTION, path: "direction",
      message: `direction must be "above" or "below", got "${String(rule.direction)}"`,
    });
  }
  // Operands are checked by the strategy validator rather than a second copy of
  // the same rules here — a crossing alert and a crossing condition must accept
  // and reject exactly the same operands, or a rule that saves in one screen
  // would be unrunnable from the other.
  const probe = validateStrategy({ name: "alert", root: crossingNode(rule) });
  for (const err of probe.errors) {
    errors.push({
      code: RULE_ERROR.INVALID_OPERAND,
      path: err.path.replace(/^root\.?/, ""),
      message: err.message,
    });
  }
}

/**
 * @returns {{valid:boolean, errors:Array<{code:string,path:string,message:string}>}}
 */
export function validateRule(rule) {
  const errors = [];
  if (!isPlainObject(rule)) {
    errors.push({ code: RULE_ERROR.MISSING_RULE, path: "", message: "rule must be an object" });
    return { valid: false, errors };
  }
  if (!nonEmptyString(rule.id)) {
    // Without an id a result cannot be attributed, and cooldown cannot be looked
    // up — an unidentified rule would re-fire forever.
    errors.push({ code: RULE_ERROR.MISSING_ID, path: "id", message: "rule needs an id" });
  }
  if (!KINDS.has(rule.kind)) {
    errors.push({
      code: RULE_ERROR.UNKNOWN_KIND, path: "kind",
      message: `unknown alert kind "${String(rule.kind)}"`,
    });
  }
  if (!nonEmptyString(rule.symbol)) {
    errors.push({ code: RULE_ERROR.MISSING_SYMBOL, path: "symbol", message: "rule needs a symbol" });
  }

  if (THRESHOLD_KINDS.has(rule.kind)) {
    if (rule.threshold === null || rule.threshold === undefined || rule.threshold === "") {
      errors.push({
        code: RULE_ERROR.MISSING_THRESHOLD, path: "threshold",
        message: `${rule.kind} needs a threshold`,
      });
    } else if (!isFiniteNumber(rule.threshold)) {
      // "70" from a form field must be parsed by the form, not silently by the
      // comparator: string comparison would make "9" > "70" and misfire.
      errors.push({
        code: RULE_ERROR.INVALID_THRESHOLD, path: "threshold",
        message: "threshold must be a finite number (no strings, no null)",
      });
    } else if (rule.kind === ALERT_KIND.VOLUME_RATIO_ABOVE && rule.threshold <= 0) {
      // Volume is never negative, so a ratio threshold of 0 or less is satisfied
      // by every tick — an always-on alert, which is a broken rule, not a signal.
      errors.push({
        code: RULE_ERROR.INVALID_THRESHOLD, path: "threshold",
        message: "volume ratio threshold must be greater than 0 or the rule always fires",
      });
    }
  }

  if (rule.cooldownMs !== undefined && rule.cooldownMs !== null) {
    if (!isFiniteNumber(rule.cooldownMs) || rule.cooldownMs < 0) {
      errors.push({
        code: RULE_ERROR.INVALID_COOLDOWN, path: "cooldownMs",
        message: "cooldownMs must be a finite number of milliseconds, zero or more",
      });
    }
  }

  if (rule.kind === ALERT_KIND.INDICATOR_CROSSING) validateCrossing(rule, errors);

  if (rule.kind === ALERT_KIND.STRATEGY && !nonEmptyString(rule.strategyId)) {
    errors.push({
      code: RULE_ERROR.MISSING_STRATEGY_ID, path: "strategyId",
      message: "strategy alert needs the id of a saved strategy",
    });
  }

  return { valid: errors.length === 0, errors };
}

// ── evaluation ──────────────────────────────────────────────────────────────────

function outcome(rule, fields) {
  return {
    ruleId: isPlainObject(rule) && nonEmptyString(rule.id) ? rule.id : null,
    kind: isPlainObject(rule) && KINDS.has(rule.kind) ? rule.kind : null,
    symbol: isPlainObject(rule) && nonEmptyString(rule.symbol) ? rule.symbol : null,
    fired: false,
    status: ALERT_STATUS.VALID,
    cause: null,
    reason: "",
    observedValue: null,
    threshold: null,
    observations: null,
    ...fields,
  };
}

/** No answer exists. observedValue stays null — never a stand-in zero. */
function notEvaluable(rule, cause, reason, extra = {}) {
  return outcome(rule, {
    fired: false,
    status: ALERT_STATUS.NOT_EVALUABLE,
    cause,
    reason,
    ...extra,
  });
}

function lookup(map, symbol) {
  if (!isPlainObject(map) || !nonEmptyString(symbol)) return null;
  const direct = map[symbol];
  if (direct !== undefined && direct !== null) return direct;
  const upper = symbol.trim().toUpperCase();
  const byUpper = map[upper];
  return byUpper === undefined || byUpper === null ? null : byUpper;
}

/**
 * Pull one numeric field off a quote, or null with the reason it is unusable.
 * `allowZero` distinguishes the two zeros that matter: a traded volume of 0 is a
 * real observation (a symbol with no trades today), while a price of 0 is a
 * parse artefact, never a NEPSE quote.
 */
function quoteNumber(quote, field, { allowZero = true } = {}) {
  const raw = quote[field];
  if (raw === null || raw === undefined || raw === "") {
    return { value: null, reason: `quote carries no ${field}` };
  }
  if (!isFiniteNumber(raw)) {
    return { value: null, reason: `quote ${field} is not a finite number` };
  }
  if (!allowZero && raw <= 0) {
    return { value: null, reason: `quote ${field} is not positive` };
  }
  return { value: raw, reason: null };
}

/** Observation count behind a quote — null when the feed does not declare one. */
const quoteObservations = (quote) =>
  (isFiniteNumber(quote?.observations) ? quote.observations : null);

/**
 * Resolve the observed number for a threshold rule.
 * @returns {{value:number|null, cause:string|null, reason:string}}
 */
function observed(rule, quote) {
  if (rule.kind === ALERT_KIND.PRICE_ABOVE || rule.kind === ALERT_KIND.PRICE_BELOW) {
    const price = quoteNumber(quote, "price", { allowZero: false });
    if (price.value === null) {
      return { value: null, cause: ALERT_CAUSE.FIELD_UNAVAILABLE, reason: price.reason };
    }
    return { value: price.value, cause: null, reason: "" };
  }

  if (rule.kind === ALERT_KIND.PERCENT_CHANGE_ABOVE || rule.kind === ALERT_KIND.PERCENT_CHANGE_BELOW) {
    const price = quoteNumber(quote, "price", { allowZero: false });
    if (price.value === null) {
      return { value: null, cause: ALERT_CAUSE.FIELD_UNAVAILABLE, reason: price.reason };
    }
    // A percent change is a statement about two bars. On the first session of a
    // newly listed symbol there is no previous close, and inventing one (or
    // reusing today's price for a tidy 0%) would report "unchanged" about a day
    // nobody observed. INSUFFICIENT_HISTORY is the honest answer.
    const prev = quoteNumber(quote, "previousClose", { allowZero: false });
    if (prev.value === null) {
      return {
        value: null,
        cause: ALERT_CAUSE.INSUFFICIENT_HISTORY,
        reason: `percent change needs a previous close: ${prev.reason}`,
      };
    }
    return { value: round4(((price.value - prev.value) / prev.value) * 100), cause: null, reason: "" };
  }

  if (rule.kind === ALERT_KIND.VOLUME_RATIO_ABOVE) {
    const volume = quoteNumber(quote, "volume");
    if (volume.value === null) {
      return { value: null, cause: ALERT_CAUSE.FIELD_UNAVAILABLE, reason: volume.reason };
    }
    // The average is the divisor, so zero is not merely unusable, it is undefined.
    const average = quoteNumber(quote, "averageVolume", { allowZero: false });
    if (average.value === null) {
      return {
        value: null,
        cause: ALERT_CAUSE.INSUFFICIENT_HISTORY,
        reason: `volume ratio needs a positive average volume: ${average.reason}`,
      };
    }
    return { value: round4(volume.value / average.value), cause: null, reason: "" };
  }

  return { value: null, cause: ALERT_CAUSE.FIELD_UNAVAILABLE, reason: `no observation for ${rule.kind}` };
}

const fires = (kind, value, threshold) => {
  switch (kind) {
    case ALERT_KIND.PRICE_ABOVE:
    case ALERT_KIND.PERCENT_CHANGE_ABOVE:
    case ALERT_KIND.VOLUME_RATIO_ABOVE:
      return value > threshold;
    case ALERT_KIND.PRICE_BELOW:
    case ALERT_KIND.PERCENT_CHANGE_BELOW:
      return value < threshold;
    default:
      return false;
  }
};

function evaluateThresholdRule(rule, context) {
  const quote = lookup(context.quotes, rule.symbol);
  if (!isPlainObject(quote)) {
    return notEvaluable(rule, ALERT_CAUSE.FIELD_UNAVAILABLE,
      `no quote for ${rule.symbol}`, { threshold: rule.threshold });
  }
  // A stale quote is worse than a missing one: it looks like a price. Firing on
  // yesterday's number would tell a user the level was crossed today.
  if (quote.stale === true) {
    return notEvaluable(rule, ALERT_CAUSE.DATA_STALE,
      `quote for ${rule.symbol} is marked stale${quote.asOf ? ` (as of ${quote.asOf})` : ""}`,
      { threshold: rule.threshold, observations: quoteObservations(quote) });
  }

  const obs = observed(rule, quote);
  if (obs.value === null) {
    return notEvaluable(rule, obs.cause, obs.reason,
      { threshold: rule.threshold, observations: quoteObservations(quote) });
  }

  // Compared at the same precision it is reported at, so the number the user is
  // shown is exactly the number that decided — a value displayed as 5.0000 must
  // never sit on the un-fired side of a threshold of 5 because of a hidden tail.
  return outcome(rule, {
    fired: fires(rule.kind, obs.value, rule.threshold),
    status: ALERT_STATUS.VALID,
    observedValue: obs.value,
    threshold: rule.threshold,
    observations: quoteObservations(quote),
  });
}

/**
 * The current value of a crossing operand, for REPORTING only. The decision is
 * made by evaluateStrategy; this never gates it, so it may safely return null.
 */
function reportedOperandValue(operand, readings) {
  if (!isPlainObject(operand) || !isPlainObject(readings)) return null;
  if (isFiniteNumber(operand.value)) return operand.value;
  const res = readings[operand.reading];
  if (!isPlainObject(res) || res.status !== INDICATOR_STATUS.VALID) return null;
  const raw = operand.field !== undefined
    ? (isPlainObject(res.value) ? res.value[operand.field] : null)
    : res.value;
  return isFiniteNumber(raw) ? raw : null;
}

/** Shared tail for the two rule kinds that delegate to the strategy evaluator. */
function fromStrategyResult(rule, res, extra = {}) {
  if (res.matched === null) {
    const blocker = res.blockers?.[0];
    return notEvaluable(rule, res.status,
      blocker ? `${blocker.reason} (${blocker.status})` : `strategy is undecided (${res.status})`,
      { ...extra, observations: res.readingObservations });
  }
  return outcome(rule, {
    fired: res.matched === true,
    status: ALERT_STATUS.VALID,
    observations: res.readingObservations,
    ...extra,
  });
}

function evaluateCrossingRule(rule, context) {
  const readings = lookup(context.readings, rule.symbol);
  const prevReadings = lookup(context.prevReadings, rule.symbol);
  const res = evaluateStrategy(
    { name: rule.id, root: crossingNode(rule) },
    readings,
    // undefined, not null, when absent: the strategy evaluator treats a missing
    // previous frame as INSUFFICIENT_HISTORY, which is what a first tick is.
    prevReadings === null ? undefined : prevReadings,
  );
  const extra = {
    observedValue: reportedOperandValue(rule.left, readings),
    threshold: isFiniteNumber(rule.right?.value) ? rule.right.value : null,
  };
  return fromStrategyResult(rule, res, extra);
}

function evaluateStrategyRule(rule, context) {
  const strategy = lookup(context.strategies, rule.strategyId);
  if (!isPlainObject(strategy)) {
    // Validation only sees the id; whether it still resolves is a run-time fact,
    // and a deleted strategy must not read as "your conditions were not met".
    return notEvaluable(rule, ALERT_CAUSE.FIELD_UNAVAILABLE,
      `no saved strategy "${rule.strategyId}"`);
  }
  return fromStrategyResult(
    rule,
    evaluateStrategy(
      strategy,
      lookup(context.readings, rule.symbol),
      lookup(context.prevReadings, rule.symbol) ?? undefined,
    ),
  );
}

/**
 * Cooldown gate. Applied only to a result that WOULD fire, so a rule sitting
 * quietly under its threshold is reported as not-fired rather than as suppressed.
 */
function applyCooldown(rule, res, context) {
  if (!res.fired) return res;
  const cooldownMs = isFiniteNumber(rule.cooldownMs) ? rule.cooldownMs : 0;
  if (cooldownMs <= 0) return res;

  const stored = lookup(context.lastFiredAt, rule.id);
  const lastFiredAt = stored ?? rule.lastFiredAt;
  if (lastFiredAt === null || lastFiredAt === undefined) return res; // never fired: nothing to suppress

  if (!isFiniteNumber(lastFiredAt)) {
    return notEvaluable(rule, ALERT_CAUSE.FIELD_UNAVAILABLE,
      "lastFiredAt is not a timestamp, so cooldown cannot be checked",
      { observedValue: res.observedValue, threshold: res.threshold, observations: res.observations });
  }
  if (!isFiniteNumber(context.now)) {
    // Firing without a clock would re-notify on every evaluation pass; refusing to
    // answer is the safe half of the "did not fire / could not tell" split.
    return notEvaluable(rule, ALERT_CAUSE.FIELD_UNAVAILABLE,
      "no `now` timestamp supplied, so cooldown cannot be checked",
      { observedValue: res.observedValue, threshold: res.threshold, observations: res.observations });
  }

  // A negative elapsed (lastFiredAt ahead of now — clock skew, or a replayed
  // history) suppresses rather than fires: the alert is known to have gone out.
  const elapsed = context.now - lastFiredAt;
  if (elapsed >= cooldownMs) return res;

  return {
    ...res,
    fired: false,
    status: ALERT_STATUS.COOLDOWN,
    reason: `condition holds but the alert fired ${elapsed}ms ago, inside its ${cooldownMs}ms cooldown`,
  };
}

function describeOutcome(res) {
  if (res.reason) return res.reason;
  if (res.status === ALERT_STATUS.VALID && res.observedValue !== null && res.threshold !== null) {
    return `${res.observedValue} ${res.fired ? "crossed" : "did not cross"} ${res.threshold}`;
  }
  return res.fired ? "condition met" : "condition not met";
}

/**
 * Evaluate saved alert rules against one snapshot of the world.
 *
 * @param {Array} rules
 * @param {object} context
 *   @param {number} [context.now]           epoch ms; supplied by the caller, never read from the clock here
 *   @param {object} [context.quotes]        {SYMBOL: {price, previousClose, volume, averageVolume, stale?, asOf?, observations?}}
 *   @param {object} [context.readings]      {SYMBOL: {rsi: <typed indicator result>, ...}} current bar
 *   @param {object} [context.prevReadings]  the same, one bar earlier; crossings need it
 *   @param {object} [context.strategies]    {strategyId: {name, root}}
 *   @param {object} [context.lastFiredAt]   {ruleId: epoch ms}
 * @returns {Array<{ruleId:string|null, kind:string|null, symbol:string|null, fired:boolean,
 *                  status:string, cause:string|null, reason:string,
 *                  observedValue:number|null, threshold:number|null, observations:number|null}>}
 */
export function evaluateRules(rules, context = {}) {
  if (!Array.isArray(rules)) return [];
  const ctx = isPlainObject(context) ? context : {};

  return rules.map((rule) => {
    const validation = validateRule(rule);
    if (!validation.valid) {
      // An unrunnable rule has no answer either. It reports NOT_EVALUABLE so that
      // one status covers every "could not tell", with the cause naming the rule
      // itself rather than the market.
      return notEvaluable(rule, ALERT_CAUSE.INVALID_RULE,
        validation.errors.map((e) => e.message).join("; "));
    }

    let res;
    if (rule.kind === ALERT_KIND.INDICATOR_CROSSING) res = evaluateCrossingRule(rule, ctx);
    else if (rule.kind === ALERT_KIND.STRATEGY) res = evaluateStrategyRule(rule, ctx);
    else res = evaluateThresholdRule(rule, ctx);

    res = applyCooldown(rule, res, ctx);
    return { ...res, reason: describeOutcome(res) };
  });
}

/** Convenience for callers that only want the alerts they are entitled to send. */
export const firedOnly = (results) => results.filter((r) => r.fired === true);

/** The undecided ones — a count a UI must surface instead of silently dropping. */
export const notEvaluableOnly = (results) =>
  results.filter((r) => r.status === ALERT_STATUS.NOT_EVALUABLE);
