/**
 * The calibration capture deadline.
 *
 * The first implementation armed its timer after `await tap.start()`. The
 * microphone was therefore already open while the only thing that would ever
 * close it was still being constructed, so a start that hung left the device
 * live with nothing bounding it. These tests drive exactly those shapes — a
 * promise that never settles, one that resolves after the deadline, one that
 * rejects with resources half-open — and require the device to end up closed
 * every time.
 *
 * Everything is injected, so a hung start is just a promise nobody resolves and
 * time is whatever the fake clock says.
 */
import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  createCalibrationCapture,
  createSnapshotStore,
  CALIBRATION_DEADLINE_MS,
  CALIBRATION_CLEANUP_MARGIN_MS,
  TERMINAL_REASONS,
} from "./calibration-capture.js";
import { CALIBRATION_TOTAL_SECONDS } from "./mic-calibration.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const PANEL = readFileSync(
  join(HERE, "..", "..", "components", "voice", "MicCalibrationPanel.jsx"), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

describe("snapshot publication bounds", () => {
  it("freezes the subscriber cohort when listeners mutate during publication", () => {
    const store = createSnapshotStore({ value: 0 });
    const calls = [];
    let unsubscribe;
    const listenerB = () => calls.push("B");
    const listenerA = () => {
      calls.push("A");
      unsubscribe?.();
      unsubscribe = store.subscribe(listenerB);
    };
    unsubscribe = store.subscribe(listenerA);
    store.publish({ value: 1 });
    assert.deepEqual(calls, ["A"], "a new subscription must wait for the next publication");
    store.publish({ value: 2 });
    assert.deepEqual(calls, ["A", "B"]);
  });

  it("isolates subscriber errors and ignores returned Promises", () => {
    const store = createSnapshotStore({ value: 0 }); let reached = false;
    store.subscribe(() => { throw new Error("observer"); });
    store.subscribe(() => { reached = true; return new Promise(() => {}); });
    store.publish({ value: 1 });
    assert.equal(reached, true);
    assert.equal(store.getSnapshot().value, 1);
  });

  it("keeps snapshot identity stable between publications", () => {
    const store = createSnapshotStore({ value: 0 }); const first = store.getSnapshot();
    assert.equal(store.getSnapshot(), first);
    store.publish({ value: 1 });
    assert.notEqual(store.getSnapshot(), first);
    assert.equal(store.getSnapshot(), store.getSnapshot());
  });
});

/** A clock whose timers fire only when the test says so. */
function fakeClock() {
  let seq = 0;
  const timers = new Map();
  return {
    setTimeoutImpl: (fn, ms) => { const id = ++seq; timers.set(id, { fn, ms }); return id; },
    clearTimeoutImpl: (id) => { timers.delete(id); },
    fire: (ms) => {
      for (const [id, t] of [...timers]) {
        if (t.ms <= ms) { timers.delete(id); t.fn(); }
      }
    },
    pending: () => timers.size,
  };
}

function harness({ startBehaviour = "resolve" } = {}) {
  const log = [];
  const track = { kind: "audio", readyState: "live", stopped: 0, stop() { this.stopped += 1; this.readyState = "ended"; log.push("track.stop"); } };
  const stream = { getTracks: () => [track] };
  const claim = { released: 0, release() { this.released += 1; log.push("claim.release"); } };
  let preempt = null;
  let resolveStart = null;
  let rejectStart = null;
  const tap = { started: 0, stopped: 0,
    start() {
      this.started += 1;
      log.push("tap.start");
      if (startBehaviour === "hang") return new Promise(() => {});
      if (startBehaviour === "manual") return new Promise((res, rej) => { resolveStart = res; rejectStart = rej; });
      if (startBehaviour === "reject") return Promise.reject(new Error("audio graph failed"));
      return Promise.resolve();
    },
    stop() { this.stopped += 1; log.push("tap.stop"); },
  };
  const terminals = [];
  let intervalsCreated = 0;
  const clock = fakeClock();
  const capture = createCalibrationCapture({
    acquireClaim: ({ onPreempt }) => { preempt = onPreempt; log.push("claim.acquire"); return claim; },
    openMicrophone: async () => { log.push("mic.open"); return stream; },
    createTap: () => { log.push("tap.create"); return tap; },
    onTerminal: (reason, gen) => terminals.push({ reason, gen }),
    setTimeoutImpl: clock.setTimeoutImpl,
    clearTimeoutImpl: clock.clearTimeoutImpl,
  });
  return {
    capture, clock, log, track, claim, tap, terminals,
    intervalsCreated: () => intervalsCreated,
    countInterval: () => { intervalsCreated += 1; return 1; },
    preempt: (...a) => preempt?.(...a),
    resolveStart: () => resolveStart?.(),
    rejectStart: (e) => rejectStart?.(e || new Error("late failure")),
  };
}

