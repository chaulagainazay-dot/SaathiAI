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
import { createTrackProcessorAudioFrameSource, isTrackProcessorAudioSupported } from "@/lib/voice-session/track-processor-audio-frame-source";
import { frameRms, frameZcr } from "@/lib/voice-session/energy-vad";
import {
  createCalibrationCapture,
  TERMINAL_REASONS,
} from "@/lib/voice-session/calibration-capture";
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

  const captureRef = useRef(null);
  const samplesRef = useRef({});
  const startedAtRef = useRef(0);

  /**
   * One terminal handler for every exit — completion, Stop, the hard deadline,
   * an error, preemption, route change, logout and unmount. The capture manager
   * guarantees it runs exactly once per generation and that the microphone is
   * already released by the time it does.
   */
  const onTerminal = useCallback((reason, _generation, diagnostics = {}) => {
    setPhase("");
    setRemaining(0);
    if (!diagnostics.tracksEnded || !diagnostics.graphClosed || !diagnostics.claimReleased) {
      setStatus("Microphone cleanup could not be confirmed. Please close this page.");
    } else if (reason === TERMINAL_REASONS.COMPLETED) {
      setResults(summariseCalibration(samplesRef.current));
      setStatus("Calibration complete. Microphone released.");
    } else if (reason === TERMINAL_REASONS.DEADLINE) {
      // Truthful: the measurement did not finish, so no results are published.
      setStatus("Calibration timed out and the microphone was released. No results.");
    } else if (reason === TERMINAL_REASONS.PREEMPTED) {
      setStatus("Another voice surface took the microphone. Calibration stopped.");
    } else if (reason === TERMINAL_REASONS.ERROR) {
      setStatus("The microphone could not be captured. Nothing was recorded.");
    } else if (reason === TERMINAL_REASONS.STOPPED) {
      setStatus("Calibration stopped. Microphone released.");
    }
  }, []);

  function capture() {
    if (!captureRef.current) {
      captureRef.current = createCalibrationCapture({
        acquireClaim: ({ onPreempt }) =>
          acquireInputClaim({ label: "diagnostics.mic-calibration", onPreempt }),
        openMicrophone: async (claim) => {
          const stream = await openMicrophoneForClaim(claim);
          setDevice(describeTrackSettings(stream.getAudioTracks?.()[0]));
          return stream;
        },
        createTap: (stream, onFrame) => createTrackProcessorAudioFrameSource({
          track: stream?.getAudioTracks?.()[0] || null,
          onFrame,
        }),
        onCleanupPending: () => {
          setPhase("");
          setRemaining(0);
          setStatus("Releasing microphone…");
        },
        onTerminal,
      });
    }
    return captureRef.current;
  }

  // Route change, unmount and logout all reach this. pagehide/beforeunload
  // synchronously stop tracks through the capture manager before any async
  // AudioContext close can run.
  useEffect(() => {
    const dispose = () => { captureRef.current?.stop?.(TERMINAL_REASONS.DISPOSED); };
    window.addEventListener("pagehide", dispose);
    window.addEventListener("beforeunload", dispose);
    return () => {
      window.removeEventListener("pagehide", dispose);
      window.removeEventListener("beforeunload", dispose);
      dispose();
    };
  }, []);

  const start = useCallback(async () => {
    if (!isTrackProcessorAudioSupported()) {
      setStatus("Calibration unavailable in this browser");
      return;
    }
    const cap = capture();
    if (cap.isActive()) return;
    samplesRef.current = Object.fromEntries(CALIBRATION_PHASES.map((p) => [p.id, []]));
    setResults(null);
    setDevice(null);
    setStatus("Requesting the microphone…");
    startedAtRef.current = Date.now();

    const outcome = await cap.start({
      onFrame: (frame) => {
        const id = phaseAtElapsed(Date.now() - startedAtRef.current);
        if (!id) return;
        samplesRef.current[id].push({ rms: frameRms(frame), zcr: frameZcr(frame) });
      },
      onRunning: () => {
        const elapsed = Date.now() - startedAtRef.current;
        const id = phaseAtElapsed(elapsed);
        setRemaining(Math.max(0, Math.ceil((CALIBRATION_TOTAL_SECONDS * 1000 - elapsed) / 1000)));
        if (!id) return true;                 // completed: the manager terminalizes
        setPhase(id);
        return false;
      },
      setIntervalImpl: setInterval,
      clearIntervalImpl: clearInterval,
    });

    if (outcome.started) {
      setPhase(CALIBRATION_PHASES[0].id);
      setRemaining(CALIBRATION_TOTAL_SECONDS);
      setStatus("Calibrating. Audio is analysed in memory only.");
    }
  }, [onTerminal]);

  const stop = useCallback(() => {
    captureRef.current?.stop?.(TERMINAL_REASONS.STOPPED);
  }, []);

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
