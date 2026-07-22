# M45 — Test Report

## Summary

```
tests/test_m45_runtime_attestation.py .......................... 59 passed
```

Runner: `.venv/bin/python -m pytest`.

## Coverage categories

- Framework readiness / grants-nothing
- Missing / malformed / unsigned snapshots
- Tamper (fingerprint + field)
- Expiry + future timestamp
- Replay / duplicate
- Machine / process / branch / commit / dirty-repo
- Provider / scope / credential ref / presence
- Secret-read flag
- Safety switches (network, write, deploy, execution, alerts, incidents,
  rollback, kill switch, error budget, ledger, M32, TG)
- Provenance (simulated, self-reported, unsigned, hardware claim)
- Evidence binding gaps + hermetic UNKNOWN base
- Lifecycle ledger + tamper
- M44 integration readiness (positive + negative)
- Leak cleanliness, module fingerprint, M32 intact

## CLI smoke

`m45-status` → `M45_RUNTIME_ATTESTATION_READY_ADVISORY_ONLY`  
`m45-simulate` → SIMULATED_NOT_LIVE, provenance insufficient for readiness  
`m45-emit-evidence` → 5 evidence files, leak-clean
