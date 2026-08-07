# M49.2 Idempotency Migration

Additive schema only. Default ToolExecutionService uses DurableIdempotencyStore.
Process-local IdempotencyStore remains for unit tests.

Rollback: delete DB file; code falls back if durable import fails.
No raw secrets in fingerprints (request-level secret rejection first).
