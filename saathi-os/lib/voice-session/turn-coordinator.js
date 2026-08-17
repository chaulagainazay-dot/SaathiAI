/**
 * TurnCoordinator — multi-signal turn finalization.
 * PARTIAL ≠ executable. Final turn emits for Command/Chat only.
 *
 * V-NEXT-2B.1: engine-neutral normalization; punctuation / linguistic completeness;
 * backchannel hardening; false-interrupt recovery with STT evidence.
 */

import {
  isMeaningfulTranscript,
  looksSyntacticallyComplete,
  BACKCHANNEL_RE,
} from "./stt-contract.js";
import { recordVoiceTelemetry } from "./telemetry.js";

/** @typedef {"REAL_INTERRUPTION"|"FALSE_INTERRUPTION"|"UNKNOWN_INTERRUPTION"} InterruptClass */

export const DEFAULT_TURN_CONFIG = Object.freeze({
  silenceToFinalizeMs: 650,
  minFinalChars: 2,
  endpointGraceMs: 200,
  falseInterruptWaitMs: 900,
  // Prefer STT final over pure silence when both race
  preferSttFinal: true,
  // Drop stale partials that regress (shorter + not prefix) after a final
  rejectRegressivePartials: true,
});

/**
 * Normalize raw provider text for turn logic (engine-neutral).
 * @param {string} text
 */
export function normalizeTurnText(text) {
  return String(text || "")
    .replace(/\s+/g, " ")
    .replace(/^[\s,;:]+/, "")
    .trim();
}

/**
 * @param {object} opts
 * @param {(turn: object) => void} [opts.onTurnFinal]
 * @param {(ev: object) => void} [opts.onEvent]
 * @param {Partial<typeof DEFAULT_TURN_CONFIG>} [opts.config]
 */
