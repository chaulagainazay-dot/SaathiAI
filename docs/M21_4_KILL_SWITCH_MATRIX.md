# M21.4 — Kill-Switch Matrix

## Global kill

```bash
export SAATHI_INFERENCE_KILL_ALL=1
```

Must block **before** provider invocation via `preflight_inference` / provider decision.

| Path | Global kill | Provider invoked | Fallback | Retry | Cost | Telemetry |
|------|-------------|------------------|----------|-------|------|-----------|
| chat (`chat_engine`) | BLOCK | No | None | None | No charge | Privacy-safe only |
| `llm.generate` facade | BLOCK | No | None | None | No charge | Privacy-safe only |
| agent (`agent_runtime`) | BLOCK | No | None | None | No charge | Privacy-safe only |
| server tools | BLOCK | No | None | None | No charge | Privacy-safe only |
| research (`research_tools`) | BLOCK | No | None | None | No charge | Privacy-safe only |
| `cheap_ask` | BLOCK | No | None | None | No charge | Privacy-safe only |
| `prose_clean` | BLOCK | No | None | None | No charge | Privacy-safe only |
| execution gateway | BLOCK | No | None | None | No charge | Privacy-safe only |
| provider adapters | Policy killed | No | None | None | No charge | N/A |

## Provider kill (example)

```bash
export SAATHI_PROVIDER_KILL_OLLAMA=1
```

* Blocks **ollama** only (plus master kill still blocks all)  
* Must not silently fall back to cloud  
* Availability reports killed / not policy_enabled  
* Kill denial does **not** increment circuit failure count  

## Authority

`saathi/inference/provider_policy.py` — `KILL_ALL_ENV`, `is_master_killed()`, `is_provider_killed()`, per-family `SAATHI_PROVIDER_KILL_*`.

## Tests

`tests/test_m21_4_runtime_consolidation.py` — kill matrix + circuit/telemetry assertions.
