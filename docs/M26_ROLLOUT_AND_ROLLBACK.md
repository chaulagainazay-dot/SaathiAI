# M26 Rollout and Rollback

## Modes

```text
OFF → SHADOW → CANARY → ACTIVE → DRAINING → OFF
```

* **OFF** — default; no production inference  
* **SHADOW** — health/validation only  
* **CANARY** — deterministic admit (`sha256(key) % 100 < canary_percent`) or allowlist  
* **ACTIVE** — requires `production_certified=true` (computed)  
* **DRAINING** — no new work; bounded grace for inflight  

## Mode change rules

* Explicit CLI or API  
* Evidence-recorded (`docs/evidence/m26/mode_history.jsonl`)  
* Idempotent  
* Invalid transitions fail closed  
* Never enable cloud fallback  
* Never modify credentials  

## Rollback

```bash
python -m saathi.inference.ops rollback
```

1. Drain  
2. Mode → OFF  
3. Phase → STOPPED  
4. Preserve M25 certification evidence  
5. Preserve incidents and mode history  
6. Reconcile reservations via `recover` if needed  

Do **not** use `git reset --hard` for operational rollback.  
Do **not** delete evidence to force a gate pass.

## Safe config restore

Operational state lives under `docs/evidence/m26/`. Restoring OFF + STOPPED is
sufficient for safe local posture. Re-run:

```bash
python -m saathi.inference.runtime_gate
python -m saathi.inference.release_check
```
