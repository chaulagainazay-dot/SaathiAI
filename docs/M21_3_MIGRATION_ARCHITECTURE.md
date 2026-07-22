# M21.3 Migration Architecture

## Target path

```text
product caller
→ approved caller adapter
→ canonical InferenceRequest (or preflight equivalent)
→ contract validation / caller policy
→ provider availability/cost/privacy decision (M21.2)
→ kill-switch and circuit checks
→ ModelRouter
→ governed provider adapter OR explicit legacy sink
→ typed result
→ privacy-safe evidence
```

## Authorities (unchanged)

| Authority | Module |
|-----------|--------|
| Model selection | `ModelRouter` only |
| Governed execution | `execute_governed_local_inference` |
| Provider decision | `provider_decision.decide_providers` |
| Request contract | `InferenceRequest` + `contract.validate_contract` |
| Caller registry | `caller_policy` |
| Residual inventory | `residual_paths` + exception manifest |
| Release enforcement | `release_check` |

## No second systems

* No second ModelRouter
* No second inference gateway package
* No second request model (AST-guarded)
* No second caller registry
* No parallel chat engine rewrite

## Compatibility adapters

| Adapter | Public API preserved | Routes to |
|---------|----------------------|-----------|
| `chat_adapter.chat_generate` | chat `_default_llm` shape | preflight → generate |
| `cheap_ask` / `prose_clean` | tool dict shapes | compat + generate |
| `ask_llm` | string return | preflight + generate |
| `llm.generate` | LLMResult | preflight + ModelRouter + DEFAULT_CALLERS |

## Preflight (`legacy_facade`)

Shared residual gate: kill-all, registered caller, bounds, privacy-safe telemetry.
Does **not** execute providers.
