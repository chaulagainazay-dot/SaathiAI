/**
 * Canonical AudioInputOwner — at most one active microphone/STT claim.
 * Module singleton. Framework-agnostic.
 */

import { recordVoiceTelemetry } from "./telemetry.js";

let claimSeq = 0;
/** @type {{ id: string, label: string, mediaStream: MediaStream|null, recognition: any, release: () => void }|null} */
let activeClaim = null;
const listeners = new Set();

function notify() {
  const snap = getInputOwnerSnapshot();
  for (const fn of listeners) {
    try {
      fn(snap);
    } catch {
      /* ignore subscriber errors */
    }
  }
}

export function getInputOwnerSnapshot() {
  return {
    claimId: activeClaim?.id || null,
    label: activeClaim?.label || null,
    hasMediaStream: Boolean(activeClaim?.mediaStream),
    hasRecognition: Boolean(activeClaim?.recognition),
  };
}

export function subscribeInputOwner(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/**
 * Acquire exclusive input ownership. Preempts prior claim.
 * @param {object} opts
 * @param {string} opts.label
 * @param {() => void} [opts.onPreempt]
 * @returns {{ id: string, release: () => void, setMediaStream: (s: MediaStream|null) => void, setRecognition: (r: any) => void, isActive: () => boolean }}
 */
export function acquireInputClaim({ label = "anonymous", onPreempt } = {}) {
  if (activeClaim) {
    recordVoiceTelemetry("input_preempt", {
      claimId: activeClaim.id,
      reason: "CLAIM_PREEMPT",
    });
    try {
      activeClaim.release();
    } catch {
      /* ignore */
    }
    try {
      onPreempt?.();
    } catch {
      /* ignore */
    }
  }

  claimSeq += 1;
  const id = `in-${claimSeq}-${Date.now()}`;
  let mediaStream = null;
  let recognition = null;
  let released = false;

  const release = () => {
    if (released) return;
    released = true;
    try {
      recognition?.stop?.();
      recognition?.abort?.();
    } catch {
      /* ignore */
    }
    recognition = null;
    if (mediaStream) {
      try {
        mediaStream.getTracks().forEach((t) => t.stop());
      } catch {
        /* ignore */
      }
      mediaStream = null;
    }
    if (activeClaim?.id === id) {
      activeClaim = null;
      recordVoiceTelemetry("input_released", { claimId: id });
      notify();
    }
  };

  activeClaim = {
    id,
    label: String(label),
    get mediaStream() {
      return mediaStream;
    },
    get recognition() {
      return recognition;
    },
    release,
  };

  recordVoiceTelemetry("input_acquired", { claimId: id, reason: label });
  notify();

  return {
    id,
    release,
    get mediaStream() {
      return mediaStream;
    },
    setMediaStream(stream) {
      if (released || activeClaim?.id !== id) return;
      if (mediaStream && mediaStream !== stream) {
        try {
          mediaStream.getTracks().forEach((t) => t.stop());
        } catch {
          /* ignore */
        }
      }
      mediaStream = stream || null;
      notify();
    },
    setRecognition(rec) {
      if (released || activeClaim?.id !== id) return;
      if (recognition && recognition !== rec) {
        try {
          recognition.stop?.();
        } catch {
          /* ignore */
        }
      }
      recognition = rec || null;
      notify();
    },
    isActive() {
      return !released && activeClaim?.id === id;
    },
  };
}

/**
 * Force-release whoever holds the mic (route change / logout).
 */
export function forceReleaseInput(reason = "SESSION_CLOSE") {
  if (!activeClaim) return false;
  recordVoiceTelemetry("input_force_release", {
    claimId: activeClaim.id,
    reason,
  });
  try {
    activeClaim.release();
  } catch {
    activeClaim = null;
    notify();
  }
  return true;
}

export function getRecognitionCtor(win = typeof window !== "undefined" ? window : null) {
  if (!win) return null;
  return win.SpeechRecognition || win.webkitSpeechRecognition || null;
}

/**
 * The microphone capture contract for voice input.
 *
 * These are *requests*. A browser honours them at its discretion and reports
 * what it actually applied through the track settings — so this improves the
 * odds that assistant playback is attenuated in the captured signal, and it
 * guarantees nothing about echo. Acoustic barge-in still depends on the
 * echo-window logic in the VAD path, not on these flags.
 */
export const DEFAULT_MIC_CONSTRAINTS = Object.freeze({
  audio: Object.freeze({
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  }),
});

/**
 * Resolve a caller's constraints against the contract.
 *
 * A bare `{ audio: true }` is the failure mode this exists to stop: it is easy
 * to write, it looks harmless, and it silently discards the structured default
 * — the browser then picks its own processing and the capture arrives with
 * echo cancellation off. So `audio: true` resolves to the structured default,
 * and an object merges over it, which keeps a deliberate per-flag override
 * possible while making an accidental blanket one impossible.
 *
 * @param {MediaStreamConstraints|undefined|null} requested
 * @returns {MediaStreamConstraints}
 */
export function resolveMicConstraints(requested) {
  if (!requested) return DEFAULT_MIC_CONSTRAINTS;
  const { audio, ...rest } = requested;
  if (audio === false) return requested;
  const merged =
    audio && typeof audio === "object"
      ? { ...DEFAULT_MIC_CONSTRAINTS.audio, ...audio }
      : { ...DEFAULT_MIC_CONSTRAINTS.audio };
  return { ...rest, audio: merged };
}

/**
 * Open the mic under a claim. Tracks stop when the claim is released.
 * Constraints resolve against DEFAULT_MIC_CONSTRAINTS.
 */
export async function openMicrophoneForClaim(claim, constraints = DEFAULT_MIC_CONSTRAINTS) {
  if (!claim?.isActive?.()) {
    throw new Error("Input claim is not active");
  }
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone API unavailable");
  }
  const stream = await navigator.mediaDevices.getUserMedia(
    resolveMicConstraints(constraints)
  );
  if (!claim.isActive()) {
    stream.getTracks().forEach((t) => t.stop());
    throw new Error("Input claim lost during getUserMedia");
  }
  claim.setMediaStream(stream);
  recordVoiceTelemetry("input_started", { claimId: claim.id });
  return stream;
}
