"use client";

/**
 * R2.1 — Owner-validation diagnostics panel (read-only).
 *
 * Observes the canonical voice runtime that the shell already mounts. It does
 * not open a microphone, does not construct a SpeechRecognition instance, does
 * not start or stop a voice session, and holds no execution authority: every
 * value below is read from the published VoiceSessionManager snapshot, the
 * input/output owner singletons, and browser permission state.
 *
 * Use the normal Live voice dock to drive the session; watch this panel.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVoiceSession } from "./VoiceSessionProvider";
import {
  getInputOwnerSnapshot,
  getOutputOwnerSnapshot,
  getVoiceTelemetrySnapshot,
  subscribeInputOwner,
  subscribeOutputOwner,
} from "@/lib/voice-session";
import { buildVoiceDiagnostics } from "@/lib/voice-diagnostics";

const POLL_MS = 150;

const wrap = {
  border: "1px solid var(--border-subtle, rgba(255,255,255,.12))",
  borderRadius: 16,
  padding: 16,
  background: "var(--surface-raised, rgba(16,22,38,.78))",
  display: "grid",
  gap: 14,
};
const grid = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
  gap: 10,
};
const cell = {
  border: "1px solid rgba(255,255,255,.08)",
  borderRadius: 10,
  padding: "8px 10px",
  display: "grid",
  gap: 3,
};
const cellLabel = { fontSize: 10.5, letterSpacing: ".05em", textTransform: "uppercase", opacity: 0.6 };
const cellValue = { fontSize: 13.5, fontWeight: 650, wordBreak: "break-word" };

function tone(ok, warn = false) {
  if (warn) return "#f2b84b";
  return ok ? "#2dd4a8" : "#8fa0c4";
}

function Stat({ label, value, color, testId }) {
  return (
    <div style={cell} data-testid={testId}>
      <span style={cellLabel}>{label}</span>
      <span style={{ ...cellValue, color: color || "inherit" }}>{value}</span>
    </div>
  );
}

export default function VoiceDiagnosticsPanel() {
  const voiceSession = useVoiceSession();
  const manager = voiceSession?.manager || null;
  const session = voiceSession?.session || {};

  const [inputOwner, setInputOwner] = useState(() => getInputOwnerSnapshot());
  const [outputOwner, setOutputOwner] = useState(() => getOutputOwnerSnapshot());
  const [vadHealth, setVadHealth] = useState(null);
  const [permission, setPermission] = useState("unknown");
  const [deviceLabel, setDeviceLabel] = useState("");
  const [telemetry, setTelemetry] = useState(null);
  const [showTranscript, setShowTranscript] = useState(true);
  const [clearedAt, setClearedAt] = useState("");
  const clearedRef = useRef("");
  // Every value here depends on browser capability detection, so the server and
  // the first client render disagree (e.g. speech recognition "unavailable" vs
  // "available"). Render the server-safe placeholder first and publish the real
  // state after mount, the same way /unlock handles WebAuthn probing.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    const unsubIn = subscribeInputOwner(setInputOwner);
    const unsubOut = subscribeOutputOwner(setOutputOwner);
    return () => {
      unsubIn();
      unsubOut();
    };
  }, []);

  // Permission is observed, never requested. The Live voice dock remains the only
  // place in this app that asks the browser for microphone capture.
  useEffect(() => {
    let active = true;
    if (!navigator.permissions?.query) return undefined;
    let handle = null;
    navigator.permissions
      .query({ name: "microphone" })
      .then((status) => {
        if (!active) return;
        handle = status;
        setPermission(status.state === "prompt" ? "unknown" : status.state);
        status.onchange = () => {
          if (active) setPermission(status.state === "prompt" ? "unknown" : status.state);
        };
      })
      .catch(() => setPermission("unknown"));
    return () => {
      active = false;
      if (handle) handle.onchange = null;
    };
  }, []);

  // Poll the live sensors the manager does not publish per frame (RMS, frame
  // counters, device label of the stream the dock already opened).
  useEffect(() => {
    let active = true;
    const tick = () => {
      if (!active) return;
      try {
        setVadHealth(manager?.getBargeInHealth?.() || null);
      } catch {
        /* sensor optional */
      }
      try {
        const stream = manager?.getInputClaim?.()?.mediaStream || null;
        const track = stream?.getAudioTracks?.()?.[0] || null;
        setDeviceLabel(track?.label || "");
      } catch {
        setDeviceLabel("");
      }
      try {
        setTelemetry(getVoiceTelemetrySnapshot());
      } catch {
        /* telemetry optional */
      }
    };
    tick();
    const timer = setInterval(tick, POLL_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [manager]);

  const view = useMemo(
    () =>
      buildVoiceDiagnostics({
        session,
        inputOwner,
        outputOwner,
        vadHealth,
        permission,
        deviceLabel,
        telemetry,
      }),
    [session, inputOwner, outputOwner, vadHealth, permission, deviceLabel, telemetry]
  );

  const clearTranscript = useCallback(() => {
    const stamp = new Date().toISOString();
    clearedRef.current = stamp;
    setClearedAt(stamp);
    setShowTranscript(false);
  }, []);

  const meterPct = Math.max(0, Math.min(100, Math.round(view.rms * 100 * 6)));
  const thresholdPct = Math.max(
    0,
    Math.min(100, Math.round(view.vadThreshold * 100 * 6))
  );

  return (
    <section
      style={wrap}
      aria-label="Voice runtime diagnostics"
      data-testid="voice-diagnostics-panel"
      data-mounted={mounted ? "true" : "false"}
      data-mic-permission={mounted ? view.permission : undefined}
      data-session-state={mounted ? view.sessionState : undefined}
      data-input-state={mounted ? view.inputState : undefined}
      data-output-state={mounted ? view.outputState : undefined}
      data-vad-lane={mounted ? view.vadLane : undefined}
      data-barge-in-class={mounted ? view.bargeInClass : undefined}
      data-tts-lane={mounted ? view.ttsLane : undefined}
      data-cleanup={mounted ? (view.cleanup.clean ? "clean" : "held") : undefined}
      data-duplicate-input-owner={
        mounted ? (view.ownership.duplicateInputOwner ? "true" : "false") : undefined
      }
      data-error-category={mounted ? view.errorCategory : undefined}
    >
      <header style={{ display: "grid", gap: 4 }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>Voice runtime diagnostics</h2>
        <p style={{ margin: 0, fontSize: 12.5, opacity: 0.65 }}>
          Read-only. This panel observes the live voice session; it never opens the
          microphone, never starts recognition, and holds no execution authority.
          Drive the session from the <strong>Live voice</strong> dock.
        </p>
      </header>

      {!mounted ? (
        <p style={{ margin: 0, fontSize: 12.5, opacity: 0.6 }} data-testid="diag-initialising">
          Reading the live voice session…
        </p>
      ) : (
      <>
      <div style={grid}>
        <Stat
          label="Mic permission"
          value={view.permission}
          color={tone(view.permission === "granted", view.permission === "denied")}
          testId="diag-permission"
        />
        <Stat
          label="Input device"
          value={view.deviceLabel || "— (no open stream)"}
          testId="diag-device"
        />
        <Stat label="Session state" value={view.sessionState} testId="diag-session-state" />
        <Stat
          label="Input ownership"
          value={`${view.inputState} · ${view.ownership.label}`}
          color={tone(!view.ownership.duplicateInputOwner, view.ownership.duplicateInputOwner)}
          testId="diag-input-ownership"
        />
        <Stat label="Output ownership" value={view.outputState} testId="diag-output-ownership" />
        <Stat
          label="VAD lane"
          value={view.vadLane}
          color={tone(view.vadLane === "speech")}
          testId="diag-vad-lane"
        />
        <Stat
          label="Speech recognition"
          value={`${view.speechRecognitionAvailable ? "available" : "unavailable"} · ${view.sttEngineLabel}${view.sttDegraded ? " · degraded" : ""}`}
          color={tone(view.speechRecognitionAvailable, view.sttDegraded)}
          testId="diag-stt"
        />
        <Stat label="TTS lane" value={view.ttsLane} testId="diag-tts-lane" />
        <Stat
          label="Barge-in"
          value={`${view.bargeInClass}${view.bargeInLatencyMs != null ? ` · ${Math.round(view.bargeInLatencyMs)}ms` : ""}`}
          testId="diag-barge-in"
        />
        <Stat
          label="Turns finalized"
          value={`${view.finalizedTurns} · real ${view.realInterrupts} · false ${view.falseInterrupts}`}
          testId="diag-turns"
        />
        <Stat
          label="Last error category"
          value={view.errorCategory}
          color={tone(view.errorCategory === "none", view.errorCategory !== "none")}
          testId="diag-error"
        />
        <Stat
          label="Resource cleanup"
          value={view.cleanup.label}
          color={tone(view.cleanup.clean)}
          testId="diag-cleanup"
        />
      </div>

      <div style={{ display: "grid", gap: 6 }}>
        <span style={cellLabel}>Input energy (RMS {view.rms.toFixed(4)} · threshold {view.vadThreshold.toFixed(4)})</span>
        <div
          style={{
            position: "relative",
            height: 10,
            borderRadius: 999,
            background: "rgba(255,255,255,.07)",
            overflow: "hidden",
          }}
          role="meter"
          aria-label="Microphone input energy"
          aria-valuenow={meterPct}
          aria-valuemin={0}
          aria-valuemax={100}
          data-testid="diag-energy-meter"
          data-rms-nonzero={view.rms > 0 ? "true" : "false"}
        >
          <div
            style={{
              width: `${meterPct}%`,
              height: "100%",
              background: view.vadLane === "speech" ? "#2dd4a8" : "#5b7cc4",
            }}
          />
          <div
            aria-hidden="true"
            style={{
              position: "absolute",
              left: `${thresholdPct}%`,
              top: 0,
              bottom: 0,
              width: 2,
              background: "#f2b84b",
            }}
          />
        </div>
        <span style={{ fontSize: 11.5, opacity: 0.55 }}>
          VAD frames {view.vadFrames} · tap frames {view.tapFrames}. Audio is analysed
          in memory for energy only; no audio is recorded, stored, or uploaded.
        </span>
      </div>

      <div style={{ display: "grid", gap: 6 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <span style={cellLabel}>Transcript (ephemeral)</span>
          <button
            type="button"
            onClick={clearTranscript}
            style={{
              border: "1px solid rgba(255,255,255,.16)",
              background: "rgba(255,255,255,.06)",
              color: "inherit",
              borderRadius: 8,
              padding: "4px 9px",
              fontSize: 11.5,
              cursor: "pointer",
            }}
            data-testid="diag-clear-transcript"
          >
            Clear from view
          </button>
          {!showTranscript && (
            <button
              type="button"
              onClick={() => setShowTranscript(true)}
              style={{
                border: "1px solid rgba(255,255,255,.16)",
                background: "transparent",
                color: "inherit",
                borderRadius: 8,
                padding: "4px 9px",
                fontSize: 11.5,
                cursor: "pointer",
              }}
            >
              Show again
            </button>
          )}
        </div>
        {showTranscript ? (
          <>
            <p style={{ margin: 0, fontSize: 13 }} data-testid="diag-partial">
              <strong>Partial (never executable):</strong>{" "}
              {view.partialTranscript || <span style={{ opacity: 0.45 }}>—</span>}
            </p>
            <p style={{ margin: 0, fontSize: 13 }} data-testid="diag-final">
              <strong>Final:</strong>{" "}
              {view.finalTranscript || <span style={{ opacity: 0.45 }}>—</span>}
            </p>
            <p style={{ margin: 0, fontSize: 12 }} data-testid="diag-turn-flags">
              Turn reason <code>{view.turnReason || "—"}</code> · executable{" "}
              <strong>{String(view.turnIsExecutable)}</strong> · backchannel{" "}
              <strong>{String(view.turnIsBackchannel)}</strong> · authority{" "}
              <strong>{view.turnAuthority}</strong>
            </p>
          </>
        ) : (
          <p style={{ margin: 0, fontSize: 12.5, opacity: 0.6 }} data-testid="diag-transcript-cleared">
            Transcript hidden{clearedAt ? " from view" : ""}. Nothing was persisted.
          </p>
        )}
      </div>

      <footer style={{ display: "grid", gap: 4, fontSize: 11.5, opacity: 0.6 }}>
        <span>
          Claimed capabilities — acoustic barge-in{" "}
          <strong>{String(view.capabilityClaims.acousticBargeIn)}</strong>, full duplex{" "}
          <strong>{String(view.capabilityClaims.fullDuplex)}</strong>, wake word{" "}
          <strong>{String(view.capabilityClaims.wakeWord)}</strong>.
        </span>
        <span>
          Voice never grants execution or approval authority. Actionable commands
          continue through the authenticated command pipeline and the existing
          approval / ExecutionGateway boundary.
        </span>
      </footer>
      </>
      )}
    </section>
  );
}
