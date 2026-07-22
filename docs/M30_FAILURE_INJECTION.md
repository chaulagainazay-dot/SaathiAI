# M30 — Failure Injection

Deterministic failure modes exercised in the sandbox assessor:

| Injection | Expected safe behavior |
|-----------|------------------------|
| timeout | Fail closed; no false success; optional incident |
| connection failure | Fail closed; no adapter success |
| malformed response | Error path; no crash |
| rate limit | Denied with `rate_limit` |
| approval missing | Denied; no mutation |
| approval expired | TemporaryApprovalStore rejects |
| approval payload mismatch | Rejected |
| idempotency conflict | Denied |
| oversized payload | Policy reject |
| undeclared operation | Denied |
| domain deny | Denied |
| remote HTTP (non-HTTPS) | Denied |
| financial / trading ops | Denied |
| OFF / SHADOW | No external side effect |
| evidence write failure | Harness can raise; certification fails closed |
| direct adapter execute in production code | Bypass guard counts violations |

Repository defects are reported as **FAILED**, not ENVIRONMENT_BLOCKED.
