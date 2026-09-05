import { describe, it } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

import {
  VOICE_TEST_PHRASES,
  normalizeVoiceList,
  phraseCanUseLocalVoice,
  resolveLocalVoice,
  safePermissionState,
  summarizeVoiceCapability,
  describeRecognitionError,
} from "./voice-settings.js";

const voices = [
  { voiceURI: "local-en", name: "English Local", lang: "en-US", localService: true, default: true },
  { voiceURI: "remote-ne", name: "Nepali Remote", lang: "ne-NP", localService: false },
  { voiceURI: "local-en", name: "Duplicate", lang: "en-US", localService: true },
];

describe("voice settings discovery and safety", () => {
  it("derives counts and languages from the runtime list without treating remote voices as local", () => {
    const capability = summarizeVoiceCapability(voices);
    assert.equal(capability.voiceCount, 2);
    assert.equal(capability.localVoiceCount, 1);
    assert.deepEqual(capability.languages, ["en-US", "ne-NP"]);
    assert.equal(capability.hasNepaliVoice, true);
    assert.equal(capability.hasLocalNepaliVoice, false);
    assert.equal(phraseCanUseLocalVoice("nepali", capability), false);
  });

  it("fails over deterministically when a saved system voice disappears", () => {
    assert.equal(resolveLocalVoice(voices, "missing", "en-GB")?.voiceURI, "local-en");
    assert.equal(resolveLocalVoice([], "missing", "en-US"), null);
    assert.equal(normalizeVoiceList(null).length, 0);
    const delayed = summarizeVoiceCapability([]);
    assert.equal(delayed.voiceCount, 0);
    assert.equal(summarizeVoiceCapability(voices).voiceCount, 2);
  });

  it("keeps required phrases exact and permission states fail closed", () => {
    assert.equal(VOICE_TEST_PHRASES.english.text, "Hello Ajay. SaathiOS voice output is working correctly.");
    assert.equal(VOICE_TEST_PHRASES.nepali.text, "नमस्ते अजय। साथी ओएसको आवाज परीक्षण भइरहेको छ।");
    assert.equal(VOICE_TEST_PHRASES.mixed.text, "SaathiOS अहिले local private alpha mode मा चलिरहेको छ।");
    assert.equal(safePermissionState("granted"), "granted");
    assert.equal(safePermissionState("anything-else"), "unknown");
  });

  it("explains browser-managed recognition network failures without implying SaathiOS upload", () => {
    const message = describeRecognitionError("network");
    assert.match(message, /browser-managed service is unavailable/i);
    assert.match(message, /text fallback/i);
    assert.match(message, /No audio is sent to SaathiOS/i);
    assert.doesNotMatch(message, /token|credential|device id/i);
  });

  it("certifies the page exposes explicit controls and bounded privacy language", () => {
    const page = fs.readFileSync(new URL("../app/settings/voice/page.jsx", import.meta.url), "utf8");
    for (const marker of [
      "System voice status",
      "setSynthesisSupported(Boolean(window.speechSynthesis))",
      "Play test",
      "Stop test",
      "Replay last test",
      "Request microphone permission",
      "Start microphone test",
      "Stop microphone test",
      "Push-to-interrupt",
      "Full acoustic barge-in is not implemented",
      '["interrupted", "canceled"].includes(event.error)',
      'synth.cancel();',
      'window.addEventListener(PLATFORM_CONTEXT_EVENT, onContext)',
      'mediaRef.current?.getTracks?.().forEach((track) => track.stop())',
      'navigator.mediaDevices.getUserMedia({ audio: true })',
      'STT input',
      'Whisper-compatible provider',
      'Start local STT test',
      'Stop local STT test',
      'useVoiceRuntime',
      'setTranscript(text)',
      "No voice recording or transcript is persisted by this settings test",
      'href="/settings/voice"',
    ]) assert.ok(page.includes(marker), marker);
    assert.equal(/api.?key|oauth|cloud provider/i.test(page), false);
    assert.equal(/\bfetch\s*\(|\bafetch\s*\(|API_BASE/.test(page), false);
  });

  it("places discoverable Voice Settings links in every bounded product surface", () => {
    const sources = [
      "../app/settings/page.jsx",
      "../components/CommandPalette.jsx",
      "../components/mobile/MobileMe.jsx",
      "../components/chat/VoiceControl.jsx",
      "../app/platform/onboarding/page.jsx",
    ].map((path) => fs.readFileSync(new URL(path, import.meta.url), "utf8"));
    for (const source of sources) assert.ok(source.includes("/settings/voice"));
  });
});
