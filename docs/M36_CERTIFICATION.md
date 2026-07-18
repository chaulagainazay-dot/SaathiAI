# M36 — Certification

## States

`UNVERIFIED`, `AUTHORIZATION_READY`, `REAL_SANDBOX_IDENTITY_VERIFIED`,
`REAL_SANDBOX_SCOPE_VERIFIED`, `REAL_SANDBOX_SESSION_VERIFIED`,
`REAL_SANDBOX_SESSION_VERIFIED_WITH_LIMITATIONS`, `FAILED`, `STALE`,
`REVOKED`, `QUARANTINED`.

Highest: `REAL_SANDBOX_SESSION_VERIFIED` (provider/account/fingerprint/operation/
endpoint/schema-specific, timestamped, expiring, non-production, rollout-independent).

## Does not imply

`PRODUCTION_VERIFIED`, `CANARY_READY`, `CANARY_ENABLED`, `ACTIVE`,
`GENERAL_PROVIDER_AUTHORIZED`, `WRITE_AUTHORIZED`.

## Authorities at completion

```
production authorization = NOT GRANTED
rollout authorization = NOT GRANTED
CANARY authorization = NOT GRANTED
ACTIVE authorization = NOT GRANTED
write authority = NOT GRANTED
```
