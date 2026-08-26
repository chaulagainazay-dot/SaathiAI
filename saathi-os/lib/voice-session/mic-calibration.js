/**
 * Microphone energy calibration — the measurement, with no browser in it.
 *
 * R2.1-D18: a physical voice attempt opened the microphone, delivered 4849
 * frames to the VAD, and never once satisfied the speech-start condition —
 * `speechDetected` stayed false, so no turn was ever created and no transcript
 * could exist. The panel reports `lastRms`, the most recent frame, which cannot
 * distinguish "the speech was too quiet" from "the speech was fine and
 * something else is wrong". Classifying that needs distributions across known
 * conditions, not a single trailing sample.
 *
 * So this computes, from the frames the *production* tap produces and the
 * *production* RMS/ZCR functions, what the *production* speech-start rule would
 * have decided. Nothing here re-implements that rule: `isSpeechLikeFrame` is
 * imported from the live VAD, so calibration cannot quietly measure something
 * the pipeline does not use.
 *
 * Everything in this module is pure. It holds numbers — never audio, never a
 * MediaStream, never a device id.
 */
import { isSpeechLikeFrame } from "./energy-vad.js";
import { DEFAULT_VAD_CONFIG } from "./vad-contract.js";

/** The guided sequence. Fixed durations so two runs are comparable. */
export const CALIBRATION_PHASES = Object.freeze([
  Object.freeze({ id: "silence", label: "Stay silent", seconds: 5, speak: false }),
  Object.freeze({ id: "normal", label: "Speak normally", seconds: 5, speak: true }),
  Object.freeze({ id: "clear", label: "Speak clearly, 20–30 cm away", seconds: 5, speak: true }),
]);

export const CALIBRATION_SENTENCE =
  "Hello Saathi, this is Ajay testing the microphone.";

export const CALIBRATION_TOTAL_SECONDS = CALIBRATION_PHASES.reduce(
  (total, p) => total + p.seconds, 0,
);

/**
 * Which phase a sample belongs to, from elapsed milliseconds.
 *
 * Boundaries are half-open: a sample at exactly 5000 ms is the first sample of
 * the second phase, not the last of the first. Returns null once the sequence
 * is over, so late frames are dropped rather than attributed to the last phase.
 */
export function phaseAtElapsed(elapsedMs, phases = CALIBRATION_PHASES) {
  if (!(elapsedMs >= 0)) return null;
  let start = 0;
  for (const phase of phases) {
    const end = start + phase.seconds * 1000;
    if (elapsedMs < end) return phase.id;
    start = end;
  }
  return null;
}

/** Linear-interpolation-free quantile: the value at or above the fraction. */
export function quantile(sorted, fraction) {
  if (!sorted.length) return 0;
  if (fraction <= 0) return sorted[0];
  if (fraction >= 1) return sorted[sorted.length - 1];
  const idx = Math.min(sorted.length - 1, Math.floor(fraction * sorted.length));
  return sorted[idx];
}

export function median(sorted) {
  if (!sorted.length) return 0;
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * Summarise one phase's frames.
 *
 * `maxConsecutiveSpeechLike` is the number that actually decides a turn: the
 * live VAD needs `startConfirmFrames` consecutive speech-like frames before it
 * declares speech. Counting frames that merely pass the RMS threshold would
 * overstate the case, which is why both conditions are evaluated together and
 * the run length is tracked rather than a total.
 *
 * @param {Array<{rms:number, zcr:number}>} samples
 */
export function summarisePhase(samples, {
  threshold = DEFAULT_VAD_CONFIG.speechStartThreshold,
  startConfirmFrames = DEFAULT_VAD_CONFIG.startConfirmFrames,
} = {}) {
  const rms = samples.map((s) => s.rms).sort((a, b) => a - b);
  const zcr = samples.map((s) => s.zcr).sort((a, b) => a - b);

  let run = 0;
  let maxRun = 0;
  let aboveThreshold = 0;
  let inZcrRange = 0;
  for (const s of samples) {
    if (s.rms >= threshold) aboveThreshold += 1;
    const speechLike = isSpeechLikeFrame(s.rms, s.zcr, threshold);
    if (speechLike) {
      run += 1;
      if (run > maxRun) maxRun = run;
    } else {
      run = 0;
    }
    // "Inside the required ZCR range" independent of energy, so a phase that
    // failed only on loudness is distinguishable from one that failed on shape.
    if (isSpeechLikeFrame(threshold, s.zcr, threshold)) inZcrRange += 1;
  }

  return {
    frames: samples.length,
    minRms: rms.length ? rms[0] : 0,
    medianRms: median(rms),
    p95Rms: quantile(rms, 0.95),
    maxRms: rms.length ? rms[rms.length - 1] : 0,
    medianZcr: median(zcr),
    p95Zcr: quantile(zcr, 0.95),
    maxZcr: zcr.length ? zcr[zcr.length - 1] : 0,
    framesAboveThreshold: aboveThreshold,
    framesInZcrRange: inZcrRange,
    maxConsecutiveSpeechLike: maxRun,
    wouldTrigger: maxRun >= startConfirmFrames,
  };
}

/**
 * The whole run: per-phase statistics plus the comparisons that classify D18.
 *
 * The noise floor is the silent phase's p95 rather than its maximum: a single
 * door-slam frame should not define the floor a threshold has to clear.
 */
export function summariseCalibration(samplesByPhase, opts = {}) {
  const threshold = opts.threshold ?? DEFAULT_VAD_CONFIG.speechStartThreshold;
  const startConfirmFrames = opts.startConfirmFrames ?? DEFAULT_VAD_CONFIG.startConfirmFrames;

  const phases = {};
  for (const phase of CALIBRATION_PHASES) {
    phases[phase.id] = summarisePhase(samplesByPhase[phase.id] || [], {
      threshold, startConfirmFrames,
    });
  }

  const noiseFloor = phases.silence.p95Rms;
  const ratio = (value) => (noiseFloor > 0 ? value / noiseFloor : null);

  return {
    threshold,
    startConfirmFrames,
    zcrRange: { min: 0.01, max: 0.45 },
    phases,
    noiseFloor,
    normalSpeechToNoise: ratio(phases.normal.p95Rms),
    clearSpeechToNoise: ratio(phases.clear.p95Rms),
    wouldTriggerNormal: phases.normal.wouldTrigger,
    wouldTriggerClear: phases.clear.wouldTrigger,
    falseTriggerInSilence: phases.silence.wouldTrigger,
  };
}

/**
 * Track settings worth reporting, with the device id deliberately absent.
 *
 * A stable device id is a fingerprinting surface and is never rendered. The
 * human-readable label is, because "which microphone answered" is the first
 * question a calibration has to settle.
 */
export function describeTrackSettings(track) {
  const settings = track?.getSettings?.() || {};
  return {
    label: track?.label || "",
    sampleRate: settings.sampleRate ?? null,
    channelCount: settings.channelCount ?? null,
    echoCancellation: settings.echoCancellation ?? null,
    noiseSuppression: settings.noiseSuppression ?? null,
    autoGainControl: settings.autoGainControl ?? null,
  };
}
