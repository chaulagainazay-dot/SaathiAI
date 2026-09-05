# V_NEXT_2_RECOMMENDATION

Recommended next mission:

```text
V-NEXT-2 — REAL-TIME VAD, BARGE-IN AND STREAMING SPEECH PIPELINE
```

Behind VoiceSession interrupt API:

1. Silero (or equivalent) VAD → `interrupt('SPEECH_DETECTED')` when implemented
2. Evaluate Pipecat as orchestration adapter (not authority)
3. Benchmark whisper.cpp/faster-whisper on 8 GB Mac before pinning
4. Defer LiveKit until remote/mobile rooms required

Do not start without separate authorization.
