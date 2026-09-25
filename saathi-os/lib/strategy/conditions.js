// Strategy builder — the condition model behind "unlimited saved conditions". PURE.
//
// A strategy is a named tree evaluated against one symbol's typed readings (the
// output of computeIndicators). Three rules shape every decision in this file:
//
//   1. THREE-VALUED, NEVER TWO. A condition over a reading that is not VALID is
//      UNKNOWN, not false. Two-valued logic would turn "we could not tell" into
//      "did not match" — a scan that silently drops the symbols it failed to read
//      still looks like a working scan, which is the worst possible failure here.
//      UNKNOWN therefore propagates by Kleene's rules and surfaces as matched:null.
//
//   2. A BROKEN STRATEGY FAILS WHEN IT IS SAVED. validateStrategy rejects unknown
//      operators, missing/ambiguous operands, empty groups, cycles and over-deep
//      trees. Deferring those to run time would produce a strategy that returns
//      "no matches" forever and never explains why.
//
//   3. NO COERCION. Every operand is rejected as unusable BEFORE any arithmetic,
//      because Number(null) === 0 and Number("") === 0 — an absent RSI must never
//      arrive at the comparator as a maximally oversold 0.

import { INDICATOR_STATUS } from "../nepse/indicators.js";

/** Leaf comparison operators. */
export const CONDITION_OP = {
  GT: "gt",
  GTE: "gte",
  LT: "lt",
  LTE: "lte",
  EQ: "eq",
  BETWEEN: "between",
  CROSSES_ABOVE: "crossesAbove",
  CROSSES_BELOW: "crossesBelow",
};

/** Boolean group operators. Nestable, evaluated with Kleene three-valued logic. */
export const GROUP_OP = { ALL: "all", ANY: "any", NONE: "none" };

export const NODE_TYPE = { GROUP: "group", CONDITION: "condition" };

/** The third value is a first-class outcome, not an error. */
export const TRUTH = { TRUE: "TRUE", FALSE: "FALSE", UNKNOWN: "UNKNOWN" };

/**
 * The indicator vocabulary verbatim, plus the one condition the indicator layer
 * cannot express: the saved tree itself is unusable, independent of any data.
 */
export const STRATEGY_STATUS = {
  ...INDICATOR_STATUS,
  INVALID_STRATEGY: "INVALID_STRATEGY",
};

export const VALIDATION_ERROR = {
  MISSING_STRATEGY: "MISSING_STRATEGY",
  MISSING_NAME: "MISSING_NAME",
  MISSING_ROOT: "MISSING_ROOT",
  UNKNOWN_NODE_TYPE: "UNKNOWN_NODE_TYPE",
  UNKNOWN_OPERATOR: "UNKNOWN_OPERATOR",
  MISSING_OPERAND: "MISSING_OPERAND",
  INVALID_OPERAND: "INVALID_OPERAND",
  INVALID_BOUNDS: "INVALID_BOUNDS",
  EMPTY_GROUP: "EMPTY_GROUP",
  MAX_DEPTH_EXCEEDED: "MAX_DEPTH_EXCEEDED",
  CYCLE: "CYCLE",
};

/**
 * Documented nesting limit; the root counts as depth 1. Eight levels is far more
 * than any readable screen and keeps a hand-edited (or corrupted) saved strategy
 * from turning evaluation into an unbounded walk.
 */
export const MAX_STRATEGY_DEPTH = 8;

/**
 * Indicator values are published rounded to 4 decimals, so an `eq` written against
 * a displayed number would fail on the last binary place of a float. The tolerance
 * is far tighter than that rounding, so it never merges two genuinely distinct
 * published values — it only absorbs representation error.
 */
export const EQUALITY_TOLERANCE = 1e-9;

const CONDITION_OPS = new Set(Object.values(CONDITION_OP));
const GROUP_OPS = new Set(Object.values(GROUP_OP));
const CROSSING_OPS = new Set([CONDITION_OP.CROSSES_ABOVE, CONDITION_OP.CROSSES_BELOW]);

/** True only for a real, finite JS number — strings and null never qualify. */
const isFiniteNumber = (v) => typeof v === "number" && Number.isFinite(v);

const isPlainObject = (v) => typeof v === "object" && v !== null && !Array.isArray(v);

const nonEmptyString = (v) => typeof v === "string" && v.trim() !== "";

// ── validation (runs at save time; evaluation re-runs it and refuses to guess) ────

