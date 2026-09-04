import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(HERE, "..");
const read = (relative) => readFileSync(join(FRONTEND, relative), "utf8");

describe("SaathiOS exposes one canonical command voice surface", () => {
  it("mounts the VoiceRuntimeDock once in the global shell", () => {
    const shell = read("components/Shell.jsx");
    assert.equal((shell.match(/<VoiceRuntimeDock\s*\/>/g) || []).length, 1);
    assert.doesNotMatch(shell, /MobileMic|dedicatedCaptureRoute/);
  });

  it("does not retain a route-specific chat microphone owner", () => {
    assert.equal(existsSync(join(FRONTEND, "components/chat/VoiceControl.jsx")), false);
    assert.doesNotMatch(read("components/chat/ChatWorkspace.jsx"), /VoiceControl|voiceEnabled|voiceOpen/);
    assert.doesNotMatch(read("app/chat/page.jsx"), /VoiceControl|voiceEnabled/);
    assert.doesNotMatch(read("components/shell/CopilotPanel.jsx"), /VoiceControl|voiceEnabled/);
  });

  it("keeps former mobile and OS capture paths retired", () => {
    for (const relative of ["components/mobile/MobileSaathi.jsx", "app/os/page.jsx"]) {
      const source = read(relative);
      assert.doesNotMatch(source, /useVoice|onPointerDown|getUserMedia|enrollVoice/);
    }
  });

  it("redirects the retired voice route before client code can run", () => {
    const page = read("app/voice/page.jsx");
    assert.match(page, /redirect\("\/settings\/voice"\)/);
    assert.doesNotMatch(page, /^["']use client["'];/m);
  });
});
