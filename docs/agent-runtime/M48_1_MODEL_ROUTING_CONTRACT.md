# M48.1 — Model Routing Contract

## Existing router

`saathi/model_router.py` — capability labels, not hard-coded provider identity:

```text
screening | standard | reasoning | multimodal | fast | long | private
```

Selection factors: privacy, cost, latency, availability (injected; testable offline).

## Resolution statuses (M48.1)

| Status | Meaning | Success? |
|---|---|---|
| SELECTED | primary available | yes |
| FALLBACK_SELECTED | backup used | yes |
| UNAVAILABLE | no provider | **no** |
| PROHIBITED | policy blocks | **no** |
| CONFIGURATION_MISSING | not configured | **no** |

API: `classify_provider_status` / `provider_status_is_success`.

## Local Ollama

Read-only inventory only in M48.1. Observed on host (ephemeral): `qwen3:8b`, `qwen2.5:1.5b`.  
No pull/delete. No paid remote calls. No credentials created.

## Privacy

`PRIVATE` label prefers local; remote private data path must not silently downgrade to public cloud without policy.
