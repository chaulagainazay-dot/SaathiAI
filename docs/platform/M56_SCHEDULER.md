# M56 Scheduler Foundation

An advisory scheduling abstraction that prepares for future distributed
scheduling. **Single-host execution only — it produces an ordering/assignment
plan; PlatformAgentRuntime still performs all execution.**

## Plan — `GET /cluster/scheduler` (RUNTIME_READ)
Over pending executions (CREATED/QUEUED/READY/WAITING_APPROVAL), produces:
- deterministic ordering: approval-blocked last, then FIFO by creation time
  (fair, priority-aware);
- round-robin worker assignment over ACTIVE workers;
- `execution_mode: "single_host_inline"` (no distributed processing).

## Control — `POST /cluster/scheduler/control {action}` (RUNTIME_OPERATE)
`pause` / `resume`. State is config-persisted and survives restart.

## Retry / priority
Retry is expressed by re-queuing an execution through the canonical runtime;
priority is the ordering above. No second execution engine is introduced.
