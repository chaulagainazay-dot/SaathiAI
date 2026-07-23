# M49.2 Registry Convergence

| Registry | Status |
|---|---|
| saathi.tool_runtime.ToolRegistry | CANONICAL_EXECUTION_REGISTRY |
| saathi.tools.registry TOOL_SCHEMAS | DISCOVERY_ONLY + COMPATIBILITY_SOURCE |
| connectors.platform.registry | DISCOVERY_ONLY (fixtures wrapped as canonical tools) |

Bridge: `compat.try_canonical_legacy_tool` after governance gate.
Missing manifest fields never get permissive defaults.
