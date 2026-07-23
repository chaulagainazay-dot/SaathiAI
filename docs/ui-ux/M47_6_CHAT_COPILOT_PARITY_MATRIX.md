# M47.6 — Chat / Copilot Parity Matrix

**Date:** 2026-07-23  
**Canonical full workspace:** `/chat` (also `/workspace`, `/saathi` wrappers)  
**Compact surface:** Ask Saathi panel → `ChatWorkspace compact`

| Capability | /chat full | Copilot panel | Classification |
|---|---|---|---|
| Shared `/api/v1/chat/*` transport | yes | yes | **PARITY** |
| Session header afetch | yes | yes | **PARITY** |
| Conversation create | yes | yes (New) | **COMPACT_EQUIVALENT** |
| History load | yes | yes | **COMPACT_EQUIVALENT** |
| Streaming deltas | yes | yes | **PARITY** |
| Stop / cancel stream | yes (Stop) | yes | **PARITY** |
| Error not success | yes | yes | **PARITY** |
| Conversation list/search/pin | yes | no | **LEGACY_ONLY_REQUIRED** |
| Agent selector | yes | no (default saathi) | **CANONICAL_ONLY** |
| Team orchestration | yes | no | **CANONICAL_ONLY** |
| Voice control | yes | no | **CANONICAL_ONLY** |
| Execution timeline panel | yes | no | **CANONICAL_ONLY** |
| Memory links panel | yes | no | **CANONICAL_ONLY** |
| Authority advisory notice | partial | yes | **COMPACT_EQUIVALENT** |

## Redirect `/chat`

```text
KEEP_COMPATIBILITY
```

Reason: full workspace has unique required features (team, voice, timeline). Panel is compact-equivalent for core send/stream/history only.

## Outcome

Coherent dual surface: **one transport, two presentations**. Not a redirect candidate.
