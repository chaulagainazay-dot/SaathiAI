# M79 — Real-Time Voice Runtime Foundation

Date: 2026-07-28

Verdict: `M79_COMPLETE_WITH_LIMITATIONS`

## Outcome

SaathiOS gains a centralized **Voice Runtime** for live, interruptible voice
conversation on top of the certified M74–M78 speech-output foundation.

A signed-in user can:

1. Press one microphone control in the unified shell
2. Speak with explicit mic permission (no background / hidden activation)
3. Receive streaming partial transcripts (browser STT when available)
4. Receive a conversational Yeti reply with spoken output via SpeechService
5. Interrupt (barge-in) while the assistant is speaking
6. Continue the same conversation session
7. Logout and clear live voice state

## Architecture (reuse only)

| Component | Role | Authority reused |
| --- | --- | --- |
| `VoiceSessionManager` | Session lifecycle, interrupt, cleanup | Platform identity, store, audit |
| `VoiceInputService` | Mic lifecycle modes/states | Explicit client gesture only |
| `VoiceActivityDetector` | Speech start/end, silence, barge-in energy | Local energy VAD |
| STT providers | macOS helper / Whisper-compatible / browser / unavailable | No auto model install |
| `ConversationRuntime` | IDLE→…→FAILED states, transcript, interruptions | Deterministic Yeti replies (+ injectible chat) |
| `SpeechRuntime` | Incremental segment speak | **Existing** `SpeechService` |
| `AudioPlaybackController` | Exclusive play/pause/resume/stop/queue/cancel | Prevents concurrent playback |

**Not redesigned:** Platform Runtime, Mission Runtime, SpeechService, macOS TTS
provider, Identity, RBAC (only extended), PlatformAgentRuntime, ExecutionGateway,
Approval Center, Evidence/Audit stores, Notifications, ModuleRegistry, Unified Shell
(shell extended only).

## Permissions added

- `voice.listen`
- `voice.transcribe`
- `voice.session.read`
- (existing) `voice.speak`

Granted to Viewer+ for bounded conversational use.

## API (authenticated platform routes)

Prefix: `/api/v1/platform/voice/runtime/*`

- health, stt-providers
- sessions CRUD/list
- listen / stop / cancel / permission
- transcript (partial + final)
- audio upload (no raw audio persistence)
- interrupt, playback, finish
- logout clears voice sessions

## UI

- `VoiceRuntimeProvider` + `VoiceRuntimeDock` in unified shell
- Mic button, recording/listening/speaking/interruption indicators
- Partial + final transcript view
- Session history details
- No autoplay on page load (speech only after user mic turn)

## Tests

- Backend: 17 new (`test_m79_voice_runtime*.py`)
- M74 regression: 15 passed
- Frontend: voice-runtime + voice-output contracts passed

## Limitations (intentional)

- Full live browser mic + Web Speech + native speak journey is environment-dependent
  (automation often cannot grant getUserMedia)
- macOS STT provider requires an optional local helper (not auto-installed)
- Whisper-compatible only if already installed; no download
- Default conversation replies are deterministic Yeti templates unless a chat_fn is injected
- Production activation is **not** authorized
- No push, merge, deploy, paid provider, cloning, or Trading Guardian change

## Security

- Tenant/user isolation on sessions
- Transcript ownership enforced
- No raw audio in SQLite or audit
- shell=False only (argv arrays)
- No public listeners
- Queue/memory/timeout bounds
- Cancellation + logout cleanup
