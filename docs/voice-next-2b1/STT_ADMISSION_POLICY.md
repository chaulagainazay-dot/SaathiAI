# STT_ADMISSION_POLICY

## States

| State | Meaning |
| --- | --- |
| `LOCAL_STT_READY` | Local model admitted; privacy LOCAL_CONFIRMED |
| `LOCAL_STT_READY_DEGRADED` | Smaller model or browser privacy path |
| `LOCAL_STT_BLOCKED_MEMORY` | Memory/LLM conflict; LLM gate not lowered |
| `LOCAL_STT_BLOCKED_MODEL_LOAD` | Missing/corrupt/load failure |
| `LOCAL_STT_UNAVAILABLE` | No adapter |

Legacy aliases: `LOCAL_STT_ALLOWED`, `LOCAL_STT_DEGRADED`, `LOCAL_STT_BLOCKED_RESOURCE_PRESSURE`.

## Rules

1. Never lower Ollama/local LLM memory gates to free STT.
2. Never silently select cloud STT.
3. Until `multilingualLocalSttQualified === true`, local is **not** auto-primary (browser remains product path).
4. Explicit `heavyLocalSttRequested` allows experimental EN-optimized local if memory allows.
5. Under pressure: degrade base→tiny, else browser, else text.

## Headroom (MiB reclaimable)

| Model | Min reclaimable |
| --- | --- |
| tiny | 600 |
| base | 900 |
| small | 1500 |

## Implementation

`saathi-os/lib/voice-session/resource-budget.js` — `admitStreamingStt`, `resolveSttHierarchy`.

