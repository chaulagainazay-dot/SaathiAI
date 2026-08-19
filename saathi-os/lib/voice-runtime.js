"use client";

import { API_BASE } from "./api.js";
import { getToken, plat } from "./platform-client.js";

export const VOICE_RUNTIME_STATES = Object.freeze([
  "IDLE",
  "LISTENING",
  "THINKING",
  "RESPONDING",
  "INTERRUPTED",
  "FINISHED",
  "FAILED",
]);

export const INPUT_STATES = Object.freeze([
  "idle",
  "listening",
  "recording",
  "processing",
  "error",
  "cancelled",
]);

export const INITIAL_VOICE_RUNTIME = Object.freeze({
  sessionId: "",
  state: "IDLE",
  inputState: "idle",
  playbackState: "idle",
  partialUser: "",
  partialAssistant: "",
  transcript: [],
  interruptions: [],
  history: [],
  message: "Press the microphone to talk with Yeti.",
  error: "",
  speaking: false,
  recording: false,
  listening: false,
  interrupted: false,
  // Backend sessions whose terminal request has not yet succeeded. Non-empty
  // means "this client could not confirm cleanup", never "cleanup is done".
  pendingCleanup: [],
});

function authHeaders(token, extra = {}) {
  return {
    "Content-Type": "application/json",
    "X-Platform-Token": token,
    ...extra,
  };
}

async function parseJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data?.detail;
    const message =
      (typeof detail === "object" && detail?.message) ||
      detail ||
      data?.message ||
      `Voice runtime request failed (${response.status})`;
    const error = new Error(String(message));
    error.status = response.status;
    error.code = detail?.code || data?.code || "";
    throw error;
  }
  return data;
}

export const voiceRuntimeActions = {
  async health(token, signal) {
    const response = await fetch(
      `${API_BASE}/api/v1/platform/voice/runtime/health`,
      { headers: authHeaders(token), signal }
    );
    return parseJson(response);
  },
  async sttProviders(token, signal) {
    const response = await fetch(
      `${API_BASE}/api/v1/platform/voice/runtime/stt-providers`,
      { headers: authHeaders(token), signal }
    );
    return parseJson(response);
  },
  async createSession(token, body = {}, signal) {
    const response = await fetch(
      `${API_BASE}/api/v1/platform/voice/runtime/sessions`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify(body),
        signal,
      }
    );
    return parseJson(response);
  },
  async getSession(token, sessionId, signal) {
    const response = await fetch(
      `${API_BASE}/api/v1/platform/voice/runtime/sessions/${encodeURIComponent(sessionId)}`,
      { headers: authHeaders(token), signal }
    );
    return parseJson(response);
  },
  async listSessions(token, signal) {
    const response = await fetch(
      `${API_BASE}/api/v1/platform/voice/runtime/sessions`,
      { headers: authHeaders(token), signal }
    );
    return parseJson(response);
  },
  async listen(token, sessionId, body = {}, signal) {
    const response = await fetch(
      `${API_BASE}/api/v1/platform/voice/runtime/sessions/${encodeURIComponent(sessionId)}/listen`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify(body),
        signal,
      }
    );
    return parseJson(response);
  },
  async stop(token, sessionId, signal) {
    const response = await fetch(
      `${API_BASE}/api/v1/platform/voice/runtime/sessions/${encodeURIComponent(sessionId)}/stop`,
      { method: "POST", headers: authHeaders(token), signal }
    );
    return parseJson(response);
  },
  async cancel(token, sessionId, signal) {
    const response = await fetch(
      `${API_BASE}/api/v1/platform/voice/runtime/sessions/${encodeURIComponent(sessionId)}/cancel`,
      { method: "POST", headers: authHeaders(token), signal }
    );
    return parseJson(response);
  },
  async transcript(token, sessionId, body, signal) {
    const response = await fetch(
      `${API_BASE}/api/v1/platform/voice/runtime/sessions/${encodeURIComponent(sessionId)}/transcript`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify(body),
        signal,
      }
    );
    return parseJson(response);
  },
  async interrupt(token, sessionId, signal) {
    const response = await fetch(
      `${API_BASE}/api/v1/platform/voice/runtime/sessions/${encodeURIComponent(sessionId)}/interrupt`,
      { method: "POST", headers: authHeaders(token), signal }
    );
    return parseJson(response);
  },
  async playback(token, sessionId, action, signal) {
    const response = await fetch(
      `${API_BASE}/api/v1/platform/voice/runtime/sessions/${encodeURIComponent(sessionId)}/playback`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify({ action }),
        signal,
      }
    );
    return parseJson(response);
  },
  /**
   * Terminal cleanup. `keepalive` lets the request outlive the page during a
   * hard navigation or a tab close — sendBeacon cannot carry the platform
   * token header, so keepalive fetch is the only authenticated option.
   */
  async finish(token, sessionId, { signal, keepalive = false } = {}) {
    const response = await fetch(
      `${API_BASE}/api/v1/platform/voice/runtime/sessions/${encodeURIComponent(sessionId)}/finish`,
      { method: "POST", headers: authHeaders(token), signal, keepalive }
    );
    return parseJson(response);
  },
};

