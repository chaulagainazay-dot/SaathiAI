// Price alert rule engine — evaluation only.
//
// The distinction this whole module exists to protect: "did not fire" and "could
// not tell" are different answers. A user who acts on the first when it was really
// the second is the failure mode here, so most of what follows checks that
// NOT_EVALUABLE never collapses into a quiet false.

import test from "node:test";
import assert from "node:assert/strict";
import {
  ALERT_KIND, ALERT_STATUS, ALERT_CAUSE, CROSS_DIRECTION, RULE_ERROR,
  validateRule, evaluateRules, firedOnly, notEvaluableOnly,
} from "./alerts/rules.js";
import { INDICATOR_STATUS } from "./nepse/indicators.js";

const valid = (v, extra = {}) => ({ value: v, status: INDICATOR_STATUS.VALID, observations: 30, ...extra });
const only = (rule, context) => evaluateRules([rule], context)[0];

const PRICE_RULE = { id: "r1", kind: ALERT_KIND.PRICE_ABOVE, symbol: "NABIL", threshold: 545 };

test("a price rule fires when the quote crosses its threshold", () => {
  const r = only(PRICE_RULE, { quotes: { NABIL: { price: 550 } } });
  assert.equal(r.fired, true);
  assert.equal(r.status, ALERT_STATUS.VALID);
  assert.equal(r.observedValue, 550);
  assert.equal(r.threshold, 545);
});

test("a price rule that has not been reached reports a REAL not-fired", () => {
  const r = only(PRICE_RULE, { quotes: { NABIL: { price: 539 } } });
  assert.equal(r.fired, false);
  assert.equal(r.status, ALERT_STATUS.VALID);   // evaluated, and the answer is no
  assert.equal(r.cause, null);
});

test("a missing price is NOT_EVALUABLE, never a quiet not-fired", () => {
  const r = only(PRICE_RULE, { quotes: {} });
  assert.equal(r.fired, false);
  assert.equal(r.status, ALERT_STATUS.NOT_EVALUABLE);
  assert.notEqual(r.cause, null);
  // The two "false" results above are only distinguishable by status. That
  // distinction is the point of the module.
  const answered = only(PRICE_RULE, { quotes: { NABIL: { price: 539 } } });
  assert.equal(answered.fired, r.fired);
  assert.notEqual(answered.status, r.status);
});

test("a null price is not treated as a price of zero", () => {
  const below = { id: "r2", kind: ALERT_KIND.PRICE_BELOW, symbol: "NABIL", threshold: 100 };
  // If null became 0, this would fire — 0 is below 100.
  const r = only(below, { quotes: { NABIL: { price: null } } });
  assert.equal(r.status, ALERT_STATUS.NOT_EVALUABLE);
  assert.equal(r.fired, false);
});

test("percent change needs a previous close; without one it cannot be told", () => {
  const rule = { id: "r3", kind: ALERT_KIND.PERCENT_CHANGE_ABOVE, symbol: "RHPC", threshold: 5 };
  const fired = only(rule, { quotes: { RHPC: { price: 840, previousClose: 776 } } });
  assert.equal(fired.fired, true);            // +8.25%
  const blind = only(rule, { quotes: { RHPC: { price: 840 } } });
  assert.equal(blind.status, ALERT_STATUS.NOT_EVALUABLE);
});

test("percent change against a zero previous close does not divide by zero", () => {
  const rule = { id: "r4", kind: ALERT_KIND.PERCENT_CHANGE_ABOVE, symbol: "X", threshold: 5 };
  const r = only(rule, { quotes: { X: { price: 10, previousClose: 0 } } });
  assert.equal(r.status, ALERT_STATUS.NOT_EVALUABLE);
  assert.ok(!Number.isFinite(r.observedValue) === false || r.observedValue === null);
});

test("an indicator crossing needs the previous reading", () => {
  // Operands use the strategy module's shape — a reading on the left, a constant
  // on the right — so a crossing rule and a saved strategy speak one language.
  const rule = {
    id: "r5", kind: ALERT_KIND.INDICATOR_CROSSING, symbol: "CKHL",
    direction: CROSS_DIRECTION.ABOVE,
    left: { reading: "rsi" }, right: { value: 30 },
  };
  const crossed = only(rule, {
    readings: { CKHL: { rsi: valid(32) } },
    prevReadings: { CKHL: { rsi: valid(28) } },
  });
  assert.equal(crossed.fired, true);

  // Already above on both bars is not a crossing.
  const stayed = only(rule, {
    readings: { CKHL: { rsi: valid(35) } },
    prevReadings: { CKHL: { rsi: valid(33) } },
  });
  assert.equal(stayed.fired, false);
  assert.equal(stayed.status, ALERT_STATUS.VALID);

  // No previous bar at all: unknowable, not false.
  const blind = only(rule, { readings: { CKHL: { rsi: valid(32) } } });
  assert.equal(blind.status, ALERT_STATUS.NOT_EVALUABLE);
});

