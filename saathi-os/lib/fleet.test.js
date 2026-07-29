import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { healthTone, trustTone } from "./fleet.js";

describe("fleet UI helpers", () => {
  it("maps trust tones", () => {
    assert.equal(trustTone("TRUSTED_LOCAL"), "ok");
    assert.equal(trustTone("DRAINING"), "warn");
    assert.equal(trustTone("QUARANTINED"), "bad");
    assert.equal(trustTone("REVOKED"), "bad");
  });

  it("maps health tones", () => {
    assert.equal(healthTone("HEALTHY"), "ok");
    assert.equal(healthTone("DEGRADED"), "warn");
    assert.equal(healthTone("STALE"), "warn");
    assert.equal(healthTone("OFFLINE"), "bad");
  });
});
