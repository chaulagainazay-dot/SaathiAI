import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const source = (relativePath) =>
  readFileSync(new URL(`../${relativePath}`, import.meta.url), "utf8");

describe("canonical microphone surface", () => {
  it("does not mount the legacy global mobile microphone", () => {
    const shell = source("components/Shell.jsx");
    assert.doesNotMatch(shell, /MobileMic/);
    assert.match(shell, /<VoiceRuntimeDock \/>/);
  });

  it("does not expose the legacy chat or mobile push-to-talk controls", () => {
    const chat = source("components/chat/ChatWorkspace.jsx");
    const mobile = source("components/mobile/MobileSaathi.jsx");
    const os = source("app/os/page.jsx");

    assert.doesNotMatch(chat, /VoiceControl|voiceOpen/);
    assert.doesNotMatch(mobile, /useVoice|onPointerDown/);
    assert.doesNotMatch(os, /useVoice|onPointerDown/);
  });

  it("keeps the canonical runtime dock off dedicated enrollment routes", () => {
    const shell = source("components/Shell.jsx");
    assert.match(
      shell,
      /dedicatedCaptureRoute = pathname === "\/voice" \|\| pathname === "\/os"/,
    );
    assert.match(shell, /!dedicatedCaptureRoute && <VoiceRuntimeDock \/>/);
  });

  it("keeps the authenticated runtime dock reachable in the viewport", () => {
    const dock = source("components/voice/VoiceRuntimeDock.jsx");
    assert.match(dock, /position: fixed;/);
    assert.match(dock, /left: 16px;/);
    assert.match(dock, /bottom: 16px;/);
    assert.match(dock, /z-index: 50;/);
  });
});
