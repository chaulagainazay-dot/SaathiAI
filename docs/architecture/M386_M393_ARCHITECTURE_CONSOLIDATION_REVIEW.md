# M386–M393 — SaathiOS Architecture Consolidation and Overlap Review

| Field | Value |
| --- | --- |
| **Status** | ANALYSIS + DESIGN COMPLETE — documentation only |
| **Date** | 2026-08-06 |
| **Terminal verdict** | `SAATHIOS_ARCHITECTURE_READY_WITH_CONSOLIDATION_REQUIRED` |
| **Branch** | `milestone/m377-m385-qm-agent-harness-design` |
| **Repository SHA inspected** | `e9581f43848cf90283c7c4e1c0dbfbad65a4a531` |
| **Formal ADR** | [`docs/adr/ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION.md`](../adr/ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION.md) |
| **Mode** | Read-only source + documentation verification; **no** runtime, schema, CI, provider, or credential changes |

---

## Integrity statement

This milestone changes **documentation only** under:

- `docs/adr/`
- `docs/architecture/`
- `docs/AUTONOMOUS_ROADMAP.md`

It does **not**:

- implement AgentHarness, policy floors, skill promotion, or FakeInMemoryHarness;
- refactor, delete, or migrate production modules;
- connect providers or add credentials;
- change ExecutionGateway, Approval, RBAC, audit, certification, or Trading Guardian behavior;
- weaken any authority boundary;
- claim production readiness.

Claims below cite **current source paths** inspected at the SHA above. Milestone reports were used as leads only; contradictory docs are listed in §14.

### Milestone renumbering note

| Prior (QM/M385 ADR) | This review |
| --- | --- |
| M386 = policy floor design | **M386–M393 = architecture consolidation** |
| M387 = skill promotion design | Policy floors & skill promotion **deferred**, not cancelled |

---

# Primary decision question

**What should the authoritative SaathiOS architecture be before any new foundational runtime abstraction is implemented?**

### Answer (summary)

SaathiOS already has a **governance-first control plane**:

```text
Product surfaces (chat, platform API, CLI, consoles)
        ↓
Orchestration planes (agent_runtime | PlatformAgentRuntime / mission_runtime | bounded domain)
        ↓
Immutable ToolIntent / registered tool request
        ↓
ExecutionGateway (validate → authorize → risk → approval → credentials → execute)
        ↓
Family handlers (tool_runtime, connectors, browser, application_harness, computer_agent, inference)
        ↓
Evidence + audit + run ledgers + certification packages
```

**Trading Guardian** sits as an independent **veto** before any order-class intent may approach execution.

**AgentHarness** (M385 design only) may later sit **under** orchestration as an **untrusted multi-turn driver**, never as a second gateway.

Before implementing new foundations, **freeze expansion** of parallel harness/session/approval planes and reconcile existing `engineering.AgentSessionAdapter` with the AgentHarness design.

---

# Mandatory principles preserved

| Principle | Status in review |
| --- | --- |
| Fail-closed execution | Reaffirmed |
| ExecutionGateway as governed execution boundary | Reaffirmed sole external-action authority |
| Approval as authorization lifecycle | Reaffirmed; multiple *implementations* noted, not dual self-approval rights |
| RBAC and tenancy isolation | Reaffirmed (platform M50+) |
| Provider governance | Reaffirmed (inference M21–M25) |
| Trading Guardian restrictions | Reaffirmed; paper/research/sandbox only unless separately authorized |
| Audit and replay | Distinct ownership reaffirmed |
| Evidence-based certification | Reaffirmed |
| Explicit authority ownership | Matrix in §M387 |
| Bounded cancellation and idempotency | Present; residual RR-02 cooperative cancel accepted |
| No hidden execution path | Residual legacy domains documented, not expanded |
| No implicit provider/credential authority | Reaffirmed |
| No production-readiness without evidence | Reaffirmed |

---

# M386 — Architecture inventory

**Method:** directory enumeration of `saathi/` (~1326 Python files, ~136 second-level packages) + class/interface grep + key file reads + maturity matrix cross-check.

**Legend — status:** `ACTIVE` | `EXPERIMENTAL` | `DEPRECATED` | `DUPLICATED` | `UNCLEAR` | `DESIGN_ONLY`
**Legend — maturity:** from CAPABILITY_MATURITY_MATRIX + source presence (not a new certification).

## M386.1 Component inventory table

