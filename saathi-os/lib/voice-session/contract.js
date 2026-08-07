/**
 * V-NEXT-1 — Canonical VoiceSession contract.
 * Provider-agnostic. SaathiOS-owned boundary.
 * Does not grant execution or financial authority.
 */

/** States that can be represented truthfully without VAD */
export const VOICE_SESSION_STATES = Object.freeze([
  "IDLE",
  "READY",
  "LISTENING",
  "TRANSCRIBING",
  "THINKING",
  "SPEAKING",
  "INTERRUPTING",
  "DEGRADED",
  "ERROR",
  "CLOSED",
]);

/** Future-compatible; SPEECH_DETECTED reserved until VAD exists */
export const RESERVED_FUTURE_STATES = Object.freeze(["SPEECH_DETECTED"]);

export const INTERRUPT_REASONS = Object.freeze([
  "USER_MIC_REQUEST",
  "USER_CANCEL",
  "ROUTE_CHANGE",
  "NEW_ASSISTANT_RESPONSE",
  "SESSION_CLOSE",
  "ERROR",
  "CLAIM_PREEMPT",
  "LOGOUT",
]);

export const CAPABILITY_DEFAULTS = Object.freeze({
  microphoneAvailable: false,
  speechRecognitionAvailable: false,
  speechOutputAvailable: false,
  manualInterruptAvailable: true,
  vadAvailable: false,
  wakeWordAvailable: false,
  streamingSttAvailable: false,
  streamingTtsAvailable: false,
  fullDuplexAvailable: false,
});

/**
 * Detect browser capabilities without claiming VAD/full-duplex.
 * @param {Window|null} win
 */
export function detectVoiceCapabilities(win = typeof window !== "undefined" ? window : null) {
  if (!win) {
    return { ...CAPABILITY_DEFAULTS };
  }
  const hasMedia =
    typeof win.navigator?.mediaDevices?.getUserMedia === "function";
  const Recognition =
    win.SpeechRecognition || win.webkitSpeechRecognition || null;
  const hasSynth = typeof win.speechSynthesis !== "undefined";
  return {
    ...CAPABILITY_DEFAULTS,
    microphoneAvailable: Boolean(hasMedia),
    speechRecognitionAvailable: Boolean(Recognition),
    speechOutputAvailable: hasSynth || true, // platform SpeechService path may exist
    manualInterruptAvailable: true,
    vadAvailable: false,
    wakeWordAvailable: false,
    streamingSttAvailable: false,
    streamingTtsAvailable: false,
    fullDuplexAvailable: false,
  };
}

/**
 * @typedef {object} VoiceSessionSnapshot
 * @property {string} sessionId
 * @property {string} state
 * @property {string} inputState
 * @property {string} outputState
 * @property {string} transcriptPartial
 * @property {string} transcriptFinal
 * @property {string} assistantText
 * @property {string|null} startedAt
 * @property {string|null} lastActivityAt
 * @property {boolean} interruptible
 * @property {string} inputProvider
 * @property {string} outputProvider
 * @property {string} error
 * @property {object} capabilities
 * @property {string|null} inputClaimId
 * @property {string|null} outputClaimId
 */

export const INITIAL_VOICE_SESSION = Object.freeze({
  sessionId: "",
  state: "IDLE",
  inputState: "idle",
  outputState: "idle",
  transcriptPartial: "",
  transcriptFinal: "",
  assistantText: "",
  startedAt: null,
  lastActivityAt: null,
  interruptible: true,
  inputProvider: "none",
  outputProvider: "none",
  error: "",
  capabilities: { ...CAPABILITY_DEFAULTS },
  inputClaimId: null,
  outputClaimId: null,
  degraded: false,
});

/**
 * Map internal activity to canonical state (truthful subset).
 */
export function deriveSessionState({
  closed = false,
  error = "",
  listening = false,
  recording = false,
  speaking = false,
  thinking = false,
  interrupting = false,
  degraded = false,
  ready = false,
} = {}) {
  if (closed) return "CLOSED";
  if (error) return "ERROR";
  if (interrupting) return "INTERRUPTING";
  if (speaking) return "SPEAKING";
  if (thinking) return "THINKING";
  if (listening || recording) return "LISTENING";
  if (degraded) return "DEGRADED";
  if (ready) return "READY";
  return "IDLE";
}

/** Map to UI-NEXT-1 authority chip vocabulary */
export function toCommandVoiceLabel(state) {
  const map = {
    IDLE: "OFF",
    CLOSED: "OFF",
    READY: "READY",
    LISTENING: "LISTENING",
    TRANSCRIBING: "LISTENING",
    THINKING: "THINKING",
    SPEAKING: "SPEAKING",
    INTERRUPTING: "INTERRUPTED",
    DEGRADED: "DEGRADED",
    ERROR: "ERROR",
  };
  return map[state] || "UNKNOWN";
}
