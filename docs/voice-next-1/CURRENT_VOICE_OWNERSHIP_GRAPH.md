# CURRENT_VOICE_OWNERSHIP_GRAPH

**Branch tip base:** UI-NEXT-1 @ `d66fa3a`  
**After V-NEXT-1:** canonical owners under `lib/voice-session/*`

## Before (pre V-NEXT-1)

| Owner | Files | Mic | Playback | Lifecycle | Class (before) |
| --- | --- | --- | --- | --- | --- |
| VoiceRuntimeProvider | `components/voice/VoiceRuntimeProvider.jsx` | getUserMedia + SpeechRecognition | delegates VoiceOutputProvider | route hardReset, logout | CANONICAL (platform) |
| VoiceOutputProvider | `components/voice/VoiceOutputProvider.jsx` | no | HTMLAudio + SpeechService poll | route stop, logout | CANONICAL (output) |
| Chat VoiceControl | `components/chat/VoiceControl.jsx` | SpeechRecognition (own) | speechSynthesis (own) | unmount cleanup | LEGACY/COMPAT |
| Settings voice page | `app/settings/voice/page.jsx` | test getUserMedia | speechSynthesis test | page-local | COMPATIBILITY |
| Legacy /voice | `app/voice/page.jsx` | MediaRecorder enrollment | n/a | page-local | DEPRECATED |
| useVoice | `lib/useVoice.js` | MediaRecorder | Audio base64 | hook-local | LEGACY |
| MobileMic | `components/MobileMic.jsx` | may open mic | — | mobile | LEGACY |

## After (V-NEXT-1)

| Layer | Role |
| --- | --- |
| **AudioInputOwner** (`input-owner.js`) | Sole module-level mic claim mutex |
| **AudioOutputOwner** (`output-owner.js`) | Sole module-level playback claim mutex |
| **VoiceSessionManager** | Interrupt policy, session snapshot, telemetry |
| **VoiceSessionProvider** | React publish + route/logout cleanup |
| VoiceRuntimeProvider | **ADAPTER** — acquires input claim via manager |
| VoiceOutputProvider | **ADAPTER** — acquires output claim via manager |
| Chat VoiceControl | **COMPATIBILITY_WRAPPER** — uses input claim |
| CommandComposer | **CANONICAL_CONSUMER** — no mic ownership |
| Settings / legacy / useVoice | **DEPRECATE_LATER** / remaining islands (documented) |

### Invariants

```
AT MOST ONE ACTIVE INPUT OWNER
AT MOST ONE ACTIVE OUTPUT OWNER
START INPUT STOPS OUTPUT (USER_MIC_REQUEST)
ROUTE_CHANGE / LOGOUT release resources
```