| Name | Source path | Documentation path | Originating milestone | Responsibility | Public interfaces | State owned | Authority owned | Dependencies | Dependents | Persistence | Execution privileges | Maturity | Certification | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Agent Runtime (M10/M48) | `saathi/agent_runtime/` | `docs/agent-runtime/M48_*` | M10, M48.1–5 | Multi-agent plan/DAG/run lifecycle | `Orchestrator`, `service`, API, CLI, `contracts` | Runs, tasks, events, leases | Run lifecycle + contract validation | ExecutionGateway, models | Chat multi-agent, CLI | SQLite `data/agent_runtime.db` (RunStore) | Plans/tools via gateway_exec | deterministic-tested | M48 residual accepted | **ACTIVE** canonical general multi-agent |
| RunStore (agent) | `agent_runtime/store.py` | M48.3 durable state | M10 | Durable agent runs | `RunStore` | Run rows, events, checkpoints | Run state machine | SQLite | Orchestrator, lifecycle, API | SQLite | none external | implemented | — | **ACTIVE** |
| Run lifecycle | `agent_runtime/lifecycle.py` | M48.3 | M48.3 | Lease, cancel, stale, recovery classes | `RunLifecycleController` | Leases, cancel flags | Cancel/kill for agent runs | RunStore | Orchestrator | SQLite | cancel signals | implemented | — | **ACTIVE** |
| Agent contracts | `agent_runtime/contracts.py` | M48.1 authority | M48.1 | Fail-closed request validation; FINANCIAL_EXECUTION PROHIBITED | `AgentRunRequest`, `AuthorityClass` | none | Contract rejection authority | models | service, API | none | none | implemented | — | **ACTIVE** |
| Agent policy | `agent_runtime/policy.py` | M48.1 | M10 | Tool risk / approval narrowing for runs | `check_tool` | none | Deny/allow proposal | RiskClass | Orchestrator | none | none | implemented | — | **ACTIVE** |
| AgentExecutor / gateway_exec | `agent_runtime/gateway_exec.py` | M48.1 execution | M10 | LLM/tool turns via gateway | `AgentExecutor`, `gateway_llm` | in-run cancel token | none (proposes) | ExecutionGateway | Orchestrator | none | tool via gateway | implemented | — | **ACTIVE** |
| Agent registry (runtime) | `agent_runtime/registry.py` | M48.1 inventory | M10 | Production agent definitions | get/all_agents | definitions | none | models | Orchestrator | code | none | implemented | — | **ACTIVE** |
| Platform Agent Runtime | `saathi/platform/runtime.py` | M52 docs in platform | M52 | Platform-scoped tool dispatch lifecycle | `PlatformAgentRuntime` | PlatformExecutionRecord | Platform execution coordination | PlatformStore, EG | mission_runtime, orchestration, fleet | Platform SQLite | via `execute_registered_tool` | deterministic-tested | Phase A fleet cert | **ACTIVE** platform multi-agent path |
| Platform core service | `saathi/platform/service.py` | M50+ | M50 | Tenancy, RBAC, approvals, modules | platform APIs | users/orgs/workspaces/projects | RBAC grant evaluation | PlatformStore | all platform modules | SQLite | tool path via EG | deterministic-tested | private alpha etc. | **ACTIVE** |
| Platform models | `saathi/platform/models.py` | M50 | M50 | Roles, permissions, approval records | enums/dataclasses | schema definitions | permission vocabulary | — | entire platform | — | — | implemented | — | **ACTIVE** |
| Platform identity | `saathi/platform/identity.py` | M51 | M51 | Local-alpha auth → IdentityAssertion | providers | sessions (auth) | authentication | PlatformStore | API | SQLite | none | deterministic-tested | — | **ACTIVE** preferred product identity |
| Security identity (OAuth skeleton) | `saathi/security/identity.py` | security docs | earlier | OAuth/SSO adapter skeleton | `IdentityProviderRouter` | none live | none until configured | — | future SSO | none | none | implemented skeleton | not live | **ACTIVE** but **incomplete**; parallel naming |
| Mission domain (product) | `saathi/missions/` | mission docs | pre-M50 | Brand/content/workflow missions | MissionStore, workflows | mission domain rows | domain ops (not EG) | various | product surfaces | SQLite | varies | implemented | — | **ACTIVE** product layer; **not** M10 runtime |
| Mission Runtime (platform) | `saathi/platform/mission_runtime/` | CAPABILITY matrix M69–M72 | M69–M72 | Durable mission hierarchy/DAG/budgets | service, orchestrator, agents | mission graphs | mission orchestration only | PlatformAgentRuntime | private alpha, UI | platform store | via PAR→EG | deterministic+browser | M72 cert | **ACTIVE** |
| Platform orchestration | `saathi/platform/orchestration/` | M95–M102 | M95–M102 | Plan compile/validate/roles | service | plans | planning only | mission_runtime | UI `/orchestration` | platform | no direct tools | deterministic-tested | browser cert | **ACTIVE** |
| Engineering agent sessions | `saathi/engineering/` | engineering docs | engineering series | Claude Code / mock session adapters | `AgentSessionAdapter` | session ledger | **must not** own tools | adapters | engineering console | session ledger | process launch (bounded) | partial | RR-08 deferred orch | **ACTIVE**; **overlaps AgentHarness design** |
| AgentHarness (design) | docs only | ADR-AGENT-HARNESS + M385 | M385 | Multi-turn driver contract | design Protocol | n/a | none (forbidden) | future controller | future | n/a | none | design-only | n/a | **DESIGN_ONLY** |
| ApplicationHarness | `saathi/application_harness/` | M17.3–M17.21 docs | M17.3+ | Argv CLI tool harness under gateway | `ApplicationHarnessAdapter`, registry | harness runs/ledger | process spawn under trust | EG families | media/db/json tools | SQLite harness ledger | argv only, no shell=True | live-app tested (4 apps) | various M17 | **ACTIVE** distinct from AgentHarness |
| ExecutionGateway | `saathi/execution/gateway.py` | ADR-EXECUTIONGATEWAY | Phase 3.2 / M17.22 | Sole external-action authority | `submit`, `execute_registered_tool`, approve/cancel | ExecutionRecords via boundary | **tool execution authority** | ToolIntent, UniversalBoundary | agent_runtime, platform, connectors | queue + store | invokes handlers | live+red-team / deterministic | M15.2, M17.22 | **ACTIVE** canonical |
| UniversalBoundary | `saathi/execution/universal.py` | M17.22 | M17.22 | Durable submit pipeline | `UniversalBoundary.submit` | execution records | permission/risk/approval gates | ToolIntent, handlers | ExecutionGateway | SQLite/memory queue | family dispatch | deterministic-tested | M17.22 | **ACTIVE** |
| ToolIntent | `saathi/execution/toolintent.py` | ADR-TOOLINTENT | Phase 3 | Immutable intent contract | `ToolIntent`, builder | none (immutable values) | none | — | gateway | none | none | implemented | — | **ACTIVE** |
| ToolExecutionService | `saathi/tool_runtime/service.py` | M49 tool framework | M49 | Governed tool execution service | `ToolExecutionService` | durable idempotency | executes registered tools under policy | ToolRegistry, contracts | EG local/tool family | DurableIdempotencyStore | tool handlers | deterministic-tested | M49 closure audits | **ACTIVE** |
| ToolRegistry | `saathi/tool_runtime/registry.py` | M49 | M49 | Tool manifests registration | `ToolRegistry` | registry | registration not permission | contracts | service, platform | memory/code | none | implemented | M49.4 closure | **ACTIVE** |
| Command manifests | `tool_runtime/command_manifest.py` | M49 | M49 | Allowlisted argv commands | get/list/run_allowlisted | none | allowlist enforce | — | tools | code | argv | implemented | shell closure audit | **ACTIVE** |
| ModelRouter | `saathi/model_router.py` | M48.1 model routing | earlier/M48 | Capability label → model | `ModelRouter` | none | selection advice | provider specs | chat, runtime | none | none | implemented | — | **ACTIVE**; complement to inference |
| ModelGateway (exec orch) | `execution/orchestrators/model_gateway.py` | older exec docs | Phase 3 | LLM provider enum gateway | `ModelGateway` | — | historical path | providers | residual callers | — | may call models | implemented | residual | **DUPLICATED** surface vs inference |
| Inference stack | `saathi/inference/` | M21–M25 docs | M21–M25 | Provider policy, runtime gate, cert, cost | governance, engine, cert | governance store, cost | provider policy / kill | catalogue | chat, agent turns | SQLite | model invoke under policy | durable gov tested; live env-blocked | M24/M25 limitations | **ACTIVE** provider plane |
| Credentials | `saathi/credentials/` | M35–M46 docs | M35+ | Secret handles, leases, sessions | lease, m35–m46 APIs | leases, sessions | credential materialization | approvals | gateway, connectors | SQLite | lease at exec only | deterministic-tested | M35+ | **ACTIVE** |
| Approvals (platform) | `platform/models.py` + service | M50 | M50 | Product approval lifecycle | request/decide APIs | ApprovalRecord | decide/request perms | RBAC | mission, tools | PlatformStore | none | deterministic-tested | — | **ACTIVE** product SoT |
| Approvals (gateway) | execution state + universal | ADR-EG | Phase 3 | Execution binding approval | ApprovalGate path | intent states | fail-closed exec wait | ToolIntent | UniversalBoundary | exec store | none | live+red-team | — | **ACTIVE** execution SoT |
| Approvals (agent contracts) | `agent_runtime/contracts.py` | M48.1 | M48.1 | Run-level approval records | `ApprovalRecord` | run-linked | contract validate | — | Orchestrator | RunStore | none | implemented | — | **ACTIVE** run binding |
| Approvals (credentials M35) | `credentials/m35.py` | M35 | M35 | ApprovalEnvelope for secrets | envelopes | lease linkage | credential gate | — | leases | SQLite | none | deterministic-tested | — | **ACTIVE** secret binding |
| Approvals (TG domains) | `platform/tg/**/approvals*` | TG series | M192+ | Paper/activation/connectivity approvals | various centers | TG-specific | TG domain only | TG policy | TG UIs | TG stores | none order live | paper certs | WITH_LIMITATIONS | **ACTIVE** specialized |
| Memory engine | `saathi/memory/engine/` | memory docs M9 | M9 | Scoped memory lifecycle | `MemoryEngine` | MemoryStore | write/read policy within scopes | embeddings | agents, chat | SQLite | local only | deterministic-tested | — | **ACTIVE** |
| Hierarchical/platform memory | `memory/hierarchical.py`, `platform.py` | M2/M9 | various | Layered memory | APIs | hierarchical nodes | promotion rules | engine | CEO, agents | SQLite | local | implemented | — | **ACTIVE** / partial overlap |
| Codebase memory | `saathi/codebase_memory/` | M18.2 | M18.2 | Code index retrieval | index/search | IndexStore | index write governance | MCP gov | tools | SQLite | local FS read | deterministic-tested | — | **ACTIVE** specialized retrieval |
| Knowledge (platform) | `saathi/platform/knowledge/` | M87–M94 | M87–M94 | Grounding + citations | search/ingest | knowledge index | KNOWLEDGE_* perms | platform | conversation | platform | no tools | deterministic-tested | browser cert | **ACTIVE** |
| Skills library | `saathi/skills_library/` | skills docs | earlier | SkillStore packages | SkillStore | skill records | install metadata | — | product | SQLite | none | implemented | — | **ACTIVE** |
| Platform skills runtime | `saathi/platform/skills/` | M112–M120 | M112–M120 | Skill lifecycle local packages | service | skill packages | lifecycle not tool auth | ToolRegistry extended | UI skill-runtime | local packages | via EG for tools | deterministic-tested | browser cert | **ACTIVE** |
| Repo skills content | `saathi/skills/*`, `.grok/skills/*` | Agents.md | various | Content skill packs | SKILL.md trees | files | none | — | agents | files | none | docs | — | **ACTIVE** content |
| Scheduler (product) | `saathi/scheduler.py` | ops docs | early | Cron-like product jobs | job functions | process loop | triggers product work | various | ops | none central | high (jobs call systems) | implemented | — | **ACTIVE**; **fragmented** |
| App harness schedulers | `application_harness/scheduler*.py` | M17.10–11 | M17 | Mission/monitor schedules | MissionScheduler, MonitorScheduler | schedules | harness alerts | harness ledger | CC attention | SQLite | local | staging-ready | — | **ACTIVE** specialized |
| TG experiment scheduler | `platform/tg/research_orchestrator/scheduler.py` | M280–M287 | M280+ | Research job queue | ExperimentScheduler | jobs | research only | research stores | TG UI | SQLite | in-process | deterministic-tested | cert m287 | **ACTIVE** specialized |
| Graph / pipeline | `saathi/graph/` | M17.16 | M17 | Pipeline DAG | service | pipeline state | pipeline domain | — | content pipelines | SQLite | may call tools | implemented | — | **ACTIVE**; distinct from TaskGraph |
| TaskGraph (agent) | `agent_runtime/graph.py` | M48 | M10 | Agent task DAG | TaskGraph | in-run graph | none | — | Orchestrator | RunStore | none | implemented | — | **ACTIVE** |
| Computer agent | `saathi/computer_agent/` | M17 series | M17 | Desktop ops under policy | session, drivers | ComputerSession | none; tools via policy | browser/native | gateway family | local | OS actuation gated | live-desktop partial | TCC blocked some | **ACTIVE** |
| Browser governance | `saathi/browser/` | M17.23–26 | M17.23+ | Governed browser actions | gov_session, guard | browser sessions | domain policy | EG browser family | computer, tools | local | browser CDP | deterministic + live | residual ungoverned open() noted | **ACTIVE** |
| Connectors | `saathi/connectors/` | M15, M30 | M15+ | External connector platform | registry, adapters | connector store | connector link/exec under EG | credentials | EG connector family | SQLite | external APIs when creds | local live; cloud env-blocked | M30 cert model | **ACTIVE** |
| Evidence store | `saathi/evidence/` | evidence docs | early | Universal evidence records | EvidenceStore | evidence rows | write evidence | adapters | CEO, learning, cert | `~/.saathi/evidence.db` | none | partial/implemented | — | **ACTIVE** |
| Security store / timeline | `saathi/security/` | security docs | M15.2 | Security events, risk | SecurityStore | events | security audit | — | redteam, ops | SQLite | none | implemented | red-team | **ACTIVE** |
| Certification stores | `connectors/conformance/`, inference cert, TG cert packages | M25/M30/M36… | various | Package/provider cert | various | cert records | cert verdicts | evidence | release gates | SQLite/files | none | mixed | many WITH_LIMITATIONS | **ACTIVE** fragmented by domain |
| Replay | computer_agent/replay, harness tapes, run checkpoints | M17, M385 notes | various | Reproduce runs | replay modules | tapes/checkpoints | none | ledgers | cert, debug | files/SQLite | read | partial | — | **ACTIVE** partial; not one system |
| Control Center | `saathi/control_center/` | M16, M17.21–22 | M16 | Ops cells / attention | APIs | attention state | read + ack admin | harness, gateway metrics | UI | SQLite | none side-effect | deterministic-tested | — | **ACTIVE** |
| M20 console | `saathi/m20_console/` | M20 series | M20 | Engineering loop console | CLI/status | flags | none authority | inference | operators | local | none | series complete | — | **ACTIVE** ops surface |
| Agentdev | `saathi/agentdev/` | M344–M376 series | agentdev | Dev agent env, model qual, terminology | CLI, consoles | missions, artifacts | evaluation only | models | operators | local data | local models | model_evaluated limited | qualification | **ACTIVE** non-prod control |
| Agent operations / ops | `saathi/ops/` | ops docs | various | Backup, release gate, integrity | CLI | process meta | release gate checks | release_check | deploy humans | local | host ops | implemented | — | **ACTIVE** |
| Trading Guardian core | `platform/trading_guardian.py`, `platform/tg/` | TG docs M62+ | M62+ | Independent order veto + paper/research | `TradingGuardian`, services | TG domain state | **veto / deny trade** | trading_models | paper, research UIs | many TG SQLite | **no live orders** | paper/research certified WITH_LIMITATIONS | many cert:* | **ACTIVE**; live **not** authorized |
| Finance ExecutionService | `execution/trade.py` | M48 inventory | finance | Paper-first trade layer | ExecutionService | trade status | must stay paper/advisory | TG | finance UIs | SQLite | paper only intended | implemented | TG gates | **ACTIVE** specialized; not agent runtime |
| Chat engine | `saathi/chat/` | M8, M48.2 | M8 | Product chat + agent roles | engine, store | chat messages, agent_run bridge | product chat | ModelRouter, optional orch | UI `/chat` | SQLite | may call gateway | implemented | RR-04 dual record | **ACTIVE** |
| SaathiAgent (root) | `saathi/agent.py` | M48 inventory | early | Voice/text product agent | SaathiAgent | conversation | product | llm | voice | local | model | legacy product | RR-09 | **ACTIVE** legacy product |
| IELTS agents | `saathi/agents/` | M48.2 boundary | domain | IELTS coaching | master/router | domain | domain only | Groq-direct noted | IELTS product | local | provider-direct risk | domain KEEP | RR-01 | **ACTIVE** bounded legacy |
| CEO surfaces | `saathi/ceo/`, `ceo_os.py` | M14 | M14 | Briefings / dashboards | CEOStore | briefs | read aggregation | evidence | UI | SQLite | none | partial | — | **ACTIVE** |
| Events / eventstream | `saathi/events/`, `eventstream.py` | fabric docs | early | Event fabric | publish | ephemeral/durable events | none | — | many | varies | none | implemented | — | **ACTIVE** |
| MCP governance | `saathi/mcp_governance/` | M18.1 | M18.1 | MCP inventory/namespace | gov APIs | inventory | write governance | — | MCP pilots | local | none by default | deterministic-tested | Continuum license blocked | **ACTIVE** |
| Fleet | `saathi/platform/fleet/` | M103–M111 | M103+ | Worker fleet Phase A | service | leases, workers | admission/fencing | cluster, PAR | UI `/fleet` | platform | via PAR→EG | Phase A cert | loopback only | **ACTIVE** |
| Cluster | `saathi/platform/cluster.py` | fleet docs | M56+ | Cluster coordinator | ClusterCoordinator | cluster state | recovery certify | platform | fleet | platform | — | deterministic-tested | — | **ACTIVE** |
| Private alpha | `saathi/platform/private_alpha/` | private alpha cert | various | Alpha journey automations | automations | journey state | uses mission→EG | mission_runtime | alpha users | platform | via EG | certified limited | — | **ACTIVE** |
| Frontend | `saathi-os/` | Next app | product | UI surfaces | pages/API clients | browser state | **no** server authority | BFF/platform API | operators | none server | none | browser certs partial | — | **ACTIVE** product surface |
| QM multi-agent (external) | not vendored | ADR-QM, M377–M384 | M377–M384 | Reference only | n/a | n/a | none | n/a | design | n/a | n/a | analysis | n/a | **DESIGN_ONLY** reference; **PROHIBIT** import |