function operandKind(operand) {
  if (nonEmptyString(operand.kind)) return operand.kind;
  const hasReading = Object.prototype.hasOwnProperty.call(operand, "reading");
  const hasValue = Object.prototype.hasOwnProperty.call(operand, "value");
  if (hasReading && hasValue) return "ambiguous"; // two sources, no way to pick one
  if (hasReading) return "reading";
  if (hasValue) return "constant";
  return null;
}

function validateOperand(operand, path, errors) {
  if (operand === null || operand === undefined) {
    errors.push({ code: VALIDATION_ERROR.MISSING_OPERAND, path, message: "operand is required" });
    return null;
  }
  if (!isPlainObject(operand)) {
    errors.push({ code: VALIDATION_ERROR.INVALID_OPERAND, path, message: "operand must be an object" });
    return null;
  }
  const kind = operandKind(operand);
  if (kind === null) {
    errors.push({
      code: VALIDATION_ERROR.MISSING_OPERAND, path,
      message: "operand must name a reading or carry a constant value",
    });
    return null;
  }
  if (kind === "ambiguous") {
    errors.push({
      code: VALIDATION_ERROR.INVALID_OPERAND, path,
      message: "operand carries both a reading and a constant value",
    });
    return null;
  }
  if (kind === "constant") {
    // Rejected here, before any comparator sees it: Number(null) and Number("")
    // are both 0, and a 0 threshold silently matches instead of failing loudly.
    if (!isFiniteNumber(operand.value)) {
      errors.push({
        code: VALIDATION_ERROR.INVALID_OPERAND, path,
        message: "constant operand must be a finite number (no strings, no null)",
      });
      return null;
    }
    return { kind: "constant", value: operand.value };
  }
  if (kind === "reading") {
    if (!nonEmptyString(operand.reading)) {
      errors.push({
        code: VALIDATION_ERROR.INVALID_OPERAND, path,
        message: "reading operand must name a reading",
      });
      return null;
    }
    if (operand.field !== undefined && !nonEmptyString(operand.field)) {
      errors.push({
        code: VALIDATION_ERROR.INVALID_OPERAND, path,
        message: "reading operand field must be a non-empty string when present",
      });
      return null;
    }
    return { kind: "reading", reading: operand.reading, field: operand.field };
  }
  errors.push({ code: VALIDATION_ERROR.INVALID_OPERAND, path, message: `unknown operand kind "${kind}"` });
  return null;
}

function validateCondition(node, path, errors) {
  if (!CONDITION_OPS.has(node.op)) {
    errors.push({
      code: VALIDATION_ERROR.UNKNOWN_OPERATOR, path,
      message: `unknown condition operator "${String(node.op)}"`,
    });
    return;
  }
  validateOperand(node.left, `${path}.left`, errors);

  if (node.op === CONDITION_OP.BETWEEN) {
    if (!Array.isArray(node.right) || node.right.length !== 2) {
      errors.push({
        code: VALIDATION_ERROR.MISSING_OPERAND, path: `${path}.right`,
        message: "between requires exactly two bound operands [low, high]",
      });
      return;
    }
    const low = validateOperand(node.right[0], `${path}.right[0]`, errors);
    const high = validateOperand(node.right[1], `${path}.right[1]`, errors);
    // Inverted constant bounds can never match. That is not a data problem the
    // evaluator should report every run — it is a broken saved strategy.
    if (low?.kind === "constant" && high?.kind === "constant" && low.value > high.value) {
      errors.push({
        code: VALIDATION_ERROR.INVALID_BOUNDS, path: `${path}.right`,
        message: `between bounds are inverted (${low.value} > ${high.value}) and can never match`,
      });
    }
    return;
  }

  if (Array.isArray(node.right)) {
    errors.push({
      code: VALIDATION_ERROR.INVALID_OPERAND, path: `${path}.right`,
      message: `only between takes a pair of operands, not "${node.op}"`,
    });
    return;
  }
  validateOperand(node.right, `${path}.right`, errors);
}

