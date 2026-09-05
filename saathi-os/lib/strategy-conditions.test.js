/**
 * Strategy builder conditions — three-valued logic, save-time validation, crossings.
 *
 * The invariants under test are the ones that keep a scan honest: a reading we
 * could not compute is UNKNOWN and never false, a strategy that cannot run is
 * rejected when it is saved rather than returning "no matches" forever, and no
 * absent value is ever coerced into a number that happens to satisfy a threshold.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { INDICATOR_STATUS } from "./nepse/indicators.js";
import {
  CONDITION_OP, GROUP_OP, NODE_TYPE, TRUTH, STRATEGY_STATUS, VALIDATION_ERROR,
  MAX_STRATEGY_DEPTH, EQUALITY_TOLERANCE,
  validateStrategy, evaluateStrategy, describeStrategy,
} from "./strategy/conditions.js";

// ── fixtures ─────────────────────────────────────────────────────────────────────

/** A typed indicator result, shaped exactly like computeIndicators emits. */
const reading = (value, status = INDICATOR_STATUS.VALID, observations = 120) => ({
  indicator: "test", value, status, observations,
  instrument: "NABIL", asOf: "2024-03-07", lookback: 14,
  source: "aabishkar2/nepse-data", dataset: "data/company-wise",
  adjustment: "UNADJUSTED", quality: null,
});

const READINGS = {
  one: reading(1),
  two: reading(2),
  rsi: reading(64.2, INDICATOR_STATUS.VALID, 400),
  sma: reading(510.5, INDICATOR_STATUS.VALID, 90),
  macd: reading({ macd: 2.5, signal: 1.5, histogram: 1 }),
  bollinger: reading({ middle: 100, upper: 110, lower: 90, percentB: null, bandwidth: 0.2 }),
  thin: reading(null, INDICATOR_STATUS.INSUFFICIENT_HISTORY, 3),
  stale: reading(48, INDICATOR_STATUS.DATA_STALE, 200),
  gapped: reading(48, INDICATOR_STATUS.DATA_CONFLICT, 200),
  unavailable: reading(null, INDICATOR_STATUS.FIELD_UNAVAILABLE, 0),
  hollow: reading(null, INDICATOR_STATUS.VALID, 42), // VALID but valueless: still nothing to compare
};

const cond = (left, op, right) => ({ type: NODE_TYPE.CONDITION, left, op, right });
const group = (op, ...children) => ({ type: NODE_TYPE.GROUP, op, children });
const strat = (root, name = "S") => ({ name, root });

/** Leaves that evaluate to exactly one of the three truth values. */
const LEAF = {
  TRUE: () => cond({ reading: "one" }, CONDITION_OP.GT, { value: 0 }),
  FALSE: () => cond({ reading: "one" }, CONDITION_OP.LT, { value: 0 }),
  UNKNOWN: () => cond({ reading: "thin" }, CONDITION_OP.GT, { value: 0 }),
};

const run = (root, readings = READINGS, prev = undefined) =>
  evaluateStrategy(strat(root), readings, prev);

const valueOf = (root, readings = READINGS, prev = undefined) => run(root, readings, prev).value;

// ── the leaves themselves ────────────────────────────────────────────────────────

test("leaf fixtures produce each of the three truth values", () => {
  assert.equal(valueOf(LEAF.TRUE()), TRUTH.TRUE);
  assert.equal(valueOf(LEAF.FALSE()), TRUTH.FALSE);
  assert.equal(valueOf(LEAF.UNKNOWN()), TRUTH.UNKNOWN);
});

test("matched is true/false/null and never coerces UNKNOWN to a rejection", () => {
  assert.equal(run(LEAF.TRUE()).matched, true);
  assert.equal(run(LEAF.FALSE()).matched, false);
  assert.equal(run(LEAF.UNKNOWN()).matched, null);
});

// ── exhaustive truth tables ──────────────────────────────────────────────────────

const T = TRUTH.TRUE, F = TRUTH.FALSE, U = TRUTH.UNKNOWN;

