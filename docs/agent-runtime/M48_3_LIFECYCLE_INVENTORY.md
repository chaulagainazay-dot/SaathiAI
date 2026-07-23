# M48.3 — Lifecycle Inventory

| component | path | durability | status |
|---|---|---|---|
| Orchestrator run/pause/resume/cancel | `orchestrator.py` | via RunStore | CANONICAL (extended) |
| RunStore + events/checkpoints | `store.py` | SQLite | DURABLE + M48.3 columns |
| RunState transitions | `models.py` | in-code matrix | CANONICAL |
| Policy retry | `policy.py` | pure | CANONICAL |
| Lifecycle controller | `lifecycle.py` | RunStore-backed | **CANONICAL (M48.3)** |
| ExecutionGateway cancel/retry | `execution/universal.py` | tool executions | CANONICAL (tools) |
| M8 run_agent | `chat/engine.py` | chat store | LEGACY separate |
| Application harness ledger | M17 | separate | OUT_OF_SCOPE |
