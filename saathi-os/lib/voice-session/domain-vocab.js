/**
 * V-NEXT-2B.2 — Bounded deterministic domain vocabulary repair for STT transcripts.
 *
 * Evidence-based only. Does NOT invent intent.
 * Does NOT escalate incorrect transcripts into tool execution.
 * Applied optionally for display/normalization — never as authority.
 */

/** @type {Array<{re: RegExp, to: string, note: string}>} */
export const DOMAIN_VOCAB_RULES = Object.freeze([
  { re: /\bsafi\b/gi, to: "Saathi", note: "common EN mishear of Saathi" },
  { re: /\bsathy\b/gi, to: "Saathi", note: "common EN mishear of Saathi" },
  { re: /\bsophie\b/gi, to: "Saathi", note: "common EN mishear of Saathi" },
  { re: /\bsoffie\b/gi, to: "Saathi", note: "common EN mishear of Saathi" },
  { re: /\bexecution\s+gateway\b/gi, to: "ExecutionGateway", note: "spacing of product term" },
  { re: /\btrading\s+through\b/gi, to: "Trading Guardian", note: "rare mishear" },
  { re: /\bdraw\s+down\b/gi, to: "drawdown", note: "finance term spacing" },
  { re: /\bport\s+folio\b/gi, to: "portfolio", note: "finance term spacing" },
  { re: /\bpork\s+folio\b/gi, to: "portfolio", note: "noise mishear" },
  { re: /\breport\s+folio\b/gi, to: "portfolio", note: "noise mishear" },
  { re: /\bprovals\b/gi, to: "approvals", note: "truncation" },
  { re: /\bproofles\b/gi, to: "approvals", note: "mishear" },
  { re: /\bcommand\s+centre\b/gi, to: "command center", note: "spelling" },
]);

/**
 * Apply deterministic domain repairs. Idempotent for already-correct text.
 * @param {string} text
 * @returns {{ text: string, applied: string[] }}
 */
export function applyDomainVocabulary(text) {
  let out = String(text || "");
  const applied = [];
  for (const rule of DOMAIN_VOCAB_RULES) {
    if (rule.re.test(out)) {
      out = out.replace(rule.re, rule.to);
      applied.push(rule.note);
    }
    // reset lastIndex for global regex
    rule.re.lastIndex = 0;
  }
  return { text: out, applied };
}

/**
 * Unicode/punctuation normalization for measurement & display (not gate gaming).
 * @param {string} text
 */
export function normalizeTranscriptText(text) {
  let s = String(text || "").normalize("NFKC");
  s = s.replace(/\s+/g, " ").trim();
  // Devanagari danda variants
  s = s.replace(/[।॥]/g, "।");
  return s;
}
