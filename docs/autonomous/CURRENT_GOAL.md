# Current Autonomous Goal

- Goal: SaathiOS Real-Time Voice Runtime — transform SaathiOS from text+TTS into
  a real-time, interruptible, streaming voice assistant.
- Scope: centralized Voice Runtime (session, input, VAD, STT, conversation,
  SpeechRuntime over SpeechService, exclusive playback), RBAC extensions,
  authenticated platform APIs, unified-shell live voice UI, Yeti conversation
  modes, logout cleanup, tests and certification evidence.
- Non-goals: redesign of Platform/Mission/SpeechService/Identity/RBAC core/
  ExecutionGateway/Approvals/Evidence/Audit/Notifications/ModuleRegistry;
  automatic Whisper model download; paid STT; voice cloning; Trading Guardian
  changes; production activation; push/merge/deploy.
- Historical baseline supplied by the goal:
  `70d08932cc4e4c473f7af1db898c74bd6fd25c13`
- Branch: `milestone/m61-backend-workflow-persistence`
- Current phase: M79 complete with intentional browser/STT-provider limitations.
- Terminal verdict: `REALTIME_VOICE_RUNTIME_COMPLETE_WITH_LIMITATIONS`
- Production: not authorized.
