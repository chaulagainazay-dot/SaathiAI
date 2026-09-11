/**
 * Canonical AudioOutputOwner — at most one active assistant playback claim.
 */

import { recordVoiceTelemetry } from "./telemetry.js";

let claimSeq = 0;
/** @type {{ id: string, label: string, stop: () => void|Promise<void> }|null} */
let activeClaim = null;
const listeners = new Set();

function notify() {
  const snap = getOutputOwnerSnapshot();
  for (const fn of listeners) {
    try {
      fn(snap);
    } catch {
      /* ignore */
    }
  }
}

export function getOutputOwnerSnapshot() {
  return {
    claimId: activeClaim?.id || null,
    label: activeClaim?.label || null,
  };
}

export function subscribeOutputOwner(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/**
 * Acquire exclusive output ownership.
 * @param {object} opts
 * @param {string} opts.label
 * @param {() => void|Promise<void>} [opts.stop] cleanup for this claim's audio
 * @param {() => void} [opts.onPreempt]
 */
export function acquireOutputClaim({ label = "anonymous", stop, onPreempt } = {}) {
  if (activeClaim) {
    recordVoiceTelemetry("output_preempt", {
      claimId: activeClaim.id,
      reason: "CLAIM_PREEMPT",
    });
    try {
      const p = activeClaim.stop?.();
      if (p && typeof p.then === "function") {
        p.catch(() => {});
      }
    } catch {
      /* ignore */
    }
    try {
      onPreempt?.();
    } catch {
      /* ignore */
    }
    activeClaim = null;
  }

  claimSeq += 1;
  const id = `out-${claimSeq}-${Date.now()}`;
  let released = false;

  const release = async () => {
    if (released) return;
    released = true;
    try {
      await stop?.();
    } catch {
      /* ignore */
    }
    if (activeClaim?.id === id) {
      activeClaim = null;
      recordVoiceTelemetry("output_released", { claimId: id });
      notify();
    }
  };

  activeClaim = {
    id,
    label: String(label),
    stop: release,
  };

  recordVoiceTelemetry("output_acquired", { claimId: id, reason: label });
  notify();

  return {
    id,
    release,
    isActive() {
      return !released && activeClaim?.id === id;
    },
  };
}

export async function forceReleaseOutput(reason = "SESSION_CLOSE") {
  if (!activeClaim) return false;
  recordVoiceTelemetry("output_force_release", {
    claimId: activeClaim.id,
    reason,
  });
  try {
    await activeClaim.stop?.();
  } catch {
    activeClaim = null;
    notify();
  }
  return true;
}

/**
 * Cancel browser speechSynthesis if present (legacy path helper).
 */
export function cancelBrowserSpeechSynthesis(win = typeof window !== "undefined" ? window : null) {
  try {
    win?.speechSynthesis?.cancel?.();
  } catch {
    /* ignore */
  }
}
