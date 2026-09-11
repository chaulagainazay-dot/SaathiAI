/**
 * V-NEXT-2A — VoiceActivityDetector adapter contract.
 * VAD is a sensor only — never authority.
 */

/** @typedef {"idle"|"starting"|"running"|"speech"|"silence"|"error"|"stopped"} VadRuntimeState */

/**
 * @typedef {object} VadConfig
 * @property {number} [speechStartThreshold]  RMS 0–1
 * @property {number} [speechEndSilenceMs]
 * @property {number} [minSpeechDurationMs]
 * @property {number} [maxUtteranceDurationMs]
 * @property {number} [startConfirmFrames] consecutive frames above threshold
 * @property {number} [bargeInThreshold] higher threshold while assistant speaking
 * @property {number} [echoSuppressionMs] ignore barge-in after TTS start
 * @property {number} [frameSize]
 * @property {number} [sampleRate]
 */

export const DEFAULT_VAD_CONFIG = Object.freeze({
  speechStartThreshold: 0.018,
  speechEndSilenceMs: 450,
  minSpeechDurationMs: 120,
  maxUtteranceDurationMs: 20_000,
  startConfirmFrames: 3,
  bargeInThreshold: 0.032,
  echoSuppressionMs: 220,
  frameSize: 512,
  sampleRate: 16000,
  preRollMs: 280,
});

/**
 * @typedef {object} VoiceActivityDetector
 * @property {() => Promise<void>|void} start
 * @property {() => Promise<void>|void} stop
 * @property {(frame: Float32Array|number[], meta?: object) => void} processAudioFrame
 * @property {(cb: (ev: object) => void) => () => void} onSpeechStart
 * @property {(cb: (ev: object) => void) => () => void} onSpeechEnd
 * @property {() => object} health
 * @property {(cfg: Partial<VadConfig>) => void} [configure]
 */

export function createEmptyVadHealth() {
  return {
    state: "idle",
    adapter: "none",
    available: false,
    lastRms: 0,
    speechActive: false,
    error: "",
    framesProcessed: 0,
  };
}
