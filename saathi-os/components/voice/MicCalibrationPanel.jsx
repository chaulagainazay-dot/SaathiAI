"use client";
/**
 * Owned microphone energy calibration (R2.1-D18).
 *
 * A physical voice attempt delivered thousands of frames to the VAD and never
 * satisfied the speech-start rule, so no turn — and therefore no transcript —
 * could exist. Deciding whether that was a quiet input path, an over-high
 * threshold, or a frame-format defect needs measured distributions for known
 * conditions. This surface produces them, and nothing else.
 *
 * What it deliberately is not: it opens no backend session, constructs no
 * recognizer and no MediaRecorder, sends no request of any kind, and keeps no
 * audio. It holds numbers derived from frames the production tap produced, and
 * those numbers live in component state until Clear or unmount.
 *
 * It takes the same single input claim Live Voice takes, so the two can never
 * own the microphone at once: whichever starts second preempts the first, and
 * preemption tears this surface down.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  acquireInputClaim,
  openMicrophoneForClaim,
} from "@/lib/voice-session/input-owner";
import { createAudioFrameTap } from "@/lib/voice-session/audio-frame-tap";
import { frameRms, frameZcr } from "@/lib/voice-session/energy-vad";
import {
  CALIBRATION_PHASES,
  CALIBRATION_SENTENCE,
  CALIBRATION_TOTAL_SECONDS,
  phaseAtElapsed,
  summariseCalibration,
  describeTrackSettings,
} from "@/lib/voice-session/mic-calibration";

const ACCENT = "#9B6BFF";

export default function MicCalibrationPanel() {
  const [phase, setPhase] = useState("");        // "" while idle
  const [remaining, setRemaining] = useState(0);
  const [status, setStatus] = useState("");
  const [results, setResults] = useState(null);
  const [device, setDevice] = useState(null);

  const claimRef = useRef(null);
  const tapRef = useRef(null);
  const streamRef = useRef(null);
  const samplesRef = useRef({});
  const startedAtRef = useRef(0);
  const timerRef = useRef(null);
  const stoppedRef = useRef(false);

  /**
   * One teardown for every exit: completion, Stop, error, preemption, route
   * change, unmount, logout. Idempotent, because several of those can happen in
   * the same tick (a preempt that also throws, a Stop during teardown).
   */
  const teardown = useCallback((nextStatus) => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    try { tapRef.current?.stop?.(); } catch { /* already stopped */ }
    tapRef.current = null;
    // Stop tracks directly as well as through the claim: a run that failed
    // between getUserMedia and setMediaStream still has a live device.
    try { streamRef.current?.getTracks?.().forEach((t) => t.stop()); } catch { /* gone */ }
    streamRef.current = null;
    const claim = claimRef.current;
    claimRef.current = null;
    try { claim?.release?.(); } catch { /* already released */ }
    setPhase("");
    setRemaining(0);
    if (nextStatus !== undefined) setStatus(nextStatus);
  }, []);

  // Route change, unmount and logout all reach this.
  useEffect(() => () => teardown(), [teardown]);

  const finish = useCallback(() => {
    if (stoppedRef.current) return;
    stoppedRef.current = true;
    const collected = samplesRef.current;
    const summary = summariseCalibration(collected);
    setResults(summary);
    teardown("Calibration complete. Microphone released.");
  }, [teardown]);

  const start = useCallback(async () => {
    if (claimRef.current) return;
    stoppedRef.current = false;
    samplesRef.current = Object.fromEntries(CALIBRATION_PHASES.map((p) => [p.id, []]));
    setResults(null);
    setStatus("Requesting the microphone…");

    const claim = acquireInputClaim({
      label: "diagnostics.mic-calibration",
      onPreempt: () => teardown("Another voice surface took the microphone. Calibration stopped."),
    });
    claimRef.current = claim;

    let stream;
    try {
      // No constraint argument: the production DEFAULT_MIC_CONSTRAINTS contract
      // applies, so this measures what Live Voice would actually receive.
      stream = await openMicrophoneForClaim(claim);
    } catch (error) {
      const denied = /denied|not.?allowed|permission/i.test(String(error?.name || error?.message || ""));
      teardown(denied
        ? "Microphone permission was denied. Nothing was captured."
        : "The microphone could not be opened. Nothing was captured.");
      return;
    }
    streamRef.current = stream;
    setDevice(describeTrackSettings(stream.getAudioTracks?.()[0]));

    startedAtRef.current = Date.now();
    const tap = createAudioFrameTap({
      stream,
      onFrame: (frame) => {
        const elapsed = Date.now() - startedAtRef.current;
        const id = phaseAtElapsed(elapsed);
        if (!id) return;                       // past the end: dropped, not misattributed
        // Only two numbers per frame are kept. The frame itself is not retained.
        samplesRef.current[id].push({ rms: frameRms(frame), zcr: frameZcr(frame) });
      },
    });
    tapRef.current = tap;
    try {
      await tap.start();
    } catch {
      teardown("The audio analyser could not start. Nothing was captured.");
      return;
    }

    setPhase(CALIBRATION_PHASES[0].id);
    setRemaining(CALIBRATION_TOTAL_SECONDS);
    setStatus("Calibrating. Audio is analysed in memory only.");
    timerRef.current = setInterval(() => {
      const elapsed = Date.now() - startedAtRef.current;
      const id = phaseAtElapsed(elapsed);
      setRemaining(Math.max(0, Math.ceil((CALIBRATION_TOTAL_SECONDS * 1000 - elapsed) / 1000)));
      if (!id) { finish(); return; }
      setPhase(id);
    }, 200);
  }, [finish, teardown]);

  const stop = useCallback(() => {
    if (!claimRef.current) return;
    finish();
  }, [finish]);

  const clear = useCallback(() => {
    setResults(null);
    setDevice(null);
    samplesRef.current = {};
    setStatus("Results cleared.");
  }, []);

  const active = Boolean(phase);
  const current = CALIBRATION_PHASES.find((p) => p.id === phase);

  return (
    <section
      data-testid="mic-calibration-panel"
      data-calibration-phase={phase || "idle"}
      data-calibration-active={active ? "true" : "false"}
      style={{ padding: 18, marginTop: 14, border: "1px solid rgba(255,255,255,0.12)", borderRadius: 12 }}
    >
      <div style={{ fontSize: 13, fontWeight: 600 }}>Calibrate microphone</div>
      <p style={{ fontSize: 12, opacity: 0.65, lineHeight: 1.55, margin: "6px 0 12px" }}>
        Measures input energy against the same speech-detection rule Live Voice
        uses. Audio is analysed in memory and is not recorded, stored or
        uploaded. Calibration creates no voice session and no executable turn,
        grants no authority, and its numbers disappear when cleared or when this
        page closes.
      </p>

      {!active && (
        <button type="button" onClick={start} data-testid="calibration-start"
          style={{ padding: "10px 14px", borderRadius: 10, border: "none", cursor: "pointer",
                   background: ACCENT, color: "#fff", fontWeight: 600 }}>
          Start calibration ({CALIBRATION_TOTAL_SECONDS}s)
        </button>
      )}

      {active && (
        <div data-testid="calibration-running">
          <div style={{ fontSize: 15, fontWeight: 600 }}>
            {current?.label} — {remaining}s left
          </div>
          {current?.speak && (
            <div style={{ fontSize: 14, marginTop: 6, color: ACCENT }}>
              “{CALIBRATION_SENTENCE}”
            </div>
          )}
          <button type="button" onClick={stop} data-testid="calibration-stop"
            style={{ marginTop: 10, padding: "8px 12px", borderRadius: 10,
                     border: "1px solid rgba(255,255,255,0.2)", background: "transparent",
                     color: "inherit", cursor: "pointer" }}>
            Stop
          </button>
        </div>
      )}

      {status && <div style={{ fontSize: 12, opacity: 0.6, marginTop: 10 }}>{status}</div>}

      {device && (
        <div style={{ fontSize: 12, opacity: 0.75, marginTop: 10 }} data-testid="calibration-device">
          Input: {device.label || "unnamed"} · {device.sampleRate ?? "?"} Hz ·{" "}
          {device.channelCount ?? "?"} ch · echoCancellation {String(device.echoCancellation)} ·
          noiseSuppression {String(device.noiseSuppression)} ·
          autoGainControl {String(device.autoGainControl)}
        </div>
      )}

      {results && (
        <div style={{ marginTop: 12 }} data-testid="calibration-results">
          <table style={{ fontSize: 12, borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr style={{ opacity: 0.6, textAlign: "left" }}>
                <th>Phase</th><th>Frames</th><th>min</th><th>median</th><th>p95</th><th>max</th>
                <th>ZCR med</th><th>≥thr</th><th>run</th><th>would trigger</th>
              </tr>
            </thead>
            <tbody>
              {CALIBRATION_PHASES.map((p) => {
                const r = results.phases[p.id];
                return (
                  <tr key={p.id} data-testid={`calibration-row-${p.id}`}>
                    <td>{p.id}</td><td>{r.frames}</td>
                    <td>{r.minRms.toFixed(4)}</td><td>{r.medianRms.toFixed(4)}</td>
                    <td>{r.p95Rms.toFixed(4)}</td><td>{r.maxRms.toFixed(4)}</td>
                    <td>{r.medianZcr.toFixed(3)}</td><td>{r.framesAboveThreshold}</td>
                    <td>{r.maxConsecutiveSpeechLike}</td>
                    <td>{r.wouldTrigger ? "yes" : "no"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div style={{ fontSize: 12, opacity: 0.75, marginTop: 8 }}>
            Threshold {results.threshold.toFixed(4)} · confirm frames{" "}
            {results.startConfirmFrames} · noise floor (silence p95){" "}
            {results.noiseFloor.toFixed(4)} · normal/noise{" "}
            {results.normalSpeechToNoise === null ? "—" : results.normalSpeechToNoise.toFixed(1)}× ·
            clear/noise{" "}
            {results.clearSpeechToNoise === null ? "—" : results.clearSpeechToNoise.toFixed(1)}×
          </div>
          <button type="button" onClick={clear} data-testid="calibration-clear"
            style={{ marginTop: 10, padding: "8px 12px", borderRadius: 10,
                     border: "1px solid rgba(255,255,255,0.2)", background: "transparent",
                     color: "inherit", cursor: "pointer" }}>
            Clear results
          </button>
        </div>
      )}
    </section>
  );
}
