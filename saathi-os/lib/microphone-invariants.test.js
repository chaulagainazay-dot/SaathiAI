/**
 * R2.1-D6.6 — system-wide microphone invariants.
 *
 * These run against the production source tree, walked from disk and from the
 * shell's own import graph, not against a hand-maintained list of surfaces. A
 * list is exactly what D6 found to be wrong: MobileMic, two useVoice consumers,
 * an unclaimed settings probe, a surviving recorder in the legacy static
 * client, and a previously unlisted recognizer in the IELTS static page were
 * all "known" to be absent or claimed, and none of that was true.
 *
 * What these prove: which capture APIs each reachable production surface can
 * reach, and that every one it can reach goes through the AudioInputOwner
 * registry. Runtime exclusion — one claim, one recognizer, preemption, release
 * — is proven against the real registry in surface-exclusion.test.js and
 * settings-capture-ownership.test.js, and the relevant assertions are repeated
 * here against the registry itself so the invariant suite fails on its own if
 * ownership regresses.
 *
 * What they do not prove: anything about a physical microphone, or about
 * browsers that ignore a stop().
 */
import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative as rel, sep } from "node:path";
import { fileURLToPath } from "node:url";

import {
  acquireInputClaim,
  forceReleaseInput,
  getInputOwnerSnapshot,
  openMicrophoneForClaim,
} from "./voice-session/index.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(HERE, "..");
const REPO = join(FRONTEND, "..");
const fRead = (p) => readFileSync(join(FRONTEND, p), "utf8");

const CAPTURE_PATTERNS = {
  getUserMedia: /\bgetUserMedia\b/,
  SpeechRecognition: /\b(?:webkit)?SpeechRecognition\b/,
  MediaRecorder: /\bMediaRecorder\b/,
};

/**
 * Strip comments while leaving code, including strings, intact.
 *
 * Comments explain removals, so they necessarily name what was removed — a
 * scan that reads them reports capture surfaces that no longer exist. But a
 * naive `//` rule is worse than none: it ate
 * `` `${protocol}//${host}/api/v1/ielts/ws/speaking/...` `` and hid the one
 * channel that page is allowed to use, and reading raw source instead let the
 * phrase `no "use client"` inside a comment read as the directive itself.
 * Both were live failures of this suite.
 *
 * So this walks the source once, tracking which construct it is inside:
 * single and double quotes, template literals (including `${}` interpolation,
 * which nests), regex literals, and both comment forms. Only real comments
 * are removed.
 */
function code(source) {
  const out = [];
  // Stack so `${ ... `nested` ... }` returns to the template it came from.
  const stack = [];
  const top = () => stack[stack.length - 1];
  let i = 0;

  /** A `/` starts a regex only where a value cannot already have ended. */
  const regexAllowed = () => {
    for (let k = out.length - 1; k >= 0; k -= 1) {
      const ch = out[k];
      if (/\s/.test(ch)) continue;
      return !/[\w$)\]]/.test(ch);
    }
    return true;
  };

  while (i < source.length) {
    const ch = source[i];
    const next = source[i + 1];
    const state = top();

    if (state === "line") {
      if (ch === "\n") { stack.pop(); out.push(ch); }
      i += 1; continue;
    }
    if (state === "block") {
      if (ch === "*" && next === "/") { stack.pop(); out.push(" "); i += 2; continue; }
      if (ch === "\n") out.push(ch);
      i += 1; continue;
    }
    if (state === "'" || state === '"') {
      out.push(ch);
      if (ch === "\\") { out.push(next ?? ""); i += 2; continue; }
      if (ch === state) stack.pop();
      i += 1; continue;
    }
    if (state === "regex") {
      out.push(ch);
      if (ch === "\\") { out.push(next ?? ""); i += 2; continue; }
      if (ch === "/" || ch === "\n") stack.pop();
      i += 1; continue;
    }
    if (state === "`") {
      out.push(ch);
      if (ch === "\\") { out.push(next ?? ""); i += 2; continue; }
      if (ch === "`") { stack.pop(); i += 1; continue; }
      if (ch === "$" && next === "{") { stack.push("interp"); out.push(next); i += 2; continue; }
      i += 1; continue;
    }

    // Ordinary code, or inside a `${ }` interpolation.
    if (ch === "/" && next === "/") { stack.push("line"); i += 2; continue; }
    if (ch === "/" && next === "*") { stack.push("block"); i += 2; continue; }
    if (ch === "'" || ch === '"' || ch === "`") { stack.push(ch); out.push(ch); i += 1; continue; }
    if (ch === "/" && regexAllowed()) { stack.push("regex"); out.push(ch); i += 1; continue; }
    if (state === "interp") {
      if (ch === "{") stack.push("brace");
      else if (ch === "}") stack.pop();
    } else if (state === "brace") {
      if (ch === "{") stack.push("brace");
      else if (ch === "}") stack.pop();
    }
    out.push(ch);
    i += 1;
  }
  return out.join("");
}

