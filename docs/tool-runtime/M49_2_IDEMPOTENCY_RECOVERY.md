# M49.2 Idempotency Recovery

`DurableIdempotencyStore.reconcile_stale()`:
- NO_SIDE_EFFECT / LOCAL_REVERSIBLE → release for retry
- mutations → OUTCOME_UNKNOWN
- financial → REQUIRES_REVIEW

CLI: `python -m saathi.agent_runtime.cli tools reconcile-idempotency`
