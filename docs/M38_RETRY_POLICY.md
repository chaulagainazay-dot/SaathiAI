# M38 — Retry Policy

## Retryable

timeout, connection failure, HTTP 429/500/502/503/504

## Non-retryable

missing/empty credential, auth denial/expiry, 401/403, scope mismatch, invalid
transition, call-budget exhaustion, concurrency rejection

## Bounds

* max attempts: 3 (default)
* schedule_ms: 50, 100, 200 (deterministic)
* Retry-After capped at 1000 ms
* no probabilistic or unbounded backoff
* no retry after cleanup begins
