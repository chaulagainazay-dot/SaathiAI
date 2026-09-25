# RESOURCE_REPORT

## Host

| Item | Value |
| --- | --- |
| Chip | Apple M2 |
| RAM | 8 GB unified |
| Approx reclaimable at plan time | ~2.3 GiB |
| Ollama serve | running |
| Ollama models present | 1.5B–8B (not all loaded) |

## Measured peak RSS (process during bench)

| Model | Cold load | Peak RSS |
| --- | --- | --- |
| tiny | 1.01 s | **470 MiB** |
| base | 0.59 s | **830 MiB** |
| small | 1.10 s | **1430 MiB** |

## Coexistence

| Scenario | Assessment |
| --- | --- |
| local STT tiny + no LLM | Safe |
| local STT base + no LLM | Safe on 8 GB if browser+backend light |
| local STT small + Ollama | **Risky** — near swap territory |
| local STT + small Ollama (1.5B) | Prefer unload STT or block (admission) |
| browser STT + backend + frontend | Lightweight — default product path |

## Policy

- `neverLowerLlmMemoryGate: true`
- Concurrent heavy local models: max 1
- Prefer unload STT when LLM active

## Disk

- Models reused from HF hub cache (tiny/base/small already present)
- Bench venv: `tools/voice-stt-bench/.venv` (isolated)

