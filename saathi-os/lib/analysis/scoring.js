// Unified signal scoring — one number that summarises how far the indicators that
// ACTUALLY EXIST agree with each other. PURE: readings in, typed result out.
//
// This is a DESCRIPTIVE SUMMARY OF INDICATOR AGREEMENT. It is not a prediction of
// price, not a probability, and not investment advice. It says nothing about what
// will happen next; it says how the readings that were computable line up right now.
//
// Two failures in this codebase's history dictate the whole design:
//
//   1. A scorer once read RSI off a static seed object, so it scored a number
//      nobody had computed. Hence: a component is accepted ONLY as a typed reading
//      { value, status } from lib/nepse/indicators.js. A bare number is rejected as
//      UNTYPED_READING — an unprovenanced number is worse than a missing one,
//      because it looks like evidence.
//
//   2. An absent RSI reached the maths as Number(null) === 0 and scored as
//      maximally oversold — the strongest bullish reading the scale can express.
//      Hence: null / undefined / "" are rejected BEFORE any numeric coercion, and
//      a rejected component is DROPPED and the remaining weights RENORMALISED. It
//      is never defaulted, never zero-filled, never interpolated.
//
// Because the weight base changes with what survived, the result always reports
// which components contributed, which were dropped and why, and the exact weights
// used — so a score built from 2 of 6 inputs can never be read as one built from 6.

import { INDICATOR_STATUS } from "../nepse/indicators.js";

export { INDICATOR_STATUS };

export const SIGNAL_DIRECTION = {
  BULLISH: "BULLISH",
  BEARISH: "BEARISH",
  NEUTRAL: "NEUTRAL",
  UNKNOWN: "UNKNOWN",
};

/**
 * Why a component did not contribute. Every one of these is a refusal to invent a
 * value; none of them is a "0" in disguise.
 */
export const DROP_REASON = {
  NOT_PROVIDED: "NOT_PROVIDED",
  UNTYPED_READING: "UNTYPED_READING",
  STATUS_NOT_VALID: "STATUS_NOT_VALID",
  VALUE_NULL: "VALUE_NULL",
  VALUE_NOT_FINITE: "VALUE_NOT_FINITE",
  VALUE_OUT_OF_RANGE: "VALUE_OUT_OF_RANGE",
  FIELD_MISSING: "FIELD_MISSING",
  UNKNOWN_COMPONENT: "UNKNOWN_COMPONENT",
};

/**
 * A component either votes on direction or confirms conviction — never both.
 * ADX measures trend STRENGTH and volume measures PARTICIPATION; neither knows
 * which way price is going, so letting them into the directional sum would invent
 * a lean they cannot support. They scale confidence instead.
 */
export const COMPONENT_ROLE = {
  DIRECTIONAL: "DIRECTIONAL",
  CONVICTION: "CONVICTION",
};

export const COMPONENT_ROLES = Object.freeze({
  rsi: COMPONENT_ROLE.DIRECTIONAL,
  macd: COMPONENT_ROLE.DIRECTIONAL,
  stochastic: COMPONENT_ROLE.DIRECTIONAL,
  bollinger: COMPONENT_ROLE.DIRECTIONAL,
  adx: COMPONENT_ROLE.CONVICTION,
  volumeRatio: COMPONENT_ROLE.CONVICTION,
});

/** Directional weights sum to 1 before any drop; conviction weights likewise. */
export const DEFAULT_WEIGHTS = Object.freeze({
  rsi: 0.3,
  macd: 0.3,
  stochastic: 0.2,
  bollinger: 0.2,
  adx: 0.6,
  volumeRatio: 0.4,
});

/** Below this many surviving directional components there is no agreement to summarise. */
export const DEFAULT_MIN_CONTRIBUTORS = 2;

/** |raw| below this is a genuine draw, not a weak lean worth naming. */
export const DIRECTION_THRESHOLD = 0.25;

const r6 = (n) => +n.toFixed(6);
const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));

/**
 * The one gate every value passes through. Order matters: null/undefined/"" are
 * rejected while they are still themselves, because Number(null) === 0 and
 * Number("") === 0 both look like a legitimate reading downstream.
 */
