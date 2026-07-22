# M20.3 — Live Small-Model Validation

**Date:** 2026-07-16  
**Host:** developer Mac (8 GB class)  
**Endpoint policy:** local allowlist only (`127.0.0.1` / `localhost` / `::1`)

## Policy

* No model download / pull  
* No automatic 8B+ selection  
* No non-local hosts  
* At most one bounded non-sensitive prompt when live  
* Mock results must be labelled `mock`, never `live`

## Harness

```bash
.venv/bin/python -c "from saathi.inference.live_validation import run_live_small_model_validation; \
import json; print(json.dumps(run_live_small_model_validation().to_dict(), indent=2))"
```

## Result (this machine, this session)

| Field | Value |
|-------|--------|
| live | **false** |
| label | **unavailable** |
| ollama_installed | false |
| ollama_reachable | false |
| endpoint_local | true |
| models_installed | [] |
| error | ollama_unavailable |
| notes | list_failed:EngineUnhealthyError; no model download attempted |
| memory_before_gb | ~1.32 (below comfortable live threshold) |

**No live generation was run. No model was downloaded.**

Mock path (`force_mock=True`) is available for CI determinism and is explicitly labelled `mock`.

## Latency

Not measured live (unavailable). Deterministic unit tests use injected governed results (~12 ms simulated).

## Operator: when Ollama + small model are present

1. Ensure `ollama` serves a ≤3B model already installed.  
2. `SAATHI_INFERENCE_ENABLED=1` + `SAATHI_INFERENCE_GATEWAY_ENABLED=1` for path use.  
3. Re-run the harness; expect `label=live` only if generation succeeds.
