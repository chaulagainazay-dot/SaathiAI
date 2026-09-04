// Numeric guard for narrated analysis. PURE.
//
// The narration prompt TELLS a model not to invent numbers. This VERIFIES it did
// not. A rule a model is asked to follow is a hope; a check on its output is a
// control. Every figure in the narration must trace to the computed facts, or the
// sentence carrying it is flagged.
//
// Deliberately tolerant of harmless forms — ordinals, small counts, dates and the
// figures already present in the facts — so the guard flags fabricated PRICES and
// LEVELS rather than drowning the caller in false positives.

/** Numbers that carry no market claim and never need to appear in the facts. */
const BENIGN = new Set([
  "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
  "20", "26", "12", "14", "50", "100", "200",   // standard indicator periods
]);

/** Extract numeric tokens, ignoring dates (2026-09-03) and percent-of-word noise. */
export function numbersIn(text) {
  if (!text) return [];
  const withoutDates = String(text).replace(/\b\d{4}-\d{2}-\d{2}\b/g, " ");
  const raw = withoutDates.match(/-?\d[\d,]*(?:\.\d+)?/g) || [];
  return raw.map((t) => t.replace(/,/g, "")).filter((t) => t !== "" && t !== "-");
}

/** Canonical form so 539, 539.0 and 539.00 compare equal. */
function canon(tok) {
  const n = Number(tok);
  if (!Number.isFinite(n)) return null;
  return String(n);
}

/**
 * Verify a narration introduces no number absent from the facts.
 * @returns {{ok:boolean, invented:string[], flaggedSentences:string[], checked:number}}
 */
export function verifyNarration(narration, facts) {
  const allowed = new Set();
  for (const t of numbersIn(facts)) {
    const c = canon(t);
    if (c !== null) allowed.add(c);
  }
  // A rounded restatement of a permitted figure is acceptable prose, not invention.
  for (const c of [...allowed]) {
    const n = Number(c);
    if (Number.isFinite(n)) {
      allowed.add(String(Math.round(n)));
      allowed.add(String(+n.toFixed(1)));
      allowed.add(String(+n.toFixed(2)));
    }
  }

  const invented = [];
  for (const t of numbersIn(narration)) {
    const c = canon(t);
    if (c === null) continue;
    if (BENIGN.has(c)) continue;
    if (allowed.has(c)) continue;
    invented.push(c);
  }

  const uniqueInvented = [...new Set(invented)];
  const sentences = String(narration || "").split(/(?<=[.!?])\s+/);
  const flaggedSentences = uniqueInvented.length
    ? sentences.filter((s) => numbersIn(s).some((t) => uniqueInvented.includes(canon(t))))
    : [];

  return {
    ok: uniqueInvented.length === 0,
    invented: uniqueInvented,
    flaggedSentences,
    checked: numbersIn(narration).length,
  };
}

/** Phrases that would make an explanation into advice. */
const ADVICE_PATTERNS = [
  /\byou should (buy|sell|short|long|enter|exit)\b/i,
  /\bi (recommend|suggest) (buying|selling|shorting)\b/i,
  /\b(buy|sell) (it|this|now)\b/i,
  /\bguaranteed\b/i,
  /\bwill (definitely|certainly) (rise|fall|go)\b/i,
];

export function verifyNotAdvice(narration) {
  const hits = ADVICE_PATTERNS.filter((re) => re.test(String(narration || "")));
  return { ok: hits.length === 0, matched: hits.map((r) => r.source) };
}

/** Full gate: a narration ships only if it invents nothing and advises nothing. */
export function gateNarration(narration, facts) {
  const numeric = verifyNarration(narration, facts);
  const advice = verifyNotAdvice(narration);
  return {
    ok: numeric.ok && advice.ok,
    numeric,
    advice,
    reason: !numeric.ok ? "INVENTED_NUMBERS" : !advice.ok ? "READS_AS_ADVICE" : null,
  };
}
