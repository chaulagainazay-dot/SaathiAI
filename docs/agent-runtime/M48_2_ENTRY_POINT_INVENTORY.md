# M48.2 — Entry Point Inventory

| name | path | purpose | migration |
|---|---|---|---|
| API POST /api/v1/agents/runs | `agent_runtime/api.py` | HTTP create run | **MIGRATED** → `start_agent_run` |
| Chat start_orchestration | `chat/engine.py` | multi-agent from chat | **MIGRATED** → `start_agent_run` |
| CLI run / run-team | `agent_runtime/cli.py` | local CLI | **MIGRATED** → `start_agent_run` |
| Orchestrator.create_run | `agent_runtime/orchestrator.py` | core create | **ADAPT** — contract gate (skip only tests) |
| ChatEngine.run_agent | `chat/engine.py` | single-agent M8 turn | **KEEP_COMPATIBILITY** (not multi-agent orchestrator) |
| IELTS MasterAgentLoop | `saathi/agents/master.py` | domain coaching | **OUT_OF_SCOPE** / LEGACY |
| saathi.agent.SaathiAgent | `saathi/agent.py` | product voice/text | **OUT_OF_SCOPE** |
| EngineeringOrchestrator | `saathi/engineering/` | code repair | **OUT_OF_SCOPE** |
| Finance ExecutionService | `execution/trade.py` | paper/live trade layer | **PROHIBITED** for agent façade |
| Application harness ledger | M17 run ledger | harness jobs | **OUT_OF_SCOPE** |
| Tests store.create_run | tests | low-level store | **KEEP** (not orchestrator) |
