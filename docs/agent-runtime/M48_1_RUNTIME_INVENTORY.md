# M48.1 — Runtime Inventory

**Branch:** `milestone/m48-agent-runtime-baseline`  
**Base:** `master` @ `67efcb3`  
**Method:** source inspection only (no live provider calls)

## Canonical components

| component | path | purpose | entry | status | notes |
|---|---|---|---|---|---|
| M10 Agent Runtime package | `saathi/agent_runtime/` | multi-agent orchestration | `Orchestrator`, API, CLI | **IMPLEMENTED** | **canonical** |
| Run models + state machine | `agent_runtime/models.py` | RunState, RiskClass, Task, transitions | import | IMPLEMENTED | canonical |
| RunStore ledger | `agent_runtime/store.py` | SQLite `data/agent_runtime.db` | RunStore | IMPLEMENTED | durable |
| Policy | `agent_runtime/policy.py` | tool risk, approval, narrowing | check_tool | IMPLEMENTED | fail-closed |
| Orchestrator | `agent_runtime/orchestrator.py` | plan DAG → execute → verify | create_run/run | IMPLEMENTED | cancel/pause/resume |
| Gateway executor | `agent_runtime/gateway_exec.py` | agent turns via ExecutionGateway | AgentExecutor | IMPLEMENTED | no direct provider |
| Registry | `agent_runtime/registry.py` | agent definitions | get/all_agents | IMPLEMENTED | 8 production agents |
| Task graph | `agent_runtime/graph.py` | DAG cycle detection | TaskGraph | IMPLEMENTED | |
| Strategies | `agent_runtime/strategies.py` | plan/build role chains | choose_strategy | IMPLEMENTED | |
| HTTP API | `agent_runtime/api.py` | auth-gated run APIs | FastAPI routes | IMPLEMENTED | |
| CLI | `agent_runtime/cli.py` | inspect/run/status | `python -m saathi.agent_runtime.cli` | IMPLEMENTED | |
| M48.1 contracts | `agent_runtime/contracts.py` | fail-closed request validation | validate_run_request | **IMPLEMENTED (M48.1)** | additive |
| ExecutionGateway | `saathi/execution/gateway.py` | single tool side-effect authority | submit/approve | IMPLEMENTED | **canonical tools** |
| ToolIntent | `saathi/execution/toolintent.py` | immutable intent | ToolIntent | IMPLEMENTED | |
| Universal boundary | `saathi/execution/universal.py` | state/recovery | UniversalBoundary | IMPLEMENTED | |
| Model router | `saathi/model_router.py` | capability-based routing | labels | IMPLEMENTED | injectable |
| Chat engine | `saathi/chat/engine.py` | M8 chat + agent roles | run_agent | IMPLEMENTED | may call orchestrator |
| Memory engine | `saathi/memory/engine/` | M9 scoped memory | default_engine | IMPLEMENTED | |
| Event bus | `saathi/events/` | fabric events | publish | IMPLEMENTED | |
| Evidence | `saathi/evidence/` | audit evidence | | PARTIAL | gateway Evidence |
| Missions | `saathi/missions/` | mission domain | | IMPLEMENTED | pipeline layering |
| Scheduler | (mission/scheduler tests) | due jobs | | IMPLEMENTED | see critical manifest |
| Pipeline/graph | `saathi/graph/` | pipeline DAG | | IMPLEMENTED | separate from M10 graph |

## Legacy / domain / parallel (not general runtime)

| component | path | status | disposition |
|---|---|---|---|
| IELTS BMA agents | `saathi/agents/` (master, harness, router) | LEGACY domain | **KEEP; do not replace** — Groq-direct coaching |
| `saathi/agent.py` | root SaathiAgent | LEGACY | voice/text product agent |
| Finance ExecutionService | `saathi/execution/trade.py` | IMPLEMENTED | paper-first trade layer; **not** agent runtime |
| Computer agent | `saathi/computer_agent/` | IMPLEMENTED | gateway-governed desktop ops |
| CEO OS | `saathi/ceo/` | PARTIAL | briefing surface |

## Tests

| suite | path | status |
|---|---|---|
| M10 runtime | `tests/test_agent_runtime.py` | IMPLEMENTED |
| M48.1 contracts | `tests/test_m48_1_agent_runtime_contracts.py` | IMPLEMENTED |
| Execution gateway | critical manifest `execution.*` | IMPLEMENTED |

## Ollama (read-only discovery)

Local list observed during M48.1 inventory (host-dependent): `qwen3:8b`, `qwen2.5:1.5b`. No models downloaded or removed.
