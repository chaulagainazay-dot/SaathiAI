# AUDIO_FRAME_PIPELINE

```
getUserMedia (once, AudioInputOwner claim)
        │
        ├── SpeechRecognition / STT adapter
        │
        └── AudioFrameTap (AnalyserNode)
                │
                ├── PreRollBuffer (memory, ~280ms)
                └── EnergyVad.processAudioFrame
                        │
                        speech_start / speech_end
                        │
                 BargeInController / VoiceSessionManager
```

**Forbidden:** second getUserMedia solely for VAD.

Headless/tests: `processVadFrame` injects synthetic frames without mic.
