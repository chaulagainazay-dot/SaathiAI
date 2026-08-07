# ARCHITECTURE_OVERLAP_AUDIT

**Inspection tip:** `e1738d7deec5f44600fbf0d99e2b8f74a4bc83d0` (`hardening/fm-i6.2-macos-memory-gate-fix`)  
**Method:** code search + class inventory on committed sources. Documentation alone was not treated as proof of runtime.

## 1. Runtime and agents — multiple coexisting runtimes

| Component | Location | Role (as coded) | Overlap risk |
| --- | --- | --- | --- |
| **ExecutionGateway** | `saathi/execution/gateway.py` | Sole external tool-execution authority (M49) | Canonical — must remain sole |
| **ToolExecutionService / ToolRegistry** | `saathi/tool_runtime/` | Tool runtime service layer | Bound to gateway path |
| **AgentExecutor** | `saathi/agent_runtime/gateway_exec.py` | Agent tool path via gateway | Legacy-named but gateway-routed |
| **PlatformAgentRuntime** | `saathi/platform/runtime.py` | M52 platform-bound execution above gateway | Separate entry; constructs ExecutionGateway |
| **HarnessSessionController** | `saathi/agent_runtime/harness/controller.py` | FM-I session lifecycle; tools via RealExecutionGatewayAdapter | Newer governed session layer |
| **AgentHarness / FakeInMemoryHarness / LocalModelHarness** | `saathi/agent_runtime/harness/` | Protocol + fake + local model (no tools) | LocalModelHarness explicitly does not call gateway |
| **EngineeringOrchestrator** | `saathi/engineering/orchestrator.py` | Engineering control plane (M20) | Separate domain; disabled-by-default patterns |
| **AgentSessionAdapter** | `saathi/engineering/adapters/base.py` | Engineering session adapter ABC | FM-C2 documents relationship to harness — not fully collapsed |
| **application_harness scheduler / scheduled_graph / mission** | `saathi/application_harness/` | Mission graph scheduling & recovery | **M17 fix only on divergent tip** |
| **agent_runtime Orchestrator** | `saathi/agent_runtime/orchestrator.py` | M48 runtime orchestrator | Coexists with platform + harness |
| **saathi/agents/harness.py** | older path | Possible legacy name collision | Naming overlap with agent_runtime.harness |
| **CEO / computer_agent / studio_os agents** | various | Domain agents | Multiple agent facades |

### Findings

1. **More than one agent runtime exists by design** (M48 agent_runtime, M52 PlatformAgentRuntime, FM harness, EngineeringOrchestrator). FM-C1/C2 freeze this as known architecture debt with authority boundaries — not accidental duplication alone.
2. **Tool dispatch:** harness and platform paths intend to route tools through ExecutionGateway. Residual **direct `subprocess` usage** remains in `saathi/tools/*` (email, browser, hyperframes, projects allowlisted commands, pipelines). M49.3 docs claim freeform `shell=True` elimination for project shell; allowlisted subprocess remains.
3. **Mission authority / scheduler:** `application_harness` owns scheduled graph recovery. Concurrent recovery fix (M17) is **not** on recommended tip — race condition residual risk until cherry-pick.
4. **Model routing:** ModelRouter + inference gateway path + LocalModelHarness qualification apparatus coexist; local qualification ≠ production availability (M369/FM-I6 docs).

## 2. Tools and authority

| Concern | Status on tip |
| --- | --- |
| ExecutionGateway sole external authority | **Preserved** in contracts/harness docs and platform runtime wiring |
| Trading Guardian independent / fail-closed | **Preserved** (`docs/trading/*`, TG packages, connectivity governance) |
| Approval ≠ activation | **Encoded** in paper activation / provider contracts / production readiness flags |
| Financial execution | **PROHIBITED** at agent_runtime contract + harness controller |
| Client/model-created authority | Harness builds ToolIntent server-side patterns; residual legacy tools need ongoing audit |
| Duplicate registries | ToolRegistry (tool_runtime) + agent registries + module registry (UI) — different scopes |
| Live trading / provider connectivity | Flags default false; LOOP_STATE on private-alpha chain records all connectivity false |

### Bypass residual (not claimed closed)

- Domain tools still calling `subprocess` outside gateway wrappers
- Computer agent / browser drivers may hold privileged local paths
- Full inventory of every call site → gateway is **not** re-certified in this audit (scope = overlap detection)

## 3. Voice (architecture overlap)

Multiple independent microphone / speech owners (see `VOICE_RUNTIME_INVENTORY.md`):

- Global `VoiceRuntimeProvider` + `VoiceOutputProvider`
- Chat `VoiceControl`
- Settings page local getUserMedia/SpeechRecognition tests
- Legacy `/voice` enrollment MediaRecorder
- Server SpeechService + voice-runtime API + legacy voice session API

This is **product-surface duplication**, not a second backend authority for tools — but dual client stacks increase lifecycle bugs (partially addressed in E2E recovery: route-change cleanup, output-cancel-before-mic).

## 4. Trading systems (architecture)

TG lives under `saathi/platform/tg/` with subdomains: paper_activation, paper_simulation, portfolio_risk, market_observation, broker_sandbox, connectivity_governance, provider_contracts, research_*, kill_switch, etc.

Separate older modules: `saathi/portfolio.py`, `saathi/investment_pipeline.py`, `saathi/platform/paper_trading/`, `saathi/platform/trading_models.py`.

**Risk:** dual portfolio/risk concepts (legacy portfolio modules vs TG portfolio engines). Prefer TG as investment authority going forward; document legacy as non-canonical.

## 5. Scheduling / recovery controllers

| Controller | Package | Conflict |
| --- | --- | --- |
| Scheduled graph recovery | application_harness | Needs M17 idempotent recovery |
| Harness durable recovery | agent_runtime.harness | Session/event persistence FM-I3 |
| Platform reconcile | PlatformAgentRuntime.reconcile* | Execution record reconciliation |
| TG durable paper recovery | paper_activation.durable | Paper ops only |

Scopes differ; **do not merge controllers**. Do ensure M17 lands on baseline.

## 6. Overlap verdict

| Question | Answer |
| --- | --- |
| More than one agent runtime? | **YES** — intentional layered history; needs continued consolidation, not silent delete |
| More than one mission authority? | **Partially** — mission graphs vs platform missions vs agentdev missions |
| More than one tool dispatch path? | **YES** — gateway-mediated + residual direct tools |
| Direct tool execution bypassing gateway? | **Residual risk YES** in legacy tools/subprocess |
| Incompatible histories if naively merging m344-remote + harness tip? | **YES** — post-m369 divergence; integrate via cherry-pick m17 onto harness tip, not reverse merge of whole remote tip without care |