function finiteOrNull(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === "string") return null; // a numeric string is an unparsed reading, not a value
  if (typeof v !== "number") return null;
  return Number.isFinite(v) ? v : null;
}

// ── component scorers ───────────────────────────────────────────────────────────
//
// Directional scorers return a sub-score in [-1, +1] (negative bearish, positive
// bullish) or a drop reason. The mean-reversion convention — stretched = fade —
// matches lib/analysis/confluence.js so the two modules cannot disagree about what
// "RSI 75" means.

function scoreRsi(value) {
  const v = finiteOrNull(value);
  if (v === null) return { drop: DROP_REASON.VALUE_NOT_FINITE };
  if (v < 0 || v > 100) return { drop: DROP_REASON.VALUE_OUT_OF_RANGE };
  if (v >= 70) return { sub: -0.6, reading: `${v} overbought`, used: v };
  if (v >= 55) return { sub: 0.4, reading: `${v} momentum with buyers`, used: v };
  if (v > 45) return { sub: 0, reading: `${v} mid-band`, used: v };
  if (v > 30) return { sub: -0.4, reading: `${v} momentum with sellers`, used: v };
  return { sub: 0.6, reading: `${v} oversold`, used: v };
}

/**
 * MACD leans by histogram sign. Magnitude is only comparable once it is expressed
 * relative to the lines it came from — an absolute histogram of 4.0 means something
 * different on a 100-rupee stock and a 3000-rupee one, so it is never used raw.
 */
function scoreMacd(value) {
  if (value === null || value === undefined) return { drop: DROP_REASON.VALUE_NOT_FINITE };
  if (typeof value === "number") {
    const h = finiteOrNull(value);
    if (h === null) return { drop: DROP_REASON.VALUE_NOT_FINITE };
    // A bare histogram carries no scale, so only its sign is trustworthy; it is
    // deliberately capped at half strength rather than guessed at full.
    const sub = h === 0 ? 0 : Math.sign(h) * 0.5;
    return { sub, reading: `histogram ${h} (unscaled)`, used: h };
  }
  if (typeof value !== "object" || Array.isArray(value)) return { drop: DROP_REASON.VALUE_NOT_FINITE };
  const macd = finiteOrNull(value.macd);
  const signal = finiteOrNull(value.signal);
  let hist = finiteOrNull(value.histogram);
  if (hist === null) {
    if (macd === null || signal === null) return { drop: DROP_REASON.FIELD_MISSING };
    hist = macd - signal; // exact restatement of two given numbers, not an estimate
  }
  if (macd === null || signal === null) {
    const sub = hist === 0 ? 0 : Math.sign(hist) * 0.5;
    return { sub, reading: `histogram ${hist} (unscaled)`, used: hist };
  }
  const denom = Math.abs(macd) + Math.abs(signal);
  if (denom === 0) return { sub: 0, reading: "lines flat at zero", used: hist };
  return {
    sub: r6(clamp((2 * hist) / denom, -1, 1)),
    reading: `histogram ${hist} vs lines ${macd}/${signal}`,
    used: hist,
  };
}

/**
 * Stochastic reads %K only. A %K/%D cross needs the previous bar, which a single
 * reading does not contain — inferring one from k > d alone would be fabrication.
 */
function scoreStochastic(value) {
  let k = finiteOrNull(value);
  if (k === null && value && typeof value === "object" && !Array.isArray(value)) {
    k = finiteOrNull(value.k);
    if (k === null) return { drop: DROP_REASON.FIELD_MISSING };
  }
  if (k === null) return { drop: DROP_REASON.VALUE_NOT_FINITE };
  if (k < 0 || k > 100) return { drop: DROP_REASON.VALUE_OUT_OF_RANGE };
  if (k >= 80) return { sub: -0.6, reading: `%K ${k} overbought`, used: k };
  if (k >= 60) return { sub: 0.3, reading: `%K ${k} upper half`, used: k };
  if (k > 40) return { sub: 0, reading: `%K ${k} mid-range`, used: k };
  if (k > 20) return { sub: -0.3, reading: `%K ${k} lower half`, used: k };
  return { sub: 0.6, reading: `%K ${k} oversold`, used: k };
}

