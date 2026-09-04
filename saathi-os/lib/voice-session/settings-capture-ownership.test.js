/**
 * R2.1-D6.5 — /settings/voice borrows the microphone, it does not own it.
 *
 * The voice settings page runs two real capture operations: a transient
 * permission probe and a bounded diagnostic recognition test. Before D6.5 both
 * called `getUserMedia` directly and kept their own stream reference, so the
 * AudioInputOwner registry could neither see them nor stop them — the settings
 * page and the canonical dock could hold the microphone at the same time.
 *
 * Both now take a claim. This file proves the resulting protocol the way
 * surface-exclusion.test.js proves the dock against a synthetic future rival:
 * a faithful reproduction of the page's capture protocol against a
 * deterministic browser, plus source assertions binding that reproduction to
 * the page that actually ships.
 *
 * What it does not prove: anything about a physical microphone, recognition
 * accuracy, or what a real browser does with a permission prompt.
 */
import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  acquireInputClaim,
  forceReleaseInput,
  getInputOwnerSnapshot,
  openMicrophoneForClaim,
  subscribeInputOwner,
} from "./index.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const PAGE = readFileSync(
  join(HERE, "..", "..", "app", "settings", "voice", "page.jsx"),
  "utf8"
);

/* ── deterministic browser ─────────────────────────────────────────────── */

function installBrowserEnv({ failMic = null } = {}) {
  const recognizers = [];
  const tracks = [];

  class FakeSpeechRecognition {
    constructor() {
      this.onresult = null;
      this.onerror = null;
      this.onend = null;
      this.onstart = null;
      this.running = false;
      this.starts = 0;
      this.aborts = 0;
      recognizers.push(this);
    }
    start() {
      if (this.running) throw new Error("InvalidStateError");
      this.running = true;
      this.starts += 1;
      this.onstart?.();
    }
    stop() { this.running = false; }
    abort() { this.aborts += 1; this.running = false; }
    fireResult(text) {
      this.onresult?.({
        resultIndex: 0,
        results: [Object.assign([{ transcript: text }], { isFinal: true, length: 1 })],
      });
    }
    fireError(code) { this.onerror?.({ error: code }); }
    fireEnd() { this.running = false; this.onend?.(); }
  }

  const navigatorStub = {
    permissions: { query: async () => ({ state: "prompt", onchange: null }) },
    mediaDevices: {
      async getUserMedia() {
        if (failMic) {
          const err = new Error(failMic.message);
          err.name = failMic.name;
          throw err;
        }
        const track = {
          kind: "audio",
          readyState: "live",
          stop() { this.readyState = "ended"; },
          getSettings: () => ({
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
            deviceId: "SECRET-DEVICE-ID",
            label: "Ajay's Studio Microphone",
          }),
        };
        tracks.push(track);
        return { getTracks: () => [track], getAudioTracks: () => [track] };
      },
    },
  };
  const windowStub = { SpeechRecognition: FakeSpeechRecognition, navigator: navigatorStub };
  const realWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const realNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  Object.defineProperty(globalThis, "window", { value: windowStub, configurable: true, writable: true });
  Object.defineProperty(globalThis, "navigator", { value: navigatorStub, configurable: true, writable: true });

  return {
    Recognition: FakeSpeechRecognition,
    recognizers,
    live: () => recognizers.filter((r) => r.running),
    liveTracks: () => tracks.filter((t) => t.readyState === "live"),
    restore() {
      if (realWindow) Object.defineProperty(globalThis, "window", realWindow);
      else delete globalThis.window;
      if (realNavigator) Object.defineProperty(globalThis, "navigator", realNavigator);
      else delete globalThis.navigator;
    },
  };
}

/* ── the settings page's capture protocol, reproduced ──────────────────── */

/**
 * One page instance. `status` and `transcript` stand in for the page's
 * `inputStatus` / `transcript` React state; `unsubscribe` stands in for the
 * effect that watches for preemption; `unmount` stands in for its teardown.
 */
