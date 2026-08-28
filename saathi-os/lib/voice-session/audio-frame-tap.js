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
  let cleanupPromise = null;
  let stopping = false;

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
      stopping = false;
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
      if (stopping) return;
      source = ctx.createMediaStreamSource(stream);
      if (stopping) {
        try { source.disconnect?.(); } catch { /* already disconnected */ }
        source = null;
        return;
      }
      analyser = ctx.createAnalyser();
      analyser.fftSize = Math.max(256, cfg.frameSize * 2);
      analyser.smoothingTimeConstant = 0.2;
      source.connect(analyser);
      const interval = Math.max(10, (cfg.frameSize / (ctx.sampleRate || cfg.sampleRate)) * 1000);
      timer = setInterval(tick, interval);
      running = true;
    },
    stop({ timeoutMs = 2000, setTimeoutImpl = setTimeout, clearTimeoutImpl = clearTimeout } = {}) {
      if (cleanupPromise) return cleanupPromise;
      cleanupPromise = (async () => {
      running = false;
      stopping = true;
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
      let closeResult = { state: "closed", confirmed: true };
      if (ctx) {
        const closing = ctx;
        try {
          const result = closing.close?.();
          if (result && typeof result.then === "function") {
            let timer;
            const timeout = new Promise((resolve) => { timer = setTimeoutImpl(() => resolve({ timedOut: true }), timeoutMs); });
            const settled = await Promise.race([
              result.then(() => ({ closed: true })).catch(() => ({ rejected: true })),
              timeout,
            ]);
            if (timer !== undefined) clearTimeoutImpl(timer);
            closeResult = settled.timedOut
              ? { state: closing.state || "unknown", confirmed: false, timedOut: true }
              : { state: closing.state || "unknown", confirmed: Boolean(settled.closed && closing.state === "closed") };
          } else {
            closeResult = { state: closing.state || "closed", confirmed: closing.state === undefined || closing.state === "closed" };
          }
        } catch {
          closeResult = { state: closing.state || "unknown", confirmed: false, rejected: true };
        }
        ctx = null;
      }
      return closeResult;
      })();
      return cleanupPromise;
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