/**
 * Bollinger reads %B. bollingerValue() returns percentB === null when the bands
 * collapse (zero width) — that is "undefined", and it must drop out rather than
 * arrive as 0, which on this scale is the extreme bullish end.
 */
function scoreBollinger(value) {
  let b = finiteOrNull(value);
  if (b === null && value && typeof value === "object" && !Array.isArray(value)) {
    if (!("percentB" in value)) return { drop: DROP_REASON.FIELD_MISSING };
    if (value.percentB === null || value.percentB === undefined) return { drop: DROP_REASON.VALUE_NULL };
    b = finiteOrNull(value.percentB);
    if (b === null) return { drop: DROP_REASON.VALUE_NOT_FINITE };
  }
  if (b === null) return { drop: DROP_REASON.VALUE_NOT_FINITE };
  if (b >= 1) return { sub: -0.5, reading: `%B ${b} above upper band`, used: b };
  if (b >= 0.8) return { sub: -0.25, reading: `%B ${b} pressing upper band`, used: b };
  if (b > 0.2) return { sub: 0, reading: `%B ${b} inside the bands`, used: b };
  if (b > 0) return { sub: 0.25, reading: `%B ${b} pressing lower band`, used: b };
  return { sub: 0.5, reading: `%B ${b} below lower band`, used: b };
}

// Conviction scorers return strength in [0, 1]. Strength never has a sign: it
// cannot make a bearish score bullish, only make a read better or worse supported.

function scoreAdx(value) {
  const v = finiteOrNull(value);
  if (v === null) return { drop: DROP_REASON.VALUE_NOT_FINITE };
  if (v < 0 || v > 100) return { drop: DROP_REASON.VALUE_OUT_OF_RANGE };
  if (v >= 40) return { strength: 1, reading: `ADX ${v} strong trend`, used: v };
  if (v >= 25) return { strength: 0.7, reading: `ADX ${v} trending`, used: v };
  if (v >= 20) return { strength: 0.35, reading: `ADX ${v} marginal`, used: v };
  return { strength: 0.1, reading: `ADX ${v} no trend`, used: v };
}

function scoreVolumeRatio(value) {
  const v = finiteOrNull(value);
  if (v === null) return { drop: DROP_REASON.VALUE_NOT_FINITE };
  // A ratio to average volume is strictly positive; 0 or negative is a broken
  // reading (most often an absent volume that was divided anyway), not "no volume".
  if (v <= 0) return { drop: DROP_REASON.VALUE_OUT_OF_RANGE };
  if (v >= 2) return { strength: 1, reading: `${v}x average volume`, used: v };
  if (v >= 1.2) return { strength: 0.75, reading: `${v}x average volume`, used: v };
  if (v >= 0.7) return { strength: 0.4, reading: `${v}x average volume`, used: v };
  return { strength: 0.1, reading: `${v}x average volume — thin`, used: v };
}

const SCORERS = {
  rsi: scoreRsi,
  macd: scoreMacd,
  stochastic: scoreStochastic,
  bollinger: scoreBollinger,
  adx: scoreAdx,
  volumeRatio: scoreVolumeRatio,
};

export const COMPONENTS = Object.freeze(Object.keys(SCORERS));

/**
 * A reading must be the typed shape indicators.js emits: an object carrying both a
 * value and the status that value was earned under. A bare number is refused even
 * when it is a perfectly good number — provenance is the point, not plausibility.
 */
function readingProblem(reading) {
  if (reading === null || reading === undefined) return DROP_REASON.NOT_PROVIDED;
  if (typeof reading !== "object" || Array.isArray(reading)) return DROP_REASON.UNTYPED_READING;
  if (!("status" in reading) || !("value" in reading)) return DROP_REASON.UNTYPED_READING;
  if (reading.status !== INDICATOR_STATUS.VALID) return DROP_REASON.STATUS_NOT_VALID;
  // The exact trap that produced the maximally-oversold phantom RSI.
  if (reading.value === null || reading.value === undefined || reading.value === "") {
    return DROP_REASON.VALUE_NULL;
  }
  return null;
}

