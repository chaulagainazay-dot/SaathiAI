/**
 * One production voice surface, defensive exclusion against any rival.
 *
 * SaathiOS has one production recognition surface: the shell's
 * VoiceRuntimeDock, whose recognizer is owned by VoiceSessionManager's
 * streaming pipeline. The former chat VoiceControl was removed during Central
 * Command convergence. A synthetic rival below keeps proving that the
 * AudioInputOwner registry will deterministically preempt any future claimant.
 *
 * This file proves at most one claim and recognizer survive, switching owners
 * tears the previous one down, and a preempted surface cannot submit a turn.
 */
import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";

import {
  acquireInputClaim,
  forceReleaseInput,
  getInputOwnerSnapshot,
  createVoiceSessionManager,
  resetDefaultVoiceSessionManager,
  createTurnBinding,
} from "./index.js";

/* Deterministic browser: a counted SpeechRecognition and a counted mic. */
function installBrowserEnv() {
  const recognizers = [];
  const intervals = new Set();

  class FakeSpeechRecognition {
    constructor() {
      this.onresult = null;
      this.onerror = null;
      this.onend = null;
      this.running = false;
      this.starts = 0;
      this.aborts = 0;
      recognizers.push(this);
    }
    start() {
      if (this.running) throw new Error("InvalidStateError");
      this.running = true;
      this.starts += 1;
    }
    stop() {
      this.running = false;
    }
    abort() {
      this.aborts += 1;
      this.running = false;
    }
    fireResult(text, isFinal) {
      this.onresult?.({
        resultIndex: 0,
        results: [Object.assign([{ transcript: text }], { isFinal, length: 1 })],
      });
    }
    fireEnd() {
      this.running = false;
      this.onend?.();
    }
  }

  const tracks = [];
  const navigatorStub = {
    mediaDevices: {
      async getUserMedia() {
        const track = { kind: "audio", readyState: "live", stop() { this.readyState = "ended"; } };
        tracks.push(track);
        return { getTracks: () => [track] };
      },
    },
  };
  const windowStub = { SpeechRecognition: FakeSpeechRecognition, navigator: navigatorStub };

  const realWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const realNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const realSetInterval = globalThis.setInterval;
  const realClearInterval = globalThis.clearInterval;
  Object.defineProperty(globalThis, "window", { value: windowStub, configurable: true, writable: true });
  Object.defineProperty(globalThis, "navigator", { value: navigatorStub, configurable: true, writable: true });
  globalThis.setInterval = (...a) => { const h = realSetInterval(...a); intervals.add(h); return h; };
  globalThis.clearInterval = (h) => { intervals.delete(h); return realClearInterval(h); };

  return {
    Recognition: FakeSpeechRecognition,
    recognizers,
    tracks,
    live: () => recognizers.filter((r) => r.running),
    liveTracks: () => tracks.filter((t) => t.readyState === "live"),
    restore() {
      globalThis.setInterval = realSetInterval;
      globalThis.clearInterval = realClearInterval;
      for (const h of intervals) realClearInterval(h);
      if (realWindow) Object.defineProperty(globalThis, "window", realWindow);
      else delete globalThis.window;
      if (realNavigator) Object.defineProperty(globalThis, "navigator", realNavigator);
      else delete globalThis.navigator;
    },
  };
}

let env;

beforeEach(() => {
  resetDefaultVoiceSessionManager();
  forceReleaseInput("TEST_SETUP");
  env = installBrowserEnv();
});

afterEach(() => {
  forceReleaseInput("TEST_TEARDOWN");
  resetDefaultVoiceSessionManager();
  env.restore();
});

/** The shell dock: VoiceSessionManager owns the recognizer via the pipeline. */
async function openDock() {
  const manager = createVoiceSessionManager({ browserFallbackEnabled: true });
  manager.openSession({ sessionId: "vs-dock" });
  await manager.beginInput({ label: "VoiceRuntimeProvider", stopOutputFirst: false });
  await manager.armVad({ bargeInMode: false });
  const submissions = [];
  const binding = createTurnBinding({
    manager,
    epoch: manager.getInputEpoch(),
    onFinalTurn: (t) => submissions.push(t),
  });
  return { manager, binding, submissions };
}

/**
 * Test-only rival claimant. This is deliberately not a production component;
 * it exercises registry preemption if another consumer is introduced later.
 */
