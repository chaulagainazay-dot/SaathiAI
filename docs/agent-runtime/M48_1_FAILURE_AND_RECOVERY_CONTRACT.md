# M48.1 — Failure and Recovery Contract

| Scenario | Behavior |
|---|---|
| User cancel | `Orchestrator.cancel` → CANCELLED; no further tasks |
| Timeout | TIMED_OUT terminal |
| Provider unavailable | ModelResolutionStatus.UNAVAILABLE ≠ success |
| Tool failure | task failed; retry only if transient + progress |
| Approval missing | AWAITING_APPROVAL / BLOCKED; not success |
| Approval expired | cannot resolve; fail-closed |
| Process restart | checkpoints + RunStore recovery; terminal states immutable |
| Duplicate submit | gateway idempotency + ledger uniqueness tests |
| Unknown state | BLOCKED / FAILED — never SUCCESS |
| Unbounded retry | contracts reject max_retries > 5 |

Principles: cooperative cancel; terminal no silent resume; non-idempotent no blind retry; durable evidence preferred over process memory.
