/**
 * V-NEXT-2B — Provider-neutral StreamingTranscriptionAdapter contract.
 * PARTIAL transcript ≠ executable intent.
 */

/** @typedef {"LOCAL_CONFIRMED"|"PLATFORM_MANAGED_UNKNOWN"|"REMOTE"|"UNAVAILABLE"} SttPrivacyClass */

/**
 * @typedef {object} TranscriptEvent
 * @property {string} sessionId
 * @property {string} utteranceId
 * @property {string} text
 * @property {boolean} isFinal
 * @property {number|null} confidence
 * @property {string|null} language
 * @property {string|null} startedAt
 * @property {string|null} endedAt
 * @property {number} sequence
 * @property {string} source
 * @property {SttPrivacyClass} privacyClass
 */

/**
 * @typedef {object} StreamingTranscriptionAdapter
 * @property {(session: object) => Promise<void>|void} start
 * @property {(frame: Float32Array|number[], meta?: object) => void} [pushAudio]
 * @property {(cb: (ev: TranscriptEvent) => void) => () => void} onPartial
 * @property {(cb: (ev: TranscriptEvent) => void) => () => void} onFinal
 * @property {() => Promise<void>|void} [flush]
 * @property {() => Promise<void>|void} cancel
 * @property {() => Promise<void>|void} close
 * @property {() => object} health
 * @property {() => object} capabilities
 */

export const STT_PRIVACY = Object.freeze({
  LOCAL_CONFIRMED: "LOCAL_CONFIRMED",
  PLATFORM_MANAGED_UNKNOWN: "PLATFORM_MANAGED_UNKNOWN",
  REMOTE: "REMOTE",
  UNAVAILABLE: "UNAVAILABLE",
});

let utteranceSeq = 0;
export function nextUtteranceId() {
  utteranceSeq += 1;
  return `utt-${Date.now()}-${utteranceSeq}`;
}

let transcriptSeq = 0;
export function nextTranscriptSequence() {
  transcriptSeq += 1;
  return transcriptSeq;
}

/**
 * Backchannel / non-turn short forms (English + common particles).
 * Used by TurnCoordinator — not authority.
 */
export const BACKCHANNEL_RE =
  /^(yeah|yes|yep|yup|uh-huh|uh huh|hmm+|mm+|mhm|okay|ok|right|sure|अँ|हजुर|हुन्छ|ठिकै|ठीक|अह|हो)$/i;

/**
 * Meaningful interruption requires more than a grunt.
 */
export function isMeaningfulTranscript(text) {
  const t = String(text || "").trim();
  if (!t) return false;
  if (t.length < 2) return false;
  if (BACKCHANNEL_RE.test(t)) return false;
  // at least one letter (Latin or Devanagari)
  if (!/[\p{L}]/u.test(t)) return false;
  return true;
}

/**
 * Heuristic endpoint: punctuation or long enough clause.
 */
export function looksSyntacticallyComplete(text) {
  const t = String(text || "").trim();
  if (!t) return false;
  if (/[.!?।]\s*$/.test(t)) return true;
  if (t.split(/\s+/).length >= 6) return true;
  return false;
}
