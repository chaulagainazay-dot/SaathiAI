/**
 * D2 — browser recognition has exactly one owner.
 *
 * VoiceRuntimeProvider used to construct its own `SpeechRecognition` while
 * `beginInput()` started the streaming pipeline, which constructs one too. Two
 * recognizers ran against one microphone: two result streams, two self-restart
 * loops, and a final transcript that could arrive from either — so one spoken
 * sentence could submit twice, and stopping one recognizer left the other
 * listening.
 *
 * Ownership now sits with the pipeline. Consumers bind through
 * `createTurnBinding`, which is where every rule separating "the user said
 * something" from "submit work to the backend" lives. These tests drive that
 * path end to end against the real browser adapter with a fake
 * `SpeechRecognition` — deterministic, no microphone, no renderer — and count
 * submissions the way the provider makes them.
 */
import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  createVoiceSessionManager,
  resetDefaultVoiceSessionManager,
  forceReleaseInput,
  createTurnBinding,
  evaluateRecognitionSupport,
  RECOGNITION_UNSUPPORTED_MESSAGE,
  createRealtimeVoicePipeline,
} from "./index.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROVIDER = join(HERE, "..", "..", "components", "voice", "VoiceRuntimeProvider.jsx");

/* ------------------------------------------------------------------ */
/* deterministic browser environment                                    */
/* ------------------------------------------------------------------ */

function installBrowserEnv({ withSpeechRecognition = true } = {}) {
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
    /** Deliver a transcript the way Chromium does. */
    fireResult(text, isFinal) {
      this.onresult?.({
        resultIndex: 0,
        results: [Object.assign([{ transcript: text }], { isFinal, length: 1 })],
      });
    }
    fireError(code) {
      this.onerror?.({ error: code });
    }
  }

  const navigatorStub = {
    mediaDevices: {
      async getUserMedia() {
        const tracks = [{ kind: "audio", readyState: "live", stop() { this.readyState = "ended"; } }];
        return { getTracks: () => tracks };
      },
    },
  };
  const windowStub = { navigator: navigatorStub };
  if (withSpeechRecognition) windowStub.SpeechRecognition = FakeSpeechRecognition;

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
    live: () => recognizers.filter((r) => r.running),
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

afterEach(() => {
  forceReleaseInput("TEST_TEARDOWN");
  resetDefaultVoiceSessionManager();
  env?.restore();
  env = null;
});

/**
 * A manager with a live pipeline plus a binding wired exactly the way
 * VoiceRuntimeProvider wires one: partials display, eligible finals submit,
 * backchannels do not.
 */
async function talk() {
  const manager = createVoiceSessionManager();
  manager.openSession({ sessionId: "vs-d2" });
  await manager.beginInput({ label: "test", stopOutputFirst: false });

  const submissions = [];
  const partials = [];
  const backchannels = [];
  const ignored = [];
  const binding = createTurnBinding({
    manager,
    epoch: manager.getInputEpoch(),
    onPartial: (p) => partials.push(p),
    onFinalTurn: (t) => submissions.push(t),
    onBackchannel: (t) => backchannels.push(t),
    onIgnored: (t) => ignored.push(t),
  });

  return { manager, binding, submissions, partials, backchannels, ignored };
}

/* ------------------------------------------------------------------ */
/* 1–2: one recognizer, one start                                       */
/* ------------------------------------------------------------------ */

