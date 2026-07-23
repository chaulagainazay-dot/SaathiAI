# M49.1 Implementation Plan

## Goal
Canonical fail-closed tool execution framework beneath existing ExecutionGateway.

## Approach
1. Inventory existing tool paths (agent_runtime, saathi.tools, connectors, execution)
2. Add `saathi/tool_runtime` contracts + registry + service
3. Integrate via `ExecutionGateway.execute_registered_tool`
4. Migrate bounded builtins only
5. Tests + docs + draft PR

## Non-goals
Second gateway, live trading, full tool migration, plugin marketplace, M49.2.
