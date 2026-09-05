"use client";

import { useVoiceRuntime } from "./VoiceRuntimeProvider";

function stateColor(runtime) {
  if (runtime.interrupted && runtime.listening) return "#ff8c8c";
  if (runtime.speaking) return "#c9b6ff";
  if (runtime.recording) return "#ff5a5a";
  if (runtime.listening) return "#4fe3cb";
  if (runtime.state === "THINKING") return "#ffb04f";
  if (runtime.state === "FAILED") return "#ff5a5a";
  return "#8fa0c4";
}

export default function VoiceRuntimeDock() {
  const { token, runtime, busy, toggleMic, interrupt, retry, micLabel, inputMode, setInputMode } =
    useVoiceRuntime();
  if (!token) return null;

  const color = stateColor(runtime);

  return (
    <section
      className="voice-runtime-dock"
      data-voice-runtime-state={runtime.state}
      data-voice-input-state={runtime.inputState}
      aria-label="Real-time voice conversation"
    >
      <div className="voice-runtime-head">
        <strong>Live voice</strong>
        <span
          className="voice-runtime-badge"
          style={{ color, borderColor: `${color}66`, background: `${color}22` }}
          aria-live="polite"
        >
          {runtime.speaking
            ? "Speaking"
            : runtime.recording
              ? "Recording"
              : runtime.listening
                ? "Listening"
                : runtime.state === "THINKING"
                  ? "Thinking"
                  : runtime.interrupted
                    ? "Interrupted"
                    : "Idle"}
        </span>
      </div>

      <div className="voice-runtime-controls">
        <label className="voice-runtime-mode">
          <span>Input</span>
          <select value={inputMode} onChange={(e) => setInputMode(e.target.value)} disabled={runtime.recording || runtime.listening}>
            <option value="LOCAL">Local</option>
            <option value="BROWSER">Browser</option>
          </select>
        </label>
        <button
          type="button"
          className="voice-runtime-mic"
          data-active={runtime.recording || runtime.listening ? "true" : "false"}
          data-speaking={runtime.speaking ? "true" : "false"}
          aria-label={micLabel}
          title={micLabel}
          disabled={busy && !runtime.recording && !runtime.speaking}
          onClick={() => toggleMic()}
          style={{
            borderColor: `${color}88`,
            background: runtime.recording ? `${color}33` : "rgba(255,255,255,.05)",
            color,
          }}
        >
          {runtime.recording ? "■" : runtime.speaking ? "✦" : "🎤"}
        </button>

        {runtime.speaking ? (
          <button
            type="button"
            className="voice-runtime-interrupt"
            aria-label="Interrupt assistant"
            onClick={() => interrupt()}
          >
            Interrupt
          </button>
        ) : null}

        {runtime.error ? (
          <button
            type="button"
            className="voice-runtime-retry"
            aria-label="Retry voice"
            onClick={() => retry()}
          >
            Retry
          </button>
        ) : null}
      </div>

      {(runtime.listening || runtime.recording) && (
        <div
          className="voice-runtime-listening-pulse"
          aria-hidden="true"
          data-listening="true"
        />
      )}

      {runtime.speaking && (
        <div
          className="voice-runtime-speaking-bars"
          aria-hidden="true"
          data-speaking="true"
        >
          <span />
          <span />
          <span />
        </div>
      )}

      {runtime.interrupted && (
        <p className="voice-runtime-interrupted" data-interrupted="true">
          Interrupted — listening again.
        </p>
      )}

      <div className="voice-runtime-transcript" aria-live="polite">
        <div className="voice-runtime-partial">
          {runtime.partialUser ? (
            <em>You: {runtime.partialUser}</em>
          ) : runtime.partialAssistant ? (
            <em>Yeti: {runtime.partialAssistant}</em>
          ) : (
            <span className="voice-runtime-hint">{runtime.message}</span>
          )}
        </div>
        <ul className="voice-runtime-history">
          {(runtime.transcript || []).slice(-8).map((entry) => (
            <li key={entry.entry_id || `${entry.role}-${entry.created_at}-${entry.text?.slice(0, 12)}`}>
              <strong>{entry.role === "user" ? "You" : "Yeti"}:</strong>{" "}
              {entry.text}
              {entry.interrupted ? " (interrupted)" : ""}
            </li>
          ))}
        </ul>
      </div>

      {runtime.history?.length > 0 && (
        <details className="voice-runtime-sessions">
          <summary>Voice session history</summary>
          <ul>
            {runtime.history.slice(0, 8).map((item) => (
              <li key={item.session_id}>
                {item.session_id.slice(0, 12)}… — {item.state} —{" "}
                {item.yeti_mode || "general"}
              </li>
            ))}
          </ul>
        </details>
      )}

      {runtime.error ? (
        <p className="voice-runtime-error" role="alert">
          {runtime.error}
        </p>
      ) : null}

      <style jsx>{`
        .voice-runtime-dock {
          position: fixed;
          left: 16px;
          bottom: 16px;
          z-index: 50;
          width: min(360px, calc(100vw - 32px));
          box-sizing: border-box;
          margin: 0;
          padding: 10px 12px;
          border-radius: 14px;
          border: 1px solid rgba(255, 255, 255, 0.08);
          background: rgba(10, 14, 28, 0.72);
          color: #e8eefc;
          font-size: 12px;
        }
        .voice-runtime-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          margin-bottom: 8px;
        }
        .voice-runtime-badge {
          border: 1px solid;
          border-radius: 999px;
          padding: 2px 8px;
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }
        .voice-runtime-controls {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
        }
        .voice-runtime-mic {
          width: 44px;
          height: 44px;
          border-radius: 999px;
          border: 1px solid;
          cursor: pointer;
          font-size: 18px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
        }
        .voice-runtime-interrupt,
        .voice-runtime-retry {
          border-radius: 8px;
          border: 1px solid rgba(255, 255, 255, 0.16);
          background: rgba(255, 255, 255, 0.06);
          color: inherit;
          padding: 6px 10px;
          cursor: pointer;
          font-size: 11px;
        }
        .voice-runtime-listening-pulse {
          height: 4px;
          border-radius: 999px;
          margin-bottom: 8px;
          background: linear-gradient(
            90deg,
            transparent,
            #4fe3cb,
            transparent
          );
          background-size: 200% 100%;
          animation: voice-pulse 1.2s linear infinite;
        }
        .voice-runtime-speaking-bars {
          display: flex;
          gap: 3px;
          height: 14px;
          align-items: flex-end;
          margin-bottom: 8px;
        }
        .voice-runtime-speaking-bars span {
          width: 4px;
          background: #c9b6ff;
          border-radius: 2px;
          animation: voice-bar 0.8s ease-in-out infinite;
        }
        .voice-runtime-speaking-bars span:nth-child(2) {
          animation-delay: 0.15s;
        }
        .voice-runtime-speaking-bars span:nth-child(3) {
          animation-delay: 0.3s;
        }
        .voice-runtime-transcript {
          min-height: 42px;
        }
        .voice-runtime-partial {
          opacity: 0.9;
          margin-bottom: 6px;
        }
        .voice-runtime-hint {
          opacity: 0.65;
        }
        .voice-runtime-history,
        .voice-runtime-sessions ul {
          margin: 0;
          padding-left: 16px;
        }
        .voice-runtime-history li,
        .voice-runtime-sessions li {
          margin: 3px 0;
          word-break: break-word;
        }
        .voice-runtime-interrupted {
          color: #ff8c8c;
          margin: 0 0 6px;
        }
        .voice-runtime-error {
          color: #ff8a8a;
          margin: 6px 0 0;
        }
        .voice-runtime-sessions {
          margin-top: 8px;
          opacity: 0.85;
        }
        @keyframes voice-pulse {
          0% {
            background-position: 100% 0;
          }
          100% {
            background-position: -100% 0;
          }
        }
        @keyframes voice-bar {
          0%,
          100% {
            height: 4px;
          }
          50% {
            height: 14px;
          }
        }
        @media (max-width: 720px) {
          .voice-runtime-dock {
            left: 8px;
            bottom: 8px;
            width: calc(100vw - 16px);
          }
        }
      `}</style>
    </section>
  );
}
