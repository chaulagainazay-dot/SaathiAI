/**
 * Bounded in-memory pre-roll of audio frames for barge-in / utterance start.
 * Never persisted to disk.
 */

export function createPreRollBuffer({
  sampleRate = 16000,
  preRollMs = 280,
  frameSize = 512,
} = {}) {
  const maxSamples = Math.max(frameSize, Math.ceil((sampleRate * preRollMs) / 1000));
  /** @type {Float32Array[]} */
  let chunks = [];
  let total = 0;

  return {
    push(frame) {
      if (!frame || !frame.length) return;
      const copy = frame instanceof Float32Array ? frame.slice() : Float32Array.from(frame);
      chunks.push(copy);
      total += copy.length;
      while (total > maxSamples && chunks.length > 1) {
        const dropped = chunks.shift();
        total -= dropped?.length || 0;
      }
      // trim head of first chunk if still over
      while (total > maxSamples && chunks[0]) {
        const need = total - maxSamples;
        if (need >= chunks[0].length) {
          total -= chunks[0].length;
          chunks.shift();
        } else {
          chunks[0] = chunks[0].subarray(need);
          total -= need;
        }
      }
    },
    /** Concatenated samples oldest→newest */
    snapshot() {
      const out = new Float32Array(total);
      let o = 0;
      for (const c of chunks) {
        out.set(c, o);
        o += c.length;
      }
      return out;
    },
    sampleCount() {
      return total;
    },
    durationMs() {
      return sampleRate > 0 ? (total / sampleRate) * 1000 : 0;
    },
    clear() {
      chunks = [];
      total = 0;
    },
    maxSamples,
  };
}
