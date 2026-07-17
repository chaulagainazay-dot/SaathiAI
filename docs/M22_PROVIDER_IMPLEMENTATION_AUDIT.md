# M22 Provider Implementation Audit

**Milestone:** Platform M22 — Governed Provider Implementation and Legacy SDK Migration  
**Baseline HEAD:** `cc7fceb` (M21.4 tip)  
**Branch:** `milestone/m7-security-engine`  
**Production certified:** false  

## Required outcomes

| Invariant | Count |
|-----------|------:|
| UNKNOWN provider implementations | 0 |
| DIRECT_CALLER_PROVIDER_EXECUTION (migrated facades) | 0 |
| UNCLASSIFIED_PROVIDER_TRANSPORT | 0 |
| EXPLICIT_LEGACY_EXCEPTION (residual table) | 0 |
| Manifest exceptions remaining | 3 (chat M23; cloud/openai_compat M24) |

## Inventory (inference-relevant)

| ID | File | Symbol | Family | Transport | Classification | M22 action |
|----|------|--------|--------|-----------|----------------|------------|
| HP-ANTH | adapters/http_providers.py | call_anthropic | anthropic | httpx | CANONICAL_TRANSPORT | Owned |
| HP-OAI | adapters/http_providers.py | call_openai | openai | httpx | CANONICAL_TRANSPORT | Owned |
| HP-GROQ | adapters/http_providers.py | call_groq | groq | httpx | CANONICAL_TRANSPORT | Owned |
| HP-GEM | adapters/http_providers.py | call_gemini | gemini | httpx | CANONICAL_TRANSPORT | Owned |
| HP-OR | adapters/http_providers.py | call_openrouter | deepseek/glm/qwen | httpx | CANONICAL_TRANSPORT | Owned |
| HP-OLL | adapters/http_providers.py | call_ollama | ollama | httpx | CANONICAL_TRANSPORT | Owned |
| GND | adapters/grounding.py | grounded_generate | gemini+search | httpx | CANONICAL_ADAPTER | Owned |
| AGT | adapters/agent_provider.py | build_agent_session | multi | OpenAI/Anthropic SDK | CANONICAL_ADAPTER | Owned |
| OLL-E | adapters/ollama.py | OllamaEngine | ollama | urllib | CANONICAL_ADAPTER | Unchanged |
| OAI-C | adapters/openai_compat.py | OpenAICompatEngine | local-compat | urllib | COMPATIBILITY_WRAPPED | Unchanged (M24) |
| CLD | adapters/cloud.py | CloudCallerEngine | multi | wraps HP | COMPATIBILITY_WRAPPED | Points at HP |
| FAK | adapters/fake.py | FakeEngine | fake | none | TEST_FAKE | Unchanged |
| LLM | saathi/llm.py | generate | — | none | COMPATIBILITY_FACADE | HTTP removed |
| AGT-F | saathi/agent.py | SaathiAgent | — | none | COMPATIBILITY_WRAPPED | SDK removed |
| RES | tools/research.py | research/_grounded | — | none | COMPATIBILITY_WRAPPED | HTTP removed |
| CHAT | chat/engine.py | ChatEngine | — | via chat_adapter | COMPATIBILITY_WRAPPED | M23 expiry |
| VIS | vision.py | vision helpers | gemini | SDK | OUT_OF_SCOPE | Media/vision |
| VOX | tools/voice.py etc. | TTS/STT | openai | httpx | OUT_OF_SCOPE | Media |
| EMB | memory/engine/embeddings.py | Ollama embed | ollama | httpx | HEALTH/EMB | Non-chat |
| OJ | execution/.../openjarvis_adapter.py | OpenJarvisAdapter | local stub | OllamaEngine | COMPATIBILITY_WRAPPED | No OJ process |

## Answers (M22 questions)

1. **Bypass adapters?** Migrated product facades no longer execute providers; remaining non-inference media tools out of M22 scope.
2. **SDKs remaining?** Only inside `inference/adapters/` (plus out-of-scope media/eval).
3. **All execution behind adapters?** Yes for llm.generate, agent, research grounding.
4. **`llm.generate` pure facade?** Yes — selection via ModelRouter; transport via `http_providers`.
5. **Agent delegates?** Yes — `build_agent_session` / `AgentProviderSession`.
6. **Research grounding governed?** Yes — `grounded_generate`.
7. **Legacy exceptions removed?** Four M22-expiry entries migrated; three residual remain (M23/M24).
8. **URLs/SDK/credentials confined?** Yes for M22 facades; release_check enforces.
9. **Public compatibility?** Signatures preserved (`generate`, `LLMResult`, agent complete/respond, research/deep_plan).
10. **Suite green?** See validation report.

## Credential boundary

| Allowed | Role |
|---------|------|
| `saathi/config.py` | Bootstrap env load |
| `adapters/http_providers.py` | Family HTTP keys |
| `adapters/grounding.py` | Gemini grounding key |
| `adapters/agent_provider.py` | Agent session keys |
| Other adapters / descriptor modules | Availability metadata |

Product facades `llm.py`, `agent.py`, `research.py` must not `getenv` provider API keys.
