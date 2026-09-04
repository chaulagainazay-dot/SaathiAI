/**
 * R2.1-D10 — a failed turn's clock must stop.
 *
 * Physical Test A: the recognizer died with a `network` fault around 00:04 and
 * the dock's counter kept climbing past 01:13. A dead turn read as a live one,
 * which is the opposite of what the number is for. The cause was that the
 * dock's interval effect treated every stage except `idle` as active, so `fail`
 * kept ticking.
 *
 * The transition is pure, so these drive it with explicit timestamps rather
 * than sleeping or reading rendered text. The dock wiring itself is asserted
 * against the component source at the bottom.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  ACTIVE_TURN_STAGES,
  TIMER_IDLE_DISPLAY,
  advanceTurnTimer,
  createTurnTimerState,
  formatElapsed,
  isActiveTurnStage,
} from "./voice-turn-timer.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const DOCK = readFileSync(
  join(HERE, "..", "components", "voice", "VoiceRuntimeDock.jsx"),
  "utf8"
);

const EPOCH = "vses_first";
const NEXT_EPOCH = "vses_second";

/** Fold a script of [stage, now] observations, returning the final state. */
function run(script, { epochKey = EPOCH, from = createTurnTimerState() } = {}) {
  let state = from;
  for (const [stage, now, key = epochKey] of script) {
    state = advanceTurnTimer(state, { stage, epochKey: key, now });
  }
  return state;
}

/* ------------------------------------------------------------------ */
/* idle and active                                                      */
/* ------------------------------------------------------------------ */

describe("an idle dock measures nothing", () => {
  it("renders the idle placeholder", () => {
    const state = run([["idle", 1_000]]);
    assert.equal(state.display, TIMER_IDLE_DISPLAY);
    assert.equal(state.running, false);
  });

  it("holds no start time", () => {
    assert.equal(run([["idle", 1_000]]).startedAt, null);
  });
});

describe("an active turn advances", () => {
  it("begins at 00:00", () => {
    assert.equal(run([["listen", 10_000]]).display, "00:00");
  });

  it("advances with the clock", () => {
    const state = run([
      ["listen", 10_000],
      ["listen", 13_000],
    ]);
    assert.equal(state.display, "00:03");
    assert.equal(state.running, true);
  });

  it("measures the turn, not the stage", () => {
    // listen -> hear -> think must not restart the count.
    const state = run([
      ["listen", 10_000],
      ["hear", 12_000],
      ["think", 15_000],
    ]);
    assert.equal(state.display, "00:05");
  });

  it("treats exactly the four active stages as running", () => {
    assert.deepEqual([...ACTIVE_TURN_STAGES], ["listen", "hear", "think", "speak"]);
    assert.equal(isActiveTurnStage("fail"), false, "a failed turn is not running");
    assert.equal(isActiveTurnStage("idle"), false);
  });
});

/* ------------------------------------------------------------------ */
/* the freeze                                                           */
/* ------------------------------------------------------------------ */

describe("a failed turn freezes", () => {
  it("freezes at the transition, not the next tick", () => {
    const state = run([
      ["listen", 10_000],
      ["fail", 14_000],
    ]);
    assert.equal(state.display, "00:04", "the reading is the failure time");
    assert.equal(state.running, false, "a failed turn holds no interval");
  });

  it("does not advance as time passes", () => {
    const state = run([
      ["listen", 10_000],
      ["fail", 14_000],
      ["fail", 73_000],
      ["fail", 600_000],
    ]);
    assert.equal(state.display, "00:04", "this is the defect: 00:04 became 01:13");
  });

  it("survives the D9 cleanup snapshots that follow a fault", () => {
    // The terminal funnel publishes again after teardown; each republish
    // arrives here with a later timestamp and the same stage.
    const state = run([
      ["listen", 10_000],
      ["fail", 14_000],
      ["fail", 14_050],
      ["fail", 14_120],
      ["fail", 20_000],
    ]);
    assert.equal(state.display, "00:04");
    assert.equal(state.frozenMs, 4_000, "repeated ERROR must not re-freeze");
  });

  it("freezes at 00:00 when the turn failed before it started", () => {
    assert.equal(run([["fail", 9_000]]).display, "00:00");
  });
});

/* ------------------------------------------------------------------ */
/* retry                                                                */
/* ------------------------------------------------------------------ */

