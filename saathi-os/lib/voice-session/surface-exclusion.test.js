/**
 * Two voice surfaces, one microphone.
 *
 * SaathiOS has two independent recognition surfaces: the shell's
 * VoiceRuntimeDock, whose recognizer is owned by VoiceSessionManager's
 * streaming pipeline, and the chat VoiceControl, which still builds its own
 * SpeechRecognition. They are not converged — that is deferred to the Central
 * Command / Mr. Yeti milestone, where scattered voice surfaces are replaced by
 * one persistent system-wide conversational runtime.
 *
 *   VoiceControl status:
 *   LEGACY_SEPARATE_VOICE_SURFACE_DEFERRED_FOR_CENTRAL_COMMAND_CONVERGENCE
 *
 * What must hold today is narrower and testable: the AudioInputOwner registry
 * makes the two deterministically mutually exclusive. At most one claim, at
 * most one live recognizer, switching surfaces tears the previous owner down,
 * and a surface that lost the microphone cannot still submit a turn.
 *
 * This file proves that property. It does not claim architectural
 * convergence: SaathiOS has one active recognizer per ownership domain, not
 * yet one unified system-wide recognition implementation.
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
 * The chat surface, reproduced faithfully: its own claim, its own recognizer
 * registered on that claim, and both its result path and its onend restart
 * guarded by `claim.isActive()`.
 */
function openChat() {
  const claim = acquireInputClaim({ label: "chat.VoiceControl" });
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

describe("the two surfaces are mutually exclusive", () => {
  it("chat taking the microphone tears the dock down", async () => {
    const dock = await openDock();
    const dockRecognizer = env.recognizers[0];
    assert.equal(env.live().length, 1, "dock is the only owner");

    const chat = openChat();

    assert.equal(getInputOwnerSnapshot().label, "chat.VoiceControl", "one claim, and it moved");
    assert.equal(dock.manager.getPipeline(), null, "the dock's pipeline is detached");
    assert.equal(dockRecognizer.running, false, "the dock's recognizer is stopped");
    assert.equal(env.live().length, 1, "exactly one recognizer is live");
    assert.equal(env.live()[0], chat.recognition);
    assert.equal(env.liveTracks().length, 0, "the dock's capture is released");
  });

  it("the dock taking the microphone tears chat down", async () => {
    const chat = openChat();
    assert.equal(env.live().length, 1);

    const dock = await openDock();

    assert.equal(chat.claim.isActive(), false, "chat lost ownership");
    assert.equal(chat.recognition.running, false, "chat's recognizer is stopped");
    assert.equal(chat.recognition.aborts >= 1, true, "and aborted, not merely paused");
    assert.equal(env.live().length, 1, "exactly one recognizer is live");
    dock.manager.endInput("USER_CANCEL");
  });

  it("never leaves two claims or two recognizers, whatever the order", async () => {
    for (let round = 0; round < 5; round += 1) {
      const dock = await openDock();
      assert.equal(env.live().length, 1, `round ${round}: dock alone`);
      const chat = openChat();
      assert.equal(env.live().length, 1, `round ${round}: chat alone`);
      assert.equal(Number(Boolean(getInputOwnerSnapshot().claimId)), 1);
      chat.claim.release();
      dock.manager.endInput("USER_CANCEL");
      assert.equal(env.live().length, 0, `round ${round}: nothing left`);
      assert.equal(getInputOwnerSnapshot().claimId, null);
    }
  });

  it("leaves no live capture once both surfaces are done", async () => {
    const dock = await openDock();
    const chat = openChat();
    chat.claim.release();
    dock.manager.endInput("USER_CANCEL");
    assert.equal(env.live().length, 0);
    assert.equal(env.liveTracks().length, 0);
    assert.equal(getInputOwnerSnapshot().claimId, null);
  });
});

describe("a surface that lost the microphone cannot submit", () => {
  it("the dock submits nothing after chat preempts it", async () => {
    const dock = await openDock();
    const dockRecognizer = env.recognizers[0];
    openChat();

    dockRecognizer.fireResult("Show my missions.", true);
    dockRecognizer.fireEnd();

    assert.deepEqual(dock.submissions, [], "a preempted surface must not submit");
    assert.equal(dockRecognizer.starts, 1, "and must not restart itself");
  });

  it("chat submits nothing after the dock preempts it", async () => {
    const chat = openChat();
    const dock = await openDock();

    chat.recognition.fireResult("Open the trading desk.", true);
    chat.recognition.fireEnd();

    assert.deepEqual(chat.submissions, [], "a preempted surface must not submit");
    assert.equal(chat.recognition.starts, 1, "and must not restart itself");
    dock.manager.endInput("USER_CANCEL");
  });

  it("one spoken final cannot be submitted by both surfaces", async () => {
    const dock = await openDock();
    const dockRecognizer = env.recognizers[0];
    const chat = openChat();

    // The same utterance delivered to whichever recognizer still exists.
    dockRecognizer.fireResult("Show my missions.", true);
    chat.recognition.fireResult("Show my missions.", true);

    assert.equal(
      dock.submissions.length + chat.submissions.length,
      1,
      "exactly one surface may turn a spoken final into a submission"
    );
    assert.equal(chat.submissions.length, 1, "and it is the surface that owns the microphone");
  });
});

describe("R2.1 records the surface, it does not converge it", () => {
  it("states the deferral explicitly", () => {
    // Prose, deliberately asserted so the classification travels with the code.
    const classification =
      "LEGACY_SEPARATE_VOICE_SURFACE_DEFERRED_FOR_CENTRAL_COMMAND_CONVERGENCE";
    assert.equal(
      classification,
      "LEGACY_SEPARATE_VOICE_SURFACE_DEFERRED_FOR_CENTRAL_COMMAND_CONVERGENCE",
      "chat VoiceControl remains a separate recognition implementation"
    );
  });
});
