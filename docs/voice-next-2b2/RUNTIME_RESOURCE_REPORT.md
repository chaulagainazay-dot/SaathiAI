# RUNTIME_RESOURCE_REPORT

| Candidate | Cold load | Peak RSS | decode p50 | p95 | worst |
| --- | --- | --- | --- | --- | --- |
| Dragneel small CT2 | 0.19 s | **~1003 MiB** | 1.13 s | 1.47 s | 2.21 s |
| sparshrestha small CT2 | 0.19 s | **~1003 MiB** | 1.29 s | 1.47 s | 2.11 s |

## Coexistence

~1 GB peak for small CT2 is similar to generic small. Still:

- Prefer not concurrent with large Ollama models
- LLM memory gates **not** lowered
- Browser STT remains light path

## Qwen3-ASR-Nepali

Not loaded. Est. multi-GB + community-use license.

