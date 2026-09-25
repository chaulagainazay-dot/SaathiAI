# LOCAL_STT_ADAPTER

## Module

`saathi-os/lib/voice-session/local-streaming-stt.js`

## Contract

Implements `StreamingTranscriptionAdapter`:

- `start` / `cancel` / `close` / `flush`
- `pushAudio(pcm, meta)` — **including pre-roll**
- `onPartial` / `onFinal`
- `health` / `capabilities`

## PCM path

```text
AudioInputOwner (single mic)
    → AudioFrameTap / VAD
    → PreRollBuffer + live PCM
    → LocalStreamingSttAdapter.pushAudio
    → TurnCoordinator (normalized events)
```

Browser adapter still cannot ingest PCM (metadata note only).

## Production wiring

- Factory-injected via `createRealtimeVoicePipeline({ localSttFactory })`
- Not auto-primary until multilingual gate passes
- Engine types do not leak into VoiceSession snapshot beyond privacy/model labels

## Helper note

A Node/Python decode helper may back `transcribeFn` in future live runs; unit tests use hint-driven local adapter.

