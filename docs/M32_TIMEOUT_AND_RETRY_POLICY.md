# M32 — Timeout & Retry Policy

Modules: `retry.py`, `config.py`, `runtime.py`

## Bounded execution

Every provider call is bounded: connect timeout, read timeout, total deadline,
request/response size limits, retry ceiling, concurrency ceiling, cancellation,
idempotency classification, safe error classification. No unbounded waiting; no
infinite retry; no automatic retry for non-idempotent writes. The M32 pilot is
read-only.

Retry delay is consumed as **virtual time** in the runtime loop (no real
sleeping), so no wall-clock wait ever exceeds the deadline and tests stay
deterministic.

## Retry categories (`RetryCategory`)

`NO_RETRY`, `SAFE_RETRY`, `RETRY_AFTER`, `REAUTH_REQUIRED`, `RATE_LIMITED`,
`PROVIDER_UNAVAILABLE`, `PERMANENT_FAILURE`, `POLICY_BLOCKED`, `CANCELLED`.
Retryable set: `SAFE_RETRY`, `RETRY_AFTER`, `RATE_LIMITED`, `PROVIDER_UNAVAILABLE`.

## `decide_retry` gates (all must hold)

A retry is permitted only when: the operation is idempotent (or the provider
declares idempotency support), the error category is retryable, retry budget
remains (`attempt ≤ max_retries`), the delay fits the remaining deadline, the
credential is eligible, approval is valid, the provider is not quarantined,
rollout permits, and the request fingerprint is unchanged.

No retry for: invalid approval, scope violation, credential revocation/quarantine,
malformed local request, prohibited provider, changed payload, or a non-idempotent
write without provider idempotency support. `REAUTH_REQUIRED` never loops.

Backoff is deterministic (`deterministic_backoff`, no jitter); `Retry-After` is
honored only when `≤ max_retry_after` and `≤ remaining_deadline`.