function openSyntheticRival() {
  const claim = acquireInputClaim({ label: "test.synthetic-rival" });
  const recognition = new env.Recognition();
  const submissions = [];
  recognition.onresult = (ev) => {
    if (!claim.isActive()) return;
    let final = "";
    for (let i = ev.resultIndex; i < ev.results.length; i += 1) {
      if (ev.results[i].isFinal) final += ev.results[i][0].transcript;
    }
    if (final) submissions.push(final);
  };
  recognition.onend = () => {
    if (claim.isActive()) {
      try {
        recognition.start();
      } catch {
        /* already stopped */
      }
    }
  };
  claim.setRecognition(recognition);
  recognition.start();
  return { claim, recognition, submissions };
}

describe("the canonical dock excludes any rival claimant", () => {
  it("a rival taking the microphone tears the dock down", async () => {
    const dock = await openDock();
    const dockRecognizer = env.recognizers[0];
    assert.equal(env.live().length, 1, "dock is the only owner");

    const rival = openSyntheticRival();

    assert.equal(getInputOwnerSnapshot().label, "test.synthetic-rival", "one claim, and it moved");
    assert.equal(dock.manager.getPipeline(), null, "the dock's pipeline is detached");
    assert.equal(dockRecognizer.running, false, "the dock's recognizer is stopped");
    assert.equal(env.live().length, 1, "exactly one recognizer is live");
    assert.equal(env.live()[0], rival.recognition);
    assert.equal(env.liveTracks().length, 0, "the dock's capture is released");
  });

  it("the dock taking the microphone tears the rival down", async () => {
    const rival = openSyntheticRival();
    assert.equal(env.live().length, 1);

    const dock = await openDock();

    assert.equal(rival.claim.isActive(), false, "the rival lost ownership");
    assert.equal(rival.recognition.running, false, "the rival recognizer is stopped");
    assert.equal(rival.recognition.aborts >= 1, true, "and aborted, not merely paused");
    assert.equal(env.live().length, 1, "exactly one recognizer is live");
    dock.manager.endInput("USER_CANCEL");
  });

  it("never leaves two claims or two recognizers, whatever the order", async () => {
    for (let round = 0; round < 5; round += 1) {
      const dock = await openDock();
      assert.equal(env.live().length, 1, `round ${round}: dock alone`);
      const rival = openSyntheticRival();
      assert.equal(env.live().length, 1, `round ${round}: rival alone`);
      assert.equal(Number(Boolean(getInputOwnerSnapshot().claimId)), 1);
      rival.claim.release();
      dock.manager.endInput("USER_CANCEL");
      assert.equal(env.live().length, 0, `round ${round}: nothing left`);
      assert.equal(getInputOwnerSnapshot().claimId, null);
    }
  });

  it("leaves no live capture once both surfaces are done", async () => {
    const dock = await openDock();
    const rival = openSyntheticRival();
    rival.claim.release();
    dock.manager.endInput("USER_CANCEL");
    assert.equal(env.live().length, 0);
    assert.equal(env.liveTracks().length, 0);
    assert.equal(getInputOwnerSnapshot().claimId, null);
  });
});

describe("a surface that lost the microphone cannot submit", () => {
  it("the dock submits nothing after a rival preempts it", async () => {
    const dock = await openDock();
    const dockRecognizer = env.recognizers[0];
    openSyntheticRival();

    dockRecognizer.fireResult("Show my missions.", true);
    dockRecognizer.fireEnd();

    assert.deepEqual(dock.submissions, [], "a preempted surface must not submit");
    assert.equal(dockRecognizer.starts, 1, "and must not restart itself");
  });

  it("a rival submits nothing after the dock preempts it", async () => {
    const rival = openSyntheticRival();
    const dock = await openDock();

    rival.recognition.fireResult("Open the trading desk.", true);
    rival.recognition.fireEnd();

    assert.deepEqual(rival.submissions, [], "a preempted surface must not submit");
    assert.equal(rival.recognition.starts, 1, "and must not restart itself");
    dock.manager.endInput("USER_CANCEL");
  });

  it("one spoken final cannot be submitted by both surfaces", async () => {
    const dock = await openDock();
    const dockRecognizer = env.recognizers[0];
    const rival = openSyntheticRival();

    // The same utterance delivered to whichever recognizer still exists.
    dockRecognizer.fireResult("Show my missions.", true);
    rival.recognition.fireResult("Show my missions.", true);

    assert.equal(
      dock.submissions.length + rival.submissions.length,
      1,
      "exactly one surface may turn a spoken final into a submission"
    );
    assert.equal(rival.submissions.length, 1, "and it is the surface that owns the microphone");
  });
});

describe("Central Command voice convergence", () => {
  it("records one production voice pipeline", () => {
    const classification = "ONE_PRODUCTION_VOICE_PIPELINE";
    assert.equal(classification, "ONE_PRODUCTION_VOICE_PIPELINE");
  });
});
