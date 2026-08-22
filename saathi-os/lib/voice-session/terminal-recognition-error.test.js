/**
 * R2.1-D9 — a recognition error that cannot be recovered from must end the
 * whole attempt, not just get printed.
 *
 * Physical Test A produced the failure this file pins. The microphone worked:
 * RMS reached 0.0614 against a 0.0180 threshold, VAD moved silence -> speech,
 * and the tap counted 7465 frames. Chrome's speech service was unreachable, so
 * `onerror("network")` fired — and the only thing that happened was
 * `setError()` publishing a string. `network` was not classified fatal, so the
 * adapter's `onend` restarted the recognizer, forever, with no console error.
 * The claim stayed held, the tap and VAD kept running, and the backend session
 * stayed LISTENING because nothing ever called `POST /finish`.
 *
 * These tests drive the real browser adapter through a fake SpeechRecognition.
 * They prove the lifecycle ends. They prove nothing about transcription: with
 * the speech service unreachable there is no transcript, and none is invented.
 */
import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";

import {
  createVoiceSessionManager,
  resetDefaultVoiceSessionManager,
  forceReleaseInput,
  getInputOwnerSnapshot,
} from "./index.js";

/* ------------------------------------------------------------------ */
/* deterministic browser environment                                    */
/* ------------------------------------------------------------------ */

function installBrowserEnv() {
  const recognizers = [];
  const tracks = [];
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
      // Chromium dispatches onend from abort(); the adapter's restart path
      // lives there, so the re-entrancy is part of what is under test.
      this.onend?.();
    }
    fireResult(text, isFinal) {
      this.onresult?.({
        resultIndex: 0,
        results: [Object.assign([{ transcript: text }], { isFinal, length: 1 })],
      });
    }
    fireError(code) {
      this.onerror?.({ error: code });
    }
    fireEnd() {
      this.onend?.();
    }
  }

  const navigatorStub = {
    mediaDevices: {
      async getUserMedia() {
        const track = {
          kind: "audio",
          readyState: "live",
          stop() {
            this.readyState = "ended";
          },
        };
        tracks.push(track);
        return { getTracks: () => [track] };
      },
    },
  };
  const windowStub = { navigator: navigatorStub, SpeechRecognition: FakeSpeechRecognition };

  const realWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const realNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const realSetInterval = globalThis.setInterval;
  const realClearInterval = globalThis.clearInterval;

  Object.defineProperty(globalThis, "window", { value: windowStub, configurable: true, writable: true });
  Object.defineProperty(globalThis, "navigator", { value: navigatorStub, configurable: true, writable: true });
  globalThis.setInterval = (...args) => {
    const handle = realSetInterval(...args);
    intervals.add(handle);
    return handle;
  };
  globalThis.clearInterval = (handle) => {
    intervals.delete(handle);
    return realClearInterval(handle);
  };

  return {
    recognizers,
    tracks,
    liveRecognizers: () => recognizers.filter((r) => r.running),
    liveTracks: () => tracks.filter((t) => t.readyState === "live"),
    openIntervals: () => intervals.size,
    restore() {
      globalThis.setInterval = realSetInterval;
      globalThis.clearInterval = realClearInterval;
      for (const handle of intervals) realClearInterval(handle);
      intervals.clear();
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
  env?.restore();
  env = null;
});

/** A manager holding the microphone with a live streaming pipeline. */
async function listening(sessionId = "vs-d9") {
  const manager = createVoiceSessionManager({ browserFallbackEnabled: true });
  manager.openSession({ sessionId });
  await manager.beginInput({ label: "d9", stopOutputFirst: false });
  return manager;
}

/** Record every terminal-input notification the provider would receive. */
function watchTerminal(manager) {
  const events = [];
  const unsubscribe = manager.onTerminalInput((ev) => events.push(ev));
  return { events, unsubscribe };
}

/* ------------------------------------------------------------------ */
/* the fault is terminal, published once, and survives cleanup           */
/* ------------------------------------------------------------------ */

