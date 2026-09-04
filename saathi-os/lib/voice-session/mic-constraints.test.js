/**
 * D4 — production microphone capture uses the constraints contract.
 *
 * `openMicrophoneForClaim` defaults to DEFAULT_MIC_CONSTRAINTS, and both
 * production callers passed `{ audio: true }` anyway, which silently replaced
 * it. The browser then chose its own processing, so the capture that the
 * assistant's own playback bleeds into arrived with echo cancellation off.
 *
 * These tests assert what the *actual* getUserMedia request contains, not what
 * the constant says, and they assert that a caller cannot reintroduce the bare
 * form by accident.
 *
 * What they do not assert: that any of this suppresses echo. These are
 * requests a browser honours at its discretion; acoustic barge-in still
 * depends on the echo-window logic in the VAD path.
 */
import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  acquireInputClaim,
  forceReleaseInput,
  openMicrophoneForClaim,
  resolveMicConstraints,
  DEFAULT_MIC_CONSTRAINTS,
} from "./index.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const root = (...parts) => join(HERE, "..", "..", ...parts);

const REQUIRED = ["echoCancellation", "noiseSuppression", "autoGainControl"];

let requests;
let restoreNavigator;

beforeEach(() => {
  forceReleaseInput("TEST_SETUP");
  requests = [];
  const stub = {
    mediaDevices: {
      async getUserMedia(constraints) {
        requests.push(constraints);
        const tracks = [
          { kind: "audio", readyState: "live", stop() { this.readyState = "ended"; } },
        ];
        return { getTracks: () => tracks };
      },
    },
  };
  const real = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  Object.defineProperty(globalThis, "navigator", {
    value: stub,
    configurable: true,
    writable: true,
  });
  restoreNavigator = () => {
    if (real) Object.defineProperty(globalThis, "navigator", real);
    else delete globalThis.navigator;
  };
});

afterEach(() => {
  forceReleaseInput("TEST_TEARDOWN");
  restoreNavigator();
});

function assertContractApplied(constraints, label) {
  assert.ok(constraints, `${label}: a request was made`);
  assert.equal(typeof constraints.audio, "object", `${label}: audio must be structured`);
  for (const flag of REQUIRED) {
    assert.equal(constraints.audio[flag], true, `${label}: ${flag} must be requested`);
  }
}

describe("the production getUserMedia request carries the contract", () => {
  it("requests all three processing flags with no argument", async () => {
    const claim = acquireInputClaim({ label: "test" });
    await openMicrophoneForClaim(claim);
    assert.equal(requests.length, 1);
    assertContractApplied(requests[0], "default");
  });

  it("a caller passing a bare { audio: true } still gets the contract", async () => {
    const claim = acquireInputClaim({ label: "test" });
    await openMicrophoneForClaim(claim, { audio: true });
    assertContractApplied(requests[0], "bare audio:true");
  });

  it("the bare form cannot reach the browser at all", () => {
    assert.deepEqual(resolveMicConstraints({ audio: true }), {
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    assert.deepEqual(resolveMicConstraints(undefined), DEFAULT_MIC_CONSTRAINTS);
    assert.deepEqual(resolveMicConstraints(null), DEFAULT_MIC_CONSTRAINTS);
  });

  it("a deliberate per-flag override wins, and the rest keep the contract", async () => {
    const claim = acquireInputClaim({ label: "test" });
    await openMicrophoneForClaim(claim, { audio: { echoCancellation: false } });
    const sent = requests[0];
    assert.equal(sent.audio.echoCancellation, false, "an explicit choice is honoured");
    assert.equal(sent.audio.noiseSuppression, true);
    assert.equal(sent.audio.autoGainControl, true);
  });

  it("unrelated constraint keys survive resolution", () => {
    const resolved = resolveMicConstraints({
      audio: { deviceId: "mic-2" },
      video: false,
    });
    assert.equal(resolved.video, false);
    assert.equal(resolved.audio.deviceId, "mic-2");
    for (const flag of REQUIRED) assert.equal(resolved.audio[flag], true);
  });

  it("the contract constant is frozen at both levels", () => {
    assert.ok(Object.isFrozen(DEFAULT_MIC_CONSTRAINTS));
    assert.ok(Object.isFrozen(DEFAULT_MIC_CONSTRAINTS.audio));
  });
});

describe("no production caller replaces the contract", () => {
  const sttCaptureSurfaces = [
    "components/voice/VoiceRuntimeProvider.jsx",
    "app/settings/voice/page.jsx",
  ];

  // R2.1-D6.4: lib/useVoice.js is gone, so it is no longer in the list above.
  // Dropping it silently would look identical to dropping coverage, so the
  // removal is asserted instead: the hook that opened an unclaimed recorder
  // and uploaded to /api/v1/voice/command must not come back.
  it("the unclaimed recording hook no longer exists", () => {
    assert.ok(
      !existsSync(root("lib/useVoice.js")),
      "lib/useVoice.js is back — an unclaimed MediaRecorder outside the input registry"
    );
  });

  for (const relative of sttCaptureSurfaces) {
    it(`${relative} does not request a bare { audio: true }`, () => {
      const source = readFileSync(root(relative), "utf8");
      assert.ok(
        !/getUserMedia\(\s*\{\s*audio:\s*true\s*\}\s*\)/.test(source),
        "STT capture must go through the constraints contract"
      );
      assert.ok(
        !/openMicrophoneForClaim\([^)]*\{\s*audio:\s*true\s*\}/.test(source),
        "passing { audio: true } here is what discarded the contract"
      );
    });
  }

  it("every openMicrophoneForClaim caller passes no constraints at all", () => {
    for (const relative of [
      "components/voice/VoiceRuntimeProvider.jsx",
      // R2.1-D6.5: settings capture joined the claimed callers.
      "app/settings/voice/page.jsx",
    ]) {
      const source = readFileSync(root(relative), "utf8");
      const calls = source.match(/openMicrophoneForClaim\([^)]*\)/g) || [];
      assert.ok(calls.length > 0, `${relative} must open the microphone`);
      for (const call of calls) {
        assert.ok(
          /^openMicrophoneForClaim\(\s*claim\s*\)$/.test(call),
          `${relative}: ${call} must let the default contract apply`
        );
      }
    }
  });

  it("speaker enrollment no longer opts out, because it no longer exists", () => {
    // Enrollment was the one documented exception to the capture contract: it
    // recorded the raw voice for speaker identity, so browser AEC/NS/AGC would
    // have processed the very signal being enrolled. R2.1-S6 retired the
    // capability, so the exception is gone rather than justified — these two
    // pages must now open no microphone at all.
    for (const relative of ["app/voice/page.jsx", "app/os/page.jsx"]) {
      const source = readFileSync(root(relative), "utf8");
      assert.ok(
        !/getUserMedia\(/.test(source),
        `${relative} must not open a microphone; enrollment is retired`
      );
      assert.ok(
        !/new MediaRecorder\(/.test(source),
        `${relative} must not record a speaker sample`
      );
    }
  });
});
