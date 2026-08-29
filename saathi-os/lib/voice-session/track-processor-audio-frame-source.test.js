import test from "node:test";
import assert from "node:assert/strict";
import { createTrackProcessorAudioFrameSource, isTrackProcessorAudioSupported } from "./track-processor-audio-frame-source.js";

function harness({ rejectCancel = false, errorCopy = false } = {}) {
  const track = { readyState: "live", stopCalls: 0, stop() { this.stopCalls += 1; this.readyState = "ended"; } };
  let resolveRead; let cancelled = false;
  const reader = { read() { return new Promise((resolve) => { resolveRead = resolve; if (cancelled) resolve({ done: true }); }); }, cancel() { cancelled = true; resolveRead?.({ done: true }); return rejectCancel ? Promise.reject(new Error("cancel")) : Promise.resolve(); }, releaseLock() {} };
  class Processor { constructor() { this.readable = { getReader: () => reader }; } }
  const frame = { sampleRate: 48000, numberOfFrames: 1536, numberOfChannels: 2, format: "f32-planar", closed: false, copyTo(buf) { if (errorCopy) throw new Error("copy"); buf.fill(.25); }, close() { this.closed = true; } };
  return { track, reader, Processor, frame, push: () => resolveRead?.({ value: frame, done: false }) };
}

function frameSource(format, values, sampleRate = 16000, channels = 1) {
  const h = harness();
  h.frame.format = format; h.frame.sampleRate = sampleRate; h.frame.numberOfChannels = channels;
  h.frame.numberOfFrames = channels > 1 ? values[0].length : values.length;
  h.frame.copyTo = (buf, { planeIndex = 0 } = {}) => {
    const vals = channels > 1 && format.includes("planar") ? values[planeIndex] : values;
    buf.set(vals);
  };
  return h;
}

test("supported source frames and downsamples to exact 512-frame output", async () => {
  const h = harness(); const frames = []; const source = createTrackProcessorAudioFrameSource({ track: h.track, ProcessorImpl: h.Processor, onFrame: (f) => frames.push(f) });
  await source.start(); h.push(); await new Promise((r) => setTimeout(r, 0)); const d = source.diagnostics(); assert.equal(d.framesRead, 1); assert.equal(d.framesClosed, 1); assert.equal(d.outstandingFrames, 0); assert.equal(frames[0].length, 512); assert.equal(h.frame.closed, true); await source.stop();
});

test("pending read cancellation settles and repeated stop shares cleanup", async () => { const h = harness(); const source = createTrackProcessorAudioFrameSource({ track: h.track, ProcessorImpl: h.Processor }); await source.start(); const p1 = source.stop(); const p2 = source.stop(); assert.equal(p1, p2); await p1; assert.equal(source.diagnostics().readerCancelSettled, true); assert.equal(source.diagnostics().pipelineSettled, true); });
test("cancel rejection remains settled", async () => { const h = harness({ rejectCancel: true }); const source = createTrackProcessorAudioFrameSource({ track: h.track, ProcessorImpl: h.Processor }); await source.start(); await source.stop(); assert.equal(source.diagnostics().readerCancelSettled, true); });
test("AudioData closes on calculation failure", async () => { const h = harness({ errorCopy: true }); const source = createTrackProcessorAudioFrameSource({ track: h.track, ProcessorImpl: h.Processor }); await source.start(); h.push(); await new Promise((r) => setTimeout(r, 0)); assert.equal(h.frame.closed, true); await source.stop(); });
test("unsupported browser refuses before a source is constructed", () => { assert.equal(isTrackProcessorAudioSupported(null), false); });
test("track ownership remains external to the source", async () => { const h = harness(); const source = createTrackProcessorAudioFrameSource({ track: h.track, ProcessorImpl: h.Processor }); await source.start(); await source.stop(); assert.equal(h.track.stopCalls, 0); });
test("stereo planar input is downmixed and chunked", async () => { const h = frameSource("f32-planar", [new Float32Array(1024).fill(.2), new Float32Array(1024).fill(-.2)], 16000, 2); const out = []; const source = createTrackProcessorAudioFrameSource({ track: h.track, ProcessorImpl: h.Processor, onFrame: (f) => out.push(f) }); await source.start(); h.push(); await new Promise((r) => setTimeout(r, 0)); assert.equal(out.length, 2); assert.equal(out[0][0], 0); await source.stop(); });
test("interleaved input preserves duration across chunk boundaries", async () => { const h = frameSource("f32", Array.from({ length: 1024 }, (_, i) => i % 2 ? -.5 : .5), 16000, 1); const out = []; const source = createTrackProcessorAudioFrameSource({ track: h.track, ProcessorImpl: h.Processor, onFrame: (f) => out.push(f) }); await source.start(); h.push(); await new Promise((r) => setTimeout(r, 0)); assert.equal(out.length, 2); assert.equal(out[0].length, 512); await source.stop(); });

test("cancellation starts before the claimed track is stopped", async () => {
  const track = { readyState: "live", stopCalls: 0, stop() { this.stopCalls += 1; this.readyState = "ended"; releaseCancel?.(); } };
  let releaseRead; let releaseCancel;
  let cancelStarted = false;
  const reader = {
    read: () => new Promise((resolve) => { releaseRead = () => resolve({ done: true }); }),
    cancel: () => { cancelStarted = true; return new Promise((resolve) => { releaseCancel = resolve; }); },
    releaseLock: () => {},
  };
  class Processor { constructor() { this.readable = { getReader: () => reader }; } }
  const source = createTrackProcessorAudioFrameSource({ track, ProcessorImpl: Processor });
  await source.start();
  const cleanup = source.stop();
  assert.equal(cancelStarted, true);
  assert.equal(track.readyState, "live");
  track.stop();
  releaseRead();
  const diagnostics = await cleanup;
  assert.equal(diagnostics.readerCancelSettled, true);
  assert.equal(diagnostics.pipelineSettled, true);
  assert.equal(track.readyState, "ended");
  assert.equal(track.stopCalls, 1);
});