describe("a network fault ends the recognition attempt", () => {
  it("marks the epoch terminal", async () => {
    const manager = await listening();
    const epoch = manager.getInputEpoch();
    env.recognizers[0].fireError("network");
    assert.equal(manager.getTerminalInputEpoch(), epoch);
  });

  it("publishes the bounded category exactly once", async () => {
    const manager = await listening();
    const published = [];
    manager.subscribe((snap) => {
      if (snap.error) published.push(snap.error);
    });
    published.length = 0;

    env.recognizers[0].fireError("network");

    assert.deepEqual(published, ["network"], "one fault, one publication");
  });

  it("keeps the fault visible after cleanup finishes", async () => {
    const manager = await listening();
    env.recognizers[0].fireError("network");
    await manager.whenInputPipelineStopped();
    assert.equal(manager.getSnapshot().error, "network");
  });

  it("publishes no raw error object", async () => {
    const manager = await listening();
    env.recognizers[0].fireError("network");
    assert.equal(typeof manager.getSnapshot().error, "string");
  });
});

/* ------------------------------------------------------------------ */
/* the restart window closes synchronously                              */
/* ------------------------------------------------------------------ */

describe("the recognizer cannot restart itself", () => {
  it("stops the recognizer before the error call returns", async () => {
    const manager = await listening();
    env.recognizers[0].fireError("network");
    // Synchronous assertion on purpose: awaiting first would hide a restart
    // that won the race inside the same tick.
    assert.equal(env.liveRecognizers().length, 0);
  });

  it("ignores an onend arriving after the fault", async () => {
    const manager = await listening();
    const rec = env.recognizers[0];
    rec.fireError("network");
    rec.fireEnd();
    rec.fireEnd();
    assert.equal(env.recognizers.length, 1, "onend must not construct a recognizer");
    assert.equal(env.liveRecognizers().length, 0, "onend must not restart one");
  });

  it("survives an abort that dispatches onend re-entrantly", async () => {
    const manager = await listening();
    env.recognizers[0].fireError("network");
    assert.equal(env.liveRecognizers().length, 0);
    assert.equal(manager.getSnapshot().error, "network");
  });
});

/* ------------------------------------------------------------------ */
/* resources                                                            */
/* ------------------------------------------------------------------ */

describe("every input resource is released", () => {
  it("stops every media track", async () => {
    const manager = await listening();
    await manager.armVad({});
    env.recognizers[0].fireError("network");
    assert.equal(env.liveTracks().length, 0, "a live track is a hot microphone");
  });

  it("releases the AudioInputOwner claim", async () => {
    const manager = await listening();
    env.recognizers[0].fireError("network");
    assert.equal(getInputOwnerSnapshot().claimId, null);
    assert.equal(manager.getInputClaim(), null);
  });

  it("leaves the session in ERROR rather than still listening", async () => {
    const manager = await listening();
    env.recognizers[0].fireError("network");
    const snap = manager.getSnapshot();
    assert.equal(snap.state, "ERROR");
    assert.equal(snap.speechDetected, false);
  });
});

/* ------------------------------------------------------------------ */
/* terminal notification — the provider's half                          */
/* ------------------------------------------------------------------ */