function mountSettingsPage(env) {
  const page = {
    status: "Microphone is off.",
    permission: "unknown",
    transcript: "",
    claim: null,
    recognition: null,
    stream: null,
    submissions: [],      // must stay empty: the test never submits a command
    backendSessions: [],  // must stay empty: the test never opens a session
  };

  const stopTracks = () => {
    page.stream?.getTracks?.().forEach((t) => t.stop());
    page.stream = null;
  };
  const releaseInputClaim = () => {
    const claim = page.claim;
    page.claim = null;
    try { claim?.release?.(); } catch { /* already released */ }
    stopTracks();
  };

  page.stopInput = () => {
    try { page.recognition?.stop?.(); } catch { /* already stopped */ }
    page.recognition = null;
    releaseInputClaim();
    page.status = "Microphone is off.";
  };

  page.requestPermission = async () => {
    const claim = acquireInputClaim({ label: "settings.voice.permission-probe" });
    page.claim = claim;
    try {
      const stream = await openMicrophoneForClaim(claim);
      page.stream = stream;
      const applied = stream.getAudioTracks()[0]?.getSettings?.() || {};
      const flags = ["echoCancellation", "noiseSuppression", "autoGainControl"]
        .filter((key) => applied[key] === true);
      page.permission = "granted";
      page.status = `Microphone permission granted. Capture remains off. Browser applied: ${flags.join(", ")}.`;
    } catch (error) {
      const denied = /denied|not.?allowed|permission/i.test(String(error?.name || error?.message || ""));
      page.permission = denied ? "denied" : "unknown";
      page.status = denied
        ? "Microphone permission was denied. Text fallback remains available."
        : "The microphone could not be opened. Text fallback remains available.";
    } finally {
      releaseInputClaim();
    }
  };

  page.startInput = async () => {
    let claim = null;
    try {
      page.stopInput();
      claim = acquireInputClaim({ label: "settings.voice.input-test" });
      page.claim = claim;
      page.stream = await openMicrophoneForClaim(claim);
      page.permission = "granted";
      const recognition = new env.Recognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.onstart = () => { page.status = "Listening. Choose Stop microphone test at any time."; };
      recognition.onresult = (event) => {
        if (!claim?.isActive?.()) return;
        let text = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          text += event.results[i][0]?.transcript || "";
        }
        page.transcript = text;
        page.status = "Transcript preview updated in memory only.";
      };
      recognition.onerror = (event) => {
        page.status = `Microphone test failed safely: ${event.error || "recognition error"}.`;
        page.recognition = null;
        releaseInputClaim();
      };
      recognition.onend = () => {
        page.recognition = null;
        releaseInputClaim();
        if (!page.status.startsWith("Microphone test failed")) page.status = "Microphone test ended.";
      };
      claim.setRecognition(recognition);
      page.recognition = recognition;
      recognition.start();
    } catch {
      page.permission = "denied";
      page.recognition = null;
      releaseInputClaim();
      page.status = "Microphone permission was denied or capture could not start. Text fallback remains available.";
    }
  };

  page.unsubscribe = subscribeInputOwner(() => {
    const claim = page.claim;
    if (!claim || claim.isActive()) return;
    page.claim = null;
    page.recognition = null;
    stopTracks();
    page.status = "Microphone test ended: another voice surface took the microphone.";
  });

  page.unmount = () => {
    page.unsubscribe();
    try { page.recognition?.stop?.(); } catch { /* already stopped */ }
    page.recognition = null;
    releaseInputClaim();
  };

  return page;
}

/** A stand-in for whichever other surface takes the microphone. */
function openRivalSurface(env, label) {
  const claim = acquireInputClaim({ label });
  const recognition = new env.Recognition();
  claim.setRecognition(recognition);
  recognition.start();
  return { claim, recognition };
}

let env;

beforeEach(() => {
  forceReleaseInput("TEST_SETUP");
  env = installBrowserEnv();
});

afterEach(() => {
  forceReleaseInput("TEST_TEARDOWN");
  env.restore();
});

