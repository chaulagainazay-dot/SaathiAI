# PRIVACY_CLASSIFICATION

| Engine | Class | UI label |
| --- | --- | --- |
| faster-whisper / whisper.cpp (on-device) | **LOCAL_CONFIRMED** | `Local · Whisper [model]` |
| Mock STT (tests) | **LOCAL_CONFIRMED** | Mock · Local test |
| Browser SpeechRecognition | **PLATFORM_MANAGED_UNKNOWN** | `Browser · Privacy unknown` |
| Cloud STT | **REMOTE** | not used |
| Apple SFSpeech (unverified) | LOCAL_WITH_SYSTEM_DEPENDENCY | deferred |

## Rules

- Never label browser STT as offline or private.
- Show `LOCAL SPEECH` / Local only when LOCAL_CONFIRMED.
- Command strip uses `formatVoiceInputLabel()`.

