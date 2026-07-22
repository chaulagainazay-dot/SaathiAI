# M21.3 Chat Compatibility

## Previous path

```text
ChatEngine.send → gateway ToolIntent → ChatLLMAdapter → _default_llm → llm.generate
```

## New path

```text
ChatEngine.send → gateway ToolIntent → ChatLLMAdapter → _default_llm
  → chat_adapter.chat_generate
    → preflight (caller chat_engine)
    → optional governed local (if flags + governed-callable)
    → EXPLICIT_LEGACY_EXCEPTION sink: llm.generate (caller_id=chat_engine)
```

## Preserved

* Public chat API (`ChatEngine.send`, regenerate, agents, tools)
* Return shape `{text, provider, tokens}`
* Session / memory / RAG pipeline
* ExecutionGateway audit trail
* Local-first posture; no silent cloud fallback (`cloud_fallback_allowed=false` on chat policy)

## Kill / cloud

* `SAATHI_INFERENCE_KILL_ALL` blocks before provider
* Provider kills checked inside `llm.generate` chain
* Cloud only via historical ModelRouter privacy when policy allows; no automatic cloud failover loop

## Remaining limitations

* Chat still not fully on governed path by default (legacy certification)
* Streaming not newly added; streaming permission remains policy-controlled
* Full chat migration target: **M23**
* Do not claim "chat fully migrated" — classification is COMPATIBILITY_WRAPPED
