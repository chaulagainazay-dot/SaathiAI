# VOICE_TECHNOLOGY_DECISION

Evaluation for SaathiOS (Python backend, Next.js UI, 8 GB Apple Silicon, local-first).

| Technology | Classification | Rationale |
| --- | --- | --- |
| **SaathiOS VoiceSession contract** | **KEEP** (authority) | Platform-owned boundary; frameworks adapt behind it |
| Browser Web Speech API | **KEEP** (adapter) | Existing STT path; no credentials; limited quality/locale |
| Platform SpeechService / local say | **KEEP** (adapter) | Existing TTS without cloud credentials |
| **Pipecat** | **INTEGRATE_LATER / ADAPT** | Strong real-time orchestration candidate for V-NEXT-2 behind our contract — not authority today |
| **LiveKit Agents** | **DEFER** | Excellent for remote/mobile WebRTC rooms; overkill for local private-alpha now |
| openWakeWord | **INTEGRATE_LATER** | Wake word only after single owner exists |
| Silero VAD / equivalent | **INTEGRATE_LATER** | Feeds interrupt API; not implemented in V-NEXT-1 |
| whisper.cpp / faster-whisper | **DEFER** (benchmark later) | Local STT quality; RAM pressure on 8 GB — measure before pin |
| Native WebRTC | **DEFER** | Needed for multi-device; not V-NEXT-1 |
| Cloud speech SDKs | **REJECT** (this program) | Credentials / network policy |

## Decision

```text
SaathiOS-owned VoiceSession boundary
+ framework adapters later (Pipecat-class for VAD/streaming)
```

Pipecat / LiveKit must not become architectural authority.
