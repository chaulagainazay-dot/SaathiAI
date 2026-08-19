// R2.1-S6 — the speaker-enrollment surface is retired.
//
// /voice recorded ~5 seconds of the owner's voice and told them it "unlocks
// owner actions"; /os carried the same button. The claim was false before the
// authority repair and is impossible after it, so the surfaces are removed
// rather than re-gated, and /voice redirects to the enrollment-free voice
// settings page.
//
// Source-contract tests in the style of lib/e2e-voice-route-cleanup.test.js:
// they pin the wiring. Backend behaviour (401 anonymous, 410 unavailable, no
// profile write) is covered by tests/test_r2_1_voice_enrollment_retired.py.
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const read = (rel) => readFileSync(new URL(`../${rel}`, import.meta.url), "utf8");

const voicePage = read("app/voice/page.jsx");
const voiceSettings = read("app/settings/voice/page.jsx");
const osPage = read("app/os/page.jsx");
const api = read("lib/api.js");
const missionsPage = read("app/missions/page.jsx");
const missionDashboard = read("app/missions/[id]/page.jsx");

const CAPTURE_APIS = ["getUserMedia", "MediaRecorder", "AudioContext", "createMediaStreamSource"];

describe("/voice redirects to the enrollment-free settings surface", () => {
  it("redirects to /settings/voice", () => {
    assert.ok(voicePage.includes('import { redirect } from "next/navigation"'));
    assert.ok(voicePage.includes('redirect("/settings/voice")'));
  });

  it("is a server component, so no browser code runs before the redirect", () => {
    // the directive, not the word — the file's own comment mentions it
    assert.ok(!/^\s*["']use client["']/m.test(voicePage),
      "a client component would execute before the redirect");
    assert.ok(!/useState|useEffect|useRef/.test(voicePage), "no client hooks");
  });

  it("opens no microphone during the redirect", () => {
    for (const api of CAPTURE_APIS) {
      assert.ok(!voicePage.includes(api), `/voice still references ${api}`);
    }
  });

  it("uploads no audio during the redirect", () => {
    assert.ok(!voicePage.includes("FormData"), "no upload body is built");
    assert.ok(!voicePage.includes("Blob("), "no audio blob is built");
    assert.ok(!/from "@\/lib\/api"/.test(voicePage), "the redirect needs no API client");
  });

  it("does not duplicate the mission list into the voice surface", () => {
    assert.ok(!voicePage.includes("fetchMissions"), "mission list must stay on /missions");
  });
});

describe("the redirect destination has no enrollment capture", () => {
  it("/settings/voice never posts to the enrollment endpoint", () => {
    assert.ok(!voiceSettings.includes("/api/v1/voice/enroll"));
    assert.ok(!voiceSettings.includes("enrollVoice"));
  });

  it("/settings/voice exposes no enrollment control", () => {
    assert.ok(!/enroll/i.test(voiceSettings), "no enrollment control or copy");
  });

  it("/settings/voice records no speaker sample", () => {
    assert.ok(!voiceSettings.includes("MediaRecorder"), "no recorder on the settings page");
  });
});

describe("Voice Studio stays reachable from /missions", () => {
  it("/missions opens each mission dashboard", () => {
    assert.ok(missionsPage.includes("fetchMissions"), "the mission list is still the read model");
    assert.ok(
      missionsPage.includes("router.push(`/missions/${m.id}`)"),
      "each mission card opens its dashboard"
    );
  });

  it("the mission dashboard links to that mission's Voice Studio", () => {
    assert.ok(
      missionDashboard.includes("`/missions/${id}/voice`"),
      "Voice Studio link missing from the mission dashboard"
    );
    assert.ok(/Voice/.test(missionDashboard), "the link is labelled");
  });

  it("the per-Mission Voice Studio route still exists", () => {
    const page = statSync(new URL("../app/missions/[id]/voice/page.jsx", import.meta.url));
    assert.ok(page.isFile());
  });
});

describe("no production frontend calls the retired endpoint", () => {
  const APP_DIR = new URL("../app/", import.meta.url).pathname;
  const LIB_DIR = new URL("../lib/", import.meta.url).pathname;
  const COMPONENTS_DIR = new URL("../components/", import.meta.url).pathname;

  const walk = (dir) => {
    const out = [];
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) out.push(...walk(full));
      else if (/\.(js|jsx|ts|tsx)$/.test(entry.name) && !entry.name.includes(".test.")) out.push(full);
    }
    return out;
  };

  const sources = [...walk(APP_DIR), ...walk(LIB_DIR), ...walk(COMPONENTS_DIR)];

  it("finds no call to /api/v1/voice/enroll", () => {
    const offenders = sources.filter((f) => {
      const text = readFileSync(f, "utf8");
      // a tombstone comment naming the retired route is allowed; a call is not
      return /(fetch|afetch)\([^)]*voice\/enroll/.test(text);
    });
    assert.deepEqual(offenders, [], "production source still calls the retired endpoint");
  });

  it("finds no enrollVoice client wrapper or consumer", () => {
    const offenders = sources.filter((f) =>
      /(^|[^/*\s])\benrollVoice\s*\(/.test(readFileSync(f, "utf8"))
    );
    assert.deepEqual(offenders, [], "enrollVoice is still called");
    assert.ok(!api.includes("export async function enrollVoice"), "the wrapper still exists");
  });

  it("/os no longer carries an enrollment button", () => {
    assert.ok(!osPage.includes("enrollVoice"));
    assert.ok(!/Teach Saathi my voice/.test(osPage));
    assert.ok(!/Voice enrolled/.test(osPage));
  });
});

describe("no active UI promises voice-based owner or admin access", () => {
  const CLAIMS = [
    /unlocks owner actions/i,
    /unlock privileged/i,
    /recognise you when you speak/i,
    /admin by voice/i,
    /verified as ajay/i,
  ];

  const walk = (dir) => {
    const out = [];
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) out.push(...walk(full));
      else if (/\.(js|jsx|ts|tsx)$/.test(entry.name) && !entry.name.includes(".test.")) out.push(full);
    }
    return out;
  };

  const sources = [
    ...walk(new URL("../app/", import.meta.url).pathname),
    ...walk(new URL("../components/", import.meta.url).pathname),
  ];

  for (const claim of CLAIMS) {
    it(`no source asserts ${claim}`, () => {
      const offenders = sources.filter((f) => claim.test(readFileSync(f, "utf8")));
      assert.deepEqual(offenders, [], `authority claim ${claim} is still shown to users`);
    });
  }
});

describe("the legacy static client is retired too", () => {
  const legacy = readFileSync(new URL("../../client/index.html", import.meta.url), "utf8");

  it("no longer posts audio to the enrollment endpoint", () => {
    assert.ok(!/fetch\([^)]*voice\/enroll/.test(legacy), "legacy client still uploads audio");
  });

  it("no longer records an enrollment sample", () => {
    assert.ok(!legacy.includes("_enrollRecorder"), "the guided recorder is still present");
    assert.ok(!legacy.includes("startEnroll()"), "the enrollment control is still wired");
  });

  it("no longer claims voice unlocks privileged tools", () => {
    assert.ok(!/unlock privileged tools/i.test(legacy));
  });

  it("says plainly that the capability is retired", () => {
    assert.ok(/Retired\./.test(legacy));
  });
});
