"use client";

import { API_BASE } from "./api.js";
import { getToken, plat } from "./platform-client.js";

export const VOICE_PREFERENCE_KEY = "saathi_voice_output_v1";
export const VOICE_STATES = Object.freeze([
  "idle",
  "queued",
  "preparing",
  "synthesizing",
  "streaming",
  "playing",
  "completed",
  "cancelled",
  "failed",
  "unavailable",
  "expired",
]);
export const ACTIVE_VOICE_STATES = new Set([
  "queued",
  "preparing",
  "synthesizing",
  "streaming",
  "playing",
]);
const VOICE_STATE_SET = new Set(VOICE_STATES);
const SAFE_PROFILE_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/;

export const DEFAULT_VOICE_PREFERENCES = Object.freeze({
  version: 1,
  enabled: true,
  profileId: "saathi_default",
  speakingRate: 1,
});

export function normalizeVoicePreferences(value) {
  const candidate = value && typeof value === "object" ? value : {};
  const rawRate = Number(candidate.speakingRate);
  const speakingRate = Number.isFinite(rawRate)
    ? Math.min(2, Math.max(0.5, rawRate))
    : DEFAULT_VOICE_PREFERENCES.speakingRate;
  const profileId =
    typeof candidate.profileId === "string" &&
    SAFE_PROFILE_ID.test(candidate.profileId)
      ? candidate.profileId
      : DEFAULT_VOICE_PREFERENCES.profileId;
  return {
    version: 1,
    enabled:
      typeof candidate.enabled === "boolean"
        ? candidate.enabled
        : DEFAULT_VOICE_PREFERENCES.enabled,
    profileId,
    speakingRate,
  };
}

export function normalizeVoiceOperation(value) {
  if (!value || typeof value !== "object" || !value.operation_id) return null;
  const state = VOICE_STATE_SET.has(value.state) ? value.state : "failed";
  return {
    operationId: String(value.operation_id),
    state,
    provider: String(value.provider || value.requested_provider || "unavailable"),
    requestedProvider: String(value.requested_provider || "auto"),
    streamingState: String(value.streaming_state || "not_started"),
    fallbackUsed: Boolean(value.fallback_used),
    fallbackReason: String(value.fallback_reason || ""),
    errorCategory: String(value.error_category || ""),
    audioAvailable: Boolean(value.audio_available),
    sampleRate: Math.max(0, Number(value.sample_rate) || 0),
    durationSeconds: Math.max(0, Number(value.duration_seconds) || 0),
    artifactBytes: Math.max(0, Number(value.artifact_bytes) || 0),
  };
}

export const INITIAL_VOICE_OUTPUT = Object.freeze({
  state: "idle",
  operation: null,
  audioReady: false,
  message: "Speech is ready when you choose Speak.",
});

export function voiceOutputReducer(current, action) {
  switch (action.type) {
    case "RESET":
      return { ...INITIAL_VOICE_OUTPUT };
    case "OPERATION": {
      const operation = normalizeVoiceOperation(action.operation);
      if (!operation) {
        return {
          state: "failed",
          operation: null,
          audioReady: false,
          message: "Speech returned an invalid operation.",
        };
      }
      return {
        state: operation.state,
        operation,
        audioReady: false,
        message: voiceStateLabel(operation.state),
      };
    }
    case "READY": {
      const operation = normalizeVoiceOperation(action.operation);
      return {
        state: "completed",
        operation,
        audioReady: true,
        message: "Audio is ready. Choose Play to hear it.",
      };
    }
    case "PLAYING":
      return { ...current, state: "playing", message: "Playing speech." };
    case "ENDED":
      return {
        ...current,
        state: "completed",
        message: "Playback completed. Choose Play to hear it again.",
      };
    case "CANCELLED":
      return {
        ...current,
        state: "cancelled",
        audioReady: false,
        message: "Speech stopped.",
      };
    case "FAILED":
      return {
        ...current,
        state: action.unavailable ? "unavailable" : "failed",
        audioReady: false,
        message: action.message || "Speech could not be produced.",
      };
    default:
      return current;
  }
}

export function voiceStateLabel(state) {
  return {
    idle: "Speech is idle.",
    queued: "Speech is queued.",
    preparing: "Preparing speech.",
    synthesizing: "Synthesizing speech.",
    streaming: "Preparing audio stream.",
    playing: "Playing speech.",
    completed: "Speech completed.",
    cancelled: "Speech stopped.",
    failed: "Speech failed.",
    unavailable: "Speech is unavailable.",
    expired: "Speech audio expired.",
  }[state] || "Speech state is unknown.";
}

export async function voiceRequest(
  path,
  { method = "GET", body, token, signal } = {}
) {
  return plat(`/voice${path}`, {
    method,
    body,
    token: token || getToken(),
    signal,
  });
}

export const voiceActions = Object.freeze({
  health: (token, signal) => voiceRequest("/health", { token, signal }),
  providers: (token, signal) => voiceRequest("/providers", { token, signal }),
  profiles: (token, signal) => voiceRequest("/profiles", { token, signal }),
  speak: (body, token, signal) =>
    voiceRequest("/speech", { method: "POST", body, token, signal }),
  operation: (operationId, token, signal) =>
    voiceRequest(`/speech/${encodeURIComponent(operationId)}`, {
      token,
      signal,
    }),
  cancel: (operationId, token, signal) =>
    voiceRequest(`/speech/${encodeURIComponent(operationId)}/cancel`, {
      method: "POST",
      token,
      signal,
    }),
});

export async function fetchVoiceAudio(operationId, { token, signal } = {}) {
  const activeToken = token || getToken();
  if (!activeToken) throw new Error("Voice authentication required");
  const response = await fetch(
    `${API_BASE}/api/v1/platform/voice/speech/${encodeURIComponent(operationId)}/audio`,
    {
      method: "GET",
      headers: { "X-Platform-Token": activeToken },
      credentials: "include",
      cache: "no-store",
      signal,
    }
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    const error = new Error(
      detail?.detail?.message || `Audio unavailable (${response.status})`
    );
    error.status = response.status;
    throw error;
  }
  return response.blob();
}
