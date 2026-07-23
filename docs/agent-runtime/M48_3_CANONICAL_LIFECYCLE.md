# M48.3 — Canonical Lifecycle

**Owner:** `RunLifecycleController` (`lifecycle.py`) coordinating `Orchestrator` + `RunStore`.

| Concern | Owner |
|---|---|
| State transitions | RunStore.transition + models.RunState |
| Persistence | RunStore |
| Attempts | orchestration_run.attempt |
| Heartbeat/lease | lifecycle.acquire_lease / heartbeat |
| Cancellation | lifecycle.request_cancel → Orchestrator.cancel |
| Timeout | lifecycle.enforce_timeout + run deadline_at |
| Recovery | lifecycle.recover_run / recover_all |
| Events | RunStore.event ordered by created_at |

No second orchestrator or run store.
