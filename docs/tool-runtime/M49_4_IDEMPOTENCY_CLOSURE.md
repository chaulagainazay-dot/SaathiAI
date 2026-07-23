# M49.4 Durable Idempotency Closure

## Implementation

`saathi.tool_runtime.durable_idempotency.DurableIdempotencyStore`

- Storage: SQLite at `data/tool_runtime/idempotency.db` (DEFAULT_DB)
- BEGIN IMMEDIATE reservation
- Fingerprint conflict detection
- Lease ownership + expiry
- Replay of terminal SUCCESS
- Stale recovery rules (read-only vs mutation)
- Uncertain mutation → OUTCOME_UNKNOWN / no auto-retry
- Result persistence with redaction path

## Classification

```text
SINGLE_HOST_SAFE
MULTI_HOST_UNSAFE
MULTI_HOST_NOT_REQUIRED_FOR_CURRENT_SCOPE
```

Do **not** claim multi-host / distributed safety.

## Tests

- `tests/test_m49_2_durable_idempotency.py`
- `tests/test_m49_4_regression_gates.py::test_m49_2_durable_idempotency_replay`

## State

`DURABLE_IDEMPOTENCY_ENFORCED` (single-host)