describe("one talk action owns one recognizer", () => {
  beforeEach(() => {
    resetDefaultVoiceSessionManager();
    forceReleaseInput("TEST_SETUP");
    env = installBrowserEnv();
  });

  it("constructs exactly one recognizer", async () => {
    const { manager } = await talk();
    assert.equal(env.recognizers.length, 1, "a second recognizer means split ownership");
    manager.endInput("USER_CANCEL");
  });

  it("starts that recognizer exactly once", async () => {
    const { manager } = await talk();
    assert.equal(env.recognizers[0].starts, 1);
    assert.equal(env.live().length, 1);
    manager.endInput("USER_CANCEL");
  });

  it("the provider constructs no recognizer of its own", () => {
    const source = readFileSync(PROVIDER, "utf8");
    assert.ok(
      !/new\s+Ctor\s*\(/.test(source) && !/new\s+Recognition\s*\(/.test(source),
      "recognizer construction belongs to the pipeline alone"
    );
    assert.ok(
      !/recognitionRef/.test(source),
      "a provider-held recognizer ref is the defect this removed"
    );
    assert.ok(
      /createTurnBinding\(/.test(source),
      "the provider must bind to the authoritative stream"
    );
    assert.ok(
      /detachPipelineSubscriptions\(\);/.test(source),
      "cleanup must detach the binding"
    );
  });
});

/* ------------------------------------------------------------------ */
/* 3–7: what may and may not become a submission                        */
/* ------------------------------------------------------------------ */

describe("submission is exactly once per eligible final turn", () => {
  beforeEach(() => {
    resetDefaultVoiceSessionManager();
    forceReleaseInput("TEST_SETUP");
    env = installBrowserEnv();
  });

  it("one final produces one submission and one finalized turn", async () => {
    const { manager, submissions } = await talk();
    env.recognizers[0].fireResult("Show my missions.", true);

    assert.equal(submissions.length, 1);
    assert.equal(submissions[0].text, "Show my missions.");
    assert.equal(submissions[0].isExecutable, true);
    assert.equal(
      manager.getPipeline().turns.health().finalizedTurns,
      1,
      "exactly one finalized turn"
    );
    manager.endInput("USER_CANCEL");
  });

  it("a redelivered final cannot double-submit", async () => {
    const { manager, submissions, ignored } = await talk();
    const rec = env.recognizers[0];

    rec.fireResult("Show my missions.", true);
    rec.fireResult("Show my missions.", true); // same utterance, delivered twice

    assert.equal(submissions.length, 1, "the second delivery is a redelivery");
    assert.equal(manager.getPipeline().turns.health().finalizedTurns, 1);
    manager.endInput("USER_CANCEL");
    void ignored;
  });

  it("a doubled callback on the same turn cannot double-submit", async () => {
    const { manager, submissions, ignored } = await talk();
    const captured = [];
    manager.onFinalTurn((turn) => captured.push(turn));
    env.recognizers[0].fireResult("Show my missions.", true);
    assert.equal(submissions.length, 1);

    // Replay the identical turn through the manager's fan-out.
    manager.notifyTurnFinal(captured[0]);

    assert.ok(
      submissions.length === 1,
      "identity-keyed dedupe must survive a repeated callback"
    );
    assert.ok(
      ignored.some((t) => t.ignoredReason === "duplicate_turn"),
      "the duplicate is recorded, not silently dropped"
    );
    manager.endInput("USER_CANCEL");
  });

  it("the same sentence in a new utterance is a new turn", async () => {
    const { manager, submissions } = await talk();
    const rec = env.recognizers[0];
    rec.fireResult("Show my missions.", true);
    rec.fireResult("Show my partial", false); // new utterance begins
    rec.fireResult("Show my missions.", true);

    assert.equal(submissions.length, 2, "a genuine repeat is not a duplicate");
    manager.endInput("USER_CANCEL");
  });

  it("backchannels produce zero submissions", async () => {
    const { manager, submissions, backchannels } = await talk();
    const rec = env.recognizers[0];
    rec.fireResult("okay", true);
    rec.fireResult("mhm", true);

    assert.equal(submissions.length, 0);
    assert.equal(backchannels.length, 2);
    for (const turn of backchannels) {
      assert.equal(turn.isExecutable, false, "a backchannel is never executable");
      assert.equal(turn.isBackchannel, true);
    }
    manager.endInput("USER_CANCEL");
  });

  it("partial transcripts produce zero submissions and are never executable", async () => {
    const { manager, submissions, partials } = await talk();
    const rec = env.recognizers[0];
    rec.fireResult("Show my", false);
    rec.fireResult("Show my miss", false);

    assert.equal(submissions.length, 0);
    assert.equal(partials.length, 2);
    for (const partial of partials) {
      assert.equal(partial.isExecutable, false);
      assert.equal(partial.isFinal, false);
    }
    assert.equal(manager.getSnapshot().transcriptPartial, "Show my miss");
    manager.endInput("USER_CANCEL");
  });

  it("empty finals submit nothing", async () => {
    const { manager, submissions } = await talk();
    env.recognizers[0].fireResult("   ", true);
    assert.equal(submissions.length, 0);
    manager.endInput("USER_CANCEL");
  });

  it("events after teardown produce zero submissions", async () => {
    const { manager, submissions } = await talk();
    const rec = env.recognizers[0];

    manager.endInput("USER_CANCEL");
    rec.fireResult("Show my missions.", true);
    rec.fireResult("Open the trading desk.", true);

    assert.equal(submissions.length, 0, "a closed session cannot submit");
  });

  it("a binding left over from a previous session cannot submit", async () => {
    // The hazard is a consumer that reopened input without detaching: its
    // callbacks are still registered, and a new session's speech would flow
    // into work the old session started.
    const { manager, submissions, ignored } = await talk();
    manager.endInput("USER_CANCEL");
    await manager.beginInput({ label: "test", stopOutputFirst: false });

    env.recognizers[1].fireResult("Show my missions.", true);

    assert.equal(submissions.length, 0, "a stale binding submits nothing");
    assert.ok(
      ignored.some((t) => t.ignoredReason === "stale_epoch"),
      "the stale delivery is classified, not silently dropped"
    );
    manager.endInput("USER_CANCEL");
  });
});

/* ------------------------------------------------------------------ */
/* subscriptions: removed on teardown, replaced on restart              */
/* ------------------------------------------------------------------ */

describe("subscriptions follow the session, not the app", () => {
  beforeEach(() => {
    resetDefaultVoiceSessionManager();
    forceReleaseInput("TEST_SETUP");
    env = installBrowserEnv();
  });

  it("a detached binding receives nothing", async () => {
    const { manager, binding, submissions, partials } = await talk();
    binding.detach();
    assert.equal(binding.isAttached(), false);

    env.recognizers[0].fireResult("partial text", false);
    env.recognizers[0].fireResult("Show my missions.", true);

    assert.equal(submissions.length, 0);
    assert.equal(partials.length, 0);
    manager.endInput("USER_CANCEL");
  });

  it("restarting binds once, not once more", async () => {
    const first = await talk();
    first.binding.detach();
    first.manager.endInput("USER_CANCEL");

    const manager = first.manager;
    await manager.beginInput({ label: "test", stopOutputFirst: false });
    const submissions = [];
    createTurnBinding({
      manager,
      epoch: manager.getInputEpoch(),
      onFinalTurn: (t) => submissions.push(t),
    });

    env.recognizers[1].fireResult("Show my missions.", true);

    assert.equal(submissions.length, 1, "one delivery per turn after a restart");
    assert.equal(first.submissions.length, 0, "the old binding is gone, not stacked");
    manager.endInput("USER_CANCEL");
  });

  it("five cycles hold one live recognizer inside each and none after", async () => {
    const manager = createVoiceSessionManager();
    manager.openSession({ sessionId: "vs-cycles" });
    const submissions = [];

    for (let cycle = 0; cycle < 5; cycle += 1) {
      await manager.beginInput({ label: "test", stopOutputFirst: false });
      const binding = createTurnBinding({
        manager,
        epoch: manager.getInputEpoch(),
        onFinalTurn: (t) => submissions.push(t),
      });
      assert.equal(env.live().length, 1, `cycle ${cycle}: one live recognizer`);

      env.recognizers[cycle].fireResult("Show my missions.", true);

      binding.detach();
      manager.endInput("USER_CANCEL");
      assert.equal(env.live().length, 0, `cycle ${cycle}: none live afterwards`);
    }

    assert.equal(env.recognizers.length, 5, "one recognizer per cycle");
    assert.equal(submissions.length, 5, "one submission per cycle, never more");
  });
});

/* ------------------------------------------------------------------ */
/* errors reach published runtime state, once                           */
/* ------------------------------------------------------------------ */

describe("engine errors are published once", () => {
  beforeEach(() => {
    resetDefaultVoiceSessionManager();
    forceReleaseInput("TEST_SETUP");
    env = installBrowserEnv();
  });

  it("a recognizer error lands in the published session state", async () => {
    const { manager } = await talk();
    env.recognizers[0].fireError("no-speech");
    assert.equal(manager.getSnapshot().error, "no-speech");
    manager.endInput("USER_CANCEL");
  });

  it("the same fault repeated is published once", async () => {
    const { manager } = await talk();
    const errors = [];
    manager.subscribe((snap) => {
      if (snap.error) errors.push(snap.error);
    });
    errors.length = 0;

    const rec = env.recognizers[0];
    rec.fireError("not-allowed");
    rec.fireError("not-allowed");
    rec.fireError("not-allowed");

    assert.equal(errors.length, 1, "one fault, one message");
    manager.endInput("USER_CANCEL");
  });

  it("a cancelled recognizer's error does not reopen the session", async () => {
    const { manager } = await talk();
    const rec = env.recognizers[0];
    manager.endInput("USER_CANCEL");
    rec.fireError("aborted");
    assert.notEqual(manager.getSnapshot().error, "aborted");
  });
});

/* ------------------------------------------------------------------ */
/* 9–10: truthful unavailability                                        */
/* ------------------------------------------------------------------ */

describe("unsupported recognition fails truthfully", () => {
  it("the gate rejects a browser with no native recognition", () => {
    const gate = evaluateRecognitionSupport({ recognitionCtor: null });
    assert.equal(gate.supported, false);
    assert.equal(gate.reason, RECOGNITION_UNSUPPORTED_MESSAGE);
  });

  it("the gate rejects a pipeline that selected the mock adapter", () => {
    const gate = evaluateRecognitionSupport({
      recognitionCtor: function Fake() {},
      engineState: { mode: "mock", supported: true },
    });
    assert.equal(gate.supported, false, "the deterministic adapter is not a product engine");
    assert.equal(gate.reason, RECOGNITION_UNSUPPORTED_MESSAGE);
  });

  it("the gate accepts a real browser engine", () => {
    const gate = evaluateRecognitionSupport({
      recognitionCtor: function Fake() {},
      engineState: { mode: "browser_streaming", supported: true },
    });
    assert.equal(gate.supported, true);
  });

  it("a browser without SpeechRecognition gets no mock fallback", async () => {
    env = installBrowserEnv({ withSpeechRecognition: false });
    const manager = createVoiceSessionManager();
    manager.openSession({ sessionId: "vs-unsupported" });

    await manager.beginInput({ label: "test", stopOutputFirst: false });

    const pipeline = manager.getPipeline();
    const engine = pipeline.getEngineState();
    assert.equal(engine.mode, "unavailable");
    assert.equal(engine.supported, false);
    assert.equal(pipeline.getStt(), null, "no adapter at all, least of all the mock");
    assert.equal(env.recognizers.length, 0, "nothing was constructed to pretend with");

    const snapshot = manager.getSnapshot();
    assert.equal(snapshot.sttUnsupported, true);
    assert.match(snapshot.error, /unavailable/i);
    assert.equal(snapshot.sttDegraded, true);

    assert.equal(
      evaluateRecognitionSupport({ recognitionCtor: null, engineState: engine }).supported,
      false,
      "the consumer gate agrees with the engine"
    );
    manager.endInput("USER_CANCEL");
  });

  it("the mock adapter is reachable only when explicitly requested", async () => {
    env = installBrowserEnv({ withSpeechRecognition: false });
    const explicit = createRealtimeVoicePipeline({ manager: null, sttMode: "mock" });
    await explicit.start();
    assert.equal(explicit.health().selectedMode, "mock");

    const auto = createRealtimeVoicePipeline({ manager: null, sttMode: "auto" });
    await auto.start();
    assert.notEqual(auto.health().selectedMode, "mock", "auto must never land on the mock in a browser");
    assert.equal(auto.health().selectedMode, "unavailable");

    await explicit.stop();
    await auto.stop();
  });
});
