/**
 * Voice session teardown must be idempotent — and silent when it is a no-op.
 *
 * Regression guard for a defect that made every link and sidebar button in the
 * shell inert while direct URL loads still worked, with no error anywhere.
 *
 * The chain: `publish()` allocates a new snapshot with a fresh `lastActivityAt`
 * on every call, so a publish is always a *changed* value to a React
 * subscriber. `endInput()` published unconditionally, including when no input
 * was held. VoiceRuntimeProvider's cleanup calls `endInput()`, and that cleanup
 * belonged to an effect whose dependencies included the session value — so the
 * publish changed the value, which changed the effect's identity, which re-ran
 * the cleanup, which published again. The resulting synchronous update loop
 * never let React commit a navigation transition.
 *
 * Two properties keep it dead, and either one alone is sufficient — which is
 * why both are asserted here rather than trusting one:
 *
 *   1. teardown with nothing held publishes nothing (this file);
 *   2. teardown callbacks do not close over session state (asserted below by
 *      source inspection of the provider).
 */
import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  createVoiceSessionManager,
  resetDefaultVoiceSessionManager,
} from "./index.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROVIDER = join(HERE, "..", "..", "components", "voice", "VoiceRuntimeProvider.jsx");

function countingManager() {
  const manager = createVoiceSessionManager();
  const seen = [];
  manager.subscribe((snapshot) => seen.push(snapshot));
  // subscribe() replays the current snapshot; that first call is not a publish.
  seen.length = 0;
  return { manager, seen };
}

describe("voice session teardown is idempotent", () => {
  beforeEach(() => {
    resetDefaultVoiceSessionManager();
  });

  it("endInput publishes nothing when no input is held", () => {
    const { manager, seen } = countingManager();
    manager.endInput("USER_CANCEL");
    assert.equal(seen.length, 0, "a no-op teardown must not notify subscribers");
  });

  it("repeated endInput stays silent", () => {
    const { manager, seen } = countingManager();
    for (let i = 0; i < 25; i += 1) manager.endInput("USER_CANCEL");
    assert.equal(seen.length, 0);
  });

  it("endOutput publishes nothing when no output is held", async () => {
    const { manager, seen } = countingManager();
    await manager.endOutput("USER_CANCEL");
    assert.equal(seen.length, 0);
  });

  it("repeated endOutput stays silent", async () => {
    const { manager, seen } = countingManager();
    for (let i = 0; i < 25; i += 1) await manager.endOutput("USER_CANCEL");
    assert.equal(seen.length, 0);
  });

  it("a no-op teardown does not advance the snapshot identity", () => {
    const { manager } = countingManager();
    const before = manager.getSnapshot();
    manager.endInput("USER_CANCEL");
    assert.equal(
      manager.getSnapshot(),
      before,
      "identity must be stable, or React subscribers see a phantom change",
    );
  });

  it("still reports the idle state truthfully", () => {
    const { manager } = countingManager();
    manager.endInput("USER_CANCEL");
    const snapshot = manager.getSnapshot();
    assert.equal(snapshot.inputState, "idle");
    assert.equal(snapshot.inputClaimId, null);
  });
});

describe("teardown callbacks do not track session state", () => {
  const source = readFileSync(PROVIDER, "utf8");

  it("reads the session through a ref in teardown paths", () => {
    assert.match(source, /voiceSessionRef\.current\?\.endInput/);
    assert.match(source, /voiceSessionRef\.current\?\.interrupt/);
  });

  it("cleanupLocal does not depend on the session value", () => {
    assert.ok(
      !/\}, \[voiceSession\]\);/.test(source),
      "a teardown callback keyed on the session value re-runs whenever voice " +
        "state changes, and its cleanup publishes more voice state",
    );
  });
});
