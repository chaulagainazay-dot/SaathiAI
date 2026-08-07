# M48.1 — Ledger and Event Contract

## Durable ledger

`RunStore` → SQLite `data/agent_runtime.db`

Tables: orchestration_run, agent_run, agent_step, task, task_dependency, delegation, tool_request, approval_request, verification, review, retry, run_event, run_checkpoint, failure, artifact, agent_message.

Every `transition()` validates RunState edges and emits `run.state` events.

## Event envelope (existing)

| Field | Storage |
|---|---|
| event id | run_event.id |
| run_id | run_event.run_id |
| name | e.g. `run.state` |
| payload | JSON |
| timestamp | created_at |

## Gateway evidence

`saathi.execution.results.Evidence` + ExecutionRecord — append-oriented audit for tool executions.

## Event bus

`saathi.events` fabric for cross-subsystem notifications; M10 also writes local run_event rows for recovery.
