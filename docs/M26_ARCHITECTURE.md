# M26 Architecture — Production Inference Operations

## Purpose

Operationalize the **already-certified** M22–M25 inference path on an
Apple Silicon 8 GB host. No new inference architecture.

## Layers (do not confuse)

| Layer | Meaning |
|-------|---------|
| **production certification** | M25 package + runtime_gate (`production_certified`) |
| **health** | Is the SaathiOS ops process functioning? |
| **readiness** | Can we accept a new governed request *now*? |
| **rollout mode** | OFF / SHADOW / CANARY / ACTIVE / DRAINING |
| **provider state** | Session-level supervision (not Ollama PID ownership) |
| **resource pressure** | Memory/disk/concurrency/cooldown |
| **incident state** | Deduplicated operational incidents |

## Component map

```text
python -m saathi.inference.ops
        │
        ▼
InferenceOpsService
  ├── OpsStateStore (atomic JSON under docs/evidence/m26/)
  ├── resource probe → certification.memory_selection_ok (M25 rule)
  ├── production_certified_probe → runtime_gate
  ├── provider reachability → live_cert discover (read-only)
  ├── circuit_open_probe → durable circuit breaker
  ├── recover → governance_store.recover_stale_reservations
  └── events → redacted JSONL (+ optional event bus)
```

## Ownership

```text
external provider process  = Ollama (operator-managed)
SaathiOS provider session  = governed adapter path
SaathiOS inference ops     = this service (lifecycle + readiness)
```

SaathiOS **never** claims Ollama PID ownership.

## CLI

```bash
python -m saathi.inference.ops start|status|readiness|health|drain|stop|restart|recover
python -m saathi.inference.ops mode <OFF|SHADOW|CANARY|ACTIVE|DRAINING>
python -m saathi.inference.ops rollback
python -m saathi.m20_console inference-ops
```

## Default

Rollout mode **OFF**. ACTIVE requires computed production certification.
Cloud fallback remains disabled. Trading Guardian unengaged.
