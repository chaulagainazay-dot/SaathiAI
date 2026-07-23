# M49.1 Tool Architecture Inventory

| Path | Domain | Registry | Caller | Status | Decision |
|---|---|---|---|---|---|
| ExecutionGateway | execution | universal boundary | API/connectors/agent | CANONICAL | KEEP + extend |
| ToolExecutionService (new) | tool_runtime | ToolRegistry | Gateway | CANONICAL | MIGRATE_NOW |
| AgentExecutor.request_tool | agent_runtime | policy + gateway | orchestrator | PARTIAL→CANONICAL | WRAP_CANONICAL |
| SaathiExecutionSystem | execution | ops: llm/video | AgentExecutor | CANONICAL ops | KEEP_BOUNDED |
| saathi.tools.registry TOOL_SCHEMAS | voice/agent | schema list | saathi.agent | LEGACY | DEFER_WITH_REASON |
| connectors.platform.registry | connectors | ToolDef | connector platform | LEGACY | DEFER_WITH_REASON |
| connectors.gov runtime | connectors | governed | gateway submit | PARTIAL | WRAP_CANONICAL later |
| finance execution.trade | finance | BrokerRegistry | trade UI | FINANCIAL | PROHIBITED for agent tools |
| IELTS agents tools | ielts | domain | agents | LEGACY | DEFER_WITH_REASON |
| browser tools | browser | governed browser | gateway | LEGACY/PARTIAL | DEFER_WITH_REASON |
| M49 builtins echo/note/timeout/cancel/fin | tool_runtime | ToolRegistry | gateway | CANONICAL | MIGRATE_NOW |

## Direct bypasses
- Historical: saathi.tools.execute_tool from voice agent (deferred; not agent_runtime path)
- AgentExecutor unknown tools: now **rejected** (fail-closed), not success

## Migration slice (M49.1)
m49.echo_readonly, m49.local_note_write, m49.timeout_demo, m49.cooperative_cancel, m49.financial_execution_stub (prohibited)