describe("the terminal-input notification", () => {
  it("fires exactly once for one fault", async () => {
    const manager = await listening();
    const { events } = watchTerminal(manager);
    const rec = env.recognizers[0];
    rec.fireError("network");
    rec.fireError("network");
    rec.fireError("network");
    assert.equal(events.length, 1);
  });

  it("carries only bounded, non-sensitive data", async () => {
    const manager = await listening();
    const { events } = watchTerminal(manager);
    env.recognizers[0].fireError("network");
    assert.deepEqual(Object.keys(events[0]).sort(), ["category", "epoch", "reason"]);
    assert.equal(events[0].category, "network");
    assert.equal(events[0].reason, "RECOGNITION_ERROR");
    assert.equal(typeof events[0].epoch, "number");
  });

  it("fires synchronously, before a retry can replace the session id", async () => {
    const manager = await listening();
    let claimWasReleasedFirst = null;
    manager.onTerminalInput(() => {
      // The provider consumes its backend session id here. If the claim were
      // still held, a retry could begin against a microphone this epoch owns.
      claimWasReleasedFirst = getInputOwnerSnapshot().claimId === null;
    });
    env.recognizers[0].fireError("network");
    assert.equal(claimWasReleasedFirst, true);
  });

  it("is not blocked by a throwing subscriber", async () => {
    const manager = await listening();
    manager.onTerminalInput(() => {
      throw new Error("provider blew up");
    });
    const { events } = watchTerminal(manager);
    assert.doesNotThrow(() => env.recognizers[0].fireError("network"));
    assert.equal(events.length, 1, "a bad subscriber must not starve the next");
    assert.equal(getInputOwnerSnapshot().claimId, null, "cleanup still completed");
  });

  /**
   * The adapter path cannot produce this on its own — `beginStop()` detaches
   * the error subscription, so a second `onerror` never reaches the manager.
   * The terminal marker exists for the callers that bypass that: a subscriber
   * whose cleanup reports the fault again, or a browser dispatching `onerror`
   * synchronously from inside `abort()`. Driving the entry point directly is
   * the only way to hold that guard honest.
   */
  it("is idempotent when the same epoch reports the fault twice", async () => {
    const manager = await listening();
    const { events } = watchTerminal(manager);
    const epoch = manager.getInputEpoch();

    manager.notifySttError({ code: "network" }, epoch);
    manager.notifySttError({ code: "network" }, epoch);
    manager.notifySttError({ code: "not-allowed" }, epoch);

    assert.equal(events.length, 1, "one failed epoch, one terminal notification");
    assert.equal(manager.getSnapshot().error, "network", "the first fault is the cause");
  });

  it("is idempotent when a subscriber re-enters during teardown", async () => {
    const manager = await listening();
    const epoch = manager.getInputEpoch();
    const { events } = watchTerminal(manager);
    manager.onTerminalInput(() => {
      // A provider whose cleanup reports the same fault back into the manager.
      manager.notifySttError({ code: "network" }, epoch);
    });

    env.recognizers[0].fireError("network");

    assert.equal(events.length, 1, "re-entrant reporting must not notify twice");
  });

  it("stops notifying after unsubscribe", async () => {
    const manager = await listening();
    const { events, unsubscribe } = watchTerminal(manager);
    unsubscribe();
    env.recognizers[0].fireError("network");
    assert.equal(events.length, 0);
  });
});

/* ------------------------------------------------------------------ */
/* epoch discipline                                                     */
/* ------------------------------------------------------------------ */

describe("stale callbacks cannot reach a live epoch", () => {
  it("ignores a transcript from the failed generation", async () => {
    const manager = await listening();
    const stale = env.recognizers[0];
    stale.fireError("network");

    await manager.beginInput({ label: "retry", stopOutputFirst: false });
    const before = manager.getSnapshot().transcriptPartial || "";

    stale.fireResult("ghost of the failed attempt", false);
    stale.fireResult("ghost final", true);

    assert.equal(manager.getSnapshot().transcriptPartial || "", before);
  });

  it("ignores a second error from the failed generation", async () => {
    const manager = await listening();
    const failedEpoch = manager.getInputEpoch();
    const stale = env.recognizers[0];
    stale.fireError("network");
    await manager.beginInput({ label: "retry", stopOutputFirst: false });

    stale.fireError("not-allowed");

    assert.equal(manager.getSnapshot().error, "", "retry cleared the fault; stale must not restore it");
    assert.equal(
      manager.getTerminalInputEpoch(),
      failedEpoch,
      "old epoch stays the terminal one"
    );
  });
});

/* ------------------------------------------------------------------ */
/* retry                                                                */
/* ------------------------------------------------------------------ */

describe("retry opens a clean generation", () => {
  it("creates exactly one fresh recognizer", async () => {
    const manager = await listening();
    env.recognizers[0].fireError("network");
    await manager.beginInput({ label: "retry", stopOutputFirst: false });
    assert.equal(env.recognizers.length, 2);
    assert.equal(env.liveRecognizers().length, 1);
  });

  it("advances the epoch and clears the fault", async () => {
    const manager = await listening();
    const failed = manager.getInputEpoch();
    env.recognizers[0].fireError("network");
    await manager.beginInput({ label: "retry", stopOutputFirst: false });
    assert.equal(manager.getInputEpoch(), failed + 1);
    assert.equal(manager.getSnapshot().error, "");
  });

  it("republishes an identical fault in the new generation", async () => {
    const manager = await listening();
    env.recognizers[0].fireError("network");
    await manager.beginInput({ label: "retry", stopOutputFirst: false });

    const published = [];
    manager.subscribe((snap) => {
      if (snap.error) published.push(snap.error);
    });
    published.length = 0;

    env.recognizers[1].fireError("network");

    assert.deepEqual(published, ["network"], "the same code must report again for a new attempt");
  });

  it("notifies terminal input once per failed generation", async () => {
    const manager = await listening();
    const { events } = watchTerminal(manager);
    env.recognizers[0].fireError("network");
    await manager.beginInput({ label: "retry", stopOutputFirst: false });
    env.recognizers[1].fireError("network");
    assert.equal(events.length, 2);
    assert.equal(events[0].epoch + 1, events[1].epoch);
  });

  it("accumulates nothing across five fail/retry cycles", async () => {
    const manager = await listening();
    const { events } = watchTerminal(manager);
    for (let i = 0; i < 5; i += 1) {
      env.recognizers[env.recognizers.length - 1].fireError("network");
      await manager.beginInput({ label: `retry-${i}`, stopOutputFirst: false });
    }
    env.recognizers[env.recognizers.length - 1].fireError("network");

    assert.equal(env.liveRecognizers().length, 0, "no recognizer may survive");
    assert.equal(env.liveTracks().length, 0, "no microphone track may survive");
    assert.equal(getInputOwnerSnapshot().claimId, null, "no claim may survive");
    assert.equal(events.length, 6, "one terminal notification per failed attempt");
  });
});

