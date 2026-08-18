/**
 * D3 — ending a voice session must end the streaming input pipeline.
 *
 * The browser STT adapter is self-restarting: `SpeechRecognition.onend` calls
 * `start()` again, because a live recognizer stops itself after every silence
 * gap. That is correct while a session is running and catastrophic once it
 * ends — teardown that only released the input *claim* left the recognizer
 * restarting itself, so the microphone stayed hot after the user stopped
 * voice, after a route change, and after logout.
 *
 * The fix is a synchronous cancellation boundary. `pipeline.beginStop()` closes
 * every path that could restart capture — tick timer, transcript
 * subscriptions, the adapter's `cancelled` flag, the recognizer's handlers, the
 * recognizer itself — before it returns, and hands the asynchronous remainder
 * back separately. These tests assert the boundary is synchronous (no `await`
 * between the teardown call and a dead recognizer), that it is reached from
 * every terminal path, and that repeating it accumulates nothing.
 *
 * Everything here is deterministic: a fake `SpeechRecognition`, a fake
 * `getUserMedia`, and counted interval timers. No real microphone, no browser.
 */
import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";

import {
  createVoiceSessionManager,
  resetDefaultVoiceSessionManager,
  forceReleaseInput,
  getInputOwnerSnapshot,
  createRealtimeVoicePipeline,
} from "./index.js";

/* ------------------------------------------------------------------ */
/* deterministic browser environment                                    */
/* ------------------------------------------------------------------ */

