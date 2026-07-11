"use client";
// M12 — Voice OS control for Saathi Chat. Real browser APIs, not a mock:
// - STT: window.SpeechRecognition / webkitSpeechRecognition (Chrome-native,
//   genuinely streams partial + final transcripts from real microphone audio).
// - TTS: window.speechSynthesis (Chrome-native, genuinely speaks audio).
// Final transcripts submit through /api/v1/voice/sessions/{id}/turns, which
// on the backend calls the REAL ChatEngine/Orchestrator (voice_os/bridge.py)
// — never a separate/parallel chat path.
//
// Honesty note (see M12 report): this component was verified by code review,
// unit-level provider checks, and a full production build. Live microphone
// permission + a real spoken utterance were NOT exercised in this session —
// the sandboxed browser-automation environment cannot grant getUserMedia.
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";

const STATES = {
  idle: { label: "Voice off", color: "#8fa0c4" },
  connecting: { label: "Connecting…", color: "#8fa0c4" },
  listening: { label: "Listening…", color: "#4fe3cb" },
  speech_detected: { label: "Hearing you…", color: "#5ea1ff" },
  transcribing: { label: "Transcribing…", color: "#5ea1ff" },
  processing: { label: "Thinking…", color: "#ffb04f" },
  speaking: { label: "Speaking…", color: "#c9b6ff" },
  interrupted: { label: "Interrupted", color: "#ff8c8c" },
  paused: { label: "Paused", color: "#8fa0c4" },
  error: { label: "Voice error", color: "#ff5a5a" },
};

