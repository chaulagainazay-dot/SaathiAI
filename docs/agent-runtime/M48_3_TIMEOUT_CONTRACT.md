# M48.3 — Timeout Contract

- `deadline_at` set at create (budget.timeout_sec or default 300s)
- wall-clock `max_wall_sec` on Orchestrator.run
- `enforce_timeout` → TIMED_OUT + evidence `run.timeout`
- Nested tool timeouts remain ExecutionGateway ToolIntent.timeout (1–3600s)
- Cancellation grace: reconcile STALE_CANCELLATION_PENDING
