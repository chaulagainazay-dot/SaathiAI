# VOICE_RUNTIME_INVENTORY

**Primary evidence tip:** private-alpha / full-e2e chain (contained in recommended baseline).  
**Sources:** committed `docs/e2e-functional-audit/VOICE_*`, frontend under `saathi-os/`, backend voice tests M74/M77/M79.

## Implementation inventory

| ID | Classification | Owners / files | Mic owner? | Audio out owner? |
| --- | --- | --- | --- | --- |
| global_voice_output | IMPLEMENTED_AND_EXPOSED | `VoiceOutputProvider.jsx`, `VoiceOutputDock.jsx`, `lib/voice-output.js` + platform SpeechService | No | **Yes** (primary platform playback) |
| global_voice_runtime | BROWSER_DEPENDENT | `VoiceRuntimeProvider.jsx`, `VoiceRuntimeDock.jsx`, `lib/voice-runtime.js` | **Yes** (getUserMedia + SpeechRecognition) | Delegates to VoiceOutputProvider |
| chat_voice_control | CHAT_ONLY | `components/chat/VoiceControl.jsx` | **Yes** (separate) | **Yes** (speechSynthesis) |
| settings_voice | IMPLEMENTED_AND_EXPOSED | `app/settings/voice/page.jsx`, `lib/voice-settings.js` | Test-only mic | Browser TTS test |
| legacy_enrollment | PARTIALLY_IMPLEMENTED | `app/voice/page.jsx` | MediaRecorder | N/A |
| server speech API | IMPLEMENTED | platform `/api/v1/platform/voice/*` | N/A | Server TTS artifacts |
| legacy voice sessions | IMPLEMENTED | `/api/v1/voice/sessions` | N/A | interrupt path for chat |

## Lifecycle & cleanup

| Concern | State |
| --- | --- |
| Route-change cleanup | **Addressed** in E2E recovery (stop speech + release mic) — tests `e2e-voice-route-cleanup` |
| Logout cleanup | Claimed via platform context events |
| Independent mic owners | **≥3** (runtime, chat, settings/enrollment) |
| Independent audio output owners | **≥2** (VoiceOutputProvider, chat speechSynthesis) |
| Cancel output before mic open | **Repaired** (DEFECT-007 / interruption decision OPTION_A) |

## Interruption model

| Mode | Present? |
| --- | --- |
| Push-to-talk / explicit mic | **YES** (platform runtime) |
| Half-duplex (input interrupts output on mic press) | **YES** after repair — `VOICE_INPUT_INTERRUPTS_OUTPUT` |
| Full duplex | **NO** |
| True acoustic barge-in / continuous VAD during playback | **NO** |
| Chat stack recognition-result interruption | **YES** within chat only |

## Governance

| Question | Answer |
| --- | --- |
| Can voice bypass tool governance? | Transcripts submit to platform/chat bridges; **should** enter normal tool/approval paths — no evidence voice grants ExecutionGateway authority |
| Voice activation grants execution authority? | **Must not** — architecture forbids; no contrary code path certified |
| External speech providers | **Disabled / intentionally unavailable** |
| Nepali TTS | **INTENTIONALLY_UNAVAILABLE** when no local `ne-*` voice |
| Offline mode | Partial — browser recognition locality not guaranteed; server TTS local when SpeechService local |
| Owner audible review | Checklist exists (`MANUAL_AUDIO_CHECKLIST.md`); not re-run in this audit → **UNVERIFIED** for this mission |

## Next bounded voice milestone (recommendation only)

**V-NEXT-1 — Single audio owner consolidation (no streaming architecture):**  
Unify mic/playback ownership so chat and platform runtime share one capture stack and one playback stack; keep push-to-interrupt; add latency metrics surface; still no full-duplex/VAD barge-in.

Do **not** start this milestone in the integration mission without separate authorization.
