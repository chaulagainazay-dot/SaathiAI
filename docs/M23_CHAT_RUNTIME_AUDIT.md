# M23 — Chat Runtime Audit

## Scope

Inventory of every SaathiOS chat entrypoint and execution path after Platform M23
(Full Governed Chat Default and Conversation Runtime Migration).

Baseline HEAD: `232ff78` (M22 tip). Branch: `milestone/m7-security-engine`.

## Summary invariants

```text
UNKNOWN = 0
UNCLASSIFIED_CHAT_PATHS = 0
DIRECT_CHAT_PROVIDER_EXECUTION = 0
legacy production chat paths = 0
chat residual exceptions = 0
governed_chat_default = true
legacy_chat_execution = unavailable
production_certified = false
```

## Path inventory

| Path ID | File | Symbol | Surface | Auth | Caller | Conv ID | Session | Context | System prompt | History | Model | Provider | Stream | Cancel | Tools | Persist | Cost | Privacy | Prod | Authority | Classification | M23 action | Tests |
|---------|------|--------|---------|------|--------|---------|---------|---------|---------------|---------|-------|----------|--------|--------|-------|---------|------|---------|------|-----------|----------------|------------|-------|
| CHAT-01 | saathi/chat/api.py | send_message | HTTP POST /api/v1/chat/.../messages | global /api/v1 | chat_engine | path cid | inherited | context builder via engine | compose layers | store list | ModelRouter | adapters | SSE compat | client disconnect | gateway only | ChatStore | preflight bounds | internal | yes | chat.runtime | CANONICAL_CHAT_ENTRY / STREAMING_ENTRY / NON_STREAMING_ENTRY | MIGRATE_NOW→done | test_m23, test_chat |
| CHAT-02 | saathi/chat/api.py | regenerate / edit | HTTP | global | chat_engine | message→cid | inherited | engine | same | store | ModelRouter | adapters | no | n/a | n/a | ChatStore | same | internal | yes | chat.runtime | COMPATIBILITY_ENTRY | via send | test_chat |
| CHAT-03 | saathi/chat/api.py | call_tool | HTTP tools | global | chat_engine | message→cid | inherited | n/a | n/a | n/a | n/a | n/a | no | n/a | ExecutionGateway | ChatStore tool rows | n/a | internal | yes | ExecutionGateway | CANONICAL_CHAT_ENTRY (tools separate) | UNCHANGED authority | test_chat |
| CHAT-04 | saathi/chat/api.py | run_agent / team-run | HTTP | global | chat_engine | cid | inherited | engine+agent role | AGENT_ROLES | store | ModelRouter | adapters | no | n/a | gateway/orch | ChatStore | same | internal | yes | chat.runtime / M10 orch | INTERNAL_CHAT_CALLER | via send | test_chat |
| CHAT-05 | saathi/chat/engine.py | ChatEngine.send | internal | actor user:ajay | chat_engine | required | local | build_chat_context | CANONICAL_BASE + layers | store | ModelRouter | adapters | via API only | n/a | call_tool separate | ChatStore | token counters | internal | yes | chat.runtime | CANONICAL_CHAT_ENTRY | MIGRATE_NOW→done | test_m23, test_chat |
| CHAT-06 | saathi/chat/engine.py | _default_llm / ChatLLMAdapter | internal | n/a | chat_engine | via intent meta | n/a | pre-built prompt | system arg | n/a | ModelRouter | adapters | no | n/a | off | execution row | n/a | internal | yes | chat_adapter→runtime | CANONICAL_CHAT_ENTRY | MIGRATE_NOW→done | test_m23 |
| CHAT-07 | saathi/inference/chat_adapter.py | chat_generate | compat facade | n/a | chat_engine | optional | n/a | direct prompt | system arg | n/a | ModelRouter | adapters | no | cancel token | off | none | preflight | internal | yes | chat.runtime only | COMPATIBILITY_ENTRY | thin wrap only | test_m23, test_m21_3 |
| CHAT-08 | saathi/chat/runtime.py | run_chat_completion | sole runtime | caller policy | chat_engine | optional | optional | ContextBuildResult or prompt | policy | optional | ModelRouter + optional gateway local | http_providers / ollama | delivery via run_chat_stream | mark_cancelled | denied default | none (engine persists) | ceiling 0 cloud | policy | yes | CANONICAL | CANONICAL_CHAT_ENTRY | NEW | test_m23 |
| CHAT-09 | saathi/chat/runtime.py | run_chat_stream | stream lifecycle | same | chat_engine | optional | optional | same | same | same | same | same | yes | yes | off | none | same | same | yes | stream_events | STREAMING_ENTRY | NEW | test_m23 |
| CHAT-10 | saathi/chat/context.py | build_chat_context | context authority | n/a | n/a | required for hist | n/a | history+layers | compose_system_prompt | select_history | n/a | n/a | n/a | n/a | tool_policy text only | n/a | token estimate | safe meta | yes | CANONICAL | CANONICAL | NEW | test_m23 |
| CHAT-11 | saathi/chat/store.py | ChatStore | persistence | local single-user | n/a | PK | n/a | n/a | n/a | messages | stored model field | n/a | n/a | n/a | tool_invocation | sole store | tokens_in/out | content at rest | yes | CANONICAL store | CANONICAL | unchanged authority | test_chat |
| CHAT-12 | saathi/voice_os/bridge.py | VoiceBridge | voice→chat | local | chat_engine | created | n/a | engine | engine | store | via engine | via engine | no | n/a | orch optional | ChatStore | via engine | internal | yes | ChatEngine | INTERNAL_CHAT_CALLER | uses engine only | test_voice_os |
| CHAT-13 | saathi/studio_os/service.py | StudioService | studio | local | chat_engine | via engine | n/a | engine | engine | store | via engine | via engine | no | n/a | n/a | ChatStore | via engine | internal | yes | ChatEngine | INTERNAL_CHAT_CALLER | uses engine only | test_studio_os |
| CHAT-14 | tests/* | inject_fn / mocks | test | n/a | test_* | tmp | n/a | fixtures | fixtures | fixtures | fake | fake | various | various | mocked | tmp db | n/a | test | no | inject only | TEST_ONLY | keep | test_m23 |

## Classifications achieved

| Class | Count (prod-relevant) |
|-------|----------------------|
| CANONICAL_CHAT_ENTRY | CHAT-01,05,06,08 |
| COMPATIBILITY_ENTRY | CHAT-07 (thin only) |
| INTERNAL_CHAT_CALLER | CHAT-12,13,04 |
| STREAMING_ENTRY | CHAT-01 stream, CHAT-09 |
| NON_STREAMING_ENTRY | CHAT-01 non-stream |
| TEST_ONLY | CHAT-14 |
| UNKNOWN | **0** |
| DIRECT_CHAT_PROVIDER_EXECUTION | **0** |

## Previous vs new default

| | Before M23 | After M23 |
|--|------------|-----------|
| Default path | chat_adapter → optional governed → **llm.generate sink** | chat_adapter → **chat.runtime only** |
| Residual exception | chat_engine_legacy_sink | **removed** |
| Caller certification | LEGACY | PILOT (governed callable) |
| Provider HTTP | via llm facade | via adapters.http_providers / gateway local |

## System prompt sources (inventory)

| Source | Classification |
|--------|----------------|
| CANONICAL_BASE_PROMPT in context.py | CANONICAL_BASE |
| AGENT_ROLES in engine.py | PRODUCT_POLICY / agent role |
| User `system` override on send | CONVERSATION_OVERRIDE |
| Project context | PRODUCT_POLICY |
| Conversation summary | CONVERSATION_OVERRIDE (bounded) |
| Memory context block | PRODUCT_POLICY (existing M9) |
| Knowledge/RAG chunks | PRODUCT_POLICY (existing) |
| Tool policy string | TOOL_POLICY (text only; no execution) |

Composition order is deterministic in `compose_system_prompt`. Raw composed system prompt is not logged.

## Trading Guardian

```text
UNCHANGED
UNENGAGED
LIVE TRADING NOT AUTHORIZED
```
