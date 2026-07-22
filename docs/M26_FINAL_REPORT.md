# M26 Final Report — Production Inference Operations

## Executive result

```text
M26 COMPLETE WITH LIMITATIONS
```

Implementation and automated tests complete. Live environment: Ollama reachable with
`qwen2.5:1.5b` installed; current free memory often below 1.8 GB floor so readiness
may be ENVIRONMENT_BLOCKED while `production_certified` remains true and mode stays OFF.

## Baseline

| Item | Value |
|------|-------|
| Start HEAD | `d543c9e` |
| Ending HEAD | `6e78496` |
| Branch | `milestone/m7-security-engine` |
| Full suite | 3163 passed, 1 skipped, 0 failed |
| M25 package | production_certified when evidence fresh |

## What shipped

* `saathi/inference/ops` lifecycle (start/status/readiness/health/drain/stop/restart/recover)
* Health vs readiness distinction with check IDs
* Resource guardian (M25 memory rule, concurrency, cooldown)
* Provider session supervision (no Ollama PID ownership claim)
* Rollout modes OFF/SHADOW/CANARY/ACTIVE/DRAINING + rollback
* Deduplicated incidents + redacted events
* CLI + `m20_console inference-ops`
* Focused tests (`tests/test_m26_inference_operations.py`)

## Roadmap note

M21.39 program listed M26 as connectors (Gmail/browser). Operator-authorized M26
is **production inference operations**. Connector scope deferred.

## Invariants preserved

```text
cloud fallback = disabled
residual exceptions = 0
Trading Guardian = UNCHANGED / UNENGAGED
historical live cert preserved under dual evidence
production_certified computed (not hard-coded)
```

## Limitations

* Default mode OFF — operator must explicitly activate  
* Live smoke may be memory-blocked on 8 GB during/after full suite  
* Idle model unload disabled by default  
* Does not start/stop external Ollama  

## Next

```text
READY FOR OPERATOR AUTHORIZATION TO START M27
```

Do not auto-start M27.
