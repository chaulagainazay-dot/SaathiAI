import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { skillStateTone } from "./skill-runtime.js";

describe("skill runtime UI helpers", () => {
  it("maps lifecycle tones", () => {
    assert.equal(skillStateTone("ENABLED"), "ok");
    assert.equal(skillStateTone("DISABLED"), "warn");
    assert.equal(skillStateTone("QUARANTINED"), "bad");
    assert.equal(skillStateTone("REVOKED"), "bad");
  });
});
