/** Calibration-only frame source. It consumes an already-claimed track. */
export const isTrackProcessorAudioSupported = (impl = typeof MediaStreamTrackProcessor !== "undefined" ? MediaStreamTrackProcessor : null) => typeof impl === "function";

export function createTrackProcessorAudioFrameSource({
  track, onFrame, outputSampleRate = 16000, frameSize = 512,
  onStage = () => {},
  ProcessorImpl = typeof MediaStreamTrackProcessor !== "undefined" ? MediaStreamTrackProcessor : null,
} = {}) {
  let processor = null;
  let reader = null;
  let loopPromise = null;
  let cleanupPromise = null;
  let cancellationHandle = null;
  let stopped = false;
  let inputSampleRate = null;
  let sourceSamples = [];
  let sourcePosition = 0;
  let framesRead = 0;
  let framesClosed = 0;
  let outputFrames = 0;
  let outstandingFrames = 0;
  let cancelSettled = false;
  let pipelineSettled = false;

  const diagnostics = () => ({
    source: "track_processor",
    inputSampleRate,
    outputSampleRate,
    framesRead,
    framesClosed,
    outstandingFrames,
    outputFrames,
    processorCreated: Boolean(processor),
    readerCreated: Boolean(reader),
    processingLoopStarted: Boolean(loopPromise),
    readerCancelSettled: cancelSettled,
    pipelineSettled,
    trackState: track?.readyState || "unknown",
  });

  function emitFrames() {
    if (!inputSampleRate) return;
    const ratio = inputSampleRate / outputSampleRate;
    while (sourcePosition + (frameSize - 1) * ratio < sourceSamples.length) {
      const out = new Float32Array(frameSize);
      for (let i = 0; i < frameSize; i += 1) {
        const p = sourcePosition + i * ratio;
        const a = Math.floor(p); const b = Math.min(a + 1, sourceSamples.length - 1);
        const f = p - a;
        out[i] = sourceSamples[a] * (1 - f) + sourceSamples[b] * f;
      }
      sourcePosition += frameSize * ratio;
      outputFrames += 1;
      onFrame?.(out);
    }
    const drop = Math.floor(sourcePosition);
    if (drop > 0) { sourceSamples = sourceSamples.slice(drop); sourcePosition -= drop; }
  }

  function toMono(audioData) {
    const channels = Math.max(1, Number(audioData.numberOfChannels) || 1);
    const frames = Number(audioData.numberOfFrames) || 0;
    const format = String(audioData.format || "f32-planar");
    const integer = /s16|s32|u8/.test(format);
    const Ctor = format.includes("s16") ? Int16Array : format.includes("s32") ? Int32Array : format.includes("u8") ? Uint8Array : Float32Array;
    const scale = format.includes("s16") ? 1 / 32768 : format.includes("s32") ? 1 / 2147483648 : format.includes("u8") ? 1 / 128 : 1;
    const planar = format.includes("planar");
    const planes = [];
    if (planar) {
      for (let c = 0; c < channels; c += 1) {
        const buf = new Ctor(frames);
        audioData.copyTo(buf, { planeIndex: c });
        planes.push(integer ? Float32Array.from(buf, (v) => (format.includes("u8") ? (v - 128) : v) * scale) : buf);
      }
    } else {
      const buf = new Ctor(frames * channels);
      audioData.copyTo(buf, { planeIndex: 0 });
      for (let i = 0; i < frames; i += 1) {
        let sum = 0; for (let c = 0; c < channels; c += 1) { const v = buf[i * channels + c]; sum += (format.includes("u8") ? v - 128 : v) * scale; }
        sourceSamples.push(sum / channels);
      }
      return;
    }
    for (let i = 0; i < frames; i += 1) {
      let sum = 0; for (const plane of planes) sum += plane[i] || 0;
      sourceSamples.push(sum / channels);
    }
  }

  async function consume() {
    try {
      while (!stopped) {
        const item = await reader.read();
        if (item.done) break;
        const frame = item.value;
        outstandingFrames += 1;
        framesRead += 1;
        if (framesRead === 1) { onStage("first_frame_received"); }
        try {
          inputSampleRate = inputSampleRate || Number(frame.sampleRate) || outputSampleRate;
          toMono(frame);
          emitFrames();
        } finally {
          try { frame?.close?.(); } finally { framesClosed += 1; outstandingFrames -= 1; }
        }
      }
    } catch { /* bounded processing failure; cleanup remains authoritative */ }
    finally { pipelineSettled = true; }
  }

  return {
    async start() {
      if (!track) { const e = new Error("no audio track"); e.code = "NO_AUDIO_TRACK"; throw e; }
      if (!isTrackProcessorAudioSupported(ProcessorImpl)) { const e = new Error("unsupported"); e.code = "TRACK_PROCESSOR_UNSUPPORTED"; throw e; }
      try { processor = new ProcessorImpl({ track }); } catch (cause) { const e = new Error("processor construction failed"); e.code = "TRACK_PROCESSOR_CONSTRUCTION_FAILED"; e.name = cause?.name; throw e; }
      onStage("processor_constructed");
      try { reader = processor?.readable?.getReader?.(); } catch (cause) { const e = new Error("reader acquisition failed"); e.code = "READER_ACQUISITION_FAILED"; e.name = cause?.name; throw e; }
      if (!reader) { const e = new Error("reader acquisition failed"); e.code = "READER_ACQUISITION_FAILED"; throw e; }
      onStage("reader_acquired");
      stopped = false;
      loopPromise = consume();
      onStage("processing_loop_started");
      await Promise.resolve();
    },
    beginCancellation() {
      if (cancellationHandle) return cancellationHandle;
      stopped = true;
      let cancelPromise = Promise.resolve();
      if (reader) {
        try {
          cancelPromise = Promise.resolve(reader.cancel()).then(
            () => { cancelSettled = true; },
            () => { cancelSettled = true; },
          );
        } catch { cancelSettled = true; }
      } else cancelSettled = true;
      cancellationHandle = { cancelPromise, started: true };
      return cancellationHandle;
    },
    drainAfterCaptureRelease() {
      if (cleanupPromise) return cleanupPromise;
      const handle = cancellationHandle || this.beginCancellation();
      cleanupPromise = (async () => {
        await handle.cancelPromise;
        if (reader) { try { reader.releaseLock(); } catch { /* already released */ } }
        try { await loopPromise; } catch { /* pipeline is terminal */ }
        return diagnostics();
      })();
      return cleanupPromise;
    },
    stop() {
      if (cleanupPromise) return cleanupPromise;
      this.beginCancellation();
      return this.drainAfterCaptureRelease();
    },
    diagnostics,
  };
}
