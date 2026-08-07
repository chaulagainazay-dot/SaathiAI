# OWNER_ACCENT_REPORT

Owner subset used only where `SPEECH_DETECTED` (RMS gate).

| Engine | owner intent (proxy) |
| --- | --- |
| Omni CTC 300M | 0.0 |
| Whisper CS Small | not re-run on owner in this mission |

Omni owner results are poor (near-zero intent). Whisper owner comparison deferred (historical champion remains best on TTS corpus).

Browser SpeechRecognition: not re-measured; privacy stays `PLATFORM_MANAGED_UNKNOWN`.

