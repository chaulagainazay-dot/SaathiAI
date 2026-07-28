# Autonomous Task Queue

## Active

- None. Real-time voice goal closed with limitations after M79.

## Pending

- Optional: bind production ChatEngine as ConversationRuntime `chat_fn`
- Optional: human browser mic + interrupt journey recording
- Optional: local macOS STT helper packaging (no auto-install)

## Completed

- M79 — Real-Time Voice Runtime: VoiceSessionManager, VoiceInputService, VAD,
  provider-neutral STT (macOS helper / Whisper-compatible / browser / unavailable),
  ConversationRuntime, SpeechRuntime over SpeechService, AudioPlaybackController,
  RBAC (`voice.listen`, `voice.transcribe`, `voice.session.read`), authenticated
  platform APIs, shell Live Voice dock, logout cleanup, 17 backend + 10 frontend
  tests, M74 regression retained.
- M78 — browser re-certification and playback hardening for voice output foundation.
- M73–M77 — Voice Output Foundation.
- M69–M72 — Autonomous Mission Runtime.

## Blocked

- None for local real-time voice foundation.

## Deferred

- Automatic Whisper model download (forbidden)
- Paid STT/TTS providers
- Voice cloning
- Production activation
- Trading Guardian changes
