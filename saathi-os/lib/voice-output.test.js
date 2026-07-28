import { describe, it } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

import {
  ACTIVE_VOICE_STATES,
  DEFAULT_VOICE_PREFERENCES,
  INITIAL_VOICE_OUTPUT,
  fetchVoiceAudio,
  normalizeVoiceOperation,
  normalizeVoicePreferences,
  voiceActions,
  voiceOutputReducer,
  voiceStateLabel,
} from "./voice-output.js";

function operation(state, over = {}) {
  return {
    operation_id: "speech_fixture",
    state,
    requested_provider: "auto",
    provider: "macos_system",
    streaming_state: state,
    fallback_used: false,
    audio_available: state === "completed",
    ...over,
  };
}

describe("voice output contract", () => {
  it("bounds and versions safe local preferences", () => {
    assert.deepEqual(normalizeVoicePreferences(null), DEFAULT_VOICE_PREFERENCES);
    assert.deepEqual(
      normalizeVoicePreferences({
        version: 99,
        enabled: false,
        profileId: "../../private",
        speakingRate: 99,
        token: "must-not-persist",
      }),
      {
        version: 1,
        enabled: false,
        profileId: "saathi_default",
        speakingRate: 2,
      }
    );
  });

  it("normalizes backend operations without provider-native objects", () => {
    const normalized = normalizeVoiceOperation(
      operation("completed", {
        fallback_used: true,
        fallback_reason: "voxcpm_unavailable",
        duration_seconds: -3,
        artifact_bytes: 12,
        private_path: "/private/audio.aiff",
      })
    );
    assert.equal(normalized.fallbackUsed, true);
    assert.equal(normalized.durationSeconds, 0);
    assert.equal(normalized.artifactBytes, 12);
    assert.equal("private_path" in normalized, false);
    assert.equal(normalizeVoiceOperation({}), null);
  });

  it("represents every required synthesis and playback state", () => {
    let state = INITIAL_VOICE_OUTPUT;
    for (const name of [
      "queued",
      "preparing",
      "synthesizing",
      "streaming",
      "completed",
      "cancelled",
      "failed",
      "unavailable",
    ]) {
      state = voiceOutputReducer(state, {
        type: "OPERATION",
        operation: operation(name),
      });
      assert.equal(state.state, name);
      assert.ok(voiceStateLabel(name));
    }
    state = voiceOutputReducer(state, {
      type: "READY",
      operation: operation("completed"),
    });
    assert.equal(state.audioReady, true);
    state = voiceOutputReducer(state, { type: "PLAYING" });
    assert.equal(state.state, "playing");
    state = voiceOutputReducer(state, { type: "ENDED" });
    assert.equal(state.state, "completed");
    state = voiceOutputReducer(state, { type: "CANCELLED" });
    assert.equal(state.state, "cancelled");
    state = voiceOutputReducer(state, {
      type: "FAILED",
      unavailable: true,
    });
    assert.equal(state.state, "unavailable");
    assert.ok(ACTIVE_VOICE_STATES.has("synthesizing"));
    assert.equal(ACTIVE_VOICE_STATES.has("completed"), false);
  });

  it("uses authenticated platform speech and binary routes", async () => {
    const seen = [];
    const original = globalThis.fetch;
    globalThis.fetch = async (url, options) => {
      seen.push({ url: String(url), options });
      if (String(url).endsWith("/audio")) {
        return new Response(new Blob(["audio"]), {
          status: 200,
          headers: { "content-type": "audio/aiff" },
        });
      }
      return new Response(
        JSON.stringify({ operation: operation("queued") }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    };
    try {
      await voiceActions.speak({ text: "Approved response." }, "voice-token");
      await voiceActions.cancel("speech_fixture", "voice-token");
      const blob = await fetchVoiceAudio("speech_fixture", {
        token: "voice-token",
      });
      assert.equal(blob.size, 5);
      assert.match(seen[0].url, /\/api\/v1\/platform\/voice\/speech$/);
      assert.equal(seen[0].options.headers["X-Platform-Token"], "voice-token");
      assert.match(seen[1].url, /\/speech\/speech_fixture\/cancel$/);
      assert.match(seen[2].url, /\/speech\/speech_fixture\/audio$/);
      assert.equal(seen[2].options.headers["X-Platform-Token"], "voice-token");
      assert.equal(seen[2].options.cache, "no-store");
    } finally {
      globalThis.fetch = original;
    }
  });

  it("shell controls are explicit, accessible, and never autoplay", () => {
    const provider = fs.readFileSync(
      new URL("../components/voice/VoiceOutputProvider.jsx", import.meta.url),
      "utf8"
    );
    const dock = fs.readFileSync(
      new URL("../components/voice/VoiceOutputDock.jsx", import.meta.url),
      "utf8"
    );
    const chat = fs.readFileSync(
      new URL("../components/chat/ChatWorkspace.jsx", import.meta.url),
      "utf8"
    );
    for (const text of [
      "Speak assistant response",
      "voiceOutput.speak(m.content",
      'm.role !== "user"',
    ]) {
      assert.ok(chat.includes(text), text);
    }
    for (const text of [
      'aria-label="Enable speech output"',
      'aria-label="Voice profile"',
      'aria-label="Speaking rate"',
      'aria-label="Play synthesized speech"',
      'aria-label="Stop speaking"',
      'aria-live="polite"',
      "fallback used",
      "Provider unavailable · Retry",
    ]) {
      assert.ok(dock.includes(text), text);
    }
    assert.ok(provider.includes('audio.preload = "auto"'));
    assert.ok(provider.includes("const play = useCallback"));
    const prepareStart = provider.indexOf("const prepareAudio");
    const playStart = provider.indexOf("const play = useCallback");
    assert.equal(
      provider.slice(prepareStart, playStart).includes(".play()"),
      false,
      "synthesis completion must not autoplay"
    );
    assert.ok(provider.includes("PLATFORM_CONTEXT_EVENT"));
    assert.ok(provider.includes("clearLocalAudio()"));
  });
});