/* ------------------------------------------------------------------ */
/* policy: what is terminal and what is not                             */
/* ------------------------------------------------------------------ */

describe("terminal error policy", () => {
  for (const code of ["network", "not-allowed", "service-not-allowed", "audio-capture"]) {
    it(`treats ${code} as terminal`, async () => {
      const manager = await listening();
      const epoch = manager.getInputEpoch();
      env.recognizers[0].fireError(code);
      assert.equal(manager.getTerminalInputEpoch(), epoch, `${code} must end the attempt`);
      assert.equal(getInputOwnerSnapshot().claimId, null, `${code} must release the microphone`);
    });
  }

  it("leaves no-speech retryable and holding the microphone", async () => {
    const manager = await listening();
    const epoch = manager.getInputEpoch();
    env.recognizers[0].fireError("no-speech");

    assert.equal(manager.getSnapshot().error, "no-speech", "still reported truthfully");
    assert.notEqual(manager.getTerminalInputEpoch(), epoch, "no-speech does not end the attempt");
    assert.ok(getInputOwnerSnapshot().claimId, "the user is still being listened to");
    manager.endInput("USER_CANCEL");
  });

  it("does not tight-loop on repeated no-speech", async () => {
    const manager = await listening();
    const rec = env.recognizers[0];
    for (let i = 0; i < 20; i += 1) rec.fireError("no-speech");
    assert.equal(env.recognizers.length, 1, "no-speech must not construct recognizers");
    manager.endInput("USER_CANCEL");
  });

  it("treats an unexpected aborted as terminal", async () => {
    const manager = await listening();
    const epoch = manager.getInputEpoch();
    env.recognizers[0].fireError("aborted");
    assert.equal(manager.getTerminalInputEpoch(), epoch);
  });

  it("publishes no error for an abort caused by our own teardown", async () => {
    const manager = await listening();
    const published = [];
    manager.subscribe((snap) => {
      if (snap.error) published.push(snap.error);
    });
    published.length = 0;

    // endInput() detaches the error subscription inside beginStop() before
    // abort() runs, so the expected abort has nowhere to land.
    manager.endInput("USER_CANCEL");

    assert.deepEqual(published, [], "an expected abort is not a fault");
    assert.equal(manager.getSnapshot().error, "");
  });
});

/* ------------------------------------------------------------------ */
/* nothing is fabricated, nothing else changes                          */
/* ------------------------------------------------------------------ */

describe("truthfulness", () => {
  it("invents no transcript for a failed attempt", async () => {
    const manager = await listening();
    const finals = [];
    manager.onFinalTurn?.((t) => finals.push(t));
    env.recognizers[0].fireError("network");
    const snap = manager.getSnapshot();
    assert.equal(snap.transcriptFinal || "", "");
    assert.equal(snap.transcriptPartial || "", "");
    assert.equal(finals.length, 0, "a failed attempt is not a finalized turn");
  });

  it("leaves a successful recognition path unchanged", async () => {
    const manager = await listening();
    env.recognizers[0].fireResult("hello there", false);
    assert.equal(manager.getSnapshot().transcriptPartial, "hello there");
    env.recognizers[0].fireResult("hello there", true);
    assert.equal(manager.getSnapshot().transcriptFinal, "hello there");
    assert.equal(manager.getSnapshot().error, "", "a good turn reports no fault");
    assert.equal(manager.getTerminalInputEpoch(), -1, "a good turn ends no epoch");
    manager.endInput("USER_CANCEL");
  });
});
