# CONSUMER_MIGRATION_MATRIX

| Consumer | Classification | Notes |
| --- | --- | --- |
| VoiceSessionProvider | CANONICAL | Shell root |
| VoiceSessionManager | CANONICAL | Orchestrator |
| VoiceRuntimeProvider | ADAPTER | Uses input claim + manager |
| VoiceOutputProvider | ADAPTER | Uses output claim + manager |
| CommandComposer /command | CANONICAL_CONSUMER | Mic via runtime toggle only |
| Chat VoiceControl | COMPATIBILITY_WRAPPER | Input claim; still speechSynthesis path |
| Settings voice | COMPATIBILITY | Page-local tests |
| Legacy /voice | DEPRECATED | Enrollment |
| useVoice / MobileMic | REMOVE_LATER | Documented residual |