function walkNode(node, path, depth, ancestors, errors, ctx) {
  if (!isPlainObject(node)) {
    errors.push({ code: VALIDATION_ERROR.UNKNOWN_NODE_TYPE, path, message: "node must be an object" });
    return;
  }
  // Checked before the depth limit so a self-referencing tree is reported as the
  // cycle it is, rather than as an over-deep one.
  if (ancestors.has(node)) {
    errors.push({ code: VALIDATION_ERROR.CYCLE, path, message: "node is its own ancestor" });
    return;
  }
  if (depth > MAX_STRATEGY_DEPTH) {
    errors.push({
      code: VALIDATION_ERROR.MAX_DEPTH_EXCEEDED, path,
      message: `tree is deeper than the ${MAX_STRATEGY_DEPTH}-level limit`,
    });
    return;
  }
  ctx.depth = Math.max(ctx.depth, depth);

  if (node.type === NODE_TYPE.CONDITION) {
    validateCondition(node, path, errors);
    return;
  }
  if (node.type === NODE_TYPE.GROUP) {
    if (!GROUP_OPS.has(node.op)) {
      errors.push({
        code: VALIDATION_ERROR.UNKNOWN_OPERATOR, path,
        message: `unknown group operator "${String(node.op)}"`,
      });
      return;
    }
    if (!Array.isArray(node.children) || node.children.length === 0) {
      errors.push({
        code: VALIDATION_ERROR.EMPTY_GROUP, path,
        message: `${node.op} group has no children to evaluate`,
      });
      return;
    }
    ancestors.add(node);
    node.children.forEach((child, i) => {
      walkNode(child, `${path}.children[${i}]`, depth + 1, ancestors, errors, ctx);
    });
    ancestors.delete(node);
    return;
  }
  errors.push({
    code: VALIDATION_ERROR.UNKNOWN_NODE_TYPE, path,
    message: `node type must be "group" or "condition", got "${String(node.type)}"`,
  });
}

/**
 * @returns {{valid:boolean, errors:Array<{code:string,path:string,message:string}>, depth:number}}
 */
export function validateStrategy(strategy) {
  const errors = [];
  if (!isPlainObject(strategy)) {
    errors.push({ code: VALIDATION_ERROR.MISSING_STRATEGY, path: "", message: "strategy must be an object" });
    return { valid: false, errors, depth: 0 };
  }
  if (!nonEmptyString(strategy.name)) {
    errors.push({ code: VALIDATION_ERROR.MISSING_NAME, path: "name", message: "strategy needs a name" });
  }
  const ctx = { depth: 0 };
  if (strategy.root === null || strategy.root === undefined) {
    errors.push({ code: VALIDATION_ERROR.MISSING_ROOT, path: "root", message: "strategy needs a root node" });
  } else {
    walkNode(strategy.root, "root", 1, new Set(), errors, ctx);
  }
  return { valid: errors.length === 0, errors, depth: ctx.depth };
}

// ── evaluation ───────────────────────────────────────────────────────────────────

function blocked(ctx, path, status, reason, reading = null) {
  ctx.blockers.push({ path, reading, status, reason });
  return null;
}

/**
 * Resolve one operand against one frame of readings. Returns a finite number, or
 * null having recorded WHY — the caller turns that null into UNKNOWN, never 0.
 */
function resolveOperand(operand, readings, path, ctx, frame) {
  if (operand.kind === "constant") return operand.value;

  const label = operand.field ? `${operand.reading}.${operand.field}` : operand.reading;
  if (!isPlainObject(readings)) {
    return blocked(ctx, path, STRATEGY_STATUS.FIELD_UNAVAILABLE,
      `no ${frame} readings supplied`, label);
  }
  const res = readings[operand.reading];
  if (res === null || res === undefined) {
    return blocked(ctx, path, STRATEGY_STATUS.FIELD_UNAVAILABLE,
      `${frame} readings carry no "${operand.reading}"`, label);
  }
  // Anything short of VALID — stale, thin history, a corporate action in the
  // window — is a reading we are not entitled to compare against.
  if (res.status !== STRATEGY_STATUS.VALID) {
    return blocked(ctx, path, res.status ?? STRATEGY_STATUS.FIELD_UNAVAILABLE,
      `${frame} "${operand.reading}" status is ${String(res.status)}`, label);
  }

  let raw = res.value;
  if (operand.field !== undefined) {
    if (!isPlainObject(raw)) {
      return blocked(ctx, path, STRATEGY_STATUS.FIELD_UNAVAILABLE,
        `${frame} "${operand.reading}" is not a multi-field reading`, label);
    }
    raw = raw[operand.field];
  }
  // A VALID result whose value is null (or an absent sub-field like a collapsed
  // Bollinger %B) is still nothing to compare — reject it before any arithmetic.
  if (raw === null || raw === undefined || raw === "") {
    return blocked(ctx, path, STRATEGY_STATUS.FIELD_UNAVAILABLE,
      `${frame} "${label}" has no value`, label);
  }
  if (!isFiniteNumber(raw)) {
    return blocked(ctx, path, STRATEGY_STATUS.FIELD_UNAVAILABLE,
      `${frame} "${label}" is not a finite number`, label);
  }

  ctx.resolved += 1;
  const obs = res.observations;
  if (isFiniteNumber(obs)) {
    ctx.minObservations = ctx.minObservations === null ? obs : Math.min(ctx.minObservations, obs);
  }
  return raw;
}

