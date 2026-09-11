# V_NEXT_2B_TECHNOLOGY_DECISION

| Layer | Decision |
| --- | --- |
| SaathiOS VoiceSession | **KEEP** (authority) |
| Energy VAD / barge-in | **KEEP** |
| **Pipecat** | **ADAPT / INTEGRATE** for streaming STT/TTS turn orchestration behind VoiceSession |
| LiveKit Agents | **DEFER** until remote/mobile WebRTC rooms |
| Silero neural VAD | **ADAPT** if energy VAD insufficient in field |
| whisper.cpp / faster-whisper | **DEFER** — benchmark 8 GB before pin |

Pipecat must remain an **adapter**, not SaathiOS authority.
