/**
 * Lightweight energy + ZCR Voice Activity Detector.
 *
 * Why not Silero-in-browser by default:
 * - No ONNX/WASM model download (saves RAM on 8 GB hosts)
 * - Deterministic for unit tests with synthetic frames
 * - Language-independent
 *
 * Silero remains an INTEGRATE_LATER adapter behind the same contract
 * if measured accuracy requires it.
 */

import { DEFAULT_VAD_CONFIG, createEmptyVadHealth } from "./vad-contract.js";

/**
 * @param {Float32Array|number[]} frame
 */
export function frameRms(frame) {
  if (!frame?.length) return 0;
  let s = 0;
  for (let i = 0; i < frame.length; i += 1) {
    const v = frame[i];
    s += v * v;
  }
  return Math.sqrt(s / frame.length);
}

/**
 * @param {Float32Array|number[]} frame
 */
export function frameZcr(frame) {
  if (!frame || frame.length < 2) return 0;
  let z = 0;
  for (let i = 1; i < frame.length; i += 1) {
    if ((frame[i] >= 0 && frame[i - 1] < 0) || (frame[i] < 0 && frame[i - 1] >= 0)) z += 1;
  }
  return z / (frame.length - 1);
}

/**
 * Create energy VAD implementing VoiceActivityDetector contract.
 * @param {Partial<import('./vad-contract.js').VadConfig> & { bargeInMode?: boolean }} [opts]
 * @returns {import('./vad-contract.js').VoiceActivityDetector}
 */
export function createEnergyVad(opts = {}) {
  let cfg = { ...DEFAULT_VAD_CONFIG, ...opts };
  let state = "idle";
  let speechActive = false;
  let confirmCount = 0;
  let silenceMs = 0;
  let speechMs = 0;
  let lastRms = 0;
  let lastZcr = 0;
  let framesProcessed = 0;
  let error = "";
  let frameMs = (cfg.frameSize / cfg.sampleRate) * 1000;

  /** @type {Set<Function>} */
  const startListeners = new Set();
  /** @type {Set<Function>} */
  const endListeners = new Set();

  function emitStart(ev) {
    for (const fn of startListeners) {
      try {
        fn(ev);
      } catch {
        /* ignore */
      }
    }
  }
  function emitEnd(ev) {
    for (const fn of endListeners) {
      try {
        fn(ev);
      } catch {
        /* ignore */
      }
    }
  }

  function threshold() {
    return cfg.bargeInMode ? cfg.bargeInThreshold : cfg.speechStartThreshold;
  }

  return {
    configure(next) {
      cfg = { ...cfg, ...next };
      frameMs = (cfg.frameSize / cfg.sampleRate) * 1000;
    },
    setBargeInMode(on) {
      cfg.bargeInMode = Boolean(on);
    },
    async start() {
      state = "running";
      speechActive = false;
      confirmCount = 0;
      silenceMs = 0;
      speechMs = 0;
      error = "";
    },
    async stop() {
      if (speechActive) {
        speechActive = false;
        emitEnd({ at: Date.now(), reason: "stop" });
      }
      state = "stopped";
    },
    processAudioFrame(frame, meta = {}) {
      if (state !== "running" && state !== "speech" && state !== "silence") {
        // allow process while running
        if (state === "idle" || state === "stopped") return;
      }
      if (state === "stopped") return;

      framesProcessed += 1;
      const rms = frameRms(frame);
      const zcr = frameZcr(frame);
      lastRms = rms;
      lastZcr = zcr;
      const thr = threshold();
      // Speech-like: enough energy; ZCR not pathologically high (pure noise) or zero
      const speechLike = rms >= thr && zcr > 0.01 && zcr < 0.45;

      if (!speechActive) {
        if (speechLike) {
          confirmCount += 1;
          if (confirmCount >= cfg.startConfirmFrames) {
            speechActive = true;
            speechMs = confirmCount * frameMs;
            silenceMs = 0;
            state = "speech";
            emitStart({
              at: Date.now(),
              rms,
              zcr,
              bargeInMode: Boolean(cfg.bargeInMode),
              ...meta,
            });
          }
        } else {
          confirmCount = 0;
          state = "silence";
        }
      } else {
        speechMs += frameMs;
        if (speechLike) {
          silenceMs = 0;
        } else {
          silenceMs += frameMs;
          if (
            silenceMs >= cfg.speechEndSilenceMs &&
            speechMs >= cfg.minSpeechDurationMs
          ) {
            speechActive = false;
            state = "silence";
            emitEnd({ at: Date.now(), rms, speechMs, reason: "silence" });
            confirmCount = 0;
            speechMs = 0;
            silenceMs = 0;
          }
        }
        if (speechMs >= cfg.maxUtteranceDurationMs) {
          speechActive = false;
          state = "silence";
          emitEnd({ at: Date.now(), rms, speechMs, reason: "max_duration" });
          confirmCount = 0;
          speechMs = 0;
          silenceMs = 0;
        }
      }
    },
    onSpeechStart(cb) {
      startListeners.add(cb);
      return () => startListeners.delete(cb);
    },
    onSpeechEnd(cb) {
      endListeners.add(cb);
      return () => endListeners.delete(cb);
    },
    health() {
      return {
        ...createEmptyVadHealth(),
        state,
        adapter: "energy_zcr_v1",
        available: true,
        lastRms,
        lastZcr,
        speechActive,
        error,
        framesProcessed,
        threshold: threshold(),
        bargeInMode: Boolean(cfg.bargeInMode),
        config: { ...cfg },
      };
    },
  };
}
