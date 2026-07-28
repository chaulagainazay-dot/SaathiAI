# M80–M86 — SaathiOS Live Conversational Intelligence

Date: 2026-07-28

Terminal verdict: `LIVE_CONVERSATIONAL_INTELLIGENCE_COMPLETE_WITH_LIMITATIONS`

## Milestone map

| Milestone | Scope | Status |
| --- | --- | --- |
| M80 | ConversationService + provider contract | Complete |
| M81 | Local Ollama NDJSON streaming + cancel + late-chunk reject | Complete |
| M82 | Yeti persona, context builder, session memory | Complete |
| M83 | Authority-safe tool intent routing (propose only) | Complete |
| M84 | Voice Runtime + Live Voice UI wired to ConversationService | Complete |
| M85 | STT browser path + synthetic browser media cert | Complete with limitations |
| M86 | Full certification evidence | Complete with limitations |

## Architecture

Central package: `saathi/platform/conversation/`

- `ConversationService` — sole conversational intelligence path for Live Voice
- `OllamaConversationProvider` — localhost-only real NDJSON stream
- `UnavailableConversationProvider` — truthful fail-closed
- `InjectedConversationProvider` — tests only (not model intelligence)
- `ConversationContextBuilder` + `SessionMemory` — bounded multi-turn
- `ToolIntentRouter` — propose/block only; never executes
- Yeti persona via `yeti_system_prompt`

Voice Runtime `ConversationRuntime` no longer emits deterministic templates as
intelligence. Empty/unavailable is fail-closed; production path uses
`ConversationService`.

## Real generation proof

- Provider: `ollama_local`
- Model: `qwen2.5:1.5b` (already installed; 986 MB; preferred for M2/8 GB)
- Streaming: Ollama `/api/chat` NDJSON (`stream: true`)
- Two-turn context retained in SessionMemory
- Evidence: `docs/evidence/m86/M86_CERTIFICATION_SUMMARY.json`

## Security / authority

- Frontend never calls model providers
- Model cannot execute tools
- Trading intents blocked; mission/approval intents require gateway path
- No auto model download; localhost Ollama only
- shell=False; no public listeners; logout clears memory + voice sessions

## Limitations

- English-primary; small-model factual drift possible
- Synthetic browser media certified; human mic not automation-certified
- Whisper/macOS STT remain optional
- Production not authorized
- Full frontend ESLint/build/full 5k backend suite may be run post-commit as capacity allows

## Production

Not authorized. No push, merge, deploy, credentials, or Trading Guardian change.