describe("retry measures a new turn", () => {
  it("resets to 00:00 on a new turn identity", () => {
    const failed = run([
      ["listen", 10_000],
      ["fail", 14_000],
    ]);
    const retried = advanceTurnTimer(failed, {
      stage: "listen",
      epochKey: NEXT_EPOCH,
      now: 20_000,
    });
    assert.equal(retried.display, "00:00");
    assert.equal(retried.running, true);
    assert.equal(retried.frozenMs, null, "the old frozen value must not survive");
  });

  it("advances independently in the new turn", () => {
    const state = run(
      [
        ["listen", 10_000],
        ["fail", 14_000],
        ["listen", 20_000, NEXT_EPOCH],
        ["listen", 27_000, NEXT_EPOCH],
      ],
    );
    assert.equal(state.display, "00:07");
  });

  it("freezes the second failure on its own clock", () => {
    const state = run([
      ["listen", 10_000],
      ["fail", 14_000],
      ["listen", 20_000, NEXT_EPOCH],
      ["fail", 29_000, NEXT_EPOCH],
      ["fail", 900_000, NEXT_EPOCH],
    ]);
    assert.equal(state.display, "00:09", "not the first failure's 00:04");
  });

  it("does not reset merely because the stage left fail", () => {
    // Same turn identity: a stage change alone is not a retry.
    const state = run([
      ["listen", 10_000],
      ["fail", 14_000],
      ["fail", 15_000],
    ]);
    assert.equal(state.frozenMs, 4_000);
  });
});

/* ------------------------------------------------------------------ */
/* formatting and monotonicity                                          */
/* ------------------------------------------------------------------ */

describe("the reading is well formed", () => {
  it("pads and rolls over past a minute", () => {
    assert.equal(formatElapsed(0), "00:00");
    assert.equal(formatElapsed(9_000), "00:09");
    assert.equal(formatElapsed(59_000), "00:59");
    assert.equal(formatElapsed(60_000), "01:00");
    assert.equal(formatElapsed(73_000), "01:13");
    assert.equal(formatElapsed(3_599_000), "59:59");
    assert.equal(formatElapsed(3_600_000), "60:00", "beyond an hour stays readable");
  });

  it("never renders a negative reading", () => {
    assert.equal(formatElapsed(-5_000), "00:00");
    // A clock that jumps backwards must not produce a negative turn.
    const state = run([
      ["listen", 10_000],
      ["fail", 4_000],
    ]);
    assert.equal(state.display, "00:00");
  });

  it("is idempotent for one render, as Strict Mode requires", () => {
    const obs = { stage: "listen", epochKey: EPOCH, now: 10_000 };
    const once = advanceTurnTimer(createTurnTimerState(), obs);
    const twice = advanceTurnTimer(once, obs);
    assert.deepEqual(twice, once, "a double render must not restart the turn");
  });
});

/* ------------------------------------------------------------------ */
/* the dock wiring                                                      */
/* ------------------------------------------------------------------ */

describe("the dock drives the clock from canonical state", () => {
  it("runs its interval only while the turn is running", () => {
    assert.match(
      DOCK,
      /if \(!running\) return undefined;\s*\n\s*const timer = setInterval\(/,
      "the interval must be gated on the canonical running flag"
    );
  });

  it("clears the interval it created", () => {
    assert.match(DOCK, /return \(\) => clearInterval\(timer\);/);
  });

  it("keys the turn on the session identity, not on the stage", () => {
    assert.match(DOCK, /const epochKey = runtime\.sessionId \|\| "";/);
  });

  it("no longer restarts timing on every stage change", () => {
    assert.doesNotMatch(
      DOCK,
      /setSince\(/,
      "the per-stage restart was the reason a freeze could not be captured"
    );
  });

  it("derives nothing from labels, colours or error text", () => {
    assert.doesNotMatch(DOCK, /voiceStageLabel\(stage\) === /);
    assert.doesNotMatch(DOCK, /runtime\.error [!=]== .*(?:elapsed|timer|interval)/i);
  });

  it("keeps the failure evidence rendered while the clock is frozen", () => {
    assert.match(DOCK, /runtime\.error \|\| "Voice runtime failed"/);
    assert.match(DOCK, /className="voice-runtime-retry"/);
  });

  it("keeps the redesigned dock presentation", () => {
    for (const marker of ["vrd-clock", "vrd-ladder", "vrd-evidence", "vrd-stage"]) {
      assert.ok(DOCK.includes(marker), `${marker} must survive the timer change`);
    }
  });
});
