import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { appStateTone } from "./apps.js";

describe("app launcher helpers", () => {
  it("maps states", () => {
    assert.equal(appStateTone("RUNNING"), "ok");
    assert.equal(appStateTone("DISABLED"), "warn");
    assert.equal(appStateTone("QUARANTINED"), "bad");
  });
});
