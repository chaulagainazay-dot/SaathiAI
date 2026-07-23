# M47.7 — Chat / Copilot Runtime Evidence

**Date:** 2026-07-23  
**Transport:** shared `/api/v1/chat/*` via `afetch` + `API_BASE`  
**Surfaces:** `/chat` full (`data-chat-mode="full"`) · Ask Saathi panel compact (`data-chat-mode="compact"`)

## Chat workspace (`/chat`)

| Check | Result |
|---|---|
| Route loads, non-blank | ✅ |
| Full mode chrome | ✅ `data-chat-mode="full"` |
| New chat / search / composer | ✅ |
| Safe send without live auth/model | ✅ honest error (not success) |
| False success claim | ❌ none |
| Privileged execution claim | ❌ none |
| Stop control in code | ✅ `AbortController` + Stop button when `busy` |
| Live stream + Stop cancel | ⚠️ not exercised (no session/model in cert) |

## Copilot panel

Tested open via `]` on:

`/` `/command` `/missions` `/projects` `/approvals` `/monitoring` `/business` `/settings`

| Check | Result |
|---|---|
| Panel opens | ✅ |
| Compact ChatWorkspace | ✅ |
| “Shared chat transport” badge | ✅ |
| Authority advisory badge | ✅ |
| Full chat link | ✅ |
| Escape closes | ✅ |
| Team/voice/timeline parity falsely claimed | ❌ not claimed (compact + footer copy) |

## Coherence

| Check | Result |
|---|---|
| Compact panel + full `/chat` both present | ✅ |
| Classification | `shared_transport_two_presentations` |
| Dual systems presented as one conversation | ❌ not observed |

## Streaming / Stop

```text
STREAMING_PATH = CODE_PRESENT + UNAVAILABLE_WITHOUT_AUTH
STOP_PATH = ABORTCONTROLLER_WIRED
STOP_LIVE_EXERCISE = NOT_RUN (no deterministic mock stream without credentials)
```

Honest unavailable/error path certified. Live multi-turn streaming requires owner session + model; out of cert credential scope.

## Classification

```text
CHAT_COPILOT_RUNTIME = PASS_WITH_LIMITATIONS
```