const PAIR_TABLE = {
  [GROUP_OP.ALL]: {
    "TRUE,TRUE": T, "TRUE,FALSE": F, "TRUE,UNKNOWN": U,
    "FALSE,TRUE": F, "FALSE,FALSE": F, "FALSE,UNKNOWN": F,
    "UNKNOWN,TRUE": U, "UNKNOWN,FALSE": F, "UNKNOWN,UNKNOWN": U,
  },
  [GROUP_OP.ANY]: {
    "TRUE,TRUE": T, "TRUE,FALSE": T, "TRUE,UNKNOWN": T,
    "FALSE,TRUE": T, "FALSE,FALSE": F, "FALSE,UNKNOWN": U,
    "UNKNOWN,TRUE": T, "UNKNOWN,FALSE": U, "UNKNOWN,UNKNOWN": U,
  },
  // none = not(any): negating UNKNOWN leaves UNKNOWN
  [GROUP_OP.NONE]: {
    "TRUE,TRUE": F, "TRUE,FALSE": F, "TRUE,UNKNOWN": F,
    "FALSE,TRUE": F, "FALSE,FALSE": T, "FALSE,UNKNOWN": U,
    "UNKNOWN,TRUE": F, "UNKNOWN,FALSE": U, "UNKNOWN,UNKNOWN": U,
  },
};

const SINGLE_TABLE = {
  [GROUP_OP.ALL]: { TRUE: T, FALSE: F, UNKNOWN: U },
  [GROUP_OP.ANY]: { TRUE: T, FALSE: F, UNKNOWN: U },
  [GROUP_OP.NONE]: { TRUE: F, FALSE: T, UNKNOWN: U },
};

for (const op of Object.values(GROUP_OP)) {
  test(`${op}: single-child truth table`, () => {
    for (const [a, expected] of Object.entries(SINGLE_TABLE[op])) {
      assert.equal(valueOf(group(op, LEAF[a]())), expected, `${op}([${a}])`);
    }
  });

  test(`${op}: exhaustive two-child truth table`, () => {
    for (const [key, expected] of Object.entries(PAIR_TABLE[op])) {
      const [a, b] = key.split(",");
      assert.equal(valueOf(group(op, LEAF[a](), LEAF[b]())), expected, `${op}([${a},${b}])`);
    }
  });
}

test("the three specified propagation cases hold literally", () => {
  assert.equal(valueOf(group(GROUP_OP.ALL, LEAF.TRUE(), LEAF.UNKNOWN())), TRUTH.UNKNOWN);
  assert.equal(valueOf(group(GROUP_OP.ANY, LEAF.TRUE(), LEAF.UNKNOWN())), TRUTH.TRUE);
  assert.equal(valueOf(group(GROUP_OP.NONE, LEAF.UNKNOWN())), TRUTH.UNKNOWN);
});

test("all three-value triples are order-independent", () => {
  const names = ["TRUE", "FALSE", "UNKNOWN"];
  for (const op of Object.values(GROUP_OP)) {
    for (const a of names) for (const b of names) for (const c of names) {
      const forward = valueOf(group(op, LEAF[a](), LEAF[b](), LEAF[c]()));
      const reverse = valueOf(group(op, LEAF[c](), LEAF[b](), LEAF[a]()));
      assert.equal(forward, reverse, `${op}(${a},${b},${c}) is order-dependent`);
    }
  }
});

test("a certain FALSE decides an all-group even when a sibling is UNKNOWN", () => {
  const res = run(group(GROUP_OP.ALL, LEAF.FALSE(), LEAF.UNKNOWN()));
  assert.equal(res.value, TRUTH.FALSE);
  assert.equal(res.status, STRATEGY_STATUS.VALID);
  // The blocker is still reported: the answer is certain, the tree was not clean.
  assert.equal(res.blockers.length, 1);
});

