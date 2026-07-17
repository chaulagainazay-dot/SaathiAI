# M22 Architecture — Governed Provider Implementation

## Target flow

```text
chat / agent / server / research / tools / compatibility API
→ explicit registered caller
→ preflight / InferenceRequest (as applicable)
→ provider governance (kill, circuit, policy)
→ ModelRouter (sole selection authority)
→ canonical provider adapter / transport
→ typed result
→ compatibility mapping
```

## Modules

| Layer | Module | Role |
|-------|--------|------|
| Facade | `saathi/llm.py` | Compatibility `generate` + `LLMResult` |
| Facade | `saathi/agent.py` | Tool loop / memory orchestration |
| Facade | `saathi/tools/research.py` | Research/deep_plan public API |
| Transport | `adapters/http_providers.py` | Multi-family HTTP generate |
| Transport | `adapters/grounding.py` | Gemini google_search capability |
| Transport | `adapters/agent_provider.py` | Agent SDK session |
| Engine | `adapters/ollama.py`, `openai_compat.py`, `cloud.py`, `fake.py` | Existing engines |
| Gate | `legacy_facade.preflight_inference` | Kill + caller policy |
| Select | `model_router.ModelRouter` | Unchanged sole router |
| Release | `release_check` | Facade purity + SDK allowlist |

## Capability model

* **generate** — all family transports
* **tools** — agent_provider OpenAI/Anthropic sessions only (not http_providers text path)
* **grounding** — grounding adapter only; no silent text-model substitute
* **stream** — engine adapters where already supported; not expanded

## Error model

* Missing credentials → `RuntimeError("MISCONFIGURED: <KEY> missing")` (never secret values)
* Kill switch → preflight denial / provider_killed
* Provider HTTP errors → redacted type names at product boundaries
* No raw prompt/output in telemetry

## Non-goals (M22)

* Chat full rewrite (M23)
* Durable circuit/cost (M24)
* Live provider certification, cloud enablement, production_certified=true
* Trading Guardian engagement
