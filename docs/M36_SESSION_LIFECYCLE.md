# M36 — Session Lifecycle

```
REQUESTED → AUTHORIZED → ACCOUNT_QUALIFIED → LEASED → SECRET_LOADED
→ IDENTITY_VERIFIED → SCOPE_VERIFIED → ELIGIBLE → RUNNING → COMPLETED
→ SECRET_CLOSED → LEASE_CONSUMED → REVOKED_OR_EXPIRED
```

Failure states: `BLOCKED`, `FAILED`, `ABORTED`, `EXPIRED`, `REVOKED`, `QUARANTINED`.

Any failure closes the secret handle. No silent resume. No switch of
provider/account/credential/endpoint/method/operation/scope/authorization/lease.
