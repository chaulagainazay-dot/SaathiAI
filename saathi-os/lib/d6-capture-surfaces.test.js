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
import { readFileSync, existsSync, readdirSync } from "node:fs";
import { dirname, join, relative as relativePath, sep } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const root = (...parts) => join(HERE, "..", ...parts);
const read = (rel) => readFileSync(root(rel), "utf8");

/** Directories that ship to a browser. `scripts/` holds certificates, not app code. */
const PRODUCTION_ROOTS = ["app", "components", "lib"];
const SOURCE_EXTENSIONS = [".js", ".jsx", ".mjs", ".ts", ".tsx"];

/**
 * Every production frontend source, walked from the tree rather than listed.
 *
 * A hand-maintained list is the failure mode these invariants exist to catch:
 * a new file with a new recorder is exactly the thing nobody remembers to add
 * to a checklist. Test files are excluded — they construct fake recognizers and
 * fake microphones on purpose.
 */
function productionSources() {
  const found = [];
  const walk = (absolute) => {
    for (const entry of readdirSync(absolute, { withFileTypes: true })) {
      if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
      const next = join(absolute, entry.name);
      if (entry.isDirectory()) {
        walk(next);
        continue;
      }
      if (!SOURCE_EXTENSIONS.some((ext) => entry.name.endsWith(ext))) continue;
      if (/\.test\.[cm]?[jt]sx?$/.test(entry.name)) continue;
      found.push(relativePath(root(), next).split(sep).join("/"));
    }
  };
  for (const dir of PRODUCTION_ROOTS) walk(root(dir));
  return found.sort();
}


/**
 * Drop comments before matching.
 *
 * These invariants describe what the code *reaches*, and a source file that
 * explains why a capture API was removed necessarily names it. Matching raw
 * text would make the explanation itself the violation.
 */
function stripComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1 ");
}

const CAPTURE_APIS = ["getUserMedia", "MediaRecorder", "SpeechRecognition"];

describe("D6.2 — MobileSaathi is a text surface", () => {
  const raw = read("components/mobile/MobileSaathi.jsx");
  const source = stripComments(raw);

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
    assert.ok(/only microphone control in SaathiOS/.test(raw),
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
  const raw = read("app/os/page.jsx");
  const source = stripComments(raw);

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

describe("D6.4 — the unclaimed recording hook is gone", () => {
  it("lib/useVoice.js does not exist", () => {
    assert.ok(!existsSync(root("lib/useVoice.js")), "the recorder hook is back");
  });

  it("no client wrapper for the legacy upload endpoint remains", () => {
    const api = read("lib/api.js");
    assert.ok(!/export async function sendVoice/.test(api), "the sendVoice wrapper is back");
  });

  it("no production frontend source calls /api/v1/voice/command", () => {
    const offenders = productionSources().filter((rel) =>
      /\/api\/v1\/voice\/command/.test(stripComments(read(rel)))
    );
    assert.deepEqual(offenders, [], "a frontend caller of the legacy upload endpoint is back");
  });
});
