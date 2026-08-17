"use client";

import { useEffect, useState } from "react";
import { voiceStageLabel, voiceTurnStage } from "@/lib/voice-runtime";
import { useVoiceRuntime } from "./VoiceRuntimeProvider";

/** The four stages of one turn, in the order the runtime moves through them. */
const LADDER = [
  { key: "listen", label: "Listen" },
  { key: "hear", label: "Hear" },
  { key: "think", label: "Think" },
  { key: "speak", label: "Speak" },
];

function clock(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = String(Math.floor(total / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function MicGlyph({ stage }) {
  if (stage === "speak") {
    return (
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
        <rect x="7" y="5" width="4" height="14" rx="1" fill="currentColor" />
        <rect x="13" y="5" width="4" height="14" rx="1" fill="currentColor" />
      </svg>
    );
  }
  if (stage === "listen" || stage === "hear") {
    return (
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
        <rect x="6" y="6" width="12" height="12" rx="1.5" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
      <rect
        x="9"
        y="3"
        width="6"
        height="11"
        rx="3"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path
        d="M6 12a6 6 0 0 0 12 0M12 18v3M9 21h6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default function VoiceRuntimeDock() {
  const { token, runtime, busy, toggleMic, interrupt, retry, micLabel } =
    useVoiceRuntime();

  const stage = voiceTurnStage(runtime);
  const [since, setSince] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const started = Date.now();
    setSince(started);
    setNow(started);
    if (stage === "idle") return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [stage]);

  if (!token) return null;

  const elapsed = clock(now - since);
  const heard = String(runtime.partialUser || "").trim();
  const spoken = String(runtime.partialAssistant || "").trim();
  const activeIndex = LADDER.findIndex((step) => step.key === stage);
  const turns = (runtime.transcript || []).slice(-3);

  // One line of evidence per stage. "Listening" that has heard nothing says so.
  const readout =
    stage === "listen"
      ? "Nothing heard yet"
      : stage === "hear"
        ? `${heard.split(/\s+/).filter(Boolean).length} words heard`
        : stage === "think"
          ? "Waiting on reply"
          : stage === "speak"
            ? "Reading the reply aloud"
            : stage === "fail"
              ? runtime.error || "Voice runtime failed"
              : turns.length
                ? `${turns.length} turns this session`
                : "No turns yet";

  const slug =
    heard || spoken || (stage === "fail" ? "Retry to open a new turn." : runtime.message);

  return (
    <section
      className="voice-runtime-dock"
      data-stage={stage}
      data-voice-runtime-state={runtime.state}
      data-voice-input-state={runtime.inputState}
      aria-label="Real-time voice conversation"
    >
      <span className="vrd-rail" aria-hidden="true" />

      <header className="vrd-head">
        <span className="vrd-channel">Live voice</span>
        <span className="vrd-lamp" aria-hidden="true" />
        <span className="vrd-stage" aria-live="polite">
          {voiceStageLabel(stage)}
        </span>
        <span className="vrd-clock">{stage === "idle" ? "--:--" : elapsed}</span>
      </header>

      <div className="vrd-body">
        <button
          type="button"
          className="voice-runtime-mic"
          data-stage={stage}
          data-active={runtime.recording || runtime.listening ? "true" : "false"}
          data-speaking={runtime.speaking ? "true" : "false"}
          aria-label={micLabel}
          title={micLabel}
          disabled={busy && !runtime.recording && !runtime.speaking}
          onClick={() => toggleMic()}
        >
          <MicGlyph stage={stage} />
        </button>

        <div className="vrd-readout">
          <ol className="vrd-ladder" aria-hidden="true">
            {LADDER.map((step, index) => (
              <li
                key={step.key}
                data-state={
                  index === activeIndex
                    ? "active"
                    : activeIndex > index
                      ? "done"
                      : "pending"
                }
              >
                <span className="vrd-node" />
                {step.label}
              </li>
            ))}
          </ol>
          <p className="vrd-slug" data-quoted={heard || spoken ? "true" : "false"}>
            {slug}
          </p>
          <p className="vrd-evidence" role="status">
            {readout}
          </p>
        </div>
      </div>

      {(runtime.speaking || runtime.error || runtime.interrupted) && (
        <div className="vrd-actions">
          {runtime.interrupted ? (
            <span className="vrd-note">Interrupted — listening again.</span>
          ) : null}
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
      )}

      {turns.length > 0 && (
        <ul className="vrd-log">
          {turns.map((entry) => (
            <li
              key={
                entry.entry_id ||
                `${entry.role}-${entry.created_at}-${entry.text?.slice(0, 12)}`
              }
              data-role={entry.role === "user" ? "you" : "yeti"}
            >
              <span className="vrd-log-who">{entry.role === "user" ? "you" : "yeti"}</span>
              <span className="vrd-log-text">
                {entry.text}
                {entry.interrupted ? " (interrupted)" : ""}
              </span>
            </li>
          ))}
        </ul>
      )}

      {runtime.history?.length > 0 && (
        <details className="vrd-sessions">
          <summary>Session history</summary>
          <ul>
            {runtime.history.slice(0, 8).map((item) => (
              <li key={item.session_id}>
                {item.session_id.slice(0, 12)}… · {item.state} ·{" "}
                {item.yeti_mode || "general"}
              </li>
            ))}
          </ul>
        </details>
      )}

      {runtime.error ? (
        <p className="vrd-error" role="alert">
          {runtime.error}
        </p>
      ) : null}

      <style jsx>{`
        /* The dock is shell chrome, not page content. In document flow it landed
           after <main>, underneath the fixed sidebar and below the fixed status
           bar, so the mic was unclickable on desktop and off-viewport on phones.
           Anchor it bottom-left: clear of the sidebar (primary navigation), of
           the status bar, and of the bottom-right M75 output dock. */
        .voice-runtime-dock {
          position: fixed;
          left: calc(var(--shell-sidebar-expanded, 240px) + 16px);
          bottom: calc(var(--shell-statusbar-h, 36px) + 12px);
          z-index: 47;
          width: min(360px, calc(100vw - 32px));
          max-height: min(46vh, 420px);
          overflow-y: auto;
          overscroll-behavior: contain;
          margin: 0;
          padding: 11px 13px 12px;
          border-radius: 4px;
          border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
          background: var(--surface-overlay, #0e1729);
          box-shadow: 0 18px 40px -28px #000;
          color: var(--text-primary, #eef3fc);

          /* One hue drives the whole instrument: rail, key, ladder, evidence. */
          --stage-hue: var(--status-neutral, #6c7a96);
        }
        .voice-runtime-dock[data-stage="listen"] {
          --stage-hue: var(--color-cyan-500, #35e0d0);
        }
        .voice-runtime-dock[data-stage="hear"] {
          --stage-hue: var(--color-green-400, #5fd39a);
        }
        .voice-runtime-dock[data-stage="think"] {
          --stage-hue: var(--color-amber-500, #e8b84b);
        }
        .voice-runtime-dock[data-stage="speak"] {
          --stage-hue: var(--color-violet-500, #9b6bff);
        }
        .voice-runtime-dock[data-stage="fail"] {
          --stage-hue: var(--status-danger, #f0555a);
        }
        /* Sidebar collapse is published on the desktop chrome wrapper, which is
           a preceding sibling of this dock in the shell tree. */
        :global(.shell-desktop[data-sidebar="collapsed"]) ~ .voice-runtime-dock {
          left: calc(var(--shell-sidebar-collapsed, 64px) + 16px);
        }

        /* Signature: the channel edge is lit only while capture is genuinely
           open, and it travels only while something is being heard. */
        .vrd-rail {
          position: absolute;
          inset: 0 auto 0 0;
          width: 2px;
          background: var(--stage-hue);
          opacity: 0.55;
        }
        .voice-runtime-dock[data-stage="idle"] .vrd-rail {
          opacity: 0.18;
        }

        .vrd-head {
          display: flex;
          align-items: baseline;
          gap: 7px;
          margin-bottom: 10px;
        }
        .vrd-lamp {
          width: 5px;
          height: 5px;
          margin-left: 3px;
          background: var(--stage-hue);
          box-shadow: 0 0 6px 0 var(--stage-hue);
        }
        .voice-runtime-dock[data-stage="idle"] .vrd-lamp {
          background: var(--color-ink-700, #323d57);
          box-shadow: none;
        }
        .vrd-channel,
        .vrd-stage {
          font-family: var(--font-display, ui-sans-serif);
          font-size: 10px;
          font-weight: 500;
          letter-spacing: 0.18em;
          text-transform: uppercase;
        }
        .vrd-channel {
          color: var(--text-muted, #8b98b4);
        }
        .vrd-stage {
          color: var(--stage-hue);
        }
        .vrd-clock {
          margin-left: auto;
          font-family: var(--font-mono, ui-monospace);
          font-size: 11px;
          font-variant-numeric: tabular-nums;
          color: var(--text-muted, #8b98b4);
        }

        .vrd-body {
          display: grid;
          grid-template-columns: 48px 1fr;
          gap: 12px;
          align-items: start;
        }

        .voice-runtime-mic {
          width: 48px;
          height: 48px;
          min-width: 44px;
          min-height: 44px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          border-radius: 3px;
          border: 1px solid color-mix(in srgb, var(--stage-hue) 55%, transparent);
          background: color-mix(in srgb, var(--stage-hue) 12%, transparent);
          color: var(--stage-hue);
          cursor: pointer;
          transition: background 120ms linear, border-color 120ms linear;
        }
        .voice-runtime-mic:hover:not(:disabled) {
          background: color-mix(in srgb, var(--stage-hue) 22%, transparent);
        }
        .voice-runtime-mic:disabled {
          cursor: not-allowed;
          opacity: 0.5;
        }
        /* Live capture reads as a lit key, not a pulsing bubble. */
        .voice-runtime-mic[data-stage="listen"],
        .voice-runtime-mic[data-stage="hear"] {
          background: color-mix(in srgb, var(--stage-hue) 26%, transparent);
          box-shadow: inset 0 -2px 0 0 var(--stage-hue);
        }

        .vrd-readout {
          min-width: 0;
        }
        .vrd-ladder {
          display: flex;
          gap: 10px;
          margin: 0 0 7px;
          padding: 0;
          list-style: none;
          font-family: var(--font-display, ui-sans-serif);
          font-size: 9px;
          font-weight: 500;
          letter-spacing: 0.14em;
          text-transform: uppercase;
        }
        .vrd-ladder li {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          color: var(--color-ink-600, #4b5876);
        }
        .vrd-ladder li[data-state="done"] {
          color: var(--text-muted, #8b98b4);
        }
        .vrd-ladder li[data-state="active"] {
          color: var(--stage-hue);
        }
        .vrd-node {
          width: 5px;
          height: 5px;
          border: 1px solid currentColor;
        }
        .vrd-ladder li[data-state="active"] .vrd-node,
        .vrd-ladder li[data-state="done"] .vrd-node {
          background: currentColor;
        }

        .vrd-slug {
          margin: 0 0 5px;
          font-family: var(--font-ui, ui-sans-serif);
          font-size: 13px;
          line-height: 1.35;
          color: var(--text-secondary, #aebad4);
          display: -webkit-box;
          -webkit-line-clamp: 3;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
        .vrd-slug[data-quoted="true"] {
          color: var(--text-primary, #eef3fc);
        }
        .vrd-slug[data-quoted="true"]::before {
          content: "“";
        }
        .vrd-slug[data-quoted="true"]::after {
          content: "”";
        }

        .vrd-evidence {
          margin: 0;
          font-family: var(--font-mono, ui-monospace);
          font-size: 10px;
          font-variant-numeric: tabular-nums;
          letter-spacing: 0.02em;
          color: var(--text-muted, #8b98b4);
        }
        .voice-runtime-dock[data-stage="fail"] .vrd-evidence {
          color: var(--status-danger, #f0555a);
        }

        .vrd-actions {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 10px;
        }
        .vrd-note {
          font-family: var(--font-mono, ui-monospace);
          font-size: 10px;
          color: var(--stage-hue);
        }
        .voice-runtime-interrupt,
        .voice-runtime-retry {
          border-radius: 3px;
          border: 1px solid color-mix(in srgb, var(--stage-hue) 45%, transparent);
          background: color-mix(in srgb, var(--stage-hue) 12%, transparent);
          color: var(--text-primary, #eef3fc);
          padding: 5px 10px;
          font-family: var(--font-display, ui-sans-serif);
          font-size: 10px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          cursor: pointer;
        }
        .voice-runtime-mic:focus-visible,
        .voice-runtime-interrupt:focus-visible,
        .voice-runtime-retry:focus-visible {
          outline: 2px solid var(--focus-ring, #7aa2ff);
          outline-offset: 2px;
        }

        .vrd-log {
          margin: 11px 0 0;
          padding: 8px 9px;
          list-style: none;
          border-top: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
          background: var(--surface-sunken, #080e1a);
        }
        .vrd-log li {
          display: grid;
          grid-template-columns: 34px 1fr;
          gap: 7px;
          padding: 2px 0;
        }
        .vrd-log-who {
          font-family: var(--font-mono, ui-monospace);
          font-size: 9px;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--color-ink-600, #4b5876);
        }
        .vrd-log li[data-role="you"] .vrd-log-who {
          color: var(--text-muted, #8b98b4);
        }
        .vrd-log-text {
          font-size: 11px;
          line-height: 1.4;
          color: var(--text-secondary, #aebad4);
          word-break: break-word;
        }

        .vrd-sessions {
          margin-top: 9px;
          font-family: var(--font-mono, ui-monospace);
          font-size: 10px;
          color: var(--text-muted, #8b98b4);
        }
        .vrd-sessions summary {
          cursor: pointer;
          letter-spacing: 0.06em;
          text-transform: uppercase;
        }
        .vrd-sessions summary:focus-visible {
          outline: 2px solid var(--focus-ring, #7aa2ff);
          outline-offset: 2px;
        }
        .vrd-sessions ul {
          margin: 6px 0 0;
          padding-left: 14px;
        }
        .vrd-error {
          margin: 9px 0 0;
          font-family: var(--font-mono, ui-monospace);
          font-size: 10px;
          color: var(--status-danger, #f0555a);
        }

        @media (prefers-reduced-motion: no-preference) {
          .voice-runtime-dock[data-stage="hear"] .vrd-rail,
          .voice-runtime-dock[data-stage="listen"] .vrd-rail {
            background: linear-gradient(
              180deg,
              transparent,
              var(--stage-hue) 45%,
              transparent
            );
            background-size: 100% 220%;
            animation: vrd-travel 1.6s linear infinite;
            opacity: 1;
          }
        }
        @keyframes vrd-travel {
          from {
            background-position: 0 120%;
          }
          to {
            background-position: 0 -120%;
          }
        }

        /* Narrow desktop/tablet: the bottom-right output dock (anchored 42px up)
           reaches far enough left to meet this dock, so stack above it. */
        @media (max-width: 1023px) {
          .voice-runtime-dock {
            bottom: calc(var(--shell-statusbar-h, 36px) + 12px + 212px);
          }
        }
        /* The output dock re-anchors to 76px at this width (globals.css). */
        @media (max-width: 820px) {
          .voice-runtime-dock {
            bottom: calc(var(--shell-statusbar-h, 36px) + 12px + 246px);
          }
        }
        /* Phone companion: no sidebar, no status bar; clear the tab bar and the
           taller single-column output dock. */
        @media (max-width: 699px) {
          .voice-runtime-dock {
            left: 10px;
            width: min(360px, calc(100vw - 20px));
            max-height: min(38vh, 320px);
            bottom: calc(328px + env(safe-area-inset-bottom, 0px));
          }
        }
      `}</style>
    </section>
  );
}
