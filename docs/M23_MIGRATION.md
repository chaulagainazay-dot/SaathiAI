# M23 — Migration Notes

## From

```text
chat entrypoint
→ chat_adapter (COMPATIBILITY_WRAPPED)
→ optional governed local
→ legacy sink: saathi.llm.generate
```

## To

```text
chat entrypoint
→ chat_adapter (thin COMPATIBILITY_ADAPTER)
→ saathi.chat.runtime (CANONICAL)
→ preflight + InferenceRequest
→ ModelRouter + governed adapters
  (optional execute_governed_local_inference when gateway flags on)
```

## Removed

* Chat residual exception `chat_engine_legacy_sink`
* `llm.generate` as chat production sink
* `chat_adapter` from `KNOWN_LLM_GENERATE_SITES`
* LEGACY certification on `chat_engine` caller

## Residual exceptions after M23

Count: **2** (was 3)

1. `engine_cloud_caller` → M24
2. `engine_openai_compat` → M24

## Compatibility shims

* `chat_generate(..., legacy_fn=)` accepted as **test inject only** (`path_used=test_injected`)
* SSE event names remain `start` / `delta` / `done` / `error` via `to_wire()`

## Not migrated (out of scope)

* Durable circuit / daily cost (M24)
* Live Ollama certification
* Auth redesign
* New chat product features