/* ── 0. the scanner itself ──────────────────────────────────────────────── */
//
// Every invariant below is only as trustworthy as this scan. Both of the
// failures it was written to fix were silent: one hid a WebSocket URL, the
// other read a comment as a directive. So the scanner is tested first.

describe("0 — the source scanner reads code, not prose", () => {
  const keeps = [
    ["a WebSocket template URL", "ws = new WebSocket(`${p}//${h}/api/v1/ielts/ws/speaking/s1`);", /ielts\/ws\/speaking/],
    ["an http URL inside a string", 'const u = "https://example.com/getUserMedia";', /getUserMedia/],
    ["a regex literal containing slashes", "const re = /a\\/\\/b/;", /a\\\/\\\/b/],
    ["code after an escaped quote", 'const a = "x\\"//y"; getUserMedia();', /getUserMedia\(\)/],
    ["division that only looks like a regex", "const r = a / b; getUserMedia();", /getUserMedia\(\)/],
    ["a capture name quoted as data", 'const s = "// getUserMedia";', /getUserMedia/],
  ];
  for (const [name, source, expected] of keeps) {
    it(`keeps ${name}`, () => assert.match(code(source), expected));
  }

  const drops = [
    ["a line comment", "// getUserMedia was removed\nconst x = 1;", /getUserMedia/],
    ["a block comment", "/* MediaRecorder was here */ const x = 1;", /MediaRecorder/],
    ["a comment that quotes a directive", 'const x = 1; // no "use client" here', /use client/],
    ["a comment inside template interpolation", "const t = `${x /* SpeechRecognition */}`;", /SpeechRecognition/],
    ["a comment after a regex literal", "const re = /ab/; // getUserMedia\n", /getUserMedia/],
  ];
  for (const [name, source, forbidden] of drops) {
    it(`drops ${name}`, () => assert.doesNotMatch(code(source), forbidden));
  }
});

const SOURCE_EXT = [".js", ".jsx", ".mjs", ".ts", ".tsx"];

