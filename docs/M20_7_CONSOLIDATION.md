# M20.7 — Engineering Orchestrator and Governed Inference Runtime Consolidation

**Status:** Complete (observability consolidation; domains not merged)  
**Starting HEAD:** `94808eb` (M20.6)

## Intent

Give operators **one read-only console** over two separate pilots:

1. Engineering Orchestrator (`saathi.engineering`)  
2. Governed local inference (`saathi.inference`)

Without creating a second Mission Engine, ModelRouter, ExecutionGateway, run ledger, or merged store.

## Delivered

| Piece | Location |
|-------|----------|
| Flag catalog + snapshot | `saathi/m20_console/flags.py` |
| Unified status | `saathi/m20_console/status.py` |
| CLI | `python -m saathi.m20_console` |
| Engineering shortcut | `python -m saathi.engineering m20` |
| Control Center cells | `governed_inference()`, `m20_console()` |
| Isolation guarantees | `domains_isolated()` |

## Explicit non-merges

* Engineering sessions store ≠ inference runtime  
* ModelRouter remains sole model selector  
* ExecutionGateway unchanged  
* Harness run ledger untouched  
* Trading Guardian uncoupled  
* Caller rollout defaults remain `legacy`  
* Orchestrator remains disabled by default  

## Operator commands

```bash
python -m saathi.m20_console status
python -m saathi.m20_console flags
python -m saathi.m20_console disable
python -m saathi.m20_console discover
python -m saathi.m20_console domains
python -m saathi.m20_console engineering
python -m saathi.m20_console inference
```

## Disable all M20 pilots

```bash
unset SAATHI_ENG_ORCH_ENABLED SAATHI_ENG_ORCH_LAUNCH \
      SAATHI_ENG_ORCH_WRITES SAATHI_ENG_ORCH_COMMITS SAATHI_ENG_ORCH_PUSHES
unset SAATHI_INFERENCE_ENABLED SAATHI_INFERENCE_GATEWAY_ENABLED \
      SAATHI_ALLOW_CLOUD_FALLBACK \
      SAATHI_INF_ROLLOUT SAATHI_INF_ROLLOUT_CHEAP_ASK SAATHI_INF_ROLLOUT_PROSE_CLEAN
```

## Next

M20.8 — Bounded additional caller adoption (shadow-first), still not chat default.
