# STT_TECHNOLOGY_DECISION

| Engine | Class | Notes |
| --- | --- | --- |
| **Browser SpeechRecognition** | **INTEGRATE** (V-NEXT-2B) | Real partial/final streaming; no install; privacy PLATFORM_MANAGED_UNKNOWN |
| **MockStreamingStt** | **KEEP** (tests) | Deterministic LOCAL_CONFIRMED |
| whisper.cpp / faster-whisper | **DEFER** | Not installed on host; 8 GB pressure with Ollama models present |
| WhisperKit / Apple | **DEFER** | Native future option |
| sherpa-onnx / Vosk / Moonshine | **DEFER** | Evaluate when offline LOCAL_CONFIRMED required |
| Cloud STT APIs | **REJECT** | No credentials / network policy |

Host check: whisper/faster-whisper **not installed**. Ollama models present (1.5B–8B) — concurrent heavy STT blocked by admission policy.