function resolveWeights(override) {
  if (override === null || override === undefined) return { ...DEFAULT_WEIGHTS };
  if (typeof override !== "object" || Array.isArray(override)) {
    throw new TypeError("scoreSignal: opts.weights must be an object of component weights");
  }
  const out = { ...DEFAULT_WEIGHTS };
  for (const [k, v] of Object.entries(override)) {
    if (!(k in DEFAULT_WEIGHTS)) throw new TypeError(`scoreSignal: unknown weight "${k}"`);
    if (typeof v !== "number" || !Number.isFinite(v) || v <= 0) {
      // A zero or absent weight is a caller mistake, not data: silently accepting
      // it would drop a component without recording that it was dropped.
      throw new TypeError(`scoreSignal: weight "${k}" must be a finite number > 0`);
    }
    out[k] = v;
  }
  return out;
}

/**
 * Combine typed indicator readings into one agreement score.
 *
 * @param {object} readings  { rsi, macd, stochastic, adx, bollinger, volumeRatio },
 *   each a typed { value, status } result from lib/nepse/indicators.js. Anything
 *   else — a bare number, a missing status, a null value — is dropped, not coerced.
 * @param {object} [opts]  { weights, minContributors }
 * @returns {{score:number|null, direction:string, contributors:Array, dropped:Array,
 *   weightsUsed:object, status:string, confidence:number|null}}
 *   score is 0–100 with 50 exactly neutral, or null when there is nothing to score.
 *   It describes agreement among the contributors listed — nothing more.
 */
