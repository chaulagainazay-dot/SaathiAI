import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createAudioFrameTap } from "./audio-frame-tap.js";

function harness(closeMode = "resolve") {
  let resolveClose;
  const ctx = {
    state: "running", sampleRate: 16000,
    resume: async () => {},
    createMediaStreamSource: () => ({ connect() {}, disconnect() { this.disconnected = true; } }),
    createAnalyser: () => ({ fftSize: 512, connect() {}, disconnect() { this.disconnected = true; }, getFloatTimeDomainData() {} }),
    close: () => {
      if (closeMode === "reject") return Promise.reject(new Error("close failed"));
      if (closeMode === "hang") return new Promise(() => {});
      return new Promise((resolve) => { resolveClose = () => { ctx.state = "closed"; resolve(); }; });
    },
  };
  const track = { readyState: "live", stop() { this.readyState = "ended"; } };
  const stream = { getTracks: () => [track], getAudioTracks: () => [track] };
  const tap = createAudioFrameTap({ stream, AudioContextImpl: function AudioContext() { return ctx; } });
  return { tap, ctx, track, resolveClose: () => resolveClose?.() };
}

describe("calibration audio-frame tap cleanup", () => {
  it("is idempotent and confirms a delayed close", async () => {
    const h = harness();
    await h.tap.start();
    const p1 = h.tap.stop({ timeoutMs: 1000 });
    const p2 = h.tap.stop({ timeoutMs: 1000 });
    assert.equal(p1, p2);
    h.resolveClose();
    const result = await p1;
    assert.equal(result.confirmed, true);
    assert.equal(result.state, "closed");
  });

  it("fails closed on a rejected close", async () => {
    const h = harness("reject");
    await h.tap.start();
    const result = await h.tap.stop({ timeoutMs: 20 });
    assert.equal(result.confirmed, false);
  });

  it("does not claim closure when close never resolves", async () => {
    const h = harness("hang");
    await h.tap.start();
    const result = await h.tap.stop({ timeoutMs: 5 });
    assert.equal(result.confirmed, false);
    assert.equal(result.timedOut, true);
  });
});