function getRecognitionCtor() {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

const S = {
  wrap: {
    display: "flex", flexDirection: "column", gap: 8, padding: 10,
    borderRadius: 12, background: "rgba(255,255,255,.03)",
    border: "1px solid rgba(255,255,255,.08)", fontSize: 12,
  },
  row: { display: "flex", alignItems: "center", gap: 8 },
  micBtn: (active, color) => ({
    width: 34, height: 34, borderRadius: "50%", border: `1px solid ${color}66`,
    background: active ? `${color}33` : "rgba(255,255,255,.05)", color,
    cursor: "pointer", fontSize: 15, display: "flex", alignItems: "center",
    justifyContent: "center",
  }),
  smallBtn: (color = "#8fa0c4") => ({
    background: `${color}18`, color, border: `1px solid ${color}44`,
    borderRadius: 8, padding: "4px 9px", fontSize: 11, cursor: "pointer",
  }),
  badge: (color) => ({
    display: "inline-block", padding: "2px 9px", borderRadius: 999,
    fontSize: 10, background: `${color}22`, color, border: `1px solid ${color}55`,
  }),
  level: (v) => ({
    width: 60, height: 6, borderRadius: 3, background: "rgba(255,255,255,.08)",
    position: "relative", overflow: "hidden",
  }),
  levelFill: (v, color) => ({
    position: "absolute", left: 0, top: 0, bottom: 0, width: `${Math.min(100, v)}%`,
    background: color, transition: "width 80ms linear",
  }),
  transcript: {
    fontSize: 12, opacity: .8, minHeight: 18, wordBreak: "break-word",
    fontStyle: "italic",
  },
};

export default function VoiceControl({ conversationId, chatMode, agent,
                                       projectId, onTurn }) {
  const [voiceState, setVoiceState] = useState("idle");
  const [supported, setSupported] = useState(true);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [muted, setMuted] = useState(false);
  const [level, setLevel] = useState(0);
  const [partial, setPartial] = useState("");
  const [finalText, setFinalText] = useState("");
  const [error, setError] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [collapsed, setCollapsed] = useState(true);

  const recogRef = useRef(null);
  const synthUtterRef = useRef(null);
  const levelTimerRef = useRef(null);
  const bargeInStartRef = useRef(0);

  useEffect(() => {
    setSupported(!!getRecognitionCtor() && !!window?.speechSynthesis);
  }, []);

  // ── voice session lifecycle (real API, real ChatEngine underneath) ──────
  const ensureSession = useCallback(async () => {
    if (sessionId) return sessionId;
    try {
      const r = await afetch(`${API_BASE}/api/v1/voice/sessions`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: conversationId || "", project_id: projectId || "",
          chat_mode: chatMode || "solo", agent: agent || "",
        }),
      });
      const j = await r.json();
      if (j.error) { setError(j.error); return null; }
      setSessionId(j.session_id);
      return j.session_id;
    } catch {
      setError("Voice session failed — is the SaathiAI server running?");
      return null;
    }
  }, [sessionId, conversationId, chatMode, agent, projectId]);

  // ── TTS: speak assistant segments via real browser SpeechSynthesis ──────
  const speakSegments = useCallback((segments) => {
    if (!segments?.length || !window?.speechSynthesis) return;
    setVoiceState("speaking");
    let i = 0;
    const next = () => {
      if (i >= segments.length) { setVoiceState("listening"); return; }
      const u = new SpeechSynthesisUtterance(segments[i]);
      u.onend = () => { i += 1; next(); };
      u.onerror = () => { i += 1; next(); };
      synthUtterRef.current = u;
      window.speechSynthesis.speak(u);
    };
    next();
  }, []);

  // ── barge-in: stop playback the instant new speech is detected ─────────
  const stopPlayback = useCallback(() => {
    if (window?.speechSynthesis?.speaking) {
      const stopMs = performance.now() - bargeInStartRef.current;
      window.speechSynthesis.cancel();
      setVoiceState("interrupted");
      if (sessionId) {
        afetch(`${API_BASE}/api/v1/voice/sessions/${sessionId}/interrupt?stop_latency_ms=${stopMs}`,
          { method: "POST" }).catch(() => {});
      }
    }
  }, [sessionId]);

  // ── submit final transcript -> real ChatEngine/Orchestrator via bridge ──
  const submitFinal = useCallback(async (text) => {
    const sid = await ensureSession();
    if (!sid || !text.trim()) return;
    setVoiceState("processing");
    try {
      const r = await afetch(`${API_BASE}/api/v1/voice/sessions/${sid}/turns`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const j = await r.json();
      if (j.error) { setError(j.error); setVoiceState("error"); return; }
      onTurn?.(j);
      if (j.segments?.length) speakSegments(j.segments);
      else setVoiceState("listening");
    } catch {
      setError("Voice turn failed — network or auth.");
      setVoiceState("error");
    }
    setPartial(""); setFinalText("");
  }, [ensureSession, onTurn, speakSegments]);

  // ── start/stop real microphone capture + recognition ────────────────────
  const start = useCallback(async () => {
    const Ctor = getRecognitionCtor();
    if (!Ctor) { setSupported(false); return; }
    await ensureSession();
    const r = new Ctor();
    r.continuous = true;
    r.interimResults = true;
    r.lang = "en-US";
    r.onstart = () => setVoiceState("listening");
    r.onaudiostart = () => setPermissionDenied(false);
    r.onresult = (ev) => {
      bargeInStartRef.current = performance.now();
      stopPlayback();
      setVoiceState("speech_detected");
      let interim = "", fin = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const t = ev.results[i][0].transcript;
        if (ev.results[i].isFinal) fin += t; else interim += t;
      }
      if (interim) { setPartial(interim); setVoiceState("transcribing"); }
      if (fin) { setFinalText(fin); submitFinal(fin); }
      setLevel(Math.min(100, 20 + interim.length * 2));
    };
    r.onerror = (ev) => {
      if (ev.error === "not-allowed" || ev.error === "permission-denied") {
        setPermissionDenied(true); setVoiceState("error");
      } else {
        setError(`Recognition error: ${ev.error}`); setVoiceState("error");
      }
    };
    r.onend = () => {
      if (recogRef.current === r && voiceState !== "idle" && !muted) {
        try { r.start(); } catch { /* already stopped */ }
      }
    };
    recogRef.current = r;
    try {
      r.start();
    } catch {
      setError("Could not start microphone.");
      setVoiceState("error");
    }
  }, [ensureSession, stopPlayback, submitFinal, voiceState, muted]);

  const stop = useCallback(() => {
    recogRef.current?.stop();
    recogRef.current = null;
    window?.speechSynthesis?.cancel();
    clearInterval(levelTimerRef.current);
    setVoiceState("idle");
    setLevel(0);
    if (sessionId) {
      afetch(`${API_BASE}/api/v1/voice/sessions/${sessionId}/end`, { method: "POST" })
        .catch(() => {});
    }
  }, [sessionId]);

  useEffect(() => () => { // cleanup on unmount/navigation — never leave mic hot
    recogRef.current?.stop();
    window?.speechSynthesis?.cancel();
    clearInterval(levelTimerRef.current);
  }, []);

  const toggleMic = () => {
    if (voiceState === "idle" || voiceState === "error") start();
    else stop();
  };

  const toggleMute = () => {
    setMuted((m) => {
      const next = !m;
      if (next) recogRef.current?.stop(); else recogRef.current?.start?.();
      return next;
    });
  };

  const active = voiceState !== "idle";
  const st = STATES[voiceState] || STATES.idle;

  if (!supported) {
    return (
      <div style={S.wrap} role="status" aria-live="polite">
        Voice not supported in this browser. Text chat remains fully available.
      </div>
    );
  }

  return (
    <div style={S.wrap} role="region" aria-label="Voice control">
      <div style={S.row}>
        <button
          style={S.micBtn(active, st.color)}
          onClick={toggleMic}
          aria-label={active ? "Stop voice session" : "Start voice session"}
          aria-pressed={active}
          title={active ? "Stop listening" : "Start voice"}>
          {active ? "◉" : "🎙"}
        </button>
        <span style={S.badge(st.color)} aria-live="polite">{st.label}</span>
        {active && (
          <div style={S.level(level)} aria-hidden="true">
            <div style={S.levelFill(level, st.color)} />
          </div>
        )}
        <div style={{ flex: 1 }} />
        {active && (
          <>
            <button style={S.smallBtn()} onClick={toggleMute}
                    aria-pressed={muted}>{muted ? "Unmute" : "Mute"}</button>
            <button style={S.smallBtn("#ff5a5a")} onClick={stop}>Stop</button>
          </>
        )}
      </div>
      {(partial || finalText) && (
        <div style={S.transcript} aria-live="polite">
          {finalText || partial}
        </div>
      )}
      {permissionDenied && (
        <div style={{ color: "#ff8c8c" }} role="alert">
          Microphone permission denied. Enable it in your browser's site settings
          to use voice — text chat still works normally.
        </div>
      )}
      {error && !permissionDenied && (
        <div style={{ color: "#ff8c8c" }} role="alert">{error}</div>
      )}
    </div>
  );
}
