# M23 — Canonical Chat Architecture

## Target flow

```text
HTTP / WebSocket / CLI / UI / internal chat caller
→ chat request contract (saathi.chat.request.ChatRequest)
→ authenticated session and conversation resolution
→ canonical context builder (saathi.chat.context)
→ explicit chat caller policy (chat_engine)
→ canonical InferenceRequest
→ governed runtime (saathi.chat.runtime.run_chat_completion)
→ ModelRouter
→ governed provider adapter (http_providers / OllamaEngine)
→ typed result or canonical stream events
→ response mapper (to_llm_dict / SSE wire)
→ conversation ledger (ChatStore) and privacy-safe telemetry
```

## Modules

| Module | Role |
|--------|------|
| `saathi/chat/request.py` | ChatRequest contract + validation → InferenceRequest mapping |
| `saathi/chat/context.py` | Sole context / history / system prompt authority |
| `saathi/chat/stream_events.py` | Canonical stream event model + wire mapping |
| `saathi/chat/runtime.py` | Sole production chat execution path |
| `saathi/inference/chat_adapter.py` | Thin compatibility facade (no provider execution) |
| `saathi/chat/engine.py` | Product send pipeline; gateway + store; uses adapter |
| `saathi/chat/store.py` | Sole conversation persistence authority |
| `saathi/chat/api.py` | HTTP surface; SSE via stream_events |

## Invariants

```text
default chat path = governed runtime
legacy chat provider execution = 0
unknown chat paths = 0
direct provider calls from chat = 0
chat-specific provider retries = 0
chat-specific provider fallbacks = 0
raw prompt logging = 0
raw output logging = 0
production_certified = false
```

## Streaming vs non-streaming

Governance is identical. Delivery differs only:

* Non-streaming: `run_chat_completion` → dict / SendResult
* Streaming: complete then `stream_lifecycle` emits ordered start/delta/done (compat SSE names)

Provider SDK stream objects never escape.

## Tool governance

* `tool_mode` defaults **off**
* `chat_engine.tools_allowed = false`
* Chat runtime never executes tools
* `ChatEngine.call_tool` remains ExecutionGateway-only
* Trading / withdrawal tools forbidden in chat package

## Compatibility

Public HTTP shapes, conversation IDs, SendResult fields, and
`{text, provider, tokens}` LLM adapter contract are preserved.
