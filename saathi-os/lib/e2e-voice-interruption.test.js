// Regression tests for the SaathiOS closure mission — Phase 10 (Option A).
//
// VOICE_INPUT_INTERRUPTS_OUTPUT. Not acoustic ducking, not full duplex.
//
// interrupt() always cancelled output before starting capture, but toggleMic only
// routed to it when `runtime.speaking` was true — and that flag is derived purely
// from the SERVER voice session (state RESPONDING / playbackState playing). Audio
// started through VoiceOutputProvider from anywhere else (chat, IELTS feedback,
// the voice dock) leaves `runtime.speaking` false, so pressing the mic opened
// capture on top of audio that was still playing.
//
// Source-contract tests, matching the style of lib/ielts.test.js. The observable
// half is covered by the browser certification and the owner audio checklist.
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const runtime = readFileSync(
  new URL("../components/voice/VoiceRuntimeProvider.jsx", import.meta.url),
  "utf8"
);
const voiceRuntimeLib = readFileSync(
  new URL("./voice-runtime.js", import.meta.url),
  "utf8"
);

describe("voice input interrupts voice output", () => {
  it("runtime.speaking still reflects only the server session", () => {
    // Pins the premise of the defect. If this ever starts tracking local audio
    // too, the unconditional stop below becomes redundant rather than wrong.
    assert.match(
      voiceRuntimeLib,
      /const speaking =\s*\n?\s*session\.state === "RESPONDING" \|\| session\.playbackState === "playing";/,
      "speaking is derived from the server session payload"
    );
  });

  it("toggleMic cancels voice output before opening the microphone", () => {
    const start = runtime.indexOf("const toggleMic");
    const end = runtime.indexOf("const retry");
    assert.ok(start > -1 && end > start, "toggleMic must exist");
    const body = runtime.slice(start, end);

    const stopAt = body.indexOf("await voiceOutput?.stop?.()");
    const sessionAt = body.indexOf("await ensureSession(activeToken)");
    const recogAt = body.indexOf("await startBrowserRecognition(activeToken, sessionId)");

    assert.ok(stopAt > -1, "toggleMic must cancel voice output");
    assert.ok(sessionAt > -1 && recogAt > -1, "toggleMic must open a session and start capture");
    assert.ok(stopAt < sessionAt, "output must be cancelled before the session is created");
    assert.ok(stopAt < recogAt, "output must be cancelled before capture starts");
  });

  it("the cancellation is awaited, so capture cannot race playback", () => {
    assert.match(
      runtime,
      /await voiceOutput\?\.stop\?\.\(\);\s*\n\s*const sessionId = await ensureSession/,
      "stop() must be awaited immediately before the session is opened"
    );
  });

  it("toggleMic declares voiceOutput as a dependency", () => {
    const start = runtime.indexOf("const toggleMic");
    const end = runtime.indexOf("const retry");
    const body = runtime.slice(start, end);
    assert.match(body, /\n\s*voiceOutput,\n\s*\]\);/, "stale closure would keep an old stop()");
  });

  it("the server-session interrupt path still cancels output before capture", () => {
    const start = runtime.indexOf("const interrupt = useCallback");
    const end = runtime.indexOf("const toggleMic");
    const body = runtime.slice(start, end);
    const stopAt = body.indexOf("await voiceOutput?.stop?.()");
    const interruptAt = body.indexOf("voiceRuntimeActions.interrupt(");
    const recogAt = body.indexOf("await startBrowserRecognition(");
    assert.ok(stopAt > -1 && interruptAt > -1 && recogAt > -1);
    assert.ok(stopAt < interruptAt, "local audio stops before the server is told");
    assert.ok(interruptAt < recogAt, "capture resumes only after the interrupt is recorded");
  });

  it("stopping the microphone does not restart output", () => {
    const start = runtime.indexOf("const toggleMic");
    const end = runtime.indexOf("const retry");
    const body = runtime.slice(start, end);
    const recordingBranch = body.slice(
      body.indexOf("if (runtime.recording)"),
      body.indexOf("if (runtime.speaking)")
    );
    assert.doesNotMatch(
      recordingBranch,
      /voiceOutput\?\.(speak|play)/,
      "releasing the mic must not resume or replay speech"
    );
  });
});
