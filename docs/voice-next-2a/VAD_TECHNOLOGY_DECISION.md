# VAD_TECHNOLOGY_DECISION

| Candidate | Classification | Notes |
| --- | --- | --- |
| **Energy + ZCR VAD (in-process)** | **INTEGRATE** (V-NEXT-2A) | Tiny RAM/CPU, deterministic tests, language-independent, no model download on 8 GB host |
| **Silero VAD** | **ADAPT / INTEGRATE_LATER** | Strong accuracy; ONNX/WASM cost deferred until energy VAD proven insufficient in owner audio review |
| WebRTC VAD | **DEFER** | C binding / native; less ideal pure browser path |
| Pipecat local VAD | **DEFER to 2B** | Orchestration layer, not needed for sensor-only VAD |
| Cloud VAD | **REJECT** | Credentials / network policy |

## Decision

```text
Energy/ZCR VoiceActivityDetector — INTEGRATE now
Silero-class neural VAD — ADAPT behind same contract later if needed
```

Same `VoiceActivityDetector` interface for both.
