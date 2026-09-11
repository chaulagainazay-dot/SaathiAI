# LLM Provider Architecture Comparison

## TradingAgents

`tradingagents/llm_clients/` — 12 modules, 1,141 lines.

- `factory.py` — `create_client(provider, model, base_url, **kw)`, lazy per-provider import
- `base_client.py` — common `model` / `base_url` contract
- Concrete clients: `openai_client`, `anthropic_client`, `google_client`, `azure_client`, `bedrock_client`
- `capabilities.py` — per-model `ModelCapabilities`
- `model_catalog.py` — curated model lists per provider (GLM, Qwen, DeepSeek, MiniMax, …)
- `api_key_env.py` — provider → env-var name map (`"ollama": None`, i.e. keyless)
- `validators.py`

DeepSeek, Qwen, GLM, MiniMax, Groq, NVIDIA, xAI, and Ollama are reached through the
**OpenAI-compatible client with a `base_url` override** rather than dedicated SDKs.
Only 5 real client classes exist; the rest is configuration. That is a good decision
— it keeps the dependency surface small.

### The one genuinely valuable idea: `ModelCapabilities`

```python
@dataclass
class ModelCapabilities:
    supports_tool_choice: bool
    supports_json_mode: bool
    supports_json_schema: bool
    preferred_structured_method: StructuredMethod   # json_schema | json_mode |
                                                    # function_calling | none
```

`StructuredMethod` is a closed set including `"none"` — "no structured output
available; caller falls back to free-text". The table encodes real, model-specific
defects with comments naming them (DeepSeek 400s on `tool_choice`; MiniMax the same
shape). This is operational knowledge about provider misbehaviour, expressed as data.

### Graceful degradation

`agents/utils/structured.py`:
- `bind_structured()` returns `None` if the provider cannot bind a schema
  (`NotImplementedError` / `AttributeError`) — then *every* call uses free text,
  rather than retrying and failing per call
- `invoke_structured_or_freetext()` catches parse/validation failure and re-invokes
  free-text **with the same input**, logging a uniform warning
- Schema field descriptions double as output instructions
- `_coerce_optional_float` maps LLM placeholder strings (`"N/A"`, `"unknown"`, `"-"`)
  to `None` instead of raising — a small, real robustness fix (#1058)

## SaathiOS

`saathi/inference/` — roughly 50 modules, plus `saathi/model_router.py`.

`registry.py`, `catalogue.py`, `discovery.py`, `provider_policy.py`,
`provider_descriptor.py`, `provider_decision.py`, `provider_governance.py`,
`governance_service.py`, `governance_store.py`, `governance_clock.py`,
`certification.py`, `cert_corpus.py`, `cert_evidence.py`, `live_cert_m25.py`,
`live_validation.py`, `circuit_breaker.py`, `failure_taxonomy.py`, `cost_policy.py`,
`caller_policy.py`, `caller_rollout.py`, `availability.py`, `benchmarks.py`,
`hardware.py`, `bypass_guard.py`, `runtime_gate.py`, `release_check.py`,
`priority_policy.py`, `path_inventory.py`, `residual_paths.py`, `router_bridge.py`,
adapters for `ollama`, `openai_compat`, `http_providers`, `kimi`, `cloud`, `fake`.

`ProviderDescriptor` already carries `supported_capabilities: tuple[str, ...]` and
`structured_output_supported: bool`.

## Comparison

| Dimension | TradingAgents | SaathiOS | Winner |
|---|---|---|---|
| Provider registry | small factory | full registry + governance + certification | **SaathiOS** |
| Cost policy / budgets | none | `cost_policy.py`, `budget.py` | **SaathiOS** |
| Circuit breaking | none | `circuit_breaker.py` | **SaathiOS** |
| Failure taxonomy | per-client exceptions | `failure_taxonomy.py` | **SaathiOS** |
| Certification / live validation | none | `certification.py`, `live_cert_m25.py` | **SaathiOS** |
| Local / Ollama | `base_url` override, keyless | dedicated `adapters/ollama.py` | **SaathiOS** |
| Rollout / canary | none | `caller_rollout.py`, `provider_canary_planning` | **SaathiOS** |
| **Per-model structured-output method** | `preferred_structured_method` ∈ {json_schema, json_mode, function_calling, none} | single bool, hardcoded `pol.family_id == "kimi"` | **TradingAgents** |
| **Documented per-model quirks as data** | yes, with issue references | not present | **TradingAgents** |
| **Structured→free-text graceful fallback** | yes, bind-once + per-call | not evident | **TradingAgents** |
| **Nullish-value coercion for optional numerics** | yes | not evident | **TradingAgents** |
| Curated model catalogue for a picker UI | yes | `catalogue.py` | tie |

## Verdicts

| Item | Verdict | Note |
|---|---|---|
| Provider registry as a whole | **KEEP SAATHIOS** | SaathiOS's is an order of magnitude more capable. Do not build a second registry. |
| `ModelCapabilities.preferred_structured_method` | **ADAPT — highest-value provider borrow** | Replace `structured_output_supported: bool` with a method enum on `ProviderDescriptor`. Today SaathiOS says only Kimi supports structured output, which is coarse enough to be wrong. |
| Per-model quirk table with issue references | **ADAPT** | Encode known provider misbehaviour as data next to `provider_policy.py`. |
| `bind_structured` / `invoke_structured_or_freetext` degradation pattern | **ADAPT** | Bind once, fall back for the whole session, uniform warning. Fits `saathi/inference/engine.py`. |
| `_coerce_optional_float` nullish handling | **ADAPT (trivial, do it)** | Prevents avoidable validation failures on optional numeric fields. |
| `api_key_env` map with `None` for keyless local | **COMBINE** | Minor; `adapters/ollama.py` already covers the case. |
| Concrete client classes | **REJECT DUPLICATE** | SaathiOS adapters already cover these providers. |
| Provider SDK dependencies | **REJECT** | Do not add `langchain-*` packages to SaathiOS. |
