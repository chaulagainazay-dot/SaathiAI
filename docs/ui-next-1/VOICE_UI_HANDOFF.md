# VOICE_UI_HANDOFF — for V-NEXT-1

## Current mic/playback owners (unchanged)

| Owner | Files |
| --- | --- |
| VoiceRuntimeProvider | `components/voice/VoiceRuntimeProvider.jsx` |
| VoiceOutputProvider | `components/voice/VoiceOutputProvider.jsx` |
| Chat VoiceControl | `components/chat/VoiceControl.jsx` |
| Settings page tests | `app/settings/voice/page.jsx` |
| Legacy enrollment | `app/voice/page.jsx` |

## UI-NEXT-1 handoff

- `mapVoiceSessionViewState` + authority voice chip
- Command composer shows reserved states; does not open mic
- Copilot remains text path

## V-NEXT-1 must do

- Single audio owner
- Command consumes one VoiceSessionViewState source
- No VAD/wake word in UI-NEXT-1 (not done)
