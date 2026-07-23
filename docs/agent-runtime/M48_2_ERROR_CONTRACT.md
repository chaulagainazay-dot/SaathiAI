# M48.2 — Error Contract

| Code | When |
|---|---|
| VALIDATION_FAILED | schema/timeout/retry/secret field |
| UNKNOWN_CAPABILITY | capability not registered |
| AUTHORITY_DENIED | unknown/disallowed authority |
| APPROVAL_REQUIRED | missing approval |
| APPROVAL_EXPIRED | expired token |
| APPROVAL_REVOKED | revoked |
| PROVIDER_UNAVAILABLE | provider not available |
| CONFIGURATION_MISSING | provider not configured |
| PROHIBITED_OPERATION | financial execution etc. |
| IDEMPOTENCY_CONFLICT | key reuse mismatch |
| INVALID_STATE_TRANSITION | illegal RunState edge |
| RUNTIME_UNAVAILABLE | runtime down |
| INTERNAL_ERROR | unexpected |

Responses: `ok=false`, stable `error` code, safe `message`, optional `violations[]`. Never secrets.
