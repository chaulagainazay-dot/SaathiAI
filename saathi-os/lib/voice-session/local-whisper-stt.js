"use client";

/**
 * R2.1 — Local speech recognition transport (browser side).
 *
 * The microphone stays where it already is: AudioInputOwner owns the device,
 * the frame tap produces PCM, and this module only carries bounded utterances
 * to the local engine over the authenticated loopback endpoint and carries
 * text back. It opens no microphone, owns no session, and starts no runtime.
 *
 * Chrome Web Speech is unreachable on the owner's host (recognition error
 * `network`, no transcript), so this is the path that actually transcribes.
 *
 * Authority: a transcript returned here is input. It is not identity, not an
 * approval and not permission to execute. It reaches the command path exactly
 * the way typed text does.
 */

import { API_BASE } from "../api.js";
import { getToken } from "../platform-client.js";
import { createLocalStreamingStt } from "./local-streaming-stt.js";

/** Mirrors the server's bounded contract so oversized audio is never sent. */
export const MAX_UTTERANCE_SECONDS = 30;
export const MAX_UTTERANCE_BYTES = 4 * 1024 * 1024;
export const TARGET_SAMPLE_RATE = 16000;

/**
 * Encode mono Float32 PCM as a 16-bit PCM WAV.
 * The engine wants a file; building the container here keeps any audio codec
 * and any temporary file out of the browser.
 */
export function encodeWav(pcm, sampleRate = TARGET_SAMPLE_RATE) {
  const samples = pcm instanceof Float32Array ? pcm : Float32Array.from(pcm || []);
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const ascii = (offset, text) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i += 1) {
    const s = Math.max(-1, Math.min(1, samples[i] || 0));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Uint8Array(buffer);
}

/** Bounded failure categories, shared with the dock and diagnostics. */
function categorize(status, body) {
  if (status === 401 || status === 403) return "authentication";
  if (status === 413) return "resource";
  if (status === 415) return "unsupported";
  if (status === 0) return "network";
  if (status >= 500) return "backend";
  return String(body?.category || "recognition");
}

export class LocalSttTransportError extends Error {
  constructor(category, message) {
    super(message);
    this.name = "LocalSttTransportError";
    this.category = category;
  }
}

function endpoint(path, apiBase) {
  return `${apiBase ?? API_BASE}/api/v1/voice/stt${path}`;
}

function authHeaders(readToken) {
  const token = (readToken || getToken)() || "";
  return token ? { "X-Platform-Token": token } : {};
}

/**
 * Read-only readiness probe. Never opens a microphone, never starts a session.
 * Returns a bounded descriptor; a failure is reported, never guessed around.
 */
export async function probeLocalSttHealth({
  fetchImpl,
  apiBase,
  readToken,
  signal,
} = {}) {
  const doFetch = fetchImpl || (typeof fetch === "function" ? fetch : null);
  if (!doFetch) return { available: false, state: "UNAVAILABLE", reason: "no fetch in this runtime" };
  try {
    const res = await doFetch(endpoint("/health", apiBase), {
      method: "GET",
      headers: authHeaders(readToken),
      credentials: "include",
      signal,
    });
    if (!res.ok) {
      return {
        available: false,
        state: "UNAVAILABLE",
        category: categorize(res.status, null),
        reason: res.status === 401
          ? "sign-in required before local speech recognition is available"
          : `local speech recognition health check failed (${res.status})`,
      };
    }
    const body = await res.json();
    return {
      available: Boolean(body?.available),
      state: body?.state || "UNAVAILABLE",
      reason: body?.reason || "",
      engine: body?.engine || "",
      model: body?.model || "",
      privacyClass: body?.privacy_class || "LOCAL_CONFIRMED",
      languages: body?.languages || [],
      maxAudioSeconds: body?.max_audio_seconds ?? MAX_UTTERANCE_SECONDS,
    };
  } catch (err) {
    if (err?.name === "AbortError") {
      return { available: false, state: "UNAVAILABLE", category: "cancelled", reason: "cancelled" };
    }
    return {
      available: false,
      state: "UNAVAILABLE",
      category: "network",
      reason: "local speech recognition service is unreachable",
    };
  }
}

/**
 * Build the `transcribeFn` the local adapter consumes.
 * One in-flight request per utterance; aborting is synchronous so teardown
 * closes the window without awaiting a network round trip.
 */
export function createWhisperCppTranscriber({
  fetchImpl,
  apiBase,
  readToken,
  language = null,
} = {}) {
  const doFetch = fetchImpl || (typeof fetch === "function" ? fetch.bind(globalThis) : null);
  /** @type {AbortController|null} */
  let inflight = null;

  async function transcribe({ pcm, sampleRate = TARGET_SAMPLE_RATE, language: lang, isFinal }) {
    if (!doFetch) throw new LocalSttTransportError("unsupported", "no fetch in this runtime");
    // Only settled utterances are sent: this engine has no partial mode, and
    // publishing a partial as if it were final would make it executable.
    if (!isFinal) return { text: "", isFinal: false };

    const seconds = (pcm?.length || 0) / (sampleRate || TARGET_SAMPLE_RATE);
    if (seconds > MAX_UTTERANCE_SECONDS) {
      throw new LocalSttTransportError("resource", "utterance exceeds the bounded duration");
    }
    const wav = encodeWav(pcm, sampleRate);
    if (wav.byteLength > MAX_UTTERANCE_BYTES) {
      throw new LocalSttTransportError("resource", "utterance exceeds the bounded size");
    }

    const form = new FormData();
    form.append("file", new Blob([wav], { type: "audio/wav" }), "utterance.wav");
    const hint = lang || language;
    if (hint) form.append("language", hint);

    inflight?.abort();
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    inflight = controller;
    let res;
    try {
      res = await doFetch(endpoint("/transcribe", apiBase), {
        method: "POST",
        headers: authHeaders(readToken),
        credentials: "include",
        body: form,
        signal: controller?.signal,
      });
    } catch (err) {
      if (err?.name === "AbortError") return { text: "", isFinal: false };
      throw new LocalSttTransportError("network", "local speech recognition is unreachable");
    } finally {
      if (inflight === controller) inflight = null;
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new LocalSttTransportError(
        categorize(res.status, body),
        body?.message || `local speech recognition failed (${res.status})`
      );
    }
    const body = await res.json();
    return {
      text: String(body?.text || ""),
      isFinal: true,
      language: body?.language || null,
      confidence: typeof body?.confidence === "number" ? body.confidence : null,
    };
  }

  /** Synchronous cancellation boundary — no await, so teardown cannot race. */
  transcribe.cancelSync = () => {
    inflight?.abort();
    inflight = null;
  };
  return transcribe;
}

/**
 * The canonical local adapter for production. Reuses the existing
 * StreamingTranscriptionAdapter rather than introducing a second runtime.
 */
export function createLocalWhisperStt(opts = {}) {
  const transcribeFn = opts.transcribeFn || createWhisperCppTranscriber(opts);
  const adapter = createLocalStreamingStt({
    modelId: opts.modelId || "ggml-base",
    engineId: "whisper.cpp",
    sampleRate: opts.sampleRate || TARGET_SAMPLE_RATE,
    getSessionId: opts.getSessionId,
    language: opts.language || null,
    transcribeFn,
    admissionState: "LOCAL_STT_READY",
  });
  const baseCancel = adapter.cancelSync?.bind(adapter);
  adapter.cancelSync = () => {
    transcribeFn.cancelSync?.();
    baseCancel?.();
  };
  return adapter;
}
