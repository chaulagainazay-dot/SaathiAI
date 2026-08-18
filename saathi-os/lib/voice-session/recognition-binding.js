/**
 * The consumer side of browser recognition ownership.
 *
 * There is one SpeechRecognition in the app and the VoiceSessionManager's
 * streaming pipeline owns it. Everything else — the React runtime provider
 * today, anything else later — binds to that authority through this module
 * rather than constructing a recognizer of its own.
 *
 * Framework-free on purpose: the rules that decide whether a transcript may be
 * submitted are the part worth testing deterministically, and they should not
 * need a DOM or a renderer to exercise.
 */

import { recordVoiceTelemetry } from "./telemetry.js";

export const RECOGNITION_UNSUPPORTED_MESSAGE =
  "Speech recognition is unavailable in this browser. Use a Chromium browser or install a local STT provider.";

/**
 * Decide whether this runtime can honestly transcribe speech.
 *
 * Truthfulness is the whole point. A browser without native recognition, or a
 * pipeline that fell back to the deterministic test adapter, cannot produce a
 * transcript of what the user actually said — so voice must report unavailable
 * instead of opening a microphone and publishing invented text.
 *
 * @param {object} opts
 * @param {unknown} opts.recognitionCtor native SpeechRecognition constructor
 * @param {object|null} [opts.engineState] pipeline engine state, once started
 * @returns {{ supported: boolean, reason: string, mode: string|null }}
 */
export function evaluateRecognitionSupport({ recognitionCtor, engineState = null } = {}) {
  if (!recognitionCtor) {
    return { supported: false, reason: RECOGNITION_UNSUPPORTED_MESSAGE, mode: null };
  }
  if (!engineState) {
    // Gate passed on capability alone; the engine has not reported yet.
    return { supported: true, reason: "", mode: null };
  }
  if (engineState.supported === false) {
    return {
      supported: false,
      reason: engineState.unsupportedReason || RECOGNITION_UNSUPPORTED_MESSAGE,
      mode: engineState.mode || null,
    };
  }
  if (engineState.mode === "mock") {
    return {
      supported: false,
      reason: RECOGNITION_UNSUPPORTED_MESSAGE,
      mode: "mock",
    };
  }
  return { supported: true, reason: "", mode: engineState.mode || null };
}

/**
 * Bind to the authoritative transcript stream for one input generation.
 *
 * The binding enforces, in one place, every rule that separates "the user said
 * something" from "submit work to the backend":
 *
 *   - partials are delivered for display and are never executable;
 *   - a turn from another epoch belongs to a session this binding does not
 *     own, so it is dropped;
 *   - a turn is submitted at most once, keyed on its id rather than its text,
 *     so a doubled callback cannot double-submit and a sentence genuinely
 *     repeated by the user is still two turns;
 *   - empty finals submit nothing;
 *   - backchannels ("okay", "mm-hm") finalize as non-executable and submit
 *     nothing;
 *   - after `detach()` nothing is delivered at all.
 *
 * @param {object} opts
 * @param {object} opts.manager VoiceSessionManager
 * @param {number} opts.epoch input generation this binding owns
 * @param {(partial: object) => void} [opts.onPartial]
 * @param {(turn: object) => void} [opts.onFinalTurn] eligible turns only
 * @param {(turn: object) => void} [opts.onBackchannel]
 * @param {(turn: object) => void} [opts.onIgnored] dropped turns, for evidence
 */
export function createTurnBinding({
  manager,
  epoch,
  onPartial,
  onFinalTurn,
  onBackchannel,
  onIgnored,
} = {}) {
  if (!manager) throw new Error("createTurnBinding requires a voice session manager");

  const submitted = new Set();
  const offs = [];
  let detached = false;

  const ignore = (turn, why) => {
    recordVoiceTelemetry("turn_ignored", { reason: why });
    try {
      onIgnored?.({ ...turn, ignoredReason: why });
    } catch {
      /* ignore */
    }
  };

  const owns = (ev) => !detached && Boolean(ev) && ev.epoch === epoch;

  const offPartial = manager.onPartialTranscript?.((partial) => {
    if (!owns(partial)) return;
    try {
      onPartial?.({ ...partial, isExecutable: false });
    } catch {
      /* a consumer failure must not break the stream */
    }
  });
  if (offPartial) offs.push(offPartial);

  const offFinal = manager.onFinalTurn?.((turn) => {
    if (!owns(turn)) {
      if (turn && !detached) ignore(turn, "stale_epoch");
      return;
    }
    const text = String(turn.text || "").trim();
    if (!text) {
      ignore(turn, "empty_final");
      return;
    }
    if (submitted.has(turn.turnId)) {
      ignore(turn, "duplicate_turn");
      return;
    }
    submitted.add(turn.turnId);
    if (turn.isBackchannel) {
      try {
        onBackchannel?.(turn);
      } catch {
        /* ignore */
      }
      return;
    }
    try {
      onFinalTurn?.(turn);
    } catch {
      /* ignore */
    }
  });
  if (offFinal) offs.push(offFinal);

  return {
    epoch,
    isAttached() {
      return !detached;
    },
    submittedTurnIds() {
      return new Set(submitted);
    },
    detach() {
      if (detached) return;
      detached = true;
      for (const off of offs) {
        try {
          off?.();
        } catch {
          /* ignore */
        }
      }
      offs.length = 0;
      submitted.clear();
    },
  };
}
