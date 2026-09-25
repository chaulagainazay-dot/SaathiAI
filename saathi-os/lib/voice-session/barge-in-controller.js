/**
 * Acoustic barge-in: VAD speech_start while speaking → VoiceSession.interrupt.
 * Includes echo suppression window and latency measurement.
 */

import { recordVoiceTelemetry } from "./telemetry.js";
import { createEnergyVad } from "./energy-vad.js";
import { createAudioFrameTap } from "./audio-frame-tap.js";
import { DEFAULT_VAD_CONFIG } from "./vad-contract.js";

/**
 * @param {object} opts
 * @param {import('./session-manager.js').VoiceSessionManagerLike} opts.manager
 * @param {() => MediaStream|null} opts.getStream
 * @param {Partial<typeof DEFAULT_VAD_CONFIG>} [opts.config]
 */
export function createBargeInController({ manager = null, getStream, config = {} } = {}) {
  const cfg = { ...DEFAULT_VAD_CONFIG, ...config };
  const vad = createEnergyVad({ ...cfg, bargeInMode: false });
  let tap = null;
  let armed = false;
  let speakingSince = 0;
  let lastInterruptAt = 0;
  let speechDetected = false;
  /** @type {number[]} */
  const latencies = [];
  let unsubStart = null;
  let unsubEnd = null;
  let vadFailed = false;
  /** Mutable so session-manager can wire after construction */
  const self = { manager };

  function mgr() {
    return self.manager;
  }

  function onSpeechStart(ev) {
    speechDetected = true;
    const m = mgr();
    m?.notifySpeechDetected?.(true, ev);

    const snap = m?.getSnapshot?.() || {};
    const speaking =
      snap.outputState === "speaking" ||
      snap.state === "SPEAKING" ||
      Boolean(m?.getOutputClaim?.());
    if (!speaking) {
      // Listening-path speech start only (not barge-in)
      return;
    }

    const now = typeof performance !== "undefined" && performance.now
      ? performance.now()
      : Date.now();
    if (cfg.echoSuppressionMs > 0 && speakingSince > 0 && now - speakingSince < cfg.echoSuppressionMs) {
      recordVoiceTelemetry("barge_in_suppressed_echo", {
        reason: "echo_window",
        durationMs: now - speakingSince,
      });
      return;
    }
    if (lastInterruptAt > 0 && now - lastInterruptAt < 120) return;

    const t0 = now;
    lastInterruptAt = now;
    recordVoiceTelemetry("barge_in_triggered", {
      reason: "ACOUSTIC_SPEECH",
      sessionId: snap.sessionId,
    });

    const interruptFn = m?.interrupt?.bind(m);
    Promise.resolve(interruptFn ? interruptFn("ACOUSTIC_SPEECH") : null)
      .then(() => {
        const latency =
          (typeof performance !== "undefined" && performance.now
            ? performance.now()
            : Date.now()) - t0;
        latencies.push(latency);
        if (latencies.length > 50) latencies.shift();
        recordVoiceTelemetry("barge_in_complete", {
          durationMs: latency,
          sessionId: mgr()?.getSnapshot?.()?.sessionId,
        });
        mgr()?.notifyBargeInLatency?.(latency);
      })
      .catch((err) => {
        recordVoiceTelemetry("error", {
          errorCode: String(err?.message || err).slice(0, 80),
        });
      });
  }

  function onSpeechEnd(ev) {
    speechDetected = false;
    mgr()?.notifySpeechDetected?.(false, ev);
  }

  return {
    /** @type {any} */
    get manager() {
      return self.manager;
    },
    set manager(m) {
      self.manager = m;
    },
    vad,
    async arm({ bargeInMode = false, config: armCfg = {} } = {}) {
      Object.assign(cfg, armCfg);
      if (armed) {
        vad.setBargeInMode?.(bargeInMode);
        return;
      }
      try {
        const stream = getStream?.() || null;
        vad.configure({ ...cfg });
        vad.setBargeInMode?.(bargeInMode);
        await vad.start();
        unsubStart = vad.onSpeechStart(onSpeechStart);
        unsubEnd = vad.onSpeechEnd(onSpeechEnd);

        tap = createAudioFrameTap({
          stream,
          config: cfg,
          onFrame: (frame, meta) => {
            mgr()?.notifyPcmFrame?.(frame, meta);
            vad.processAudioFrame(frame, meta);
          },
        });
        // If no stream, tap still accepts processFrame for tests
        await tap.start();
        armed = true;
        vadFailed = false;
        if (bargeInMode) speakingSince = performance.now?.() ?? Date.now();
        recordVoiceTelemetry("vad_armed", {
          reason: bargeInMode ? "barge_in" : "listen",
        });
      } catch (err) {
        vadFailed = true;
        armed = false;
        recordVoiceTelemetry("vad_failed", {
          errorCode: String(err?.message || err).slice(0, 80),
        });
        manager?.notifyVadFailed?.(String(err?.message || err));
      }
    },

    setBargeInMode(on) {
      vad.setBargeInMode?.(on);
      if (on) speakingSince = performance.now?.() ?? Date.now();
    },

    markSpeakingStart(at = null) {
      speakingSince = at ?? (performance.now?.() ?? Date.now());
      vad.setBargeInMode?.(true);
    },
    /** Force echo window elapsed (tests) */
    clearEchoWindow() {
      speakingSince = 0;
    },

    markSpeakingEnd() {
      vad.setBargeInMode?.(false);
    },

    /** Test/synthetic path */
    processFrame(frame, meta) {
      if (!armed) return;
      if (tap) tap.processFrame(frame, meta);
      else vad.processAudioFrame(frame, meta);
    },

    getPreRoll() {
      return tap?.getPreRoll?.() || new Float32Array(0);
    },

    async disarm() {
      if (unsubStart) unsubStart();
      if (unsubEnd) unsubEnd();
      unsubStart = unsubEnd = null;
      try {
        await vad.stop();
      } catch {
        /* ignore */
      }
      try {
        tap?.stop?.();
      } catch {
        /* ignore */
      }
      tap = null;
      armed = false;
      speechDetected = false;
      recordVoiceTelemetry("vad_disarmed", {});
    },

    health() {
      const v = vad.health();
      const sorted = [...latencies].sort((a, b) => a - b);
      const p = (q) =>
        sorted.length
          ? sorted[Math.min(sorted.length - 1, Math.floor(q * (sorted.length - 1)))]
          : null;
      return {
        armed,
        vadFailed,
        speechDetected,
        vad: v,
        tap: tap?.health?.() || null,
        latencyMs: {
          samples: latencies.length,
          p50: p(0.5),
          p95: p(0.95),
          last: latencies[latencies.length - 1] ?? null,
        },
      };
    },

    isArmed() {
      return armed;
    },

    isVadFailed() {
      return vadFailed;
    },
  };
}
