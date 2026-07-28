import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  INITIAL_VOICE_RUNTIME,
  micButtonLabel,
  normalizeRuntimeSession,
  prefersBrowserStt,
  voiceRuntimeReducer,
} from "./voice-runtime.js";

describe("voice-runtime client", () => {
  it("normalizes session payloads", () => {
    const session = normalizeRuntimeSession({
      session_id: "vses_1",
      state: "LISTENING",
      input_state: "recording",
      playback_state: "idle",
      partial_user_transcript: "hello",
      transcript: [{ role: "user", text: "hi" }],
      interruptions: [],
    });
    assert.equal(session.sessionId, "vses_1");
    assert.equal(session.partialUser, "hello");
    assert.equal(session.transcript.length, 1);
  });

  it("reduces session and local recording flags", () => {
    let state = { ...INITIAL_VOICE_RUNTIME };
    state = voiceRuntimeReducer(state, {
      type: "SESSION",
      session: {
        session_id: "vses_2",
        state: "RESPONDING",
        input_state: "idle",
        playback_state: "playing",
        partial_assistant_response: "I can help",
        transcript: [],
        interruptions: [],
      },
    });
    assert.equal(state.speaking, true);
    assert.match(state.message, /Speaking/);
    state = voiceRuntimeReducer(state, {
      type: "LOCAL_RECORDING",
      recording: true,
    });
    assert.equal(state.recording, true);
  });

  it("labels the microphone button for modes", () => {
    assert.equal(micButtonLabel({ recording: true }), "Stop recording");
    assert.equal(micButtonLabel({ speaking: true }), "Interrupt assistant");
    assert.equal(micButtonLabel({ listening: true }), "Listening");
    assert.equal(micButtonLabel({}), "Start talking");
  });

  it("handles reset and error", () => {
    let state = voiceRuntimeReducer(INITIAL_VOICE_RUNTIME, {
      type: "ERROR",
      error: "mic denied",
    });
    assert.match(state.error, /mic denied/);
    state = voiceRuntimeReducer(state, { type: "RESET" });
    assert.equal(state.sessionId, "");
    assert.equal(state.error, "");
  });

  it("prefers browser STT only when available", () => {
    assert.equal(typeof prefersBrowserStt(), "boolean");
  });
});
