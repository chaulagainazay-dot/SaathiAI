# SaathiOS Real-Time Voice Runtime Final Report

Status: complete with limitations.

## 1. Final verdict

`REALTIME_VOICE_RUNTIME_COMPLETE_WITH_LIMITATIONS`.

SaathiOS now has a centralized real-time Voice Runtime on top of the certified
speech-output foundation. A signed-in user can press one microphone control,
speak, receive partial transcription, get a spoken Yeti reply, interrupt while
the assistant is talking, continue the conversation, and clear voice state on
logout.

## 2. Recovery verification

- Repository path: `/Users/macbookpro/SaathiAI`
- Branch: `milestone/m61-backend-workflow-persistence`
- Expected starting HEAD:
  `70d08932cc4e4c473f7af1db898c74bd6fd25c13` — verified
- Pre-existing dirty tree preserved and excluded from mission commits:
  `docs/evidence/m25`, `docs/evidence/m27`, `docs/evidence/m28`,
  untracked `docs/design-spec/`
- Autonomous Mission Runtime, Platform Runtime, and SpeechService were not
  redesigned

## 3. Ending branch/SHA

- Branch unchanged: `milestone/m61-backend-workflow-persistence`
- Ending SHA: recorded after mission commit (see git log)

## 4. New milestones

- **M79** — Real-Time Voice Runtime foundation and certification with limitations

## 5. Architecture

Central package: `saathi/platform/voice/runtime/`

Reuses: Platform identity/store/audit/RBAC, SpeechService (M74), unified shell,
Yeti profile (`yeti_teacher`).

Does not replace: Mission Runtime, ExecutionGateway, Approvals, ModuleRegistry,
macOS TTS provider, identity core.

## 6. Voice Runtime components

| Module | Responsibility |
| --- | --- |
| VoiceSessionManager | Session CRUD, listen/turn/interrupt/finish, logout clear |
| VoiceInputService | push/hold/toggle modes; idle/listening/recording/processing/error/cancel |
| VoiceActivityDetector | speech start/end, silence timeout, min speech, interruption energy |
| STT providers | macos_speech, whisper_compatible, browser, unavailable |
| ConversationRuntime | IDLE/LISTENING/THINKING/RESPONDING/INTERRUPTED/FINISHED/FAILED |
| SpeechRuntime | Segment incremental speak via SpeechService |
| AudioPlaybackController | play/pause/resume/stop/queue/cancel; no overlap |

## 7. Streaming behavior

- Browser STT interim results → partial transcripts
- Conversation stream chunks → partial assistant text
- SpeechRuntime emits completed sentence segments to SpeechService without
  waiting for the entire reply when sentence boundaries exist

## 8. Interruption support

Barge-in stops exclusive playback, cancels remaining synthesis, preserves
completed/partial assistant text as interrupted transcript, records interruption
history, and returns immediately to LISTENING.

## 9. Browser certification

- Deterministic API + client unit certification: PASS
- Live getUserMedia human journey: code-complete; not claimed automation-certified
  (sandboxed browsers often cannot grant microphone)

## 10. Test results

| Suite | Result |
| --- | --- |
| tests/test_m79_voice_runtime.py + api | 17 passed |
| tests/test_m74_voice_* | 15 passed |
| saathi-os voice frontend contracts | 10 passed |
| secret pattern scan (mission files) | clean |
| shell=True in platform/voice | none |
| import smoke | ok |

## 11. Security review

- Microphone permission required before listen
- Tenant + user ownership on sessions
- No raw audio SQLite persistence
- No unauthorized playback without VOICE_SPEAK
- Safe temp WAV for STT helper path with cleanup
- Cancellation, queue limits, memory limits, timeouts
- shell=False / argv arrays only
- No public listeners
- Logout clears voice sessions + speech cancel

## 12. Resource usage

- No VoxCPM/Whisper auto download
- Energy VAD is pure Python/local
- Speech synthesis still bounded by M74 SpeechService workers/queue

## 13. Known limitations

1. Browser automation often cannot complete real mic capture
2. macOS STT helper optional / not installed by default
3. Whisper only if already present
4. Default Yeti replies are deterministic templates unless chat_fn injected
5. Production not authorized

## 14. Mission success answers

1. **Can SaathiOS now hold a live voice conversation?**  
   Yes, through the authenticated Voice Runtime + shell Live Voice path
   (deterministic/backend certified; human mic depends on browser permission).
2. **Can users interrupt it while it is speaking?**  
   Yes — barge-in stops playback/synthesis and resumes listening.
3. **Is streaming transcription working?**  
   Yes for browser STT partials via `/transcript` partial path.
4. **Is streaming speech working?**  
   Yes at segment level via SpeechRuntime → SpeechService (sentence boundaries).
5. **Which STT providers are certified?**  
   - `browser` — ready (client recognition)  
   - `whisper_compatible` — available only if installed; no auto-install  
   - `macos_speech` — available only with local helper  
   - `unavailable` — truthful fail-closed  
6. **Is production authorized?**  
   **No.**
