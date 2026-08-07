# M49.2 Tool and Connector Inventory

| Identifier | Path | Domain | Registry | Decision |
|---|---|---|---|---|
| ExecutionGateway | saathi/execution | execution | universal | CANONICAL_EXECUTION |
| ToolExecutionService | saathi/tool_runtime | tool_runtime | ToolRegistry | CANONICAL |
| saathi.tools TOOL_SCHEMAS | saathi/tools/registry.py | voice/tools | DISCOVERY + handlers | COMPATIBILITY_SOURCE |
| connectors.platform | saathi/connectors/platform | connectors | ToolDef catalog | DISCOVERY_ONLY / WRAP partial |
| finance trade | saathi/execution/trade | finance | BrokerRegistry | PROHIBITED for agent tools |
| browser | computer_agent / tools | browser | various | DEFER_WITH_REASON |
| IELTS | saathi/agents | ielts | domain | DEFER_WITH_REASON |
| engineering | engineering orchestrator | eng | domain | DEFER_WITH_REASON |
| subprocess (legacy shell) | tools/system.run_shell | shell | PRIVILEGED | BLOCK freeform; use m49.subprocess_diag |

## M49.2 migrated slice
See M49_2_MIGRATION_WAVES.md
