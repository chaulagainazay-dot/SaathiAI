# M25 Certification Gates

## Production-safe memory

```text
available_memory_gb >= safety_margin_gb + minimum_model_budget_gb
# 1.5B: 0.8 + 1.0 = 1.8 GB free required
```

## Live vs production

| Gate | Meaning |
|------|---------|
| live_provider_certified | Real local non-stream path passed |
| production_certified | Full package (live + suite + secret scan + critical) — remains false until complete |

## Evidence

| File | Semantics |
|------|-----------|
| LAST_SUCCESSFUL_LIVE_CERTIFICATION.json | Historical PASS; not erased by blocked re-runs |
| LATEST_ENVIRONMENT_OBSERVATION.json | Current host snapshot |
| LIVE_CERT_EVIDENCE.json | Combined view |

## Blockers

| Code | Meaning |
|------|---------|
| insufficient_model_memory_headroom | Model installed; free RAM below formula |
| no_installed_models_observed | No models |
| embedding_model_missing | Ollama up but embed model absent (memory auto path) |
