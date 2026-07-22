# M21.2 — Provider Governance Audit

**Evidence:** `SOURCE_INSPECTED` + implementation  
**Baseline:** M21.1 tip `2aace04`  
**Scope:** Inventory providers; define descriptor, availability, cost, failover, circuit  

---

## Inventory

| Provider ID | Class | Local/Cloud | Adapter | Config | Creds | Enabled default | Health | Caps | Stream | Tools | Context | Cost | Kill | Circuit | Cert | M21.2 decision |
|-------------|-------|-------------|---------|--------|-------|-----------------|--------|------|--------|-------|---------|------|------|---------|------|----------------|
| ollama | local | local | adapters/ollama.OllamaEngine | InferenceSettings + env | none | when masters on | injectable; no live in unit tests | screening/standard/fast/private | yes | no | 8192 | ZERO_MARGINAL | SAATHI_PROVIDER_KILL_OLLAMA | process-local | production_supported (pilot) | DEGRADED without probe; AVAILABLE with healthy inject |
| fake | fake | local | adapters/fake.FakeEngine | test | none | disabled | fake | test | no | no | 8192 | ZERO_MARGINAL | SAATHI_PROVIDER_KILL_FAKE | process-local | fake | TEST_ONLY / FAKE in production |
| openai_compat | compat | cloud | adapters/openai_compat | env | optional key | disabled | none | streaming | yes | no | 128k | UNKNOWN | KILL_OPENAI_COMPAT | process-local | uncertified | DISABLED |
| anthropic | cloud | cloud | adapters/cloud.CloudCallerEngine | llm DEFAULT_CALLERS | ANTHROPIC_API_KEY | disabled | none | tools | no | yes | 128k | ESTIMATED from relative | KILL_ANTHROPIC | process-local | uncertified | DISABLED (cloud off) |
| openai | cloud | cloud | cloud | env | OPENAI_API_KEY | disabled | none | tools | no | yes | 128k | ESTIMATED | KILL_OPENAI | process-local | uncertified | DISABLED |
| groq | cloud | cloud | cloud | env | GROQ_API_KEY | disabled | none | standard | no | no | 128k | ESTIMATED | KILL_GROQ | process-local | uncertified | DISABLED |
| gemini | cloud | cloud | cloud | env | GEMINI/GOOGLE key | disabled | none | tools | no | yes | 128k | ESTIMATED | KILL_GEMINI | process-local | uncertified | DISABLED |
| openrouter | cloud | cloud | cloud | env | OPENROUTER_API_KEY | disabled | none | multiproxy | no | no | 128k | UNKNOWN | KILL_OPENROUTER | process-local | uncertified | DISABLED |
| deepseek | cloud | cloud | cloud | env | key/openrouter | disabled | none | standard | no | no | 128k | ESTIMATED | KILL_DEEPSEEK | process-local | uncertified | DISABLED |
| glm | cloud | cloud | cloud | env | key | disabled | none | standard | no | no | 128k | ESTIMATED | KILL_GLM | process-local | uncertified | DISABLED |
| qwen | cloud | cloud | cloud | env | key | disabled | none | standard | no | no | 128k | ESTIMATED | KILL_QWEN | process-local | uncertified | DISABLED |

**Rule:** Adapter existence ≠ AVAILABLE.

---

## Pre-existing mechanisms

| Mechanism | Location | M21.2 treatment |
|-----------|----------|-----------------|
| Provider policy + kills | `provider_policy.py` | Extended via descriptors |
| Static availability | `resolve_availability` | Kept; runtime uses `availability.py` |
| Cost placeholders | `CostMetadata` | Expanded `PricingMetadata` + enforcement |
| Normalized errors | `errors.py` | Supplemented by `failure_taxonomy.py` |
| Runtime fallback | `runtime.generate_with_fallback` | Not replaced; decision layer for governed path |
| ModelRouter | `model_router.py` | Unchanged authority for model selection |
| cheap_ask proxy | `cheap_llm.py` httpx | **Removed** direct invoke |

---

## Bypasses addressed

| Path | Before | After |
|------|--------|-------|
| cheap_ask CHEAP_PROXY httpx | DIRECT_PROVIDER_BYPASS | BLOCK (no invoke) |
| Transitional `unknown` caller | pilot production-risk | TEST + production posture deny |

---

## Classification summary

* **No provider marked AVAILABLE solely because adapter exists**
* Default cloud: DISABLED / uncertified
* Ollama: DEGRADED without live probe; selectable in pilot
* Fake: never production
* Global production_certified remains **false**