const settle = () => new Promise((r) => setTimeout(r, 0));

describe("the deadline is armed before anything opens", () => {
  it("arms before the claim, the device and the tap", async () => {
    const h = harness();
    const armed = [];
    const capture = createCalibrationCapture({
      acquireClaim: () => { armed.push("claim"); return { release() {} }; },
      openMicrophone: async () => { armed.push("mic"); return { getTracks: () => [{ kind: "audio", readyState: "live", stop() { this.readyState = "ended"; } }] }; },
      createTap: () => ({ start: async () => { armed.push("tap"); }, stop() {} }),
      setTimeoutImpl: (fn, ms) => { armed.push(`deadline:${ms}`); return 1; },
      clearTimeoutImpl: () => {},
    });
    await capture.start({});
    assert.equal(armed[0], `deadline:${CALIBRATION_DEADLINE_MS}`,
                 "the deadline must be first, before any resource exists");
    assert.deepEqual(armed.slice(1), ["claim", "mic", "tap"]);
    void h;
  });

  it("bounds capture just past the measurement window", () => {
    assert.equal(CALIBRATION_DEADLINE_MS,
                 CALIBRATION_TOTAL_SECONDS * 1000 + CALIBRATION_CLEANUP_MARGIN_MS);
    assert.ok(CALIBRATION_CLEANUP_MARGIN_MS > 0 && CALIBRATION_CLEANUP_MARGIN_MS <= 2000,
              "a backstop, not a second measurement window");
    assert.equal(CALIBRATION_TOTAL_SECONDS, 15, "the measurement duration is unchanged");
  });
});

describe("a start that never settles", () => {
  it("still releases the microphone when the deadline fires", async () => {
    const h = harness({ startBehaviour: "hang" });
    h.capture.start({});
    await settle();
    assert.equal(h.tap.started, 1, "capture really began");
    assert.equal(h.capture.isActive(), true);

    h.clock.fire(CALIBRATION_DEADLINE_MS);
    await settle();

    assert.equal(h.capture.isActive(), false);
    assert.equal(h.track.stopped, 1, "the track is stopped");
    assert.equal(h.tap.stopped, 1, "the tap is closed");
    assert.equal(h.claim.released, 1, "ownership is returned");
    assert.deepEqual(h.terminals.map((t) => t.reason), [TERMINAL_REASONS.DEADLINE]);
    assert.equal(h.clock.pending(), 0, "timers cleared");
  });
});

describe("a start that resolves late", () => {
  it("tears down its own resources and does not resurrect the run", async () => {
    const h = harness({ startBehaviour: "manual" });
    h.capture.start({ onRunning: () => false,
                      setIntervalImpl: () => h.countInterval(),
                      clearIntervalImpl: () => {} });
    await settle();

    h.clock.fire(CALIBRATION_DEADLINE_MS);
    assert.equal(h.capture.isActive(), false);
    const stoppedAtDeadline = h.track.stopped;

    const tapStoppedAtDeadline = h.tap.stopped;
    h.resolveStart();                      // the hung promise finally settles
    await settle();

    assert.equal(h.capture.isActive(), false, "must not restart");
    assert.deepEqual(h.terminals.map((t) => t.reason), [TERMINAL_REASONS.DEADLINE],
                     "the terminal outcome is not overwritten");
    assert.ok(h.track.stopped >= stoppedAtDeadline, "late resources are also released");
    assert.equal(h.claim.released >= 1, true);
    // The decisive checks: accepting a late resolution would leave the tap
    // running and arm a presentation interval for a run that is already over.
    assert.ok(h.tap.stopped >= tapStoppedAtDeadline && h.tap.stopped >= 1,
              "the late-resolved tap must be stopped, not left running");
    assert.equal(h.intervalsCreated(), 0,
                 "no phase interval may be armed after terminalization");
    assert.equal(h.tap.started, 1, "capture is never begun a second time");
  });

  it("a late rejection is equally inert", async () => {
    const h = harness({ startBehaviour: "manual" });
    h.capture.start({});
    await settle();
    h.clock.fire(CALIBRATION_DEADLINE_MS);
    h.rejectStart();
    await settle();
    assert.deepEqual(h.terminals.map((t) => t.reason), [TERMINAL_REASONS.DEADLINE]);
    assert.equal(h.capture.isActive(), false);
  });
});