test("a decided any-group is VALID but still records what it could not read", () => {
  const res = run(group(GROUP_OP.ANY, LEAF.TRUE(), LEAF.UNKNOWN()));
  assert.equal(res.matched, true);
  assert.equal(res.status, STRATEGY_STATUS.VALID);
  assert.equal(res.blockers[0].status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
});

// ── UNKNOWN sources: never a number, never false ─────────────────────────────────

test("an absent reading is UNKNOWN, not a zero that reads as maximally oversold", () => {
  // The real bug this guards: Number(null) === 0, and 0 < 30 is "oversold".
  const res = run(cond({ reading: "rsi" }, CONDITION_OP.LT, { value: 30 }), {});
  assert.equal(res.value, TRUTH.UNKNOWN);
  assert.equal(res.matched, null);
  assert.equal(res.status, STRATEGY_STATUS.FIELD_UNAVAILABLE);
  assert.equal(res.observations, 0);
});

test("every non-VALID status makes the condition UNKNOWN and is reported verbatim", () => {
  for (const [name, status] of [
    ["thin", INDICATOR_STATUS.INSUFFICIENT_HISTORY],
    ["stale", INDICATOR_STATUS.DATA_STALE],
    ["gapped", INDICATOR_STATUS.DATA_CONFLICT],
    ["unavailable", INDICATOR_STATUS.FIELD_UNAVAILABLE],
  ]) {
    const res = run(cond({ reading: name }, CONDITION_OP.GT, { value: 0 }));
    assert.equal(res.value, TRUTH.UNKNOWN, name);
    assert.equal(res.status, status, name);
    assert.equal(res.blockers[0].status, status, name);
  }
});

test("a VALID reading carrying a null value is still UNKNOWN", () => {
  const res = run(cond({ reading: "hollow" }, CONDITION_OP.GT, { value: 0 }));
  assert.equal(res.value, TRUTH.UNKNOWN);
  assert.equal(res.status, STRATEGY_STATUS.FIELD_UNAVAILABLE);
});

test("null readings maps produce UNKNOWN rather than throwing or matching", () => {
  // Called directly: the `run` helper defaults an undefined readings map.
  for (const readings of [null, undefined, [], 7]) {
    const res = evaluateStrategy(strat(LEAF.TRUE()), readings);
    assert.equal(res.value, TRUTH.UNKNOWN, String(readings));
    assert.equal(res.status, STRATEGY_STATUS.FIELD_UNAVAILABLE, String(readings));
  }
});

// ── operands: constants, other readings, sub-fields ──────────────────────────────

test("comparisons run against another indicator, not only constants", () => {
  const readings = { close: reading(520), sma: reading(510.5) };
  assert.equal(valueOf(cond({ reading: "close" }, CONDITION_OP.GT, { reading: "sma" }), readings), TRUTH.TRUE);
  assert.equal(valueOf(cond({ reading: "sma" }, CONDITION_OP.GT, { reading: "close" }), readings), TRUTH.FALSE);
});

test("a comparison against an unreadable second indicator is UNKNOWN", () => {
  const res = run(cond({ reading: "rsi" }, CONDITION_OP.GT, { reading: "thin" }));
  assert.equal(res.value, TRUTH.UNKNOWN);
  assert.equal(res.blockers[0].reading, "thin");
});

test("multi-field readings are addressed by field", () => {
  assert.equal(valueOf(cond({ reading: "macd", field: "histogram" }, CONDITION_OP.GT, { value: 0 })), TRUTH.TRUE);
  assert.equal(valueOf(cond({ reading: "macd", field: "macd" }, CONDITION_OP.GT, { reading: "macd", field: "signal" })), TRUTH.TRUE);
});

test("an absent sub-field is UNKNOWN, not zero", () => {
  // Bollinger %B is null when the bands collapse; 0 would read as "at the lower band".
  const res = run(cond({ reading: "bollinger", field: "percentB" }, CONDITION_OP.LTE, { value: 0 }));
  assert.equal(res.value, TRUTH.UNKNOWN);
  assert.equal(res.status, STRATEGY_STATUS.FIELD_UNAVAILABLE);
});

test("asking for a field on a scalar reading is UNKNOWN, not a silent read of the scalar", () => {
  assert.equal(valueOf(cond({ reading: "rsi", field: "histogram" }, CONDITION_OP.GT, { value: 0 })), TRUTH.UNKNOWN);
});

test("comparison operators behave at their boundaries", () => {
  const r = { a: reading(10), b: reading(10) };
  const c = (op) => valueOf(cond({ reading: "a" }, op, { reading: "b" }), r);
  assert.equal(c(CONDITION_OP.GT), TRUTH.FALSE);
  assert.equal(c(CONDITION_OP.GTE), TRUTH.TRUE);
  assert.equal(c(CONDITION_OP.LT), TRUTH.FALSE);
  assert.equal(c(CONDITION_OP.LTE), TRUTH.TRUE);
  assert.equal(c(CONDITION_OP.EQ), TRUTH.TRUE);
});

test("eq absorbs float representation error but not real differences", () => {
  const near = { a: reading(0.1 + 0.2), b: reading(0.3) };
  assert.equal(valueOf(cond({ reading: "a" }, CONDITION_OP.EQ, { reading: "b" }), near), TRUTH.TRUE);
  const apart = { a: reading(0.3 + EQUALITY_TOLERANCE * 100), b: reading(0.3) };
  assert.equal(valueOf(cond({ reading: "a" }, CONDITION_OP.EQ, { reading: "b" }), apart), TRUTH.FALSE);
});

test("between is inclusive on both bounds and accepts indicator bounds", () => {
  const r = { rsi: reading(30), lo: reading(30), hi: reading(70) };
  const bounds = (l, h) => cond({ reading: "rsi" }, CONDITION_OP.BETWEEN, [l, h]);
  assert.equal(valueOf(bounds({ value: 30 }, { value: 70 }), r), TRUTH.TRUE);
  assert.equal(valueOf(bounds({ value: 31 }, { value: 70 }), r), TRUTH.FALSE);
  assert.equal(valueOf(bounds({ reading: "lo" }, { reading: "hi" }), r), TRUTH.TRUE);
});

test("between with an unreadable bound is UNKNOWN", () => {
  const node = cond({ reading: "rsi" }, CONDITION_OP.BETWEEN, [{ value: 30 }, { reading: "thin" }]);
  const res = run(node);
  assert.equal(res.value, TRUTH.UNKNOWN);
  assert.equal(res.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
});

// ── crossings ────────────────────────────────────────────────────────────────────

const CUR = { fast: reading(11), slow: reading(10) };
const PREV = { fast: reading(9), slow: reading(10) };
const crossUp = () => cond({ reading: "fast" }, CONDITION_OP.CROSSES_ABOVE, { reading: "slow" });
const crossDown = () => cond({ reading: "fast" }, CONDITION_OP.CROSSES_BELOW, { reading: "slow" });

test("crossesAbove is TRUE only when the previous bar was not already above", () => {
  assert.equal(valueOf(crossUp(), CUR, PREV), TRUTH.TRUE);
  // already above on both bars: no crossing happened
  assert.equal(valueOf(crossUp(), CUR, { fast: reading(10.5), slow: reading(10) }), TRUTH.FALSE);
  // touching then breaking out still counts as a cross
  assert.equal(valueOf(crossUp(), CUR, { fast: reading(10), slow: reading(10) }), TRUTH.TRUE);
});

test("crossesBelow mirrors crossesAbove", () => {
  const cur = { fast: reading(9), slow: reading(10) };
  assert.equal(valueOf(crossDown(), cur, { fast: reading(11), slow: reading(10) }), TRUTH.TRUE);
  assert.equal(valueOf(crossDown(), cur, { fast: reading(9.5), slow: reading(10) }), TRUTH.FALSE);
  assert.equal(valueOf(crossDown(), CUR, PREV), TRUTH.FALSE);
});

test("a crossing without previous readings is UNKNOWN, never false", () => {
  for (const prev of [undefined, null]) {
    const res = run(crossUp(), CUR, prev);
    assert.equal(res.value, TRUTH.UNKNOWN);
    assert.equal(res.matched, null);
    assert.equal(res.status, INDICATOR_STATUS.INSUFFICIENT_HISTORY);
    assert.match(res.blockers[0].reason, /previous reading/);
  }
});

test("a crossing whose previous frame is unreadable is UNKNOWN", () => {
  const res = run(crossUp(), CUR, { fast: reading(null, INDICATOR_STATUS.INSUFFICIENT_HISTORY, 2), slow: reading(10) });
  assert.equal(res.value, TRUTH.UNKNOWN);
  assert.equal(res.blockers.some((b) => b.reason.includes("previous")), true);
  // missing previous frames must not be mistaken for a missing current frame
  assert.equal(res.blockers.every((b) => b.status !== undefined), true);
});

test("crossings compare against constants too", () => {
  const node = cond({ reading: "rsi" }, CONDITION_OP.CROSSES_ABOVE, { value: 70 });
  assert.equal(valueOf(node, { rsi: reading(71) }, { rsi: reading(69) }), TRUTH.TRUE);
  assert.equal(valueOf(node, { rsi: reading(71) }, { rsi: reading(70.5) }), TRUTH.FALSE);
});

test("prevReadings supplied to a strategy with no crossing changes nothing", () => {
  assert.equal(valueOf(LEAF.TRUE(), READINGS, READINGS), TRUTH.TRUE);
});

// ── nesting ──────────────────────────────────────────────────────────────────────

test("groups nest and UNKNOWN survives several levels", () => {
  const tree = group(GROUP_OP.ALL,
    LEAF.TRUE(),
    group(GROUP_OP.ANY,
      LEAF.FALSE(),
      group(GROUP_OP.NONE, LEAF.UNKNOWN())));
  // none([UNKNOWN]) = UNKNOWN -> any([FALSE, UNKNOWN]) = UNKNOWN -> all([TRUE, UNKNOWN]) = UNKNOWN
  assert.equal(valueOf(tree), TRUTH.UNKNOWN);
});

test("a nested certainty still decides the tree", () => {
  const tree = group(GROUP_OP.ALL,
    LEAF.TRUE(),
    group(GROUP_OP.ANY, LEAF.UNKNOWN(), LEAF.TRUE()),
    group(GROUP_OP.NONE, LEAF.FALSE()));
  const res = run(tree);
  assert.equal(res.value, TRUTH.TRUE);
  assert.equal(res.matched, true);
  assert.equal(res.status, STRATEGY_STATUS.VALID);
});

test("blocker paths point at the failing node inside the tree", () => {
  const tree = group(GROUP_OP.ALL, LEAF.TRUE(), group(GROUP_OP.ANY, LEAF.UNKNOWN()));
  const res = run(tree);
  assert.equal(res.blockers[0].path, "root.children[1].children[0].left");
});

test("a realistic multi-condition strategy evaluates end to end", () => {
  const tree = group(GROUP_OP.ALL,
    cond({ reading: "rsi" }, CONDITION_OP.BETWEEN, [{ value: 30 }, { value: 70 }]),
    cond({ reading: "macd", field: "histogram" }, CONDITION_OP.GT, { value: 0 }),
    group(GROUP_OP.NONE, cond({ reading: "sma" }, CONDITION_OP.LT, { value: 100 })));
  const res = run(tree);
  assert.equal(res.matched, true);
  assert.equal(res.status, STRATEGY_STATUS.VALID);
  assert.equal(res.observations, 3); // rsi, macd.histogram, sma — the constants are not observations
  assert.equal(res.readingObservations, 90); // the thinnest reading behind the answer (sma)
  assert.deepEqual(res.blockers, []);
});

// ── validation: a strategy that cannot run must fail when it is saved ────────────

const codes = (s) => validateStrategy(s).errors.map((e) => e.code);

test("a well-formed strategy validates", () => {
  const v = validateStrategy(strat(group(GROUP_OP.ALL, LEAF.TRUE(), LEAF.FALSE()), "Momentum"));
  assert.equal(v.valid, true);
  assert.deepEqual(v.errors, []);
  assert.equal(v.depth, 2);
});

test("an unknown condition operator is rejected", () => {
  const bad = strat(cond({ reading: "rsi" }, "approximately", { value: 30 }));
  assert.equal(validateStrategy(bad).valid, false);
  assert.deepEqual(codes(bad), [VALIDATION_ERROR.UNKNOWN_OPERATOR]);
});

test("an unknown group operator is rejected", () => {
  const bad = strat({ type: NODE_TYPE.GROUP, op: "most", children: [LEAF.TRUE()] });
  assert.deepEqual(codes(bad), [VALIDATION_ERROR.UNKNOWN_OPERATOR]);
});

test("an unknown node type is rejected", () => {
  assert.deepEqual(codes(strat({ type: "formula", op: "gt" })), [VALIDATION_ERROR.UNKNOWN_NODE_TYPE]);
  assert.deepEqual(codes(strat({ op: CONDITION_OP.GT })), [VALIDATION_ERROR.UNKNOWN_NODE_TYPE]);
});

test("missing operands are rejected", () => {
  assert.deepEqual(codes(strat(cond(undefined, CONDITION_OP.GT, { value: 1 }))), [VALIDATION_ERROR.MISSING_OPERAND]);
  assert.deepEqual(codes(strat(cond({ reading: "rsi" }, CONDITION_OP.GT, undefined))), [VALIDATION_ERROR.MISSING_OPERAND]);
  assert.deepEqual(codes(strat(cond({}, CONDITION_OP.GT, { value: 1 }))), [VALIDATION_ERROR.MISSING_OPERAND]);
});

test("a constant that is not a finite number is rejected before it can become 0", () => {
  for (const value of [null, "", "30", undefined, NaN, Infinity, {}, true]) {
    const bad = strat(cond({ reading: "rsi" }, CONDITION_OP.LT, { kind: "constant", value }));
    assert.equal(validateStrategy(bad).valid, false, `constant ${String(value)} was accepted`);
  }
});

test("an ambiguous operand naming both a reading and a value is rejected", () => {
  const bad = strat(cond({ reading: "rsi", value: 30 }, CONDITION_OP.GT, { value: 1 }));
  assert.deepEqual(codes(bad), [VALIDATION_ERROR.INVALID_OPERAND]);
});

test("a reading operand needs a name and a string field", () => {
  assert.deepEqual(codes(strat(cond({ reading: "" }, CONDITION_OP.GT, { value: 1 }))), [VALIDATION_ERROR.INVALID_OPERAND]);
  assert.deepEqual(codes(strat(cond({ reading: "macd", field: 3 }, CONDITION_OP.GT, { value: 1 }))), [VALIDATION_ERROR.INVALID_OPERAND]);
});

test("between needs exactly two bounds, and they must not be inverted", () => {
  const one = strat(cond({ reading: "rsi" }, CONDITION_OP.BETWEEN, [{ value: 30 }]));
  assert.deepEqual(codes(one), [VALIDATION_ERROR.MISSING_OPERAND]);
  const scalar = strat(cond({ reading: "rsi" }, CONDITION_OP.BETWEEN, { value: 30 }));
  assert.deepEqual(codes(scalar), [VALIDATION_ERROR.MISSING_OPERAND]);
  const inverted = strat(cond({ reading: "rsi" }, CONDITION_OP.BETWEEN, [{ value: 70 }, { value: 30 }]));
  assert.deepEqual(codes(inverted), [VALIDATION_ERROR.INVALID_BOUNDS]);
});

test("only between may carry a pair of operands", () => {
  const bad = strat(cond({ reading: "rsi" }, CONDITION_OP.GT, [{ value: 30 }, { value: 70 }]));
  assert.deepEqual(codes(bad), [VALIDATION_ERROR.INVALID_OPERAND]);
});

test("an empty group is rejected rather than silently answering", () => {
  assert.deepEqual(codes(strat(group(GROUP_OP.ALL))), [VALIDATION_ERROR.EMPTY_GROUP]);
  assert.deepEqual(codes(strat({ type: NODE_TYPE.GROUP, op: GROUP_OP.ANY })), [VALIDATION_ERROR.EMPTY_GROUP]);
});

test("a strategy needs a name and a root", () => {
  assert.deepEqual(codes({ root: LEAF.TRUE() }), [VALIDATION_ERROR.MISSING_NAME]);
  assert.deepEqual(codes({ name: "S" }), [VALIDATION_ERROR.MISSING_ROOT]);
  assert.deepEqual(codes(null), [VALIDATION_ERROR.MISSING_STRATEGY]);
  assert.deepEqual(codes([]), [VALIDATION_ERROR.MISSING_STRATEGY]);
});

/** Build a chain of nested all-groups `levels` deep, ending in a leaf. */
function chain(levels) {
  let node = LEAF.TRUE();
  for (let i = 1; i < levels; i += 1) node = group(GROUP_OP.ALL, node);
  return node;
}

test("a tree at the documented depth limit is accepted and one deeper is not", () => {
  const ok = validateStrategy(strat(chain(MAX_STRATEGY_DEPTH)));
  assert.equal(ok.valid, true);
  assert.equal(ok.depth, MAX_STRATEGY_DEPTH);
  const tooDeep = strat(chain(MAX_STRATEGY_DEPTH + 1));
  assert.deepEqual(codes(tooDeep), [VALIDATION_ERROR.MAX_DEPTH_EXCEEDED]);
});

test("a cycle is reported as a cycle and does not hang validation", () => {
  const root = group(GROUP_OP.ALL, LEAF.TRUE());
  root.children.push(root); // the saved tree refers back to itself
  assert.deepEqual(codes(strat(root)), [VALIDATION_ERROR.CYCLE]);

  const indirect = group(GROUP_OP.ANY, group(GROUP_OP.ALL, LEAF.TRUE()));
  indirect.children[0].children.push(indirect);
  assert.deepEqual(codes(strat(indirect)), [VALIDATION_ERROR.CYCLE]);
});

test("re-using one node as two siblings is a shared subtree, not a cycle", () => {
  const shared = LEAF.TRUE();
  assert.equal(validateStrategy(strat(group(GROUP_OP.ALL, shared, shared))).valid, true);
});

test("every error carries the path of the node that broke", () => {
  const bad = strat(group(GROUP_OP.ALL, LEAF.TRUE(), cond({ reading: "rsi" }, "nope", { value: 1 })));
  const [err] = validateStrategy(bad).errors;
  assert.equal(err.path, "root.children[1]");
  assert.equal(typeof err.message, "string");
});

test("validation reports every problem, not only the first", () => {
  const bad = { root: group(GROUP_OP.ALL, cond({}, "nope", undefined), group(GROUP_OP.ANY)) };
  const found = codes(bad);
  assert.equal(found.includes(VALIDATION_ERROR.MISSING_NAME), true);
  assert.equal(found.includes(VALIDATION_ERROR.UNKNOWN_OPERATOR), true);
  assert.equal(found.includes(VALIDATION_ERROR.EMPTY_GROUP), true);
});

// ── evaluating an invalid strategy ───────────────────────────────────────────────

test("an invalid strategy evaluates to UNKNOWN with INVALID_STRATEGY, never to false", () => {
  const bad = strat(cond({ reading: "rsi" }, "approximately", { value: 30 }));
  const res = evaluateStrategy(bad, READINGS, READINGS);
  assert.equal(res.value, TRUTH.UNKNOWN);
  assert.equal(res.matched, null);
  assert.equal(res.status, STRATEGY_STATUS.INVALID_STRATEGY);
  assert.equal(res.errors[0].code, VALIDATION_ERROR.UNKNOWN_OPERATOR);
  assert.equal(res.observations, 0);
  assert.equal(res.readingObservations, null);
});

test("a cyclic strategy is refused by the evaluator rather than walked", () => {
  const root = group(GROUP_OP.ALL, LEAF.TRUE());
  root.children.push(root);
  const res = evaluateStrategy(strat(root), READINGS);
  assert.equal(res.status, STRATEGY_STATUS.INVALID_STRATEGY);
  assert.equal(res.matched, null);
});

test("the strategy status vocabulary extends the indicator vocabulary verbatim", () => {
  for (const [k, v] of Object.entries(INDICATOR_STATUS)) assert.equal(STRATEGY_STATUS[k], v);
  assert.equal(STRATEGY_STATUS.VALID, INDICATOR_STATUS.VALID);
});

// ── result shape ─────────────────────────────────────────────────────────────────

test("every result carries a status and the observation count behind it", () => {
  const res = run(cond({ reading: "rsi" }, CONDITION_OP.GT, { reading: "sma" }));
  assert.equal(res.strategy, "S");
  assert.equal(res.status, STRATEGY_STATUS.VALID);
  assert.equal(res.observations, 2);
  assert.equal(res.readingObservations, 90); // the thinner of rsi (400) and sma (90)
  assert.deepEqual(res.errors, []);
});

test("observation counts ignore readings that could not be used", () => {
  const res = run(group(GROUP_OP.ANY, LEAF.TRUE(), LEAF.UNKNOWN()));
  assert.equal(res.observations, 1);
  assert.equal(res.readingObservations, 120);
});

// ── description ──────────────────────────────────────────────────────────────────

test("describeStrategy renders a nested strategy in readable text", () => {
  const tree = group(GROUP_OP.ALL,
    cond({ reading: "rsi" }, CONDITION_OP.BETWEEN, [{ value: 30 }, { value: 70 }]),
    cond({ reading: "macd", field: "histogram" }, CONDITION_OP.CROSSES_ABOVE, { value: 0 }),
    group(GROUP_OP.NONE, cond({ reading: "ema" }, CONDITION_OP.LT, { reading: "sma" })));
  assert.equal(
    describeStrategy(strat(tree, "Momentum turn")),
    "Momentum turn: all of (RSI between 30 and 70, MACD.histogram crosses above 0, none of (EMA < SMA))",
  );
});

test("describeStrategy renders each operator distinctly", () => {
  const one = (op) => describeStrategy(strat(cond({ reading: "rsi" }, op, { value: 5 }), "x"));
  assert.equal(one(CONDITION_OP.GT), "x: RSI > 5");
  assert.equal(one(CONDITION_OP.GTE), "x: RSI >= 5");
  assert.equal(one(CONDITION_OP.LT), "x: RSI < 5");
  assert.equal(one(CONDITION_OP.LTE), "x: RSI <= 5");
  assert.equal(one(CONDITION_OP.EQ), "x: RSI = 5");
  assert.equal(one(CONDITION_OP.CROSSES_BELOW), "x: RSI crosses below 5");
});

test("an unlabelled reading is described by its own name", () => {
  const s = strat(cond({ reading: "customScore" }, CONDITION_OP.GT, { value: 1 }), "x");
  assert.equal(describeStrategy(s), "x: customScore > 1");
});

test("describeStrategy refuses to render an unrunnable strategy as if it worked", () => {
  const bad = strat(cond({ reading: "rsi" }, "approximately", { value: 30 }), "Broken");
  assert.equal(describeStrategy(bad), "Broken: invalid strategy (UNKNOWN_OPERATOR at root)");
  assert.match(describeStrategy(null), /invalid strategy/);
  assert.match(describeStrategy({ root: LEAF.TRUE() }), /^\(unnamed strategy\): invalid strategy/);
});

// ── purity ───────────────────────────────────────────────────────────────────────

test("evaluation mutates neither the strategy nor the readings", () => {
  const tree = group(GROUP_OP.ALL, LEAF.TRUE(), LEAF.UNKNOWN());
  const strategy = strat(tree, "Frozen");
  const beforeStrategy = JSON.stringify(strategy);
  const beforeReadings = JSON.stringify(READINGS);
  evaluateStrategy(strategy, READINGS, READINGS);
  validateStrategy(strategy);
  describeStrategy(strategy);
  assert.equal(JSON.stringify(strategy), beforeStrategy);
  assert.equal(JSON.stringify(READINGS), beforeReadings);
});

test("evaluation is deterministic across repeated runs", () => {
  const tree = group(GROUP_OP.ANY, LEAF.UNKNOWN(), LEAF.FALSE());
  const a = run(tree);
  const b = run(tree);
  assert.deepEqual(a, b);
});