function installBrowserEnv() {
  const recognizers = [];
  const streams = [];
  const liveIntervals = new Set();

  class FakeSpeechRecognition {
    constructor() {
      this.continuous = false;
      this.interimResults = false;
      this.lang = "";
      this.onresult = null;
      this.onerror = null;
      this.onend = null;
      this.running = false;
      this.starts = 0;
      this.stops = 0;
      this.aborts = 0;
      recognizers.push(this);
    }

    start() {
      if (this.running) throw new Error("InvalidStateError: already started");
      this.running = true;
      this.starts += 1;
    }

    stop() {
      this.stops += 1;
      this.running = false;
    }

    abort() {
      this.aborts += 1;
      this.running = false;
    }

    /** Browser ends the recognition session (silence gap, engine restart). */
    fireEnd() {
      this.running = false;
      this.onend?.();
    }

    /** Deliver a transcript the way Chromium does. */
    fireResult(text, isFinal) {
      this.onresult?.({
        resultIndex: 0,
        results: [
          Object.assign([{ transcript: text }], { isFinal, length: 1 }),
        ],
      });
    }
  }

  function makeTrack() {
    return {
      kind: "audio",
      readyState: "live",
      stop() {
        this.readyState = "ended";
      },
    };
  }

  function makeStream() {
    const tracks = [makeTrack()];
    const stream = { getTracks: () => tracks, tracks };
    streams.push(stream);
    return stream;
  }

  const navigatorStub = {
    mediaDevices: {
      calls: [],
      async getUserMedia(constraints) {
        navigatorStub.mediaDevices.calls.push(constraints);
        return makeStream();
      },
    },
  };

  const windowStub = {
    SpeechRecognition: FakeSpeechRecognition,
    navigator: navigatorStub,
  };

  const realWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const realNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const realSetInterval = globalThis.setInterval;
  const realClearInterval = globalThis.clearInterval;

  Object.defineProperty(globalThis, "window", {
    value: windowStub,
    configurable: true,
    writable: true,
  });
  Object.defineProperty(globalThis, "navigator", {
    value: navigatorStub,
    configurable: true,
    writable: true,
  });
  globalThis.setInterval = (...args) => {
    const handle = realSetInterval(...args);
    liveIntervals.add(handle);
    return handle;
  };
  globalThis.clearInterval = (handle) => {
    liveIntervals.delete(handle);
    return realClearInterval(handle);
  };

  return {
    recognizers,
    streams,
    liveIntervals,
    micCalls: navigatorStub.mediaDevices.calls,
    allTracks: () => streams.flatMap((s) => s.getTracks()),
    liveTracks: () => streams.flatMap((s) => s.getTracks()).filter((t) => t.readyState === "live"),
    liveRecognizers: () => recognizers.filter((r) => r.running),
    restore() {
      globalThis.setInterval = realSetInterval;
      globalThis.clearInterval = realClearInterval;
      for (const handle of liveIntervals) realClearInterval(handle);
      liveIntervals.clear();
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

/** Open a session with a live recognizer and an open microphone. */
async function startVoice(manager) {
  manager.openSession({ sessionId: "vs-test" });
  await manager.beginInput({ label: "test", stopOutputFirst: false });
  await manager.armVad({ bargeInMode: false });
  return manager.getPipeline();
}

/**
 * The state every terminal path must converge on: nothing capturing, nothing
 * owned, nothing scheduled.
 */
function terminalState(manager) {
  return {
    pipeline: manager.getPipeline(),
    inputClaimId: getInputOwnerSnapshot().claimId,
    inputState: manager.getSnapshot().inputState,
    liveRecognizers: env.liveRecognizers().length,
    liveTracks: env.liveTracks().length,
    liveIntervals: env.liveIntervals.size,
  };
}

const TERMINAL = {
  pipeline: null,
  inputClaimId: null,
  inputState: "idle",
  liveRecognizers: 0,
  liveTracks: 0,
  liveIntervals: 0,
};

/* ------------------------------------------------------------------ */
/* 1–2: the pipeline stops, and cannot restart itself                   */
/* ------------------------------------------------------------------ */

describe("endInput stops the streaming pipeline", () => {
  it("detaches the pipeline and kills the recognizer", async () => {
    const manager = createVoiceSessionManager();
    const pipeline = await startVoice(manager);
    assert.equal(env.recognizers.length, 1, "one recognizer per session");
    assert.equal(pipeline.health().active, true);

    manager.endInput("USER_CANCEL");

    assert.equal(manager.getPipeline(), null, "pipeline reference detached");
    assert.equal(pipeline.health().active, false);
    assert.equal(env.recognizers[0].running, false);
    assert.equal(env.recognizers[0].aborts, 1, "recognizer abort initiated");
  });

  it("closes the restart window synchronously, before any await", async () => {
    const manager = createVoiceSessionManager();
    await startVoice(manager);
    const rec = env.recognizers[0];

    // No await between these two lines on purpose: the invariant is that the
    // window is shut by the time endInput returns, not by the time some
    // later microtask runs.
    manager.endInput("USER_CANCEL");

    assert.equal(rec.running, false, "recognizer stopped synchronously");
    assert.equal(rec.aborts, 1, "abort initiated synchronously");
    assert.equal(rec.onend, null, "end listener neutralized synchronously");
    assert.equal(rec.onresult, null, "result listener neutralized synchronously");
    assert.equal(env.liveIntervals.size, 0, "tick timer cleared synchronously");
    assert.equal(manager.getPipeline(), null, "reference detached synchronously");
  });

  it("recognizer onend cannot restart capture after cancellation", async () => {
    const manager = createVoiceSessionManager();
    await startVoice(manager);
    const rec = env.recognizers[0];
    // Hold the handler the way the browser event loop does: it was captured
    // before teardown and fires afterwards.
    const capturedOnEnd = rec.onend;
    assert.equal(typeof capturedOnEnd, "function");

    manager.endInput("USER_CANCEL");
    capturedOnEnd();
    rec.fireEnd();

    assert.equal(rec.starts, 1, "no restart after cancellation");
    assert.equal(rec.running, false);
    assert.equal(env.recognizers.length, 1, "no replacement recognizer built");
  });

  it("a live session still restarts on onend — the guard is cancellation, not inertness", async () => {
    const manager = createVoiceSessionManager();
    await startVoice(manager);
    const rec = env.recognizers[0];

    rec.fireEnd();

    assert.equal(rec.starts, 2, "self-restart is real while the session runs");
    manager.endInput("USER_CANCEL");
  });
});

/* ------------------------------------------------------------------ */
/* 3–4: microphone tracks and route changes                             */
/* ------------------------------------------------------------------ */

describe("owned capture is fully released", () => {
  it("stops every owned MediaStream track", async () => {
    const manager = createVoiceSessionManager();
    await startVoice(manager);
    assert.ok(env.allTracks().length > 0, "the test must actually open a mic");
    assert.equal(env.liveTracks().length, env.allTracks().length);

    manager.endInput("USER_CANCEL");

    assert.equal(env.liveTracks().length, 0, "every owned track stopped");
  });

  it("route change leaves zero active recognizers", async () => {
    const manager = createVoiceSessionManager();
    await startVoice(manager);

    await manager.interrupt("ROUTE_CHANGE");

    assert.equal(env.liveRecognizers().length, 0);
    assert.equal(manager.getPipeline(), null);
    assert.equal(getInputOwnerSnapshot().claimId, null);
    assert.equal(env.liveTracks().length, 0);
  });
});

/* ------------------------------------------------------------------ */
/* 5: repetition accumulates nothing                                    */
/* ------------------------------------------------------------------ */

describe("five start/stop cycles accumulate nothing", () => {
  it("holds recognizers, tracks, timers, claims and callbacks flat", async () => {
    const manager = createVoiceSessionManager();
    const publishes = [];
    manager.subscribe((snap) => publishes.push(snap));

    for (let cycle = 0; cycle < 5; cycle += 1) {
      const pipeline = await startVoice(manager);
      assert.equal(
        env.liveRecognizers().length,
        1,
        `cycle ${cycle}: exactly one recognizer live during the cycle`
      );
      assert.equal(env.liveIntervals.size, 1, `cycle ${cycle}: one tick timer`);
      assert.equal(pipeline.health().active, true);

      manager.endInput("USER_CANCEL");

      assert.equal(env.liveRecognizers().length, 0, `cycle ${cycle}: none left live`);
      assert.equal(env.liveIntervals.size, 0, `cycle ${cycle}: no timer left`);
      assert.equal(getInputOwnerSnapshot().claimId, null, `cycle ${cycle}: claim released`);
    }

    assert.equal(env.recognizers.length, 5, "one recognizer built per cycle, not more");
    assert.equal(env.streams.length, 5, "one capture per cycle, not more");
    assert.equal(env.liveTracks().length, 0, "no track survives its cycle");
    assert.deepEqual(terminalState(manager), TERMINAL);

    // Callbacks: every recognizer from every cycle is detached, so replaying
    // their events publishes nothing.
    const before = publishes.length;
    for (const rec of env.recognizers) {
      rec.fireResult("stale transcript", true);
      rec.fireEnd();
    }
    assert.equal(publishes.length, before, "stale recognizer events reach no subscriber");
    assert.equal(env.recognizers.length, 5, "stale events built no new recognizer");
  });
});

/* ------------------------------------------------------------------ */
/* 6–8: every terminal path converges                                   */
/* ------------------------------------------------------------------ */

describe("all terminal paths reach the same cleanup state", () => {
  /**
   * The provider's hardReset, expressed against the manager: release the local
   * claim, force-release whoever holds input, then interrupt for session close.
   */
  async function hardReset(manager) {
    manager.endInput("USER_CANCEL");
    forceReleaseInput("SESSION_CLOSE");
    await manager.interrupt("SESSION_CLOSE");
  }

  /** The provider's unmount cleanup path. */
  function unmount(manager) {
    manager.endInput("USER_CANCEL");
  }

  const paths = [
    ["hardReset", hardReset],
    ["provider unmount", unmount],
    ["close", (m) => m.close("SESSION_CLOSE")],
    ["logout", (m) => m.interrupt("LOGOUT")],
    ["error", (m) => m.interrupt("ERROR")],
    ["route change", (m) => m.interrupt("ROUTE_CHANGE")],
  ];

  for (const [name, run] of paths) {
    it(`${name} reaches the terminal cleanup state`, async () => {
      const manager = createVoiceSessionManager();
      await startVoice(manager);
      await run(manager);
      assert.deepEqual(terminalState(manager), TERMINAL, `${name} left residue`);
    });
  }
});

/* ------------------------------------------------------------------ */
/* 9–10: hostile ordering and repetition                                */
/* ------------------------------------------------------------------ */

describe("cleanup survives hostile ordering", () => {
  it("stays effective when the input claim was already released", async () => {
    const manager = createVoiceSessionManager();
    await startVoice(manager);
    const rec = env.recognizers[0];

    // A consumer whose own cleanup releases the claim first. This used to hit
    // endInput's "nothing owned" early return and leave the recognizer alive.
    forceReleaseInput("CONSUMER_CLEANUP");
    assert.equal(getInputOwnerSnapshot().claimId, null);

    manager.endInput("USER_CANCEL");

    assert.equal(rec.running, false, "recognizer still stopped");
    assert.equal(rec.aborts, 1);
    assert.equal(manager.getPipeline(), null);
    assert.deepEqual(terminalState(manager), TERMINAL);
  });

  it("repeated teardown is idempotent and never throws", async () => {
    const manager = createVoiceSessionManager();
    await startVoice(manager);

    for (let i = 0; i < 5; i += 1) {
      manager.endInput("USER_CANCEL");
      await manager.interrupt("ROUTE_CHANGE");
      await manager.close("SESSION_CLOSE");
    }

    assert.equal(env.recognizers.length, 1, "teardown never builds a recognizer");
    assert.equal(env.recognizers[0].aborts, 1, "the recognizer is aborted once");
    assert.deepEqual(terminalState(manager), TERMINAL);
  });

  it("teardown before any session is a silent no-op", async () => {
    const manager = createVoiceSessionManager();
    manager.endInput("USER_CANCEL");
    await manager.close("SESSION_CLOSE");
    assert.equal(env.recognizers.length, 0);
    assert.deepEqual(terminalState(manager), TERMINAL);
  });
});

/* ------------------------------------------------------------------ */
/* the asynchronous tail is observed, not suppressed                    */
/* ------------------------------------------------------------------ */

describe("teardown tails are classified, never suppressed", () => {
  /** An adapter whose async cleanup fails after the synchronous boundary. */
  function failingAdapter() {
    const partials = new Set();
    const finals = new Set();
    return {
      cancelledSync: false,
      async start() {},
      onPartial(cb) {
        partials.add(cb);
        return () => partials.delete(cb);
      },
      onFinal(cb) {
        finals.add(cb);
        return () => finals.delete(cb);
      },
      async cancel() {
        // No cancelSync: the coordinator must take the async path and still
        // observe the rejection.
        this.cancelledSync = true;
        throw new Error("adapter cleanup exploded");
      },
      health: () => ({ adapter: "failing" }),
      capabilities: () => ({ streaming: true, pushAudio: false }),
    };
  }

  it("resolves a rejected cleanup to a classification instead of throwing", async () => {
    const adapter = failingAdapter();
    const pipeline = createRealtimeVoicePipeline({ manager: null, sttAdapter: adapter });
    await pipeline.start();

    const { tail } = pipeline.beginStop();
    const result = await tail;

    assert.equal(result.status, "async_error");
    assert.match(result.errorCode, /adapter cleanup exploded/);
  });

  it("stop() surfaces the same classification without rejecting", async () => {
    const pipeline = createRealtimeVoicePipeline({
      manager: null,
      sttAdapter: failingAdapter(),
    });
    await pipeline.start();

    const result = await pipeline.stop();
    assert.equal(result.status, "async_error");
  });

  it("the manager exposes the settled teardown classification", async () => {
    const manager = createVoiceSessionManager();
    await startVoice(manager);

    manager.endInput("USER_CANCEL");
    const result = await manager.whenInputPipelineStopped();

    assert.equal(result.status, "clean");
    assert.equal(result.errorCode, null);
  });

  it("an unobserved teardown cannot become an unhandled rejection", async () => {
    const unhandled = [];
    const onUnhandled = (err) => unhandled.push(err);
    process.on("unhandledRejection", onUnhandled);
    try {
      const pipeline = createRealtimeVoicePipeline({
        manager: null,
        sttAdapter: failingAdapter(),
      });
      await pipeline.start();
      pipeline.beginStop(); // deliberately not awaited
      // Two macrotask turns is well past when Node reports an unhandled
      // rejection for a promise nobody attached to.
      await new Promise((resolve) => setTimeout(resolve, 0));
      await new Promise((resolve) => setTimeout(resolve, 0));
      assert.deepEqual(unhandled, []);
    } finally {
      process.off("unhandledRejection", onUnhandled);
    }
  });
});