describe("the permission probe is transient", () => {
  it("opens the device, observes bounded settings, and hands it straight back", async () => {
    const page = mountSettingsPage(env);
    await page.requestPermission();

    assert.equal(page.permission, "granted");
    assert.equal(env.liveTracks().length, 0, "the probe must not leave a track open");
    assert.equal(getInputOwnerSnapshot().claimId, null, "input ownership must return to idle");
    assert.match(page.status, /echoCancellation, noiseSuppression, autoGainControl/);
    page.unmount();
  });

  it("publishes no device identifier or device label", async () => {
    const page = mountSettingsPage(env);
    await page.requestPermission();
    assert.ok(!/SECRET-DEVICE-ID/.test(page.status), "a device id reached the UI");
    assert.ok(!/Ajay's Studio Microphone/.test(page.status), "a device label reached the UI");
    page.unmount();
  });

  it("releases the claim when permission is denied", async () => {
    env.restore();
    env = installBrowserEnv({ failMic: { name: "NotAllowedError", message: "Permission denied" } });
    const page = mountSettingsPage(env);
    await page.requestPermission();

    assert.equal(page.permission, "denied");
    assert.match(page.status, /permission was denied/i);
    assert.equal(getInputOwnerSnapshot().claimId, null, "a denial must not strand the claim");
    page.unmount();
  });

  it("releases the claim when the device itself fails", async () => {
    env.restore();
    env = installBrowserEnv({ failMic: { name: "NotReadableError", message: "Device in use" } });
    const page = mountSettingsPage(env);
    await page.requestPermission();

    assert.equal(page.permission, "unknown", "a device failure is not a denial");
    assert.match(page.status, /could not be opened/i);
    assert.equal(getInputOwnerSnapshot().claimId, null);
    page.unmount();
  });
});

describe("the diagnostic input test is claimed and bounded", () => {
  it("holds exactly one claim and one recognizer while running", async () => {
    const page = mountSettingsPage(env);
    await page.startInput();

    assert.equal(getInputOwnerSnapshot().label, "settings.voice.input-test");
    assert.equal(env.live().length, 1, "exactly one recognizer");
    assert.equal(env.liveTracks().length, 1, "exactly one capture");
    page.unmount();
  });

  it("never continues and never restarts itself", async () => {
    const page = mountSettingsPage(env);
    await page.startInput();
    assert.equal(page.recognition.continuous, false, "a diagnostic must not run continuously");

    const recognizer = page.recognition;
    recognizer.fireEnd();

    assert.equal(recognizer.starts, 1, "the bounded test must not restart");
    assert.equal(env.live().length, 0);
    assert.equal(getInputOwnerSnapshot().claimId, null, "a completed test releases");
    page.unmount();
  });

  it("keeps the transcript ephemeral and submits nothing", async () => {
    const page = mountSettingsPage(env);
    await page.startInput();
    page.recognition.fireResult("Approve the AI Studio campaign.");

    assert.equal(page.transcript, "Approve the AI Studio campaign.");
    assert.deepEqual(page.submissions, [], "a settings test must not submit a command");
    assert.deepEqual(page.backendSessions, [], "a settings test must not open a voice session");
    page.unmount();
  });

  it("releases on an explicit stop", async () => {
    const page = mountSettingsPage(env);
    await page.startInput();
    page.stopInput();

    assert.equal(env.live().length, 0);
    assert.equal(env.liveTracks().length, 0);
    assert.equal(getInputOwnerSnapshot().claimId, null);
    assert.equal(page.status, "Microphone is off.");
    page.unmount();
  });

  it("releases on a recognition error", async () => {
    const page = mountSettingsPage(env);
    await page.startInput();
    page.recognition.fireError("audio-capture");

    assert.match(page.status, /failed safely: audio-capture/);
    assert.equal(getInputOwnerSnapshot().claimId, null);
    assert.equal(env.liveTracks().length, 0);
    page.unmount();
  });

  it("releases on unmount, which is also the route-change path", async () => {
    const page = mountSettingsPage(env);
    await page.startInput();
    page.unmount();

    assert.equal(env.live().length, 0, "navigating away must not leave a recognizer running");
    assert.equal(env.liveTracks().length, 0, "navigating away must not leave the mic hot");
    assert.equal(getInputOwnerSnapshot().claimId, null);
  });
});

describe("settings capture is mutually exclusive with the other surfaces", () => {
  for (const rival of ["VoiceRuntimeProvider", "test.synthetic-rival"]) {
    it(`${rival} taking the microphone tears the settings test down`, async () => {
      const page = mountSettingsPage(env);
      await page.startInput();
      const settingsRecognizer = page.recognition;

      const other = openRivalSurface(env, rival);

      assert.equal(getInputOwnerSnapshot().label, rival, "one claim, and it moved");
      assert.equal(settingsRecognizer.running, false, "the settings recognizer is stopped");
      assert.equal(settingsRecognizer.aborts >= 1, true, "and aborted, not merely paused");
      assert.equal(env.live().length, 1, "exactly one recognizer is live");
      assert.equal(env.live()[0], other.recognition);
      assert.equal(env.liveTracks().length, 0, "the settings capture is released");
      assert.match(page.status, /another voice surface took the microphone/);

      other.claim.release();
      page.unmount();
    });

    it(`the settings test taking the microphone tears ${rival} down`, async () => {
      const other = openRivalSurface(env, rival);
      const page = mountSettingsPage(env);
      await page.startInput();

      assert.equal(other.claim.isActive(), false, `${rival} lost ownership`);
      assert.equal(other.recognition.running, false, `${rival}'s recognizer is stopped`);
      assert.equal(env.live().length, 1, "exactly one recognizer is live");
      assert.equal(getInputOwnerSnapshot().label, "settings.voice.input-test");
      page.unmount();
    });
  }

  it("a preempted settings test cannot still update its transcript", async () => {
    const page = mountSettingsPage(env);
    await page.startInput();
    const settingsRecognizer = page.recognition;

    const other = openRivalSurface(env, "VoiceRuntimeProvider");
    settingsRecognizer.fireResult("Sell everything.");

    assert.equal(page.transcript, "", "a surface that lost the microphone must publish nothing");
    other.claim.release();
    page.unmount();
  });

  it("leaves nothing capturing however the two are interleaved", async () => {
    for (let round = 0; round < 5; round += 1) {
      const page = mountSettingsPage(env);
      await page.startInput();
      const other = openRivalSurface(env, "test.synthetic-rival");
      assert.equal(env.live().length, 1, `round ${round}: exactly one live recognizer`);
      await page.requestPermission();
      assert.equal(env.live().length, 0, `round ${round}: the probe preempted and released`);
      other.claim.release();
      page.unmount();
      assert.equal(getInputOwnerSnapshot().claimId, null, `round ${round}: idle`);
      assert.equal(env.liveTracks().length, 0, `round ${round}: no live track`);
    }
  });
});

describe("the shipped page matches this protocol", () => {
  it("takes a labelled claim for each of its two capture operations", () => {
    assert.ok(PAGE.includes('acquireInputClaim({ label: "settings.voice.permission-probe" })'));
    assert.ok(PAGE.includes('acquireInputClaim({ label: "settings.voice.input-test" })'));
  });

  it("opens the microphone only through the claim", () => {
    assert.ok(!/navigator\.mediaDevices\.getUserMedia\(/.test(PAGE),
      "settings capture must not call getUserMedia directly");
    assert.equal((PAGE.match(/openMicrophoneForClaim\(claim\)/g) || []).length, 2);
  });

  it("releases in finally, on stop, on error, on end, and on teardown", () => {
    assert.ok(/\} finally \{\s*\n\s*\/\/[^\n]*\n\s*releaseInputClaim\(\);/.test(PAGE),
      "the probe must release in finally");
    assert.equal((PAGE.match(/releaseInputClaim\(\);/g) || []).length >= 5, true);
    assert.ok(/const claim = inputClaimRef\.current;\s*\n\s*inputClaimRef\.current = null;\s*\n\s*try \{ claim\?\.release\?\.\(\); \}/.test(PAGE),
      "unmount / route change / logout cleanup must release the claim");
  });

  it("registers the recognizer on the claim and guards results on it", () => {
    assert.ok(PAGE.includes("claim.setRecognition(recognition)"));
    assert.ok(PAGE.includes('if (!claim?.isActive?.()) return;'));
  });

  it("watches for preemption instead of assuming it keeps the microphone", () => {
    assert.ok(PAGE.includes("subscribeInputOwner("));
    assert.ok(PAGE.includes("another voice surface took the microphone"));
  });

  it("stays a diagnostic: no submission, no backend session, no API call at all", () => {
    assert.ok(/recognition\.continuous = false/.test(PAGE));
    assert.ok(!/onend[\s\S]{0,120}recognition\.start\(\)/.test(PAGE), "no self-restart");
    assert.equal(/\bfetch\s*\(|\bafetch\s*\(|API_BASE/.test(PAGE), false);
  });
});