describe("failures with resources partially open", () => {
  it("a rejecting start releases the device and the claim", async () => {
    const h = harness({ startBehaviour: "reject" });
    const out = await h.capture.start({});
    assert.equal(out.started, false);
    assert.equal(out.reason, TERMINAL_REASONS.ERROR);
    assert.equal(h.track.stopped, 1);
    assert.equal(h.claim.released, 1);
    assert.equal(h.clock.pending(), 0, "the deadline is cleared too");
  });

  it("reports bounded startup stage and code when capture has no audio track", async () => {
    let terminal;
    const capture = createCalibrationCapture({
      acquireClaim: () => ({ release() {} }),
      openMicrophone: async () => ({ getTracks: () => [] }),
      createTap: () => { throw new Error("must not construct"); },
      onTerminal: (_reason, _gen, d) => { terminal = d; },
    });
    const out = await capture.start({});
    await settle();
    assert.equal(out.reason, TERMINAL_REASONS.ERROR);
    assert.equal(terminal.startupStage, "capture_opened");
    assert.equal(terminal.startupErrorCode, "NO_AUDIO_TRACK");
    assert.equal(terminal.startupErrorName, "Error");
  });

  it("classifies frame-source construction failures without exposing exception text", async () => {
    let terminal;
    const capture = createCalibrationCapture({
      acquireClaim: () => ({ release() {} }),
      openMicrophone: async () => ({ getTracks: () => [{ kind: "audio", readyState: "live", stop() { this.readyState = "ended"; } }] }),
      createTap: () => { const e = new Error("secret device detail"); e.name = "NotReadableError"; throw e; },
      onTerminal: (_reason, _gen, d) => { terminal = d; },
    });
    await capture.start({});
    await settle();
    assert.equal(terminal.startupStage, "frame_source_constructing");
    assert.equal(terminal.startupErrorCode, "FRAME_SOURCE_CONSTRUCTION_FAILED");
    assert.equal(terminal.startupErrorName, "NotReadableError");
    assert.equal(JSON.stringify(terminal).includes("secret device detail"), false);
  });

  it("classifies capture request failures and releases the claim", async () => {
    let terminal; let released = 0;
    const capture = createCalibrationCapture({
      acquireClaim: () => ({ release() { released += 1; } }),
      openMicrophone: async () => { throw Object.assign(new Error("permission detail"), { name: "NotAllowedError" }); },
      onTerminal: (_reason, _gen, d) => { terminal = d; },
    });
    await capture.start({}); await settle();
    assert.equal(terminal.startupStage, "capture_requested");
    assert.equal(terminal.startupErrorCode, "CAPTURE_REQUEST_FAILED");
    assert.equal(terminal.startupErrorName, "NotAllowedError");
    assert.equal(released, 1);
  });
});