function compare(op, left, right) {
  switch (op) {
    case CONDITION_OP.GT: return left > right;
    case CONDITION_OP.GTE: return left >= right;
    case CONDITION_OP.LT: return left < right;
    case CONDITION_OP.LTE: return left <= right;
    case CONDITION_OP.EQ: return Math.abs(left - right) <= EQUALITY_TOLERANCE;
    default: return false;
  }
}

function evalCondition(node, path, readings, prevReadings, ctx) {
  const errors = [];
  const left = validateOperand(node.left, `${path}.left`, errors);
  if (!left || errors.length) return TRUTH.UNKNOWN; // unreachable once validated

  if (node.op === CONDITION_OP.BETWEEN) {
    const low = validateOperand(node.right[0], `${path}.right[0]`, errors);
    const high = validateOperand(node.right[1], `${path}.right[1]`, errors);
    const l = resolveOperand(left, readings, `${path}.left`, ctx, "current");
    const lo = resolveOperand(low, readings, `${path}.right[0]`, ctx, "current");
    const hi = resolveOperand(high, readings, `${path}.right[1]`, ctx, "current");
    if (l === null || lo === null || hi === null) return TRUTH.UNKNOWN;
    return l >= lo && l <= hi ? TRUTH.TRUE : TRUTH.FALSE;
  }

  const right = validateOperand(node.right, `${path}.right`, errors);
  if (!right) return TRUTH.UNKNOWN;

  if (CROSSING_OPS.has(node.op)) {
    // A cross is a statement about two bars. Without the previous bar we do not
    // know whether one happened — that is UNKNOWN, and reporting false instead
    // would quietly hide every cross on the first evaluation of a symbol.
    if (prevReadings === null || prevReadings === undefined) {
      blocked(ctx, path, STRATEGY_STATUS.INSUFFICIENT_HISTORY,
        `${node.op} needs the previous reading and none was supplied`);
      return TRUTH.UNKNOWN;
    }
    const curL = resolveOperand(left, readings, `${path}.left`, ctx, "current");
    const curR = resolveOperand(right, readings, `${path}.right`, ctx, "current");
    const prevL = resolveOperand(left, prevReadings, `${path}.left`, ctx, "previous");
    const prevR = resolveOperand(right, prevReadings, `${path}.right`, ctx, "previous");
    if (curL === null || curR === null || prevL === null || prevR === null) return TRUTH.UNKNOWN;
    const crossed = node.op === CONDITION_OP.CROSSES_ABOVE
      ? prevL <= prevR && curL > curR
      : prevL >= prevR && curL < curR;
    return crossed ? TRUTH.TRUE : TRUTH.FALSE;
  }

  const l = resolveOperand(left, readings, `${path}.left`, ctx, "current");
  const r = resolveOperand(right, readings, `${path}.right`, ctx, "current");
  if (l === null || r === null) return TRUTH.UNKNOWN;
  return compare(node.op, l, r) ? TRUTH.TRUE : TRUTH.FALSE;
}

/** Kleene combination. Children are ALL evaluated so every blocker is recorded. */
function combine(op, results) {
  const hasTrue = results.includes(TRUTH.TRUE);
  const hasFalse = results.includes(TRUTH.FALSE);
  const hasUnknown = results.includes(TRUTH.UNKNOWN);
  if (op === GROUP_OP.ALL) {
    if (hasFalse) return TRUTH.FALSE;      // one certain failure decides it
    return hasUnknown ? TRUTH.UNKNOWN : TRUTH.TRUE;
  }
  const any = hasTrue ? TRUTH.TRUE : (hasUnknown ? TRUTH.UNKNOWN : TRUTH.FALSE);
  if (op === GROUP_OP.ANY) return any;
  // NONE is the negation of ANY, and negating UNKNOWN leaves UNKNOWN — so
  // none([UNKNOWN]) is UNKNOWN, never a confident "nothing matched".
  if (any === TRUTH.TRUE) return TRUTH.FALSE;
  if (any === TRUTH.FALSE) return TRUTH.TRUE;
  return TRUTH.UNKNOWN;
}

