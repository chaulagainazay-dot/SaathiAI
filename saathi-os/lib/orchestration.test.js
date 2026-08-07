import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { stateTone, taskStatusLabel } from "./orchestration.js";

describe("orchestration UI helpers", () => {
  it("maps state tones", () => {
    assert.equal(stateTone("READY"), "ok");
    assert.equal(stateTone("WAITING_APPROVAL"), "warn");
    assert.equal(stateTone("FAILED"), "bad");
    assert.equal(stateTone("CERTIFIED_WITH_LIMITATIONS"), "ok");
  });

  it("labels task status", () => {
    assert.equal(taskStatusLabel("READY"), "READY");
    assert.equal(taskStatusLabel(""), "UNKNOWN");
  });
});
