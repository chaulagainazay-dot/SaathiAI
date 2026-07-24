# M52 Execution Inventory

## Pre-change call graph

| Entry | Path | Classification | M52 disposition |
|---|---|---|---|
| `POST /platform/agent/execute` | binding → service → gateway | canonical M51 | runtime inserted |
| `POST /platform/execute` | context → service → gateway | direct platform compatibility | runtime inserted |
| `PlatformService.execute_tool` | direct gateway | platform compatibility | wrapper delegates runtime |
| `PlatformAgentBinding.execute` | service | canonical binding | delegates runtime |
| `AgentExecutor.request_tool`, registered | direct gateway | functional legacy bypass of platform context | direct dispatch removed |
| `AgentExecutor.request_tool`, local LLM/video | `SaathiExecutionSystem` | functional legacy bypass of platform context | special dispatch removed |
| `saathi.tools.registry.execute_tool` | migrated bridge or bounded handlers | test-only/dead for platform reachability | retained outside platform; no production inbound caller found |
| `try_canonical_legacy_tool` | gateway | compatibility-only | retained; gateway-enforced |
| `ToolExecutionService.execute_tool` | gateway internals + tests/closure audits | internal low-level/test-only | unchanged |
| tool adapters | ToolExecutionService internals | internal low-level | unchanged |
| connector `ExecutionEngine` | established connector governance/gateway bridge | separate governed subsystem | unchanged; mutations dry-run |
| mission/scheduler layers | MissionEngine/pipeline/runtime | internal orchestration | unchanged; no M51 platform dispatch found |

## Post-change platform call graph

```text
/execute ───────────────┐
/agent/execute ─────────┤
PlatformAgentBinding ───┤
PlatformService wrapper ┤
bound AgentExecutor ────┘
  → PlatformAgentRuntime
  → ExecutionGateway.execute_registered_tool
  → ToolExecutionService.execute_tool
  → ToolRegistry → adapter
```

## Retained compatibility paths

### `PlatformService.execute_tool`

- Reason: public M50/M51 Python callers and tests still use it.
- Bypass proof: its body imports only `PlatformAgentRuntime` and delegates to
  `execute_context`, which revalidates the persisted session and binding.
- Removal condition: all Python callers use `PlatformAgentRuntime` or
  `PlatformAgentBinding`.
- Regression: `test_compatibility_wrapper_and_legacy_agent_bypass_prevention`.

### `AgentExecutor`

- Reason: M48/M10 orchestration still instantiates the class.
- Bypass proof: no gateway or `SaathiExecutionSystem` tool dispatch remains in
  `_gateway_execute`; absent runtime/token returns
  `PLATFORM_RUNTIME_REQUIRED`.
- Removal condition: legacy orchestration constructs a token-bound platform
  agent at its outer identity boundary.
- Regression: the same M52 compatibility test plus updated agent-runtime test.

### `try_canonical_legacy_tool`

- Reason: bounded M49 legacy names remain API compatibility.
- Bypass proof: migrated names call `ExecutionGateway`; mutation without an
  approval reference is blocked; platform callers do not reach it.
- Removal condition: M49 residual census reaches zero callers/handlers.
- Regressions: existing M49.3/M49.4 compatibility and closure tests.

## Baseline discrepancy

M51 documentation described `AgentExecutor → legacy execute_tool`. Current M51
source instead used direct `ExecutionGateway` for registered tools and
`SaathiExecutionSystem` for `local-llm-inference` and `video-generation`. M52
migrated the actual source paths, not the stale description.