function walk(absolute, out = []) {
  for (const entry of readdirSync(absolute, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
    const next = join(absolute, entry.name);
    if (entry.isDirectory()) {
      walk(next, out);
      continue;
    }
    if (!SOURCE_EXT.some((e) => entry.name.endsWith(e))) continue;
    if (/\.test\.[cm]?[jt]sx?$/.test(entry.name)) continue;
    out.push(rel(FRONTEND, next).split(sep).join("/"));
  }
  return out;
}

/** Every production frontend source that ships to a browser. */
const PRODUCTION = ["app", "components", "lib"].flatMap((d) => walk(join(FRONTEND, d))).sort();

/**
 * The canonical capture implementation. Everything else that touches a capture
 * API must either be in the canonical pipeline, the transient settings
 * diagnostic, or be absent.
 */
const CANONICAL_PIPELINE = PRODUCTION.filter((p) => p.startsWith("lib/voice-session/"));
const CLAIMED_SURFACES = [
  "app/settings/voice/page.jsx",
  "components/voice/VoiceRuntimeProvider.jsx",
];

/** Files allowed to name a capture API without opening one (capability probes). */
const CAPABILITY_ONLY = ["lib/voice-runtime.js"];

function reaches(file, api) {
  return CAPTURE_PATTERNS[api].test(code(fRead(file)));
}

/* ── 1. exactly one globally mounted microphone surface ─────────────────── */

describe("1 — exactly one globally mounted microphone surface", () => {
  /** Resolve the shell's import graph so "globally mounted" is computed, not asserted. */
  function importGraph(entry) {
    const seen = new Set();
    const queue = [entry];
    while (queue.length) {
      const current = queue.shift();
      if (seen.has(current)) continue;
      seen.add(current);
      let source;
      try { source = fRead(current); } catch { continue; }
      const dir = dirname(current);
      for (const match of source.matchAll(/from\s+["']([^"']+)["']/g)) {
        const spec = match[1];
        let base;
        if (spec.startsWith("@/")) base = spec.slice(2);
        else if (spec.startsWith(".")) base = rel(FRONTEND, join(FRONTEND, dir, spec)).split(sep).join("/");
        else continue;
        // A bare specifier can name a directory; only a real file is a module.
        const isFile = (c) => {
          const abs = join(FRONTEND, c);
          return existsSync(abs) && statSync(abs).isFile();
        };
        const candidate = [
          base, `${base}.js`, `${base}.jsx`, `${base}.mjs`,
          `${base}/index.js`, `${base}/index.jsx`,
        ].find(isFile);
        if (candidate) queue.push(candidate);
      }
    }
    return seen;
  }

  const shellGraph = importGraph("components/Shell.jsx");

  it("no shell-reachable capture surface exists outside the canonical pipeline", () => {
    const capturing = [...shellGraph]
      .filter((f) => !CANONICAL_PIPELINE.includes(f))
      .filter((f) => !CAPABILITY_ONLY.includes(f))
      .filter((f) => Object.keys(CAPTURE_PATTERNS).some((api) => reaches(f, api)));

    assert.deepEqual(capturing, [], "a competing shell-reachable capture surface exists");
    assert.ok(!existsSync(join(FRONTEND, "components/chat/VoiceControl.jsx")));
    const workspace = fRead("components/chat/ChatWorkspace.jsx");
    assert.doesNotMatch(workspace, /VoiceControl|voiceEnabled|voiceOpen/);
    assert.doesNotMatch(fRead("components/shell/CopilotPanel.jsx"), /voiceEnabled/);
    assert.doesNotMatch(fRead("app/chat/page.jsx"), /voiceEnabled|VoiceControl/);
  });

  it("the canonical dock is the one microphone control the shell mounts", () => {
    const shell = fRead("components/Shell.jsx");
    assert.ok(shell.includes("<VoiceRuntimeDock />"), "the canonical dock must stay mounted");
    assert.ok(!/<MobileMic\b/.test(shell), "a second global microphone control is back");
    const layout = fRead("app/layout.jsx");
    assert.ok(layout.includes("<Shell>"), "the shell is the only global chrome host");
  });

  it("chat and Copilot rely on the shell-level dock instead of owning capture", () => {
    assert.ok(!/VoiceControl|voiceEnabled/.test(fRead("components/chat/ChatWorkspace.jsx")));
    assert.ok(!/VoiceControl|voiceEnabled/.test(fRead("components/shell/CopilotPanel.jsx")));
    assert.ok(!/VoiceControl|voiceEnabled/.test(fRead("app/chat/page.jsx")));
  });
});

/* ── 2/3/4. every reachable capture call is ownership-controlled ─────────── */

describe("2, 3, 4 — every reachable capture call is ownership-controlled or absent", () => {
  for (const api of Object.keys(CAPTURE_PATTERNS)) {
    it(`no production source outside the claimed set reaches ${api}`, () => {
      const offenders = PRODUCTION
        .filter((f) => !CANONICAL_PIPELINE.includes(f))
        .filter((f) => !CLAIMED_SURFACES.includes(f))
        .filter((f) => !CAPABILITY_ONLY.includes(f))
        .filter((f) => reaches(f, api));
      assert.deepEqual(offenders, [], `unclaimed ${api} surface`);
    });
  }

  it("MediaRecorder is absent from the whole production frontend", () => {
    const offenders = PRODUCTION.filter((f) => reaches(f, "MediaRecorder"));
    assert.deepEqual(offenders, [], "a recorder is back; live voice streams, it does not upload blobs");
  });

  for (const surface of CLAIMED_SURFACES) {
    it(`${surface} opens the microphone only through a claim`, () => {
      const source = fRead(surface);
      assert.ok(source.includes("acquireInputClaim") || source.includes("beginInput"),
        "capture without a claim");
      assert.ok(!/navigator\.mediaDevices\.getUserMedia\(/.test(code(source)),
        "direct getUserMedia bypasses the claim");
    });
  }

  it("the capability probe named in the exception list really only probes", () => {
    for (const file of CAPABILITY_ONLY) {
      const source = code(fRead(file));
      assert.ok(!/getUserMedia|MediaRecorder|new\s+Ctor\(|\.start\(\)/.test(source),
        `${file} does more than report capability`);
    }
  });
});

/* ── 5/6/7/8. one claim, one recognizer, complete preemption ────────────── */

describe("5, 6, 7, 8 — the registry admits one owner and preempts completely", () => {
  beforeEach(() => forceReleaseInput("TEST_SETUP"));
  afterEach(() => forceReleaseInput("TEST_TEARDOWN"));

  function fakeRecognizer() {
    return { running: true, aborted: false, stop() { this.running = false; }, abort() { this.aborted = true; this.running = false; } };
  }
  function fakeStream() {
    const track = { readyState: "live", stop() { this.readyState = "ended"; } };
    return { track, getTracks: () => [track] };
  }

  it("a second claim leaves exactly one owner", () => {
    const first = acquireInputClaim({ label: "first" });
    const second = acquireInputClaim({ label: "second" });
    assert.equal(first.isActive(), false);
    assert.equal(second.isActive(), true);
    assert.equal(getInputOwnerSnapshot().label, "second");
  });

  it("preemption stops the previous recognizer and its tracks completely", () => {
    const first = acquireInputClaim({ label: "first" });
    const recognizer = fakeRecognizer();
    const stream = fakeStream();
    first.setMediaStream(stream);
    first.setRecognition(recognizer);

    acquireInputClaim({ label: "second" });

    assert.equal(recognizer.running, false, "the preempted recognizer still runs");
    assert.equal(recognizer.aborted, true, "stopped but not aborted leaves a restart window");
    assert.equal(stream.track.readyState, "ended", "the preempted capture is still live");
  });

  it("releasing the last claim returns input ownership to idle", () => {
    const claim = acquireInputClaim({ label: "only" });
    claim.release();
    assert.equal(getInputOwnerSnapshot().claimId, null);
    assert.equal(getInputOwnerSnapshot().hasMediaStream, false);
    assert.equal(getInputOwnerSnapshot().hasRecognition, false);
  });

  it("a stream that arrives after preemption is stopped, not adopted", async () => {
    const claim = acquireInputClaim({ label: "loser" });
    const realNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
    let opened = null;
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      writable: true,
      value: {
        mediaDevices: {
          async getUserMedia() {
            acquireInputClaim({ label: "winner" });   // preempt mid-await
            opened = fakeStream();
            return opened;
          },
        },
      },
    });
    try {
      await assert.rejects(() => openMicrophoneForClaim(claim), /claim lost/i);
      assert.equal(opened.track.readyState, "ended", "an orphaned capture stayed live");
    } finally {
      if (realNavigator) Object.defineProperty(globalThis, "navigator", realNavigator);
      else delete globalThis.navigator;
    }
  });
});

/* ── 9. route change, unmount and logout release capture ────────────────── */

describe("9 — route change, unmount and logout release capture", () => {
  it("the canonical provider releases on route change, unmount and logout", () => {
    const source = fRead("components/voice/VoiceRuntimeProvider.jsx");
    assert.ok(source.includes("usePathname()"), "no route-change release");
    assert.ok(/listeningPathRef\.current = pathname;\s*\n\s*hardReset\(\);/.test(source));
    assert.ok(source.includes("PLATFORM_CONTEXT_EVENT"), "no logout release");
    assert.ok(source.includes('forceReleaseInput("SESSION_CLOSE")'), "no terminal release");
  });

  it("the canonical session provider releases on route change and logout", () => {
    const source = fRead("components/voice/VoiceSessionProvider.jsx");
    assert.ok(source.includes('manager.interrupt("ROUTE_CHANGE")'));
    assert.ok(source.includes('manager.close("LOGOUT")'));
    assert.ok(source.includes('manager.close("SESSION_CLOSE")'));
  });

  it("settings capture releases on unmount, route change and logout", () => {
    const source = fRead("app/settings/voice/page.jsx");
    assert.ok(source.includes("PLATFORM_CONTEXT_EVENT"), "no logout release");
    assert.ok(/const cleanup = \(\) => \{[\s\S]{0,600}claim\?\.release\?\.\(\)/.test(source),
      "teardown must release the claim");
  });
});

/* ── 10/11/12. no unclaimed recorder, no speech-derived bypass ──────────── */

describe("10, 11 — no unclaimed recorder and no speech-derived bypass", () => {
  it("the legacy mobile recognizer and the recording hook are gone", () => {
    assert.ok(!existsSync(join(FRONTEND, "components/MobileMic.jsx")));
    assert.ok(!existsSync(join(FRONTEND, "lib/useVoice.js")));
    const offenders = PRODUCTION.filter((f) => /\buseVoice\b/.test(code(fRead(f))));
    assert.deepEqual(offenders, [], "the recording hook has a consumer again");
  });

  it("no production source can turn recognized speech into sendChat or sendVoice", () => {
    const offenders = PRODUCTION.filter((f) => {
      const source = code(fRead(f));
      const speech = Object.values(CAPTURE_PATTERNS).some((re) => re.test(source));
      return speech && /\bsendChat\s*\(|\bsendVoice\s*\(/.test(source);
    });
    assert.deepEqual(offenders, [], "a speech-derived bypass of the canonical pipeline is back");
  });

  it("no client wrapper for the legacy audio upload endpoint exists", () => {
    assert.ok(!/export async function sendVoice/.test(fRead("lib/api.js")));
    const offenders = PRODUCTION.filter((f) => /\/api\/v1\/voice\/command/.test(code(fRead(f))));
    assert.deepEqual(offenders, []);
  });
});

/* ── 13/14. retired route and legacy static documents ───────────────────── */

describe("13, 14 — retired and legacy documents cannot capture", () => {
  it("the retired /voice route resolves before any browser code runs", () => {
    const source = code(fRead("app/voice/page.jsx"));
    assert.ok(source.includes('redirect("/settings/voice")'));
    // The comment on that page explains it has no "use client"; only the real
    // directive counts, so this reads stripped code rather than raw source.
    assert.ok(!source.includes('"use client"'), "a client component could open a microphone");
    for (const api of Object.keys(CAPTURE_PATTERNS)) {
      assert.ok(!reaches("app/voice/page.jsx", api), `${api} is back on the retired route`);
    }
  });

  it("the legacy static client at the backend root cannot capture", () => {
    const source = code(readFileSync(join(REPO, "client", "index.html"), "utf8"));
    for (const [api, pattern] of Object.entries(CAPTURE_PATTERNS)) {
      assert.ok(!pattern.test(source), `${api} is back in the legacy static client`);
    }
    assert.ok(!/\/api\/v1\/voice\/command/.test(source),
      "the legacy client can still upload audio to the command endpoint");
  });

  it("records the one remaining unclaimed capture rather than hiding it", () => {
    // static/ielts/speaking-practice.html is a separate document served at the
    // backend's /ielts mount, so it cannot join this registry — a module
    // singleton does not span two page loads. It is a distinct product surface
    // with no SaathiOS command authority: it speaks only to the IELTS speaking
    // websocket. Removing it would remove the IELTS speaking lesson, which is
    // outside R2.1. It is therefore recorded, not silently claimed:
    //
    //   IELTS_STATIC_SPEAKING_PRACTICE_SEPARATE_DOCUMENT_CAPTURE_DEFERRED_TO_R3
    //
    // What must hold today is that it reaches no SaathiOS authority path.
    const source = code(readFileSync(join(REPO, "static", "ielts", "speaking-practice.html"), "utf8"));
    assert.ok(CAPTURE_PATTERNS.SpeechRecognition.test(source),
      "if this page stopped capturing, delete this test rather than weakening it");
    assert.ok(!/\/api\/v1\/voice\//.test(source), "it must not reach the voice command surface");
    assert.ok(!/\/api\/v1\/agent\//.test(source), "it must not reach the agent surface");
    assert.ok(!/\/api\/v1\/approvals?\//.test(source), "it must not reach approvals");
    assert.ok(/\/api\/v1\/ielts\/ws\/speaking\//.test(source), "its only channel is the IELTS lesson");

    const inventory = readFileSync(
      join(REPO, "docs", "evidence", "r2-1", "microphone-surfaces", "D6_CAPTURE_INVENTORY.md"),
      "utf8"
    );
    assert.ok(inventory.includes("static/ielts/speaking-practice.html"),
      "an unclaimed capture surface must stay in the published inventory");
  });
});

/* ── 15/16/17/18. bounded claims about what D6 achieved ─────────────────── */

describe("15, 16, 17, 18 — the surviving claims are the truthful ones", () => {
  it("the settings permission probe releases in finally", () => {
    const source = fRead("app/settings/voice/page.jsx");
    assert.ok(/\} finally \{[\s\S]{0,200}releaseInputClaim\(\);/.test(source));
  });

  it("the canonical dock is laid out for phone and desktop, and that is tested", () => {
    const dock = fRead("components/voice/VoiceRuntimeDock.jsx");
    assert.ok(dock.includes("@media (max-width: 699px)"), "no phone anchor");
    assert.ok(dock.includes("@media (max-width: 1023px)"), "no narrow-desktop anchor");
    assert.ok(dock.includes('aria-label="Real-time voice conversation"'));
    assert.ok(existsSync(join(FRONTEND, "lib/voice-dock-layout.test.js")),
      "the viewport certificate suite must exist");
  });

  it("records completed Central Command voice-surface convergence", () => {
    const inventory = readFileSync(
      join(REPO, "docs", "evidence", "r2-1", "microphone-surfaces", "D6_CAPTURE_INVENTORY.md"),
      "utf8"
    );
    assert.ok(/CENTRAL_COMMAND_VOICE_SURFACE_CONVERGENCE_COMPLETE/.test(inventory));
    assert.ok(!existsSync(join(FRONTEND, "components/chat/VoiceControl.jsx")));
    assert.doesNotMatch(fRead("components/chat/ChatWorkspace.jsx"), /VoiceControl|voiceEnabled|voiceOpen/);
  });
});