## M386.2 Inventory coverage checklist

| Required category | Covered |
| --- | --- |
| Agent runtimes | ✓ agent_runtime, PlatformAgentRuntime, engineering sessions, IELTS, SaathiAgent, chat |
| Run stores | ✓ agent RunStore; platform executions; harness ledger; many domain stores |
| Mission systems | ✓ missions/, mission_runtime, agentdev missions |
| Session systems | ✓ auth, credential, computer, browser, voice, engineering, provider |
| Execution gateways | ✓ ExecutionGateway sole; ModelGateway residual naming |
| Tool services | ✓ tool_runtime service + registry + commands |
| Provider gateways | ✓ inference + connectors providers |
| Routing | ✓ ModelRouter + provider_decision |
| Approval systems | ✓ platform, gateway, agent, credential, TG |
| Policy systems | ✓ agent policy, tool contracts, TG policy, browser domain, command policy |
| Identity/RBAC | ✓ platform + security skeleton |
| Memory/retrieval | ✓ memory engine, knowledge, codebase_memory |
| Skills | ✓ platform.skills, skills_library, content trees |
| Scheduling | ✓ scheduler.py + harness + TG research |
| Sandboxes | ✓ connector conformance sandbox, TG broker sandbox, harness file roots |
| CLI/application harnesses | ✓ application_harness, agent_runtime CLI, platform CLI, agentdev |
| Evidence/audit/replay | ✓ evidence, security store, run events, replay modules |
| Consoles | ✓ control_center, m20_console, agentdev consoles, TG UIs |
| Certification registries | ✓ multi-domain (inference, connectors, TG, fleet) |
| Trading Guardian | ✓ trading_guardian + platform/tg/* |

---

# M387 — Ownership and authority map

## M387.1 Responsibility → intended single owner

| Responsibility | Intended sole owner | Current reality | Flags |
| --- | --- | --- | --- |
| User identity | Platform identity (`platform/identity.py` + PlatformStore users) | Security OAuth skeleton also named IdentityProvider | **multiple owners (naming)**; product SoT = platform |
| Organization/workspace scope | PlatformStore + RBAC | Generally held | OK; missions must not invent tenancy |
| Mission ownership | Platform mission_runtime (platform missions); `missions/` for product content missions | Two “mission” products | **confusing naming**; split by plane |
| Run ownership | `agent_runtime.RunStore` for multi-agent runs; PlatformExecutionRecord for platform tool runs | Chat also has agent_run bridge | **partial duplication** RR-04 |
| Session ownership | **Typed by kind** — see glossary; no single Session table | Many Session* classes | **intentional specialization** if labeled |
| Model selection | Inference provider_decision + ModelRouter | ModelGateway residual | **doc/source dual surface** |
| Provider access | Inference governance + connector registry | Residual legacy paths audited | residual allowlists |
| Credential access | `saathi.credentials` lease at ExecutionGateway | Must not be harness-owned | OK principle; QM rejected opposite |
| Tool proposal | Orchestrator / AgentExecutor / future AgentHarness / agents | engineering adapters may run processes | **investigate** tool proposal vs direct spawn |
| Tool authorization | Gateway authorizer + platform bindings + approval | Multiple approval enums | compose not compete |
| Tool execution | ExecutionGateway | tool_runtime under EG | **sole** |
| Filesystem access | Tools / application harness / computer agent **via EG** | Some local product scripts | freeze new direct paths |
| Browser access | Governed browser family via EG | Residual ungoverned open() noted in matrix | residual risk |
| Network access | Connectors/tools via EG | provider HTTP under inference/connectors | residual |
| Scheduling | **No single owner today** | Multiple schedulers | **no owner (unified)** / multi-runner OK short-term |
| Cancellation | RunLifecycle (agent) + EG cancel + tool tokens + harness cancel | Partial cooperative RR-02 | partial |
| Retry | Lifecycle RetryClass + tool RetryPolicy + universal reconcile | Multiple policies | intentional layers if mapped |
| Budget enforcement | Inference cost policy + mission budgets + TG research budgets | Fragmented | **multiple owners by domain** (OK if scoped) |
| Memory writes | MemoryEngine + scoped APIs | hierarchical/platform also write | **partial duplication** |
| Memory reads | MemoryEngine / knowledge / codebase_memory | Multiple retrieval planes | specialization if labeled |
| Skill installation | platform.skills + skills_library | content dirs also “skills” | **confusing** |
| Skill promotion | **No production owner** (design deferred) | none | **no owner** (intentional defer) |
| Agent creation | agent_runtime.registry + platform bindings + mission agent roles | agentdev roles, IELTS agents | **multiple** by plane |
| Audit | SecurityStore + platform audit + EG evidence trail | Multiple streams | **compose**; need correlation_id discipline |
| Replay | Run checkpoints + domain replay modules | Not unified | partial |
| Certification | Domain cert modules + release_check | Many registries | multi-domain OK; no global fake “certified” |
| Deployment | Human + ops release gates | no auto deploy | OK |
| Financial action | Trading Guardian + paper systems | research modules advisory | OK fail-closed |
| Trading action | **Trading Guardian veto** then EG trade family (paper only) | live not authorized | OK |

## M387.2 Flag summary

| Flag | Examples |
| --- | --- |
| Multiple owners | Approvals (platform/gateway/agent/credential/TG); identity modules; “orchestrator” names; schedulers |
| No owner | Unified global scheduler; skill promotion; single global Session SoT (by design deferred) |
| Circular ownership | None hard-proven; risk if AgentHarness both proposes and “approves” (forbidden in M385) |
| Shadow authority | Engineering session process launch if tools skip ToolIntent; IELTS provider-direct; residual browser open() |
| Implied authority | UI consoles; skill packs; agent “capabilities” treated as permissions |
| Doc/source disagreement | ADR-EXECUTIONGATEWAY status “awaiting implementation” vs implemented gateway; M385 next M386 policy floors vs this consolidation M386 |

**Rule:** no responsibility remains *product-ambiguous* after this map — either single owner or **explicit multi-owner with plane labels**.

---

# M388 — Duplication and overlap analysis

| Pair / cluster | Classification | Recommendation |
| --- | --- | --- |
| AgentHarness (M385 design) vs agent_runtime | intentional composition (driver under runtime) | **compose** later; do not implement yet |
| AgentHarness vs ApplicationHarness | harmless specialization (wrong names collide) | **keep** both; **glossary** |
| AgentHarness vs engineering.AgentSessionAdapter | **partial duplication** / future shadow plane | **consolidate later** design ADR; freeze new adapters |
| ApplicationHarness vs sandbox harness (M30) | harmless specialization | **keep** |
| Mission sessions vs provider sessions vs credential sessions | intentional specialization | **keep** + glossary |
| agent RunState vs PlatformExecutionState vs IntentState vs TG JobState | intentional specialization | **keep**; forbid cross-use |
| ModelRouter vs inference provider_decision vs ModelGateway | partial duplication | **compose** ModelRouter→inference; **deprecate later** ModelGateway as public entry |
| ToolRegistry vs SkillStore vs ModuleRegistry vs command manifests | intentional composition | **keep**; skills ≠ tools |
| Skills vs agents vs commands | confusing naming risk | **terminology freeze** |
| MemoryStore vs EvidenceStore vs SecurityStore vs cert evidence | intentional separation | **keep** distinct; **prohibit** merge |
| Audit vs replay vs certification evidence | intentional separation | **keep** |
| scheduler.py vs harness schedulers vs TG ExperimentScheduler | partial duplication | **compose** policy later; **keep** runners short-term |
| Workspace scope vs mission scope vs sandbox scope | intentional composition | **keep** |
| Local-model runtime (agentdev/inference local) vs provider abstraction | intentional composition | **keep** under inference policy |
| Agent consoles (m20, agentdev, control_center, TG UIs) | harmless specialization | **keep**; no authority |
| Platform approval vs agent ApprovalRecord vs TG approvals | partial duplication of *types* | **compose** references; one human decide path per plane |
| Maturity matrix docs vs TG CURRENT_MATURITY vs cert modules | confusing multiplicity | **keep** domain maturity; **index** centrally |
| agent_runtime.Orchestrator vs engineering orchestrator vs TG research orchestrator | confusing naming | **rename later** docs; freeze new Orchestrator types |
| PlatformAgentRuntime vs agent_runtime | intentional composition (platform vs general) | **keep** both; document binding |
| missions/ vs mission_runtime | confusing naming | **rename later** in docs (“product missions” vs “platform mission runtime”) |
| Dual identity modules | partial duplication | platform = product SoT; security = future SSO adapter host |
| Chat agent_run + RunStore | partial duplication RR-04 | **deprecate later** dual write |
| QM patterns vs SaathiOS systems | conceptual overlap only | **prohibit** import |

### Dangerous duplication (must not grow)

1. Second external-action gateway or “submit” facade that skips UniversalBoundary.
2. Agent/harness self-approval.
3. Ambient credentials in sandboxes (QM pattern rejected).
4. Commercial CLI as control plane without ToolIntent.
5. Live trading path outside Trading Guardian.

---

# M389 — Data and state model review

## M389.1 Source-of-truth table

| Entity | Authoritative store / module | ID scheme | Mutability | Scope | Retention | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| User | PlatformStore | platform user id | mutable profile | org memberships | product | Auth sessions separate |
| Organization | PlatformStore | org_id | mutable | global | product | |
| Workspace | PlatformStore | workspace_id | mutable | org | product | |
| Project | PlatformStore | project_id | mutable | workspace | product | |
| Platform mission | mission_runtime repository | mission_id | state machine | project | product | ≠ missions/ brand missions |
| Product mission | missions/store | mission ids | mutable | business | product | content/ops |
| Agent run | agent_runtime.RunStore | run_id | state machine; terminal immutable intent | actor/conversation | durable local | |
| Platform execution | PlatformStore PlatformExecutionRecord | execution ids | state machine | binding fingerprint | durable | |
| Chat session/messages | chat/store | conversation ids | append messages | user | product | bridge to run_id |
| Auth session | platform identity sessions | session_id | expire/revoke | user | short | |
| Credential session / lease | credentials m35–m38 | lease/session ids | expire | actor+scope | short | secrets never in ToolIntent |
| Computer session | computer_agent.session | session_id | lifecycle | workspace | local | |
| Browser session | browser.gov_session | session_id | lifecycle | domain policy | local | |
| Engineering agent session | engineering SessionLedger | session_id | lifecycle | worktree | local | |
| Provider session (TG) | provider_contracts | provider session | lifecycle | paper/sandbox | research | not live |
| Voice session | platform.voice / voice_os | session_id | lifecycle | user | local | |
| Approval (product) | PlatformStore ApprovalRecord | approval_id | request→decide→consume | tenancy | durable | human decide |
| Approval (execution) | execution records / intent state | approval_id ref | bind to intent | intent | durable | fail-closed |
| Approval (run contract) | RunStore / contracts.ApprovalRecord | approval_id | validate expiry/revoke | run | durable | |
| ToolIntent | immutable value object | intent_id + idempotency_key | **immutable** | actor+BU | audit copies | |
| Execution record | universal boundary store | execution_id | state machine | intent | durable | |
| Provider policy/state | inference governance_store | provider ids | circuit/cost | host | durable | |
| Credentials | credentials backends | secret handles | rotate | account | secure | values leased ephemerally |
| Memory items | MemoryStore | memory ids | decay/forget | privacy scopes | policy | not evidence |
| Skills packages | platform.skills + SkillStore | skill ids | lifecycle | local | local | not permissions |
| Schedules | per-scheduler stores / code | job ids | mutable | domain | varies | **no global SoT** |
| Checkpoints | RunStore.checkpoint; harness exports | checkpoint ids | append | run/session | durable | |
| Audit events | SecurityStore + platform audit | event ids | **append-only target** | actor | durable | |
| Replay artifacts | domain modules | tape/run refs | immutable preferred | run | durable | fragmented |
| Evidence | EvidenceStore | evidence id | append | department | durable | universal schema |
| Certification records | domain cert stores/packages | cert ids | append verdicts | package | durable | evidence-backed |
| Trading / paper state | platform/tg + paper_trading stores | campaign/order sims | domain SM | paper env | durable | **not live** |
| OrderIntent | trading_models | intent ids | evaluated by TG | account | durable | veto before EG |

## M389.2 State issues

| Issue | Evidence | Severity |
| --- | --- | --- |
| Duplicated identifiers across planes without mandatory correlation | chat agent_run + canonical_run_id; multiple approval_id namespaces | P2 |
| Incompatible state machines (by design) | RunState vs IntentState vs PlatformExecutionState | OK if not mixed |
| Inconsistent naming “session/run/mission” | many modules | P3 |
| Missing formal FK across SQLite files | multi-db local-first | accepted local-first; correlation_id discipline P2 |
| Multiple sources of truth risk for approvals | platform vs gateway vs TG | P1 if consume paths diverge |
| Immutable ToolIntent | enforced in toolintent.py | good |
| Mutable that should be immutable | terminal run states enforced; harness success status untrusted (good) | OK |
| Retention rules incomplete globally | many stores lack documented TTL | P3 |
| Scope ownership gaps on older product tables | pre-M50 modules | P2 |

---

# M390 — Control-flow review

## Legend

Each flow: entry → checks → transitions → persist → side effects → audit → errors → cancel → recovery → terminal.

**Bypass flags** if path can skip RBAC / Approval / EG / credentials / audit / TG / resource controls.

### 1. User request → model response

| Stage | Path |
| --- | --- |
| Entry | UI chat / API / CLI → ChatEngine or platform conversation |
| Authority | Platform session / product auth; anonymous prohibited on platform |
| Policy | caller_policy / inference runtime_gate; ModelRouter labels |
| State | chat messages; optional agent run |
| Persist | ChatStore; inference cost store |
| Side effects | model tokens only if no tools |
| Audit | chat/inference events |
| Errors | provider unavailable ≠ success (contracts) |
| Cancel | voice/chat barge-in partial RR-10 |
| Bypass risk | residual direct provider paths audited by bypass_guard; IELTS domain may be provider-direct (**bounded legacy**) |

### 2. Agent mission creation

| Stage | Path |
| --- | --- |
| Entry | platform API mission create / orchestration intake |
| Authority | MISSION_WRITE / RBAC |
| Policy | plan validator (orchestration) |
| State | mission hierarchy CREATED |
| Persist | mission_runtime repository |
| Side effects | none external |
| Audit | platform audit |
| Bypass risk | low if platform path; product `missions/` separate plane |

### 3. Agent run execution

| Stage | Path |
| --- | --- |
| Entry | `Orchestrator.create_run` / `service.start` / API |
| Authority | contracts.validate_run_request; FINANCIAL_EXECUTION PROHIBITED |
| Policy | RiskClass → approval requirement |
| Transitions | CREATED→PLANNING→[AWAITING_APPROVAL]→QUEUED→RUNNING→… |
| Persist | RunStore |
| Side effects | only via gateway_exec → EG |
| Audit | run events |
| Cancel | lifecycle cancel + kill switch |
| Recovery | stale classes / reconcile |
| Bypass risk | `skip_contract=True` must not be HTTP-exposed (M48.2) |

### 4. Tool proposal → execution

| Stage | Path |
| --- | --- |
| Entry | AgentExecutor / PlatformAgentRuntime / future harness proposal |
| Authority | binding + permission_ok + risk |
| Policy | needs_approval; ToolManifest approval class |
| State | ToolIntent immutable → ExecutionRecord |
| Persist | universal store; durable idempotency |
| Side effects | handler family |
| Audit | Evidence + security events |
| Cancel | cancel_execution + tool tokens |
| Bypass risk | **critical** if adapter executes without ToolIntent |

### 5. Approval request → consumption

| Stage | Path |
| --- | --- |
| Entry | platform approval.request / agent awaiting_approval / TG activation |
| Authority | APPROVAL_DECIDE ≠ requestor agent |
| Policy | fail-closed if missing/expired/revoked |
| State | pending→approved/rejected→consumed |
| Persist | PlatformStore / RunStore / TG stores |
| Side effects | none until EG consumes approval_id |
| Bypass risk | UI-only decide without server; agent self-approve (**forbidden**) |

### 6. Provider selection and invocation

| Stage | Path |
| --- | --- |
| Entry | inference engine / ModelRouter |
| Authority | provider_policy production_supported; kill switches |
| Policy | cost circuit; quarantine |
| Persist | governance_store, cost |
| Side effects | external LLM HTTP |
| Bypass risk | residual legacy; bypass_guard AST |

### 7. Local-model invocation

| Stage | Path |
| --- | --- |
| Entry | Ollama/local adapters; agentdev qualification |
| Authority | local provider class; env readiness |
| Policy | production_certified=false without live evidence |
| Side effects | local process |
| Bypass risk | treating local success as production cert (**forbidden**) |

### 8. Cancellation

| Stage | Path |
| --- | --- |
| Entry | API cancel / kill switch / harness cancel token |
| Authority | run owner / admin |
| State | CANCELLED durable |
| Side effects | best-effort abort; remote may complete (RR-02) |
| Bypass risk | ignoring cancel on long tools |

### 9. Retry and recovery

| Stage | Path |
| --- | --- |
| Entry | lifecycle retry classes; universal unknown outcome reconcile |
| Policy | no blind mutation retry; MAX_RETRY_BOUNDED |
| Persist | run/exec records |
| Bypass risk | force_new without idempotency understanding |

### 10. Scheduled work

| Stage | Path |
| --- | --- |
| Entry | scheduler.py loop / harness SchedulerRunner / TG ExperimentScheduler |
| Authority | **often process-local trust** (host operator) |
| Side effects | may call many subsystems |
| Bypass risk | **medium** if jobs call privileged APIs without platform context — treat as operator plane |

### 11. Memory read/write

| Stage | Path |
| --- | --- |
| Entry | MemoryEngine APIs / agent capabilities memory_* |
| Authority | privacy scopes; contracts capabilities |
| Persist | MemoryStore |
| Bypass risk | writing secrets into memory |

### 12. Evidence generation

| Stage | Path |
| --- | --- |
| Entry | EG Evidence; domain adapters |
| Persist | EvidenceStore / run events |
| Bypass risk | success without evidence for side effects (**forbidden by invariant 8**) |

### 13. Replay

| Stage | Path |
| --- | --- |
| Entry | checkpoint restore / domain replay |
| Policy | no new side effects without EG |
| Bypass risk | replay that re-fires mutations without idempotency |

### 14. Certification

| Stage | Path |
| --- | --- |
| Entry | cert modules / browser cert scripts / release_check |
| Policy | evidence required; fail closed |
| Bypass risk | doc-only “certified” claims |

### 15. Trading-related request

| Stage | Path |
| --- | --- |
| Entry | TG UI/API paper/research |
| Authority | TradingGuardian.evaluate veto; FINANCIAL_EXECUTION prohibited in agent contracts |
| Side effects | paper sim only |
| Bypass risk | **critical** if broker path without TG + EG + owner auth |

### 16. Coding-related request

| Stage | Path |
| --- | --- |
| Entry | agent capability `code` / engineering session / future harness |
| Authority | run contracts + tool allowlist |
| Side effects | FS/tools via EG or bounded adapter |
| Bypass risk | Claude Code adapter unrestricted shell (**must not**) |

### 17. Browser-related request

| Stage | Path |
| --- | --- |
| Entry | governed browser tools |
| Authority | domain policy + approval + EG |
| Bypass risk | residual ungoverned open() (matrix) |

### 18. Filesystem-related request

| Stage | Path |
| --- | --- |
| Entry | tools / application harness file_roots / computer agent |
| Authority | confinement + trust + EG |
| Bypass risk | path escape; shell=True (**assert_no_shell_true**) |

### M390.1 Bypass summary

| Control | Bypass residual? | Disposition |
| --- | --- | --- |
| RBAC | Pre-platform product modules; host scheduler | freeze expansion; migrate critical |
| Approval | Multiple planes if not bound to EG | P1 correlation |
| ExecutionGateway | Legacy domain + residual inference + engineering process | RR-01 accepted; freeze growth |
| Credential governance | QM-style ambient rejected; watch sandboxes | prohibit |
| Audit | Fragmented streams | correlation_id P2 |
| Trading Guardian | Live not built; paper only | keep |
| Resource controls | Single-host leases RR-03 | accepted local-first |

---

# M391 — Terminology and contract review

## M391.1 Canonical glossary

| Term | Canonical meaning in SaathiOS | Not to be confused with |
| --- | --- | --- |
| **agent** | Role or runtime participant that plans and **proposes** actions | OS user identity; skill pack; commercial CLI binary |
| **harness** | Overloaded — see subtypes | Do not use bare “harness” in new APIs |
| **AgentHarness** | (Design) multi-turn coding/reasoning **driver** under platform controller | ApplicationHarness; sandbox harness |
| **ApplicationHarness** | Argv-only structured CLI tool executor under EG | AgentHarness |
| **sandbox harness** | Connector/conformance isolation environment | AgentHarness |
| **provider** | External or local model/service vendor under governance | tool; connector account |
| **model** | Specific model id/revision selected for inference | provider account |
| **runtime** | Code plane executing lifecycle (agent_runtime, PlatformAgentRuntime, inference runtime) | host OS process only |
| **mission** | Durable goal hierarchy (platform mission_runtime) **or** product content mission (`missions/`) — always qualify | agent run |
| **run** | Agent multi-step execution record (RunStore) | single tool execution; chat turn |
| **session** | Scoped interactive/auth/driver context — **always qualify kind** | run |
| **workspace** | Tenancy workspace (RBAC) | sandbox work_dir; git worktree |
| **scope** | Authorization boundary (org/workspace/project/mission/run) | QM Slack scope |
| **sandbox** | Isolated execution environment for tools/connectors | entire agent runtime |
| **tool** | Registered executable capability via ToolRegistry/ToolIntent | skill; command string |
| **skill** | Packaged instructions/assets lifecycle; **not** a permission | tool |
| **command** | Allowlisted argv manifest entry | freeform shell |
| **capability** | Declared ability label (agent planning / harness profile) | RBAC permission |
| **policy** | Rule set constraining behavior | permission grant |
| **permission** | RBAC PlatformPermission (or equivalent) | capability label |
| **authority** | Right to decide or execute in a plane | descriptive capability |
| **approval** | Human authorization record consumable by gates | model “yes” |
| **evidence** | Structured outcome/proof record (EvidenceStore / packages) | chat log alone |
| **audit** | Security/compliance event trail | evidence package |
| **replay** | Deterministic re-presentation/re-execution of recorded run/tape | live retry |
| **certification** | Evidence-backed verdict for a package/path | marketing “ready” |
| **maturity** | Staged readiness label (implemented < … < production) | certification alone |

## M391.2 Conflicting / overloaded terms (source + docs)

| Term | Conflicts | Canonical recommendation |
| --- | --- | --- |
| harness | Application / Agent / sandbox / red-team harness | Always prefix |
| orchestrator | agent_runtime, engineering, TG research, mission_runtime | Qualify: `AgentOrchestrator`, `ResearchOrchestrator`, … |
| session | 10+ classes | Kind prefix: `AuthSession`, `CredentialSession`, … |
| mission | product vs platform | `ProductMission` vs `PlatformMission` in docs |
| approval | 5+ enums/records | Shared `approval_id` + plane tag |
| run | agent run, harness run, browser run, TG job | Qualify |
| gateway | ExecutionGateway vs ModelGateway | Reserve “gateway” alone for ExecutionGateway in new prose |
| agent | runtime agents, platform roles, IELTS, SaathiAgent | Qualify plane |
| skill | content, library, platform runtime | Qualify |
| certified | many cert:* | Always attach package id + limitations |

**Do not rename production code in this milestone.**

---

# M392 — Target architecture

## M392.1 Layered architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│ L0 Product surfaces                                                  │
│  saathi-os UI · CLI · Control Center · CEO · TG consoles · voice     │
└──────────────────────────────────────────────────────────────────────┘
                                    │
┌──────────────────────────────────────────────────────────────────────┐
│ L1 Platform services                                                 │
│  identity/RBAC · tenancy · Approval Center · module registry · BFF   │
└──────────────────────────────────────────────────────────────────────┘
                                    │
┌──────────────────────────────────────────────────────────────────────┐
│ L2 Agent orchestration                                               │
│  agent_runtime (general multi-agent)                                 │
│  PlatformAgentRuntime + mission_runtime + orchestration (platform)   │
│  Bounded domain agents (IELTS, product chat) — frozen expansion      │
│  [optional later] HarnessSessionController + AgentHarness drivers    │
└──────────────────────────────────────────────────────────────────────┘
                                    │ proposals only
┌──────────────────────────────────────────────────────────────────────┐
│ L3 Model / provider access                                           │
│  inference governance · ModelRouter · local models · kill switches   │
└──────────────────────────────────────────────────────────────────────┘
                                    │
┌──────────────────────────────────────────────────────────────────────┐
│ L4 Tool governance                                                   │
│  ToolIntent · bindings · risk · approval bind · idempotency          │
└──────────────────────────────────────────────────────────────────────┘
                                    │
┌──────────────────────────────────────────────────────────────────────┐
│ L5 Tool execution authority — ExecutionGateway / UniversalBoundary   │
└──────────────────────────────────────────────────────────────────────┘
          │            │            │             │            │
   tool_runtime   connectors   browser/CA   ApplicationHarness  trade*
                                    │
┌──────────────────────────────────────────────────────────────────────┐
│ L6 Sandbox / isolation                                               │
│  file roots · connector sandbox · TG broker sandbox · process limits │
└──────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────┐
│ L7 Memory & knowledge                                                │
│  MemoryEngine · platform knowledge · codebase_memory                 │
└──────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────┐
│ L8 Scheduling (multi-runner, shared policy later)                    │
└──────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────┐
│ L9 Security & policy                                                 │
│  RBAC · security store · red-team · credentials leases               │
└──────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────┐
│ L10 Audit · replay · evidence · certification                        │
└──────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────┐
│ L11 Trading Guardian (independent veto; paper/research default)      │
└──────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────┐
│ L12 Deployment & operations (human gates; ops release_check)         │
└──────────────────────────────────────────────────────────────────────┘

* trade family only after TG allow + paper/live policy; live not authorized today.
```

## M392.2 Component dependency (simplified)

```text
UI ──► Platform API ──► PlatformAgentRuntime ──► ExecutionGateway
                 └──► agent_runtime ─────────────► ExecutionGateway
                 └──► inference (models)
                 └──► memory / knowledge (read)
AgentHarness? ──► controller ──► tool proposals ──► ToolIntent ──► EG
ApplicationHarness ◄── EG family handler
TradingGuardian ──veto──► (order intents) ──► EG trade family (paper)
```

## M392.3 Authority boundary diagram

```text
[Human owner] --approve/decide--> [Approval Center]
[RBAC] --permit--> [Platform bindings]
[Agent/Harness] --propose only--> [ToolIntent]
[ExecutionGateway] --execute--> [Handlers]
[TradingGuardian] --deny/allow--> [OrderIntent path]
[Credentials] --lease@exec only--> [Handlers]
[Certification] --verdict from evidence--> [Release human]
```

## M392.4 Execution flow (canonical)

```text
Intent → Orchestrate → (Approval?) → ToolIntent → ExecutionGateway.submit
  → validate → authorize → risk → approval bind → credential lease
  → family handler → sanitize → Evidence → ledger → terminal
```

## M392.5 Data ownership diagram

```text
PlatformStore: users, orgs, workspaces, projects, platform missions, approvals, bindings
RunStore: agent runs, tasks, events, checkpoints
Execution store: ToolIntent executions
Credentials DB: handles, leases (no plaintext in intents)
MemoryStore: agent memory
EvidenceStore: universal evidence
SecurityStore: security audit
TG stores: paper/research only
Inference gov DB: circuits, cost, provider state
```

## M392.6 Trust-boundary diagram

```text
TRUSTED_CONTROL_PLANE: platform identity, RBAC, Approval Center, EG, TG, credentials core
SEMI_TRUSTED: agent_runtime planners, mission roles, tool_runtime handlers (output untrusted)
UNTRUSTED: model outputs, connector outputs, harness process stdout, commercial CLIs, web content
HOST_OPERATOR: scheduler.py, ops CLIs (equivalent to admin machine access)
```

## M392.7 Where AgentHarness fits (if later)

```text
L2 agent_runtime task (capability code|review)
  → HarnessSessionController (platform-owned)
  → AgentHarness adapter (UNTRUSTED driver)
  → tool_request_proposed events
  → normalize → ToolIntent → ExecutionGateway
  → redacted results → continue turn
```

**AgentHarness is not assumed necessary.** Alternative: bind `engineering.AgentSessionAdapter` under the same controller contract and retire duplicate designs.

---

# M393 — Consolidation roadmap and risk

## M393.1 Risk register

| ID | Priority | Risk | Evidence | Mitigation |
| --- | --- | --- | --- | --- |
| R-01 | P0 | New side-effect path skips EG | M48 residual; engineering adapters; legacy agents | Freeze; audits; gateway coverage |
| R-02 | P0 | TG / financial path weaken | TG max states paper/research | Guardian + contract PROHIBITED |
| R-03 | P0 | Credential ambient exposure | QM rejected pattern; sandbox risk | lease-only; no harness secrets |
| R-04 | P1 | Dual harness planes (engineering vs AgentHarness) | both exist/design | reconcile ADR before code |
| R-05 | P1 | Approval plane divergence | multiple Approval* types | correlation + consume map |
| R-06 | P1 | Stale ADR status confuses implementers | ADR-EG “awaiting implementation” | doc fix |
| R-07 | P2 | Scheduler fragmentation | 3+ schedulers | policy later; freeze new |
| R-08 | P2 | Multi-db missing FK/correlation | local-first | correlation_id standard |
| R-09 | P2 | Chat dual run records | RR-04 | migrate later |
| R-10 | P2 | Orchestrator name collision | 3+ classes | glossary; rename docs |
| R-11 | P3 | Terminology overload “session/harness” | source | glossary adoption |
| R-12 | P3 | Maturity/cert registry sprawl | many cert modules | index only |
| R-13 | P2 | Cooperative cancel incomplete | RR-02 | tool cancel contracts later |
| R-14 | P4 | Multi-host lease | RR-03 | out of scope local-first |
| R-15 | P1 | Milestone number collision M386/M387 | QM ADR vs this | renumber deferred work |

## M393.2 Deprecated / frozen candidate list

| Component | Action | Rationale |
| --- | --- | --- |
| IELTS `saathi.agents` as general runtime | **FROZEN** expansion | RR-01 domain only |
| New commercial CLI adapters without cert ADR | **PROHIBIT** | M385 D10/D11 |
| New Orchestrator classes | **FROZEN** | name collision |
| New bare “Harness” modules | **FROZEN** | must use typed name |
| ModelGateway as new public entry | **FROZEN**; prefer inference | duplication |
| QM import/deploy | **PROHIBIT** | ADR-QM |
| AgentHarness implementation | **FROZEN** until P1 reconcile | this ADR |
| Policy floors / skill promotion impl | **DEFERRED** | renumbered |
| Dual chat+RunStore write expansion | **FROZEN** new fields without migration plan | RR-04 |
| Live trading / broker credentials | **PROHIBIT** without owner ceremony | TG series |
| skip_contract on HTTP | **PROHIBIT** | M48.2 |
| Dangerous/unrestricted security posture | **PROHIBIT** | ADR-QM |

## M393.3 Prioritized future milestones (one concern each)

### FM-C1 — Documentation freeze & contradiction repair (P1, docs-only)

| Field | Content |
| --- | --- |
| Problem | Stale ADR status; M386 number collision; discoverability of freezes |
| Evidence | ADR-EG header; QM ADR future table; this review |
| Affected | docs/adr, roadmap, architecture index |
| Risk | Low |
| Prerequisites | M386–M393 accepted |
| Non-actions | no code |
| Migration | none |
| Compatibility | n/a |
| Tests | none (doc) |
| Cert gate | human review |
| Rollback | revert docs |

### FM-C2 — AgentSessionAdapter ↔ AgentHarness relationship ADR (P1, design-only)

| Field | Content |
| --- | --- |
| Problem | Two multi-turn coding driver concepts |
| Evidence | `engineering/adapters/base.py` vs M385 design |
| Affected | engineering, future agent harness docs |
| Risk | Medium if skipped before code |
| Prerequisites | FM-C1 |
| Non-actions | no adapters; no commercial CLI |
| Migration | n/a design |
| Compatibility | preserve engineering behavior until later |
| Tests | n/a |
| Cert gate | design review |
| Rollback | reject ADR |

### FM-C3 — Approval plane correlation design (P1, design-only)

| Field | Content |
| --- | --- |
| Problem | Multiple approval records without single consume map |
| Evidence | platform/models, contracts, m35, TG approvals |
| Affected | platform, execution, agent_runtime, credentials, TG |
| Risk | Medium (authz confusion) |
| Prerequisites | FM-C1 |
| Non-actions | no schema merge yet |
| Migration | later if needed |
| Compatibility | keep existing IDs |
| Tests | design tests later |
| Cert gate | security review |
| Rollback | docs only |

### FM-C4 — Glossary adoption pass (P3, docs-only)

| Field | Content |
| --- | --- |
| Problem | Overloaded terms |
| Evidence | §M391 |
| Affected | docs, agentdev terminology alignment |
| Risk | Low |
| Prerequisites | this review |
| Non-actions | no mass code rename |
| Migration | none |
| Compatibility | full |
| Tests | optional scan_text expansion later |
| Cert gate | none |
| Rollback | revert docs |

### FM-C5 — Scheduler inventory freeze + policy design (P2, design-only)

| Field | Content |
| --- | --- |
| Problem | Fragmented schedulers |
| Evidence | scheduler.py, application_harness schedulers, TG ExperimentScheduler |
| Affected | ops, harness, TG |
| Risk | Medium for unattended jobs |
| Prerequisites | FM-C1 |
| Non-actions | no unified rewrite yet |
| Migration | later |
| Compatibility | keep runners |
| Tests | later |
| Cert gate | ops review |
| Rollback | docs |

### FM-C6 — AgentHarness types + FakeInMemoryHarness (implementation, **after** FM-C2)

| Field | Content |
| --- | --- |
| Problem | Need conformance driver only after relationship clear |
| Evidence | M385 D10 |
| Affected | new package under agent_runtime or platform |
| Risk | Medium |
| Prerequisites | FM-C2 accepted; freezes held |
| Non-actions | no commercial CLI; no TG change; no EG replace |
| Migration | none |
| Compatibility | additive |
| Tests | conformance suite mandatory |
| Cert gate | internal design cert; production_certified remains false |
| Rollback | remove package |

### FM-C7 — Policy floor composition design (deferred from old M386)

| Field | Content |
| --- | --- |
| Problem | Org floors vs scope tighten |
| Evidence | ADR-QM selected pattern |
| Prerequisites | freezes; FM-C1 |
| Non-actions | no dangerous postures |
| … | design-only first |

### FM-C8 — Skill promotion lifecycle design (deferred from old M387)

| Field | Content |
| --- | --- |
| Problem | private→grant→admin promote |
| Evidence | ADR-QM; platform.skills exists without org promote |
| Prerequisites | glossary skills≠tools; FM-C1 |
| Non-actions | no marketplace; no auto-promote |

### Explicitly **not** combined

Do not merge FM-C2+C6, C7+C8, or scheduler rewrite + AgentHarness in one milestone.

## M393.4 Traceability map (milestones → components)

| Milestone band | Components still present |
| --- | --- |
| M8 chat | `saathi/chat` |
| M9 memory | `saathi/memory` |
| M10 agent runtime | `saathi/agent_runtime` |
| M15 connectors/security | connectors, security |
| M17 computer/browser/app harness | computer_agent, browser, application_harness |
| M18 MCP/codebase memory | mcp_governance, codebase_memory |
| M20 engineering console | m20_console, engineering |
| M21–M25 inference | saathi/inference |
| M30 connector cert | connectors/conformance |
| M35–M46 credentials | saathi/credentials |
| M48 agent contracts | agent_runtime/contracts, lifecycle |
| M49 tools | tool_runtime |
| M50–M52 platform | platform/* |
| M62+ TG | platform/tg, trading_guardian |
| M69–M72 mission runtime | platform/mission_runtime |
| M79–M94 voice/knowledge | platform/voice, knowledge |
| M95–M120 orch/skills/apps | orchestration, skills, apps |
| M103–M111 fleet | platform/fleet |
| M216–M311 TG paper/research series | platform/tg/* |
| M344–M376 agentdev/local models | agentdev |
| M377–M384 QM analysis | docs only |
| M385 AgentHarness design | docs only |
| **M386–M393 consolidation** | **docs only (this)** |

## M393.5 Documentation / source contradictions

| # | Claim | Reality | Disposition |
| --- | --- | --- | --- |
| 1 | ADR-EXECUTIONGATEWAY Status: “SPECIFICATION (awaiting implementation)” | `ExecutionGateway` + `UniversalBoundary.submit` implemented | **Repaired in FM-C1** → `ACCEPTED_IMPLEMENTED` |
| 2 | QM ADR future M386 = policy floors | This milestone used M386–M393 for consolidation | Renumber deferred work |
| 3 | M385 “do not auto-start M386” | Owner authorized consolidation M386–M393 | OK with renumber note |
| 4 | “Single orchestrator” language in some docs | Multiple Orchestrator* types | Glossary |
| 5 | “Production ready” adjacent language in older reports | CAPABILITY matrix + cert limitations | Prefer matrix + cert packages |
| 6 | AgentHarness “approved” misread as implemented | Design-only | Emphasize in roadmap |

## M393.6 Architecture readiness scorecard

| Area | Score (0–100) | Evidence | Confidence |
| --- | --- | --- | --- |
| Responsibility clarity | **72** | Inventory + platform/agent split documented; product vs platform missions still soft | High |
| Authority clarity | **80** | EG sole side-effect; TG veto; RBAC enums; FINANCIAL_EXECUTION prohibited | High |
| Execution-path clarity | **74** | Canonical maps M48.1; residual legacy RR-01 | High |
| State ownership | **65** | SoT table; multi-db; dual approvals | Medium |
| Provider separation | **78** | inference governance; bypass_guard; ModelGateway residual | High |
| Tool governance | **82** | ToolIntent immutability; tool_runtime contracts; M49 audits | High |
| Memory architecture | **70** | MemoryEngine core; hierarchical + knowledge + codebase parallel | Medium |
| Scheduling architecture | **48** | Multiple independent schedulers | High |
| Audit and replay | **68** | Evidence + security + run events; replay fragmented | Medium |
| Certification architecture | **75** | Strong culture of cert packages; many domains | High |
| Multi-agent architecture | **76** | agent_runtime + PAR + mission_runtime; engineering dualism | High |
| Terminology consistency | **52** | Overloaded harness/session/orchestrator/mission | High |
| Implementation readiness (new foundations) | **45** | Freezes + FM-C2 required before AgentHarness code | High |
| Security readiness | **77** | Fail-closed design; residual cancel/legacy; no live trading | Medium-High |

**Composite (unweighted mean):** ≈ **68 / 100** — architecture is **governable and mappable**, not yet clean enough for unconstrained foundational expansion.

---

# Systems lists

## Retain (canonical)

- ExecutionGateway + ToolIntent + UniversalBoundary
- agent_runtime (M48 contracts, lifecycle, RunStore)
- PlatformAgentRuntime + platform RBAC/identity/approvals
- tool_runtime registry/service
- inference provider governance
- credentials lease model
- Trading Guardian (advisory/paper posture)
- ApplicationHarness (argv tools)
- MemoryEngine + EvidenceStore + SecurityStore (distinct)
- Governed browser path
- Capability maturity + evidence-based cert culture

## Freeze (no expansion)

- IELTS general-runtime expansion
- New Orchestrator types
- New untyped harness modules
- Commercial CLI control-plane adapters
- AgentHarness code until FM-C2
- Live trading / real broker credentials
- QM integration
- Dual chat run models expansion

## Future consolidation candidates

- engineering.AgentSessionAdapter ↔ AgentHarness
- Approval plane correlation
- ModelGateway deprecation as public entry
- Chat dual-record collapse
- Scheduler policy unification
- Identity module naming (platform vs security)
- missions/ vs mission_runtime naming in docs

---

# Explicit non-actions (this milestone)

- No AgentHarness / FakeInMemoryHarness / commercial CLI adapters
- No policy floors or skill promotion implementation
- No production code, tests, dependencies, CI, deploy
- No module deletion, data migration, provider connection
- No authority weakening

---

# Recommended next milestone

**FM-C1 (docs-only freeze & contradiction repair)** immediately if not folded into this merge, then **FM-C2 AgentSessionAdapter ↔ AgentHarness relationship ADR (design-only)**.

**Do not** start AgentHarness types, policy floors, or skill promotion until FM-C2 (and freezes) complete.

---

# Success criteria checklist

| Criterion | Met |
| --- | --- |
| Current source inspected | ✓ SHA `e9581f4…` |
| Docs verified against source | ✓ |
| Components inventoried | ✓ §M386 |
| Authority mapped | ✓ §M387 |
| Duplicate control planes identified | ✓ §M388 |
| State SoT identified | ✓ §M389 |
| E2E paths traced | ✓ §M390 |
| Terminology documented | ✓ §M391 |
| Target architecture defined | ✓ §M392 |
| AgentHarness reconsidered | ✓ ADR D3/D4 |
| No production code | ✓ |
| No implementation | ✓ |
| No provider/credential | ✓ |
| No authority weakened | ✓ |
| Roadmap produced | ✓ §M393 |
| Next milestone justified | ✓ FM-C1/C2 |

---

**STOP after M393. No consolidation implementation.**
