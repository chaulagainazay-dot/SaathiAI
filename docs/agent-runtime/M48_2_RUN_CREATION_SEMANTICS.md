# M48.2 — Run Creation Semantics

## Strategy A (chosen): validate before persistence

```text
invalid / prohibited request
  → structured AgentRunRecord(status=rejected)
  → no orchestration_run row
  → no RUN_STARTED / success events
```

```text
valid request
  → validation.passed metadata
  → store.create_run (CREATED)
  → PLANNING → task DAG → QUEUED
  → optional Orchestrator.run
```

## Idempotency

- Optional `idempotency_key` stored in run budget metadata.
- Same key + same request fingerprint → return existing run.
- Same key + different fingerprint → `IDEMPOTENCY_CONFLICT`.

## Terminal immutability

Unchanged: `validate_transition` rejects reactivation of terminal `RunState`s.