test("an indicator whose own status is not VALID makes the rule not evaluable", () => {
  const rule = {
    id: "r6", kind: ALERT_KIND.INDICATOR_CROSSING, symbol: "NBF3",
    direction: CROSS_DIRECTION.ABOVE,
    left: { reading: "macd" }, right: { value: 0 },
  };
  const r = only(rule, {
    readings: { NBF3: { macd: { value: null, status: INDICATOR_STATUS.INSUFFICIENT_HISTORY, observations: 4 } } },
    prevReadings: { NBF3: { macd: { value: null, status: INDICATOR_STATUS.INSUFFICIENT_HISTORY, observations: 3 } } },
  });
  assert.equal(r.status, ALERT_STATUS.NOT_EVALUABLE);
  assert.equal(r.cause, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
});

test("volume ratio fires on the ratio, and absent volume is not zero volume", () => {
  const rule = { id: "r7", kind: ALERT_KIND.VOLUME_RATIO_ABOVE, symbol: "WNLB", threshold: 2 };
  const hot = only(rule, { quotes: { WNLB: { volume: 3180, averageVolume: 1000 } } });
  assert.equal(hot.fired, true);
  assert.equal(hot.observedValue, 3.18);
  const blind = only(rule, { quotes: { WNLB: { averageVolume: 1000 } } });
  assert.equal(blind.status, ALERT_STATUS.NOT_EVALUABLE);
});

test("cooldown suppresses a still-true condition without calling it not-fired", () => {
  const rule = { ...PRICE_RULE, id: "r8", cooldownMs: 60 * 60 * 1000 };
  const ctx = {
    quotes: { NABIL: { price: 550 } },
    lastFiredAt: { r8: 1_000_000 },
    now: 1_000_000 + 10 * 60 * 1000,        // 10 minutes later
  };
  const r = only(rule, ctx);
  assert.equal(r.status, ALERT_STATUS.COOLDOWN);
  assert.equal(r.fired, false);

  // Past the cooldown it fires again.
  const later = only(rule, { ...ctx, now: 1_000_000 + 61 * 60 * 1000 });
  assert.equal(later.fired, true);
  assert.equal(later.status, ALERT_STATUS.VALID);
});

test("cooldown never suppresses a condition that is not true anyway", () => {
  const rule = { ...PRICE_RULE, id: "r9", cooldownMs: 60_000 };
  const r = only(rule, {
    quotes: { NABIL: { price: 400 } },
    lastFiredAt: { r9: 1_000_000 }, now: 1_000_010,
  });
  assert.equal(r.status, ALERT_STATUS.VALID);
  assert.equal(r.fired, false);
});

test("the module never reads the clock — cooldown without `now` is refused, not guessed", () => {
  const rule = { ...PRICE_RULE, id: "r10", cooldownMs: 60_000 };
  const r = only(rule, { quotes: { NABIL: { price: 550 } }, lastFiredAt: { r10: 1 } });
  // With no `now` the elapsed time is unknowable; it must not fire on a guess.
  assert.notEqual(r.status, ALERT_STATUS.VALID);
});

test("validation rejects a rule that could never be evaluated", () => {
  assert.equal(validateRule(null).valid, false);
  assert.equal(validateRule({ kind: ALERT_KIND.PRICE_ABOVE, symbol: "X", threshold: 1 }).errors[0].code, RULE_ERROR.MISSING_ID);
  assert.equal(validateRule({ id: "a", kind: "teleport", symbol: "X" }).errors[0].code, RULE_ERROR.UNKNOWN_KIND);
  const badThreshold = validateRule({ id: "a", kind: ALERT_KIND.PRICE_ABOVE, symbol: "X", threshold: "high" });
  assert.equal(badThreshold.valid, false);
  const negCooldown = validateRule({ ...PRICE_RULE, cooldownMs: -5 });
  assert.equal(negCooldown.valid, false);
  assert.equal(validateRule(PRICE_RULE).valid, true);
});

test("an invalid rule evaluates to NOT_EVALUABLE, blaming the rule not the market", () => {
  const r = only({ id: "bad", kind: "teleport", symbol: "X" }, {});
  assert.equal(r.status, ALERT_STATUS.NOT_EVALUABLE);
  assert.equal(r.cause, ALERT_CAUSE.INVALID_RULE);
});

test("a strategy rule with no such strategy cannot be told", () => {
  const rule = { id: "r11", kind: ALERT_KIND.STRATEGY, symbol: "NABIL", strategyId: "missing" };
  const r = only(rule, { strategies: {}, readings: { NABIL: { rsi: valid(30) } } });
  assert.equal(r.status, ALERT_STATUS.NOT_EVALUABLE);
});

test("the convenience filters separate what may be sent from what is undecided", () => {
  const results = evaluateRules(
    [PRICE_RULE, { id: "r12", kind: ALERT_KIND.PRICE_ABOVE, symbol: "GONE", threshold: 1 }],
    { quotes: { NABIL: { price: 999 } } },
  );
  assert.deepEqual(firedOnly(results).map((r) => r.ruleId), ["r1"]);
  assert.deepEqual(notEvaluableOnly(results).map((r) => r.ruleId), ["r12"]);
});

test("evaluating a non-array of rules yields nothing rather than throwing", () => {
  assert.deepEqual(evaluateRules(null, {}), []);
  assert.deepEqual(evaluateRules(undefined), []);
});

test("every result carries a human-readable reason", () => {
  const results = evaluateRules([PRICE_RULE], { quotes: { NABIL: { price: 550 } } });
  assert.ok(typeof results[0].reason === "string" && results[0].reason.length > 0);
});