function evalNode(node, path, readings, prevReadings, ctx) {
  if (node.type === NODE_TYPE.GROUP) {
    const results = node.children.map((child, i) =>
      evalNode(child, `${path}.children[${i}]`, readings, prevReadings, ctx));
    return combine(node.op, results);
  }
  return evalCondition(node, path, readings, prevReadings, ctx);
}

/**
 * Evaluate a strategy against one symbol's readings.
 *
 * @param {object} strategy   {name, root}
 * @param {object} readings   {rsi: <typed indicator result>, ...} for the current bar
 * @param {object} [prevReadings] the same map one bar earlier; required by crossings
 * @returns {{value:string, matched:boolean|null, status:string, observations:number,
 *            readingObservations:number|null, blockers:Array, errors:Array}}
 */
export function evaluateStrategy(strategy, readings, prevReadings) {
  const validation = validateStrategy(strategy);
  if (!validation.valid) {
    // A strategy that cannot be evaluated does not "not match" — it has no answer.
    return {
      strategy: isPlainObject(strategy) && nonEmptyString(strategy.name) ? strategy.name : null,
      value: TRUTH.UNKNOWN,
      matched: null,
      status: STRATEGY_STATUS.INVALID_STRATEGY,
      observations: 0,
      readingObservations: null,
      blockers: [],
      errors: validation.errors,
    };
  }

  const ctx = { blockers: [], resolved: 0, minObservations: null };
  const value = evalNode(strategy.root, "root", readings, prevReadings, ctx);

  return {
    strategy: strategy.name,
    value,
    // null, not false: the caller filters on `matched === true` and can count the
    // unknowns separately instead of mistaking them for rejections.
    matched: value === TRUTH.TRUE ? true : (value === TRUTH.FALSE ? false : null),
    // A decided result is VALID even if some branch was blocked — any([TRUE,
    // UNKNOWN]) is genuinely TRUE. Only an undecided result reports the blocker.
    status: value === TRUTH.UNKNOWN
      ? (ctx.blockers[0]?.status ?? STRATEGY_STATUS.FIELD_UNAVAILABLE)
      : STRATEGY_STATUS.VALID,
    observations: ctx.resolved,
    readingObservations: ctx.minObservations,
    blockers: ctx.blockers,
    errors: [],
  };
}

// ── description ──────────────────────────────────────────────────────────────────

const READING_LABEL = {
  rsi: "RSI", macd: "MACD", sma: "SMA", ema: "EMA",
  bollinger: "Bollinger", atr: "ATR", donchian: "Donchian",
};

const OP_LABEL = {
  [CONDITION_OP.GT]: ">",
  [CONDITION_OP.GTE]: ">=",
  [CONDITION_OP.LT]: "<",
  [CONDITION_OP.LTE]: "<=",
  [CONDITION_OP.EQ]: "=",
  [CONDITION_OP.CROSSES_ABOVE]: "crosses above",
  [CONDITION_OP.CROSSES_BELOW]: "crosses below",
};

function describeOperand(operand) {
  if (!isPlainObject(operand)) return "?";
  const kind = operandKind(operand);
  if (kind === "constant") return String(operand.value);
  if (kind === "reading") {
    const base = READING_LABEL[operand.reading] ?? operand.reading;
    return operand.field ? `${base}.${operand.field}` : base;
  }
  return "?";
}

function describeNode(node) {
  if (node.type === NODE_TYPE.GROUP) {
    return `${node.op} of (${node.children.map(describeNode).join(", ")})`;
  }
  const left = describeOperand(node.left);
  if (node.op === CONDITION_OP.BETWEEN) {
    return `${left} between ${describeOperand(node.right[0])} and ${describeOperand(node.right[1])}`;
  }
  return `${left} ${OP_LABEL[node.op]} ${describeOperand(node.right)}`;
}

/**
 * Human-readable text for a saved strategy. An invalid tree is described as
 * invalid rather than rendered as if it would run — the UI must not show a
 * plausible sentence for a strategy that can never produce a match.
 */
export function describeStrategy(strategy) {
  const validation = validateStrategy(strategy);
  const name = isPlainObject(strategy) && nonEmptyString(strategy.name)
    ? strategy.name : "(unnamed strategy)";
  if (!validation.valid) {
    const first = validation.errors[0];
    const where = first.path ? ` at ${first.path}` : "";
    return `${name}: invalid strategy (${first.code}${where})`;
  }
  return `${name}: ${describeNode(strategy.root)}`;
}
