# M21.1 — Canonical Inference Request Audit

**Evidence:** `SOURCE_INSPECTED` + implementation classification  
**Baseline:** M21.0 `65e59d7`  
**Scope:** Extend inventory; classify residual paths; enforce contract on governed path  

---

## Path inventory (M21.0 + additional)

| Path ID | File | Symbol | Area | Provider access | Model override | Tools | Stream | Governance | Decision |
|---------|------|--------|------|-----------------|----------------|-------|--------|------------|----------|
| model_router | model_router.py | ModelRouter | core | none (select) | n/a | n/a | n/a | selection | CANONICAL |
| governed_local_gateway | gateway_path.py | execute_governed_local_inference | inference | ollama via adapter | denied | denied default | denied default | M21.1 contract | CANONICAL |
| model_gateway_orchestrator | model_gateway.py | ModelGateway | execution | governed/OJ stub | policy | — | — | gateway | CANONICAL |
| legacy_llm_generate | llm.py | generate | llm | multi cloud/local | router | n/a | n/a | ModelRouter | LEGACY_ALLOWED_TEMPORARILY (M21.3) |
| cheap_ask | cheap_llm.py | cheap_ask | tools | compat + legacy + proxy | no force | no | no | M20.3/M21.1 compat | COMPATIBILITY_ADAPTER |
| prose_clean | prose.py | clean_prose | tools | compat + legacy | no force | no | no | M20.3/M21.1 compat | COMPATIBILITY_ADAPTER |
| compat_adopt_generate | compat.py | adopt_generate | inference | governed/legacy | no | no | no | adapter | COMPATIBILITY_ADAPTER |
| engine_ollama | adapters/ollama.py | OllamaEngine | engine | local HTTP | n/a | n/a | yes | adapter | CANONICAL |
| engine_cloud_caller | adapters/cloud.py | CloudCallerEngine | engine | cloud | n/a | yes | no | policy off | DEFER_WITH_GUARD |
| engine_openai_compat | adapters/openai_compat.py | OpenAICompatEngine | engine | HTTP | n/a | no | yes | policy off | DEFER_WITH_GUARD |
| engine_fake | adapters/fake.py | FakeEngine | test | none | n/a | no | no | test | FAKE_PROVIDER |
| runtime_generate_with_fallback | runtime.py | generate_with_fallback | inference | multi | settings | no | no | settings | CANONICAL |
| chat_engine | chat/engine.py | ChatLLMAdapter | chat | llm.generate | router | no | no | legacy | LEGACY_ALLOWED_TEMPORARILY (M23) |
| openjarvis_execution_adapter | openjarvis_adapter.py | OpenJarvisAdapter | execution | stub | n/a | no | no | offline stub | LEGACY_ALLOWED_TEMPORARILY |
| m20_console_inference | m20_console/status.py | inference_snapshot | ops | none | n/a | no | no | read-only | CANONICAL |
| cheap_ask_legacy_proxy | cheap_llm.py | httpx CHEAP_PROXY | tools | direct proxy | hardcoded model | no | no | residual | DIRECT_PROVIDER_BYPASS (M21.2) |
| tools_llm_helper | tools/_llm_helper.py | ask_llm | tools | direct HTTP | chain | no | no | residual | DEFER_WITH_GUARD |
| agent_sdk_clients | agent.py | OpenAI/Anthropic | agent | SDK | yes | — | — | residual | DEFER_WITH_GUARD (M22) |
| server_direct_http | server.py | provider HTTP | server | direct | — | — | — | residual | DEFER_WITH_GUARD |
| tools_research | tools/research.py | gemini URL | tools | direct | — | — | — | residual | DEFER_WITH_GUARD |

**Unclassified paths:** forbidden by design — static bypass guard + residual registry.

---

## Existing contracts

| Contract | Authority |
|----------|-----------|
| `InferenceRequest` | CANONICAL (extended M21.1 fields) |
| `validate_inference_request` | Structural M20.2 |
| `validate_contract` | M21.1 full enforcement |
| `CALLER_LIMITS` / rollout | M20.3 (preserved) |
| `CallerPolicy` registry | M21.1 caller policy |

No second ModelRouter or gateway created.

---

## Chat default

**Unchanged.** Path `chat_engine` is LEGACY_ALLOWED_TEMPORARILY; cannot enter governed path without migration. Kill-all still blocks governed path; chat legacy uses `llm.generate` (separate surface — documented limitation).

---

## Trading Guardian

No TG caller registered as governed. `trading_guardian` is FORBIDDEN. Modules contain no withdrawal/live trade.