export function createTurnCoordinator(opts = {}) {
  const cfg = { ...DEFAULT_TURN_CONFIG, ...opts.config };
  const onTurnFinal = opts.onTurnFinal || (() => {});
  const onEvent = opts.onEvent || (() => {});

  let partialText = "";
  let lastFinalText = "";
  let vadSpeechActive = false;
  let lastActivityAt = 0;
  let pendingFalseInterrupt = null;
  /** @type {InterruptClass|null} */
  let lastInterruptClass = null;
  let finalizedTurns = 0;
  let falseInterrupts = 0;
  let realInterrupts = 0;

  function now() {
    return typeof performance !== "undefined" && performance.now
      ? performance.now()
      : Date.now();
  }

  function emit(type, payload = {}) {
    onEvent({ type, at: new Date().toISOString(), ...payload });
    recordVoiceTelemetry(type.replace(/\./g, "_"), {
      reason: payload.reason || type,
    });
  }

  function tryFinalize(reason) {
    const text = normalizeTurnText(partialText || lastFinalText || "");
    if (!isMeaningfulTranscript(text) && !BACKCHANNEL_RE.test(text)) {
      return null;
    }
    // Backchannels can finalize as non-executable turns
    const isBc = BACKCHANNEL_RE.test(text);
    const turn = {
      text,
      isBackchannel: isBc,
      isExecutable: isMeaningfulTranscript(text) && !isBc,
      reason,
      finalizedAt: new Date().toISOString(),
      // Authority: never auto-execute tools from turn alone
      authority: "none",
    };
    finalizedTurns += 1;
    partialText = "";
    lastFinalText = text;
    emit("turn.finalized", { text, reason, isExecutable: turn.isExecutable });
    onTurnFinal(turn);
    return turn;
  }

  return {
    onVadSpeechStart() {
      vadSpeechActive = true;
      lastActivityAt = now();
      emit("vad.speech_started");
    },

    onVadSpeechEnd() {
      vadSpeechActive = false;
      lastActivityAt = now();
      emit("turn.possible_end", { reason: "vad_silence" });
      // silence alone does not finalize without STT evidence
    },

    onPartial(ev) {
      const text = normalizeTurnText(ev?.text || "");
      // Ordering: ignore empty; optionally reject regressive partials after final
      if (
        cfg.rejectRegressivePartials &&
        lastFinalText &&
        text &&
        text.length + 2 < lastFinalText.length &&
        !lastFinalText.startsWith(text) &&
        !text.startsWith(lastFinalText.slice(0, Math.min(8, lastFinalText.length)))
      ) {
        emit("stt.partial_ignored", { text, reason: "regressive" });
        return;
      }
      partialText = text;
      lastActivityAt = now();
      emit("stt.partial", { text: partialText });
      // NEVER executable
    },

    onFinal(ev) {
      const text = normalizeTurnText(ev?.text || "");
      lastFinalText = text;
      partialText = text;
      lastActivityAt = now();
      emit("stt.final", { text });

      // Resolve pending false-interrupt window
      if (pendingFalseInterrupt) {
        if (isMeaningfulTranscript(text)) {
          lastInterruptClass = "REAL_INTERRUPTION";
          realInterrupts += 1;
          emit("interrupt.confirmed", { text });
        } else {
          lastInterruptClass = "FALSE_INTERRUPTION";
          falseInterrupts += 1;
          emit("interrupt.false_positive", { text });
        }
        pendingFalseInterrupt = null;
      }

      // Linguistic completeness: punctuation / clause length / speech ended
      if (looksSyntacticallyComplete(text) || !vadSpeechActive || cfg.preferSttFinal) {
        return tryFinalize("stt_final");
      }
      emit("turn.possible_end", { reason: "stt_final_incomplete" });
      return null;
    },

    /**
     * Call when acoustic barge-in fires — wait for STT evidence.
     */
    beginInterruptEvaluation(reason = "ACOUSTIC_SPEECH") {
      pendingFalseInterrupt = {
        reason,
        since: now(),
      };
      lastInterruptClass = "UNKNOWN_INTERRUPTION";
      emit("interrupt.possible", { reason });
    },

    /**
     * Periodic tick for silence-based endpointing after STT final pieces.
     */
    tick() {
      if (pendingFalseInterrupt) {
        const waited = now() - pendingFalseInterrupt.since;
        if (waited >= cfg.falseInterruptWaitMs) {
          if (!isMeaningfulTranscript(partialText || lastFinalText)) {
            lastInterruptClass = "FALSE_INTERRUPTION";
            falseInterrupts += 1;
            emit("interrupt.false_positive", { reason: "timeout_no_meaningful_stt" });
          } else {
            lastInterruptClass = "REAL_INTERRUPTION";
            realInterrupts += 1;
            emit("interrupt.confirmed", { reason: "timeout_with_text" });
          }
          pendingFalseInterrupt = null;
        }
      }

      if (!partialText && !lastFinalText) return null;
      if (vadSpeechActive) return null;
      if (!lastActivityAt) return null;
      const idle = now() - lastActivityAt;
      if (idle >= cfg.silenceToFinalizeMs + cfg.endpointGraceMs) {
        if (isMeaningfulTranscript(partialText) || BACKCHANNEL_RE.test(partialText)) {
          return tryFinalize("silence_endpoint");
        }
      }
      return null;
    },

    forceFinalize(reason = "force") {
      return tryFinalize(reason);
    },

    getPartial() {
      return partialText;
    },

    getLastFinal() {
      return lastFinalText;
    },

    getLastInterruptClass() {
      return lastInterruptClass;
    },

    reset() {
      partialText = "";
      lastFinalText = "";
      vadSpeechActive = false;
      pendingFalseInterrupt = null;
      lastInterruptClass = null;
    },

    health() {
      return {
        partialText,
        lastFinalText,
        vadSpeechActive,
        pendingFalseInterrupt: Boolean(pendingFalseInterrupt),
        lastInterruptClass,
        finalizedTurns,
        falseInterrupts,
        realInterrupts,
        config: { ...cfg },
      };
    },
  };
}
