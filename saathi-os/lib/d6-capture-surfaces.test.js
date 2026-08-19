/**
 * R2.1-D6 — reachable production capture surfaces.
 *
 * D6 removes or claims every remaining production microphone surface. These
 * tests read the actual production sources rather than a hand-maintained list
 * of what is believed to be there, so a reintroduced recorder fails here even
 * if nobody remembers to update a checklist.
 *
 * Scope note: these are source-shape invariants. They prove which capture APIs
 * a surface can reach, not what a browser does with a live microphone. The
 * runtime ownership behaviour is proven separately in
 * lib/voice-session/surface-exclusion.test.js and the browser certificates.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
export const root = (...parts) => join(HERE, "..", ...parts);
const read = (relative) => readFileSync(root(relative), "utf8");

const CAPTURE_APIS = ["getUserMedia", "MediaRecorder", "SpeechRecognition"];

describe("D6.2 — MobileSaathi is a text surface", () => {
  const source = read("components/mobile/MobileSaathi.jsx");

  for (const api of CAPTURE_APIS) {
    it(`never reaches ${api}`, () => {
      assert.ok(!source.includes(api), `${api} is back in MobileSaathi`);
    });
  }

  it("does not import or consume the recording hook", () => {
    assert.ok(!/\buseVoice\b/.test(source), "the recorder hook is back");
  });

  it("has no speech-derived upload path", () => {
    assert.ok(!source.includes("sendVoice"), "sendVoice is back");
  });

  it("keeps the typed path: input, submit, and sendChat", () => {
    assert.ok(source.includes("sendChat"), "typed submission was lost");
    assert.ok(/onKeyDown=\{\(e\) => e\.key === "Enter" && send\(ask\)\}/.test(source),
      "typed Enter-to-send was lost");
    assert.ok(source.includes("const send = async (text)"), "the send path was lost");
  });

  it("keeps the inline unlock and example prompts", () => {
    assert.ok(source.includes("const unlock = async"), "inline unlock was lost");
    assert.ok(source.includes("EXAMPLE_PROMPTS"), "example prompts were lost");
  });

  it("points at the one microphone control without creating a second trigger", () => {
    assert.ok(/only microphone control in SaathiOS/.test(source),
      "the truthful voice pointer is missing");
    // A pointer is copy. A trigger is a control. Only the send button remains.
    const buttons = source.match(/<button/g) || [];
    assert.equal(buttons.length, 3, "expected exactly the prompt, unlock and send buttons");
  });

  it("mounts nothing voice-specific on /saathi — the dock is shell-global", () => {
    const page = read("app/saathi/page.jsx");
    assert.ok(!/Voice/.test(page), "/saathi must not mount its own voice surface");
    const shell = read("components/Shell.jsx");
    assert.ok(shell.includes("<VoiceRuntimeDock />"),
      "the canonical dock must stay globally mounted for every route including /saathi");
  });
});

describe("D6.3 — /os is a text surface", () => {
  const source = read("app/os/page.jsx");

  for (const api of CAPTURE_APIS) {
    it(`never reaches ${api}`, () => {
      assert.ok(!source.includes(api), `${api} is back in /os`);
    });
  }

  it("does not import or consume the recording hook", () => {
    assert.ok(!/\buseVoice\b/.test(source), "the recorder hook is back");
  });

  it("has no speech-derived upload path and no retired enrollment call", () => {
    assert.ok(!source.includes("sendVoice"), "sendVoice is back");
    assert.ok(!source.includes("enrollVoice"), "retired enrollment is back");
  });

  it("keeps the dashboard reads and the mission write", () => {
    assert.ok(source.includes("fetchCeoOs"), "fetchCeoOs was lost");
    assert.ok(source.includes("completeMission"), "completeMission was lost");
    assert.ok(source.includes("completeMissionItem"), "the mission checklist was lost");
  });

  it("keeps the typed ask flow and its authenticated retry", () => {
    assert.ok(source.includes("const submitAsk = async"), "the typed ask was lost");
    assert.ok(source.includes("submitAskText"), "the post-login retry was lost");
    assert.ok(source.includes("sendChat"), "typed submission was lost");
  });

  it("implements no second voice or session runtime", () => {
    assert.ok(!/voice\.(start|stop|busy|recording)/.test(source),
      "a recorder consumer is back in /os");
    assert.ok(!/\/api\/v1\/voice\//.test(source), "/os must not talk to voice endpoints");
  });
});
