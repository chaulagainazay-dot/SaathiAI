# M39 — Canary Eligibility Evaluation

## Verdict this run

`BLOCKED_OPERATOR_SECRET_REQUIRED`

## Grants

```
grants_canary = false
grants_active = false
grants_rollout = false
grants_production = false
grants_write = false
```

## Allowed verdicts

| Verdict | Meaning |
|---------|---------|
| `CANARY_NOT_ELIGIBLE` | Technical/security blockers |
| `CANARY_ELIGIBLE_WITH_LIMITATIONS` | Live ok with residual limitations |
| `READY_FOR_OPERATOR_CANARY_DECISION` | Eligible for separate operator decision |
| `LIVE_VALIDATION_FAILED` | Live exercise failed |
| `BLOCKED_OPERATOR_SECRET_REQUIRED` | No approved secret reference |
| `BLOCKED_EXTERNAL_REVOCATION_REQUIRED` | Live ok; external revoke unconfirmed |

## Rule

M39 may recommend readiness. **Only a future, explicit operator authorization**
may set `CANARY authorization = GRANTED`. Readiness is not authorization.
