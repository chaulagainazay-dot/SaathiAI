# M45 — Architecture

## Placement

```
M39–M43.1  evidence + machine-proof canary chain
M44        rollout authorization framework (policies, validator, gates)
M45        runtime attestation + readiness composition   ← this layer
(future)   separate operator execution authorization (not M45)
```

## Data flow

```
Collector (local observe)
    → RuntimeAttestationSnapshot (unsigned, LOCAL_MACHINE_OBSERVED)
    → attest_snapshot (integrity fp + HMAC) → MACHINE_ATTESTED
    → validate_snapshot (eligibility)
    → to_m44_runtime_snapshot → m44.validate_request
    → check_request_readiness
         └─ max: BOUNDED_ROLLOUT_READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION
```

## Provenance model

| Class | Meaning | Eligible for readiness? |
|-------|---------|-------------------------|
| `ABSENT` | no observation | no |
| `SELF_REPORTED` | caller claims | no |
| `SIMULATED` | offline simulation | no |
| `LOCAL_MACHINE_OBSERVED` | collector ran locally | after attest → yes |
| `MACHINE_ATTESTED` | local HMAC integrity over observed snapshot | yes (default) |
| `HARDWARE_ATTESTED` | TPM/secure-enclave etc. | **never claimed**; rejected |

Local HMAC is **tamper evidence**, not operator identity and not hardware proof.

## Lifecycle

`CREATED` → `VALIDATED` / `BLOCKED` / `TAMPERED` / `EXPIRED` →
`ELIGIBLE_ADVISORY_ONLY` (readiness only) → `SUPERSEDED` / `REVOKED` / `INVALIDATED`

No lifecycle state authorizes execution.

## Fail-closed defaults

- missing snapshot → incomplete
- any UNKNOWN required field → blocked
- default empty snapshot → not validated
- secret_read must be false (collector never reads secrets)
- live_network / write / deploy / rollout_execution must be false
- M32 `PROHIBITION_UNCHANGED`; Trading Guardian unengaged
