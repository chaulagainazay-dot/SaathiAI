# M48.3 — Cancellation and Kill Switch

Flow: request → durable cancel_* fields → propagating → CANCELLED terminal → task status cancelled.

Idempotent re-request. New tools/tasks check `is_cancel_requested` before start.

Kill switch scopes: `run` | `mission` (budget.mission_id) | `all` active runs.

Not connected to trading. CLI: `kill-switch all|run <id>|mission <id>`.
