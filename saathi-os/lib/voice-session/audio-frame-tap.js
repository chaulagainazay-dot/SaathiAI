/**
 * Tap a single MediaStream for VAD frames without a second getUserMedia.
 * Uses AudioContext + AnalyserNode (no AudioWorklet required).
 */

import { DEFAULT_VAD_CONFIG } from "./vad-contract.js";
import { createPreRollBuffer } from "./pre-roll-buffer.js";

/**
 * @param {object} opts
 * @param {MediaStream} opts.stream
 * @param {(frame: Float32Array, meta: object) => void} opts.onFrame
 * @param {Partial<typeof DEFAULT_VAD_CONFIG>} [opts.config]
 * @param {typeof AudioContext} [opts.AudioContextImpl]
 */
export function createAudioFrameTap({
  stream,
  onFrame,
  config = {},
  AudioContextImpl = typeof AudioContext !== "undefined" ? AudioContext : null,
} = {}) {
  const cfg = { ...DEFAULT_VAD_CONFIG, ...config };
  const preRoll = createPreRollBuffer({
    sampleRate: cfg.sampleRate,
    preRollMs: cfg.preRollMs,
    frameSize: cfg.frameSize,
  });

  let ctx = null;
  let source = null;
  let analyser = null;
  let timer = null;
  let running = false;
  let frames = 0;

  function tick() {
    if (!running || !analyser) return;
    const buf = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(buf);
    // downsample-ish: use contiguous frameSize window
    const frame =
      buf.length === cfg.frameSize
        ? buf
        : buf.subarray(0, Math.min(cfg.frameSize, buf.length));
    const copy = frame.slice();
    preRoll.push(copy);
    frames += 1;
    onFrame?.(copy, {
      at: performance.now?.() ?? Date.now(),
      frameIndex: frames,
      preRollMs: preRoll.durationMs(),
    });
  }

  return {
    preRoll,
    async start() {
      if (running) return;
      if (!stream || !AudioContextImpl) {
        // Synthetic/tests/headless: no live tap; caller feeds processFrame
        running = true;
        return;
      }
      ctx = new AudioContextImpl();
      // Prefer 16k if browser allows
      try {
        await ctx.resume?.();
      } catch {
        /* ignore */
      }
      source = ctx.createMediaStreamSource(stream);
      analyser = ctx.createAnalyser();
      analyser.fftSize = Math.max(256, cfg.frameSize * 2);
      analyser.smoothingTimeConstant = 0.2;
      source.connect(analyser);
      const interval = Math.max(10, (cfg.frameSize / (ctx.sampleRate || cfg.sampleRate)) * 1000);
      timer = setInterval(tick, interval);
      running = true;
    },
    stop() {
      running = false;
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      try {
        source?.disconnect?.();
      } catch {
        /* ignore */
      }
      try {
        analyser?.disconnect?.();
      } catch {
        /* ignore */
      }
      source = null;
      analyser = null;
      if (ctx) {
        try {
          ctx.close?.();
        } catch {
          /* ignore */
        }
        ctx = null;
      }
    },
    /** Inject synthetic frames (tests / offline) */
    processFrame(frame, meta = {}) {
      const copy =
        frame instanceof Float32Array ? frame.slice() : Float32Array.from(frame || []);
      preRoll.push(copy);
      frames += 1;
      onFrame?.(copy, { at: Date.now(), frameIndex: frames, synthetic: true, ...meta });
    },
    clearPreRoll() {
      preRoll.clear();
    },
    getPreRoll() {
      return preRoll.snapshot();
    },
    health() {
      return {
        running,
        frames,
        preRollSamples: preRoll.sampleCount(),
        preRollMs: preRoll.durationMs(),
        hasContext: Boolean(ctx),
      };
    },
  };
}