export function scoreSignal(readings, opts = {}) {
  const source = readings && typeof readings === "object" && !Array.isArray(readings) ? readings : {};
  const weights = resolveWeights(opts.weights);
  const minContributors = Number.isInteger(opts.minContributors) && opts.minContributors > 0
    ? opts.minContributors
    : DEFAULT_MIN_CONTRIBUTORS;

  const contributors = [];
  const dropped = [];

  for (const name of COMPONENTS) {
    const role = COMPONENT_ROLES[name];
    const reading = source[name];
    const weight = weights[name];

    const problem = readingProblem(reading);
    if (problem) {
      dropped.push({
        component: name,
        role,
        weight,
        reason: problem,
        status: problem === DROP_REASON.STATUS_NOT_VALID ? reading.status : null,
        observations: reading && typeof reading === "object" ? reading.observations ?? null : null,
      });
      continue;
    }

    const scored = SCORERS[name](reading.value);
    if (scored.drop) {
      dropped.push({
        component: name,
        role,
        weight,
        reason: scored.drop,
        status: reading.status,
        observations: reading.observations ?? null,
      });
      continue;
    }

    contributors.push({
      component: name,
      role,
      weight,
      weightUsed: null, // filled once the surviving set is known
      value: scored.used,
      subScore: role === COMPONENT_ROLE.DIRECTIONAL ? scored.sub : null,
      strength: role === COMPONENT_ROLE.CONVICTION ? scored.strength : null,
      reading: scored.reading,
      status: reading.status,
      observations: reading.observations ?? null,
    });
  }

  // Keys that are not components are reported, never silently swallowed: a caller
  // who misspells "volumeRatio" must see that their input did nothing.
  for (const key of Object.keys(source)) {
    if (key in COMPONENT_ROLES) continue;
    dropped.push({
      component: key,
      role: null,
      weight: null,
      reason: DROP_REASON.UNKNOWN_COMPONENT,
      status: null,
      observations: null,
    });
  }

  const directional = contributors.filter((c) => c.role === COMPONENT_ROLE.DIRECTIONAL);
  const conviction = contributors.filter((c) => c.role === COMPONENT_ROLE.CONVICTION);

  // RENORMALISATION: the surviving directional weights are rescaled to sum to 1, so
  // a score from 2 components is a genuine weighted mean of those 2 — not a sum
  // that silently counted the 2 missing ones as zero votes.
  const directionalPool = directional.reduce((a, c) => a + c.weight, 0);
  const weightsUsed = {};
  for (const c of directional) {
    c.weightUsed = directionalPool > 0 ? r6(c.weight / directionalPool) : null;
    weightsUsed[c.component] = c.weightUsed;
  }

  const directionalTotal = COMPONENTS.filter((n) => COMPONENT_ROLES[n] === COMPONENT_ROLE.DIRECTIONAL)
    .reduce((a, n) => a + weights[n], 0);
  const convictionTotal = COMPONENTS.filter((n) => COMPONENT_ROLES[n] === COMPONENT_ROLE.CONVICTION)
    .reduce((a, n) => a + weights[n], 0);

  // Coverage is the share of the INTENDED evidence base that actually showed up —
  // measured against the full weight table, never against what survived.
  const coverage = directionalTotal > 0 ? r6(directionalPool / directionalTotal) : 0;

  // Conviction is NOT renormalised: an absent confirmation is unconfirmed, so a
  // missing ADX must lower conviction rather than hand its weight to volume.
  const convictionScore = convictionTotal > 0
    ? r6(conviction.reduce((a, c) => a + (c.weight * c.strength), 0) / convictionTotal)
    : 0;
  for (const c of conviction) {
    c.weightUsed = convictionTotal > 0 ? r6(c.weight / convictionTotal) : null;
    weightsUsed[c.component] = c.weightUsed;
  }

  const basis = {
    directionalContributors: directional.length,
    directionalOffered: COMPONENTS.filter((n) => COMPONENT_ROLES[n] === COMPONENT_ROLE.DIRECTIONAL).length,
    convictionContributors: conviction.length,
    coverage,
    conviction: convictionScore,
    minContributors,
  };

  if (directional.length < minContributors) {
    // Nothing is approximated on the way out: no score, no direction, no confidence.
    return {
      score: null,
      raw: null,
      direction: SIGNAL_DIRECTION.UNKNOWN,
      contributors,
      dropped,
      weightsUsed,
      status: insufficientStatus(directional.length, dropped),
      confidence: null,
      observations: contributors.length,
      basis,
      basisNote: "descriptive summary of indicator agreement — not a prediction, not advice",
    };
  }

  const raw = r6(directional.reduce((a, c) => a + (c.subScore * c.weightUsed), 0));
  const score = r6(50 + 50 * raw);

  // Confidence answers "how much of the intended evidence base is behind this
  // number", scaled by whether trend strength and participation confirm it. Both
  // factors can only fall when a component drops, so confidence falls with
  // contributors by construction — it never rises because a weak input vanished.
  const confidence = r6(coverage * (0.5 + 0.5 * convictionScore));

  let direction = SIGNAL_DIRECTION.NEUTRAL;
  if (raw >= DIRECTION_THRESHOLD) direction = SIGNAL_DIRECTION.BULLISH;
  else if (raw <= -DIRECTION_THRESHOLD) direction = SIGNAL_DIRECTION.BEARISH;

  return {
    score,
    raw,
    direction,
    contributors,
    dropped,
    weightsUsed,
    status: INDICATOR_STATUS.VALID,
    confidence,
    observations: contributors.length,
    basis,
    basisNote: "descriptive summary of indicator agreement — not a prediction, not advice",
  };
}

/**
 * When nothing scoreable survived, say WHICH refusal it was. If every directional
 * reading failed the same way — all stale, all short of history — that shared
 * status is the honest answer and is passed straight through.
 */
function insufficientStatus(count, dropped) {
  if (count > 0) return INDICATOR_STATUS.INSUFFICIENT_HISTORY;
  const statuses = dropped
    .filter((d) => d.role === COMPONENT_ROLE.DIRECTIONAL && d.reason === DROP_REASON.STATUS_NOT_VALID)
    .map((d) => d.status);
  const directionalDrops = dropped.filter((d) => d.role === COMPONENT_ROLE.DIRECTIONAL);
  if (statuses.length === directionalDrops.length && statuses.length > 0
    && statuses.every((s) => s === statuses[0])) {
    return statuses[0];
  }
  return INDICATOR_STATUS.FIELD_UNAVAILABLE;
}

/**
 * Display helper: a score renders as a number or an em dash, never as 0 or 50.
 * A neutral 50 means "the readings genuinely cancel"; it must not double as
 * "we had nothing to read".
 */
export function scoreDisplay(result) {
  if (!result || result.status !== INDICATOR_STATUS.VALID || result.score === null) return "—";
  return `${result.score.toFixed(1)} (${result.basis.directionalContributors}/${result.basis.directionalOffered})`;
}
