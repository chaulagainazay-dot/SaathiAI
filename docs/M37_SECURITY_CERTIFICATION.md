# M37 — Security Certification

## States

| State | Meaning |
|-------|---------|
| `SECURITY_CERTIFIED` | Full lifecycle + negatives + live sandbox |
| `SECURITY_CERTIFIED_WITH_LIMITATIONS` | Full offline; live not exercised |
| `FAILED` | Core proof missing |

## Proofs

- credential isolation
- reference-only loading
- memory cleanup (handle closed)
- sender isolation (no Authorization on envelope)
- fingerprint correctness
- scope validation
- budget enforcement
- authorization gates
- session lifecycle
- provider abstraction
- negative paths

## Authorities (always)

```
production authorization = NOT GRANTED
rollout authorization = NOT GRANTED
CANARY authorization = NOT GRANTED
ACTIVE authorization = NOT GRANTED
write authority = NOT GRANTED
Trading Guardian = UNENGAGED
```

Security certification ≠ production authorization ≠ rollout readiness.
