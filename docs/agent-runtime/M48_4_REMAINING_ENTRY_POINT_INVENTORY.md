# M48.4 — Remaining Entry Point Inventory

| name | path | decision |
|---|---|---|
| start_agent_run | service.py | CANONICAL |
| API POST /agents/runs | api.py | FULLY_CONVERGED |
| CLI run/run-team | cli.py | FULLY_CONVERGED |
| Chat start_orchestration | chat/engine.py | FULLY_CONVERGED |
| Chat run_agent (M8) | chat/engine.py | **WRAP_CANONICAL** (M48.4) |
| Chat delegate | chat/engine.py | WRAP (via run_agent) |
| Orchestrator.create_run | orchestrator.py | gated; skip_contract **test-only** |
| RunStore.create_run | store.py | TEST_ONLY / low-level |
| gateway_llm / AgentExecutor | gateway_exec.py | internal after lease |
| IELTS MasterAgent | saathi/agents/ | DEFER_WITH_REASON |
| EngineeringOrchestrator | engineering/ | DEFER_WITH_REASON |
| Finance ExecutionService | execution/trade.py | PROHIBITED for agent façade |
| saathi.agent.SaathiAgent | agent.py | DEFER (product voice path) |