describe("races", () => {
  it("releases the microphone before a processor drain that never settles", async () => {
    const h = harness(); let released = false; let terminal; let pipelineEvents = 0;
    const capture = createCalibrationCapture({
      acquireClaim: () => ({ release() { released = true; } }),
      openMicrophone: async () => ({ getTracks: () => [h.track] }),
      createTap: () => ({ start: async () => {}, stop: () => new Promise(() => {}) }),
      onCaptureReleased: (d) => { assert.equal(d.captureReleased, true); assert.equal(h.track.readyState, "ended"); assert.equal(released, true); },
      onPipelineCleanup: () => { pipelineEvents += 1; },
      onTerminal: (_r, _g, d) => { terminal = d; },
      setTimeoutImpl: h.clock.setTimeoutImpl,
      clearTimeoutImpl: h.clock.clearTimeoutImpl,
      cleanupTimeoutMs: 10,
    });
    await capture.start({});
    capture.stop();
    assert.equal(released, true);
    assert.equal(h.track.readyState, "ended");
    assert.equal(terminal, undefined);
    h.clock.fire(10);
    await settle();
    assert.equal(terminal.pipelineCleanup, "timed_out");
    assert.equal(terminal.captureReleased, true);
    assert.equal(pipelineEvents, 1);
  });

  it("runs Phase A before any drain promise can settle", async () => {
    const h = harness(); let phaseA;
    const never = { start: async () => {}, beginCancellation() { return { started: true }; }, drainAfterCaptureRelease() { return new Promise(() => {}); } };
    const capture = createCalibrationCapture({
      acquireClaim: () => h.claim,
      openMicrophone: async () => ({ getTracks: () => [h.track] }),
      createTap: () => never,
      onCaptureReleased: (d) => { phaseA = d; },
    });
    await capture.start({}); capture.stop();
    assert.equal(phaseA.captureReleased, true);
    assert.equal(h.track.readyState, "ended");
    assert.equal(h.claim.released, 1);
  });

  it("arms Phase B before invoking a blocking drain adapter", async () => {
    const h = harness(); let armed = false; let invoked = 0; let terminal; let pipeline;
    const tap = {
      start: async () => {},
      beginCancellation: () => ({ started: true, cancelPromise: new Promise(() => {}) }),
      drainAfterCaptureRelease: () => { invoked += 1; return new Promise(() => {}); },
    };
    const capture = createCalibrationCapture({
      acquireClaim: () => h.claim,
      openMicrophone: async () => ({ getTracks: () => [h.track] }),
      createTap: () => tap,
      onPipelineDiagnostics: (d) => { if (d.phaseBTimeoutArmed) armed = true; },
      onPipelineCleanup: (d) => { pipeline = d.pipelineCleanup; },
      onTerminal: (_reason, _generation, d) => { terminal = d; },
      setTimeoutImpl: h.clock.setTimeoutImpl,
      clearTimeoutImpl: h.clock.clearTimeoutImpl,
      cleanupTimeoutMs: 10,
    });
    await capture.start({});
    capture.stop();
    assert.equal(armed, true, "timeout is armed synchronously during Stop");
    assert.equal(h.track.readyState, "ended");
    assert.equal(h.claim.released, 1);
    await Promise.resolve();
    assert.equal(invoked, 1);
    h.clock.fire(10);
    await settle();
    assert.equal(pipeline, "timed_out");
    assert.equal(terminal.pipelineCleanup, "timed_out");
  });

  it("publishes the Phase A/Phase B boundary markers in order", async () => {
    const h = harness(); const events = [];
    const capture = createCalibrationCapture({
      acquireClaim: () => h.claim,
      openMicrophone: async () => ({ getTracks: () => [h.track] }),
      createTap: () => ({
        start: async () => {},
        beginCancellation: () => ({ started: true, cancelPromise: new Promise(() => {}) }),
        drainAfterCaptureRelease: () => new Promise(() => {}),
      }),
      onPipelineDiagnostics: (d) => {
        if (d.phaseAFunctionReturned) events.push("phase-a-returned");
        if (d.phaseBEntered) events.push(`phase-b-entered:${d.controllerImplementationId}`);
      },
      setTimeoutImpl: h.clock.setTimeoutImpl,
      clearTimeoutImpl: h.clock.clearTimeoutImpl,
      cleanupTimeoutMs: 10,
    });
    await capture.start({});
    capture.stop();
    assert.deepEqual(events, ["phase-a-returned", "phase-b-entered:calibration-capture-v2-split-drain"]);
  });

  it("explicit Stop before the deadline wins, and the deadline is inert", async () => {
    const h = harness({ startBehaviour: "hang" });
    h.capture.start({});
    await settle();
    assert.equal(h.capture.stop(TERMINAL_REASONS.STOPPED), true);
    await settle();
    h.clock.fire(CALIBRATION_DEADLINE_MS);
    assert.deepEqual(h.terminals.map((t) => t.reason), [TERMINAL_REASONS.STOPPED]);
    assert.equal(h.track.stopped, 1, "cleanup ran exactly once");
    assert.equal(h.claim.released, 1);
  });

  it("preemption terminalizes once, and the deadline adds nothing", async () => {
    const h = harness({ startBehaviour: "hang" });
    h.capture.start({});
    await settle();
    h.preempt();
    await settle();
    h.clock.fire(CALIBRATION_DEADLINE_MS);
    assert.deepEqual(h.terminals.map((t) => t.reason), [TERMINAL_REASONS.PREEMPTED]);
    assert.equal(h.track.stopped, 1);
    assert.equal(h.claim.released, 1);
  });

  it("unmount/logout disposal is terminal and idempotent", async () => {
    const h = harness({ startBehaviour: "hang" });
    h.capture.start({});
    await settle();
    assert.equal(h.capture.stop(TERMINAL_REASONS.DISPOSED), true);
    await h.capture.stop(TERMINAL_REASONS.STOPPED);
    assert.equal(h.capture.stop(TERMINAL_REASONS.STOPPED) instanceof Promise, true, "second stop joins cleanup");
    h.clock.fire(CALIBRATION_DEADLINE_MS);
    assert.equal(h.terminals.length, 1);
    assert.equal(h.track.stopped, 1);
  });

  it("cleanup happens exactly once however many exits race", async () => {
    const h = harness({ startBehaviour: "hang" });
    h.capture.start({});
    await settle();
    h.capture.stop();
    await settle();
    h.preempt();
    await settle();
    h.clock.fire(CALIBRATION_DEADLINE_MS);
    h.capture.stop();
    assert.equal(h.terminals.length, 1);
    assert.equal(h.track.stopped, 1);
    assert.equal(h.tap.stopped, 1);
    assert.equal(h.claim.released, 1);
  });
});