export function normalizeRuntimeSession(value) {
  if (!value || typeof value !== "object") return null;
  const session = value.session && typeof value.session === "object" ? value.session : value;
  if (!session.session_id) return null;
  return {
    sessionId: String(session.session_id),
    state: String(session.state || "IDLE"),
    inputState: String(session.input_state || "idle"),
    playbackState: String(session.playback_state || "idle"),
    partialUser: String(session.partial_user_transcript || ""),
    partialAssistant: String(session.partial_assistant_response || ""),
    transcript: Array.isArray(session.transcript) ? session.transcript : [],
    interruptions: Array.isArray(session.interruptions) ? session.interruptions : [],
    activeSpeechOperationId: String(session.active_speech_operation_id || ""),
    error: String(session.error_message || session.error_category || ""),
    yetiMode: String(session.yeti_mode || "general"),
  };
}

export function voiceRuntimeReducer(current, action) {
  switch (action.type) {
    case "RESET":
      return { ...INITIAL_VOICE_RUNTIME };
    // The backend session ended, but the surface did not. Session-scoped state
    // is cleared so the next talk opens a fresh session; the history list is
    // kept, because the conversation that just happened still happened.
    case "SESSION_CLOSED":
      return {
        ...INITIAL_VOICE_RUNTIME,
        history: current.history,
        message: INITIAL_VOICE_RUNTIME.message,
      };
    case "CLEANUP_PENDING":
      return {
        ...current,
        pendingCleanup: Array.isArray(action.pending) ? action.pending : [],
      };
    case "SESSION": {
      const session = normalizeRuntimeSession(action.session);
      if (!session) {
        return {
          ...current,
          error: "Invalid voice session payload.",
          message: "Voice session is unavailable.",
        };
      }
      const speaking =
        session.state === "RESPONDING" || session.playbackState === "playing";
      const recording =
        session.inputState === "recording" || session.inputState === "listening";
      const listening = session.state === "LISTENING" || recording;
      return {
        ...current,
        sessionId: session.sessionId,
        state: session.state,
        inputState: session.inputState,
        playbackState: session.playbackState,
        partialUser: session.partialUser,
        partialAssistant: session.partialAssistant,
        transcript: session.transcript,
        interruptions: session.interruptions,
        speaking,
        recording,
        listening,
        interrupted: session.state === "INTERRUPTED" || session.interruptions.length > 0,
        error: session.error,
        message:
          session.state === "LISTENING"
            ? "Listening…"
            : session.state === "THINKING"
              ? "Thinking…"
              : session.state === "RESPONDING"
                ? "Speaking…"
                : session.state === "INTERRUPTED"
                  ? "Interrupted — listening again."
                  : current.message,
      };
    }
    case "HISTORY":
      return {
        ...current,
        history: Array.isArray(action.history) ? action.history : [],
      };
    case "ERROR":
      return {
        ...current,
        error: String(action.error || "Voice runtime error"),
        message: String(action.message || action.error || "Voice runtime error"),
        recording: false,
      };
    case "LOCAL_RECORDING":
      return {
        ...current,
        recording: Boolean(action.recording),
        listening: Boolean(action.listening ?? action.recording),
        message: action.recording ? "Recording…" : current.message,
      };
    default:
      return current;
  }
}

export function getRecognitionCtor() {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

export function prefersBrowserStt() {
  return Boolean(getRecognitionCtor());
}

/** Helper used by tests and UI for mic button labels. */
export function micButtonLabel(runtime) {
  if (!runtime) return "Microphone";
  if (runtime.recording) return "Stop recording";
  if (runtime.speaking) return "Interrupt assistant";
  if (runtime.listening) return "Listening";
  return "Start talking";
}

/**
 * The stage of one voice turn, as the runtime can actually prove it.
 *
 * Deliberately distinguishes "listen" (capture is open, nothing heard) from
 * "hear" (a transcript fragment exists). The dock reports the difference, so a
 * live capture that is producing no speech can never read as progress.
 */
export const VOICE_TURN_STAGES = Object.freeze([
  "idle",
  "listen",
  "hear",
  "think",
  "speak",
  "fail",
]);

export function voiceTurnStage(runtime) {
  if (!runtime) return "idle";
  if (runtime.error || runtime.state === "FAILED") return "fail";
  if (runtime.speaking) return "speak";
  if (runtime.state === "THINKING") return "think";
  if (runtime.recording && String(runtime.partialUser || "").trim()) return "hear";
  if (runtime.recording || runtime.listening) return "listen";
  return "idle";
}

export function voiceStageLabel(stage) {
  return (
    {
      idle: "Idle",
      listen: "Listening",
      hear: "Hearing you",
      think: "Thinking",
      speak: "Speaking",
      fail: "Failed",
    }[stage] || "Idle"
  );
}

export function createVoiceRuntimeClient() {
  return {
    getToken,
    plat,
    actions: voiceRuntimeActions,
  };
}