describe("the normal run", () => {
  it("completes through the presentation interval with the deadline never firing", async () => {
    const h = harness();
    let ticks = 0;
    const intervals = new Map();
    let intervalSeq = 0;
    const out = await h.capture.start({
      onRunning: () => { ticks += 1; return ticks >= 3; },   // "done" on the third tick
      setIntervalImpl: (fn) => { const id = ++intervalSeq; intervals.set(id, fn); return id; },
      clearIntervalImpl: (id) => intervals.delete(id),
    });
    assert.equal(out.started, true);
    const tick = intervals.values().next().value;
    tick(); tick(); tick();
    await settle();
    assert.deepEqual(h.terminals.map((t) => t.reason), [TERMINAL_REASONS.COMPLETED]);
    assert.equal(h.track.stopped, 1);
    assert.equal(h.claim.released, 1);
    assert.equal(intervals.size, 0, "the presentation interval is cleared");
    assert.equal(h.clock.pending(), 0, "the deadline is cleared on completion");
  });

  it("a second start while active is refused rather than opening a second device", async () => {
    const h = harness({ startBehaviour: "hang" });
    h.capture.start({});
    await settle();
    const again = await h.capture.start({});
    assert.equal(again.started, false);
    assert.equal(again.reason, "ALREADY_ACTIVE");
    assert.equal(h.tap.started, 1, "only one capture was ever begun");
  });
});

describe("the panel wiring", () => {
  it("delegates safety to the capture manager, not to the countdown", () => {
    assert.ok(PANEL.includes("createCalibrationCapture"));
    assert.ok(!PANEL.includes("setTimeout("), "the panel arms no timer of its own");
    // The interval exists only for presentation, and is handed to the manager.
    assert.ok(PANEL.includes("setIntervalImpl: setInterval"));
  });

  it("exposes bounded Phase B publication diagnostics on the real panel", () => {
    for (const attribute of [
      "data-phase-b-timeout-armed", "data-phase-b-timeout-fired",
      "data-controller-pipeline-state", "data-pipeline-callback-count",
      "data-pipeline-callback-last-state", "data-react-pipeline-state",
      "data-react-pipeline-commit-count", "data-terminal-callback-count",
      "data-cleanup-promise-state",
      "data-phase-a-function-returned", "data-phase-b-entered",
      "data-has-drain-after-release", "data-has-tap-cleanup",
      "data-controller-implementation-id",
    ]) assert.ok(PANEL.includes(attribute), attribute);
    assert.ok(PANEL.includes("onPipelineDiagnostics"));
  });

  it("still opens nothing on mount and keeps every forbidden path out", () => {
    const mountEffect = PANEL.slice(PANEL.indexOf("useEffect(() =>"), PANEL.indexOf("const start ="));
    assert.ok(!mountEffect.includes("openMicrophoneForClaim"));
    assert.ok(mountEffect.includes("stop"), "unmount disposes the capture");
    for (const banned of ["SpeechRecognition", "MediaRecorder", "fetch(", "afetch",
                          "createSession", "/api/", "localStorage"]) {
      assert.ok(!PANEL.includes(banned), banned);
    }
  });

  it("publishes no results when the deadline terminated the run", () => {
    const handler = PANEL.slice(PANEL.indexOf("const onTerminal"), PANEL.indexOf("function capture()"));
    const deadlineBranch = handler.slice(handler.indexOf("DEADLINE"));
    assert.ok(!deadlineBranch.includes("setResults(summariseCalibration"),
              "a timed-out run must not publish a measurement");
    assert.ok(handler.includes("setResults(summariseCalibration"), "a completed run does");
  });

  it("exposes only bounded capture and pipeline diagnostics", () => {
    for (const attr of ["data-capture-release-state", "data-track-count", "data-ended-track-count", "data-input-claim-state", "data-pipeline-cleanup-state", "data-outstanding-frame-count", "data-reader-cancel-state", "data-processing-loop-state"]) assert.ok(PANEL.includes(attr), attr);
    for (const banned of ["deviceId", "token", "cookie", "stack"]) assert.equal(PANEL.includes(banned), false, banned);
  });
});
