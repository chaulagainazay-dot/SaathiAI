# SaathiOS Canonical Terminology (FM-C1)

**Status:** AUTHORITATIVE glossary
**Date:** 2026-08-06
**Parent:** ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION · M386–M393 review
**Rule:** Prefer these meanings in **new documentation**. Do **not** rename production code in FM-C1.

---

## Vocabulary rules

1. Never use bare **harness**, **session**, **gateway**, **orchestrator**, **mission**, or **run** without a qualifier when ambiguity is possible.
2. **Capability ≠ permission.** Descriptive labels are not RBAC grants.
3. **Skill ≠ tool.** Skills package content/lifecycle; tools execute under ToolIntent.
4. **Approval** is a human authorization record, not a model “yes.”
5. **Certified** always names a package/path and limitations; never global “production ready” without evidence.

---

## Terms

### agent

| Field | Definition |
| --- | --- |
| **Canonical meaning** | A role or runtime participant that plans and **proposes** actions; it does not own external side-effect authority. |
| **Owning subsystem** | Plane-specific: `agent_runtime` definitions; platform mission agent roles; bounded domain agents |
| **Prohibited meanings** | OS user identity; automatic financial authority; commercial CLI binary as control plane |
| **Related** | runtime, capability, role |
| **Examples** | planner agent in a multi-agent run; `BoundedPlatformAgent` |
| **Legacy** | `saathi/agent.py` product SaathiAgent; IELTS `saathi/agents` |

### runtime

| Field | Definition |
| --- | --- |
| **Canonical meaning** | A code plane that owns a lifecycle (runs, platform executions, inference). |
| **Owning subsystem** | Named: agent_runtime, PlatformAgentRuntime, inference runtime |
| **Prohibited meanings** | “Any Python process”; QM Node core |
| **Related** | agent, orchestrator (qualified) |
| **Examples** | `saathi.agent_runtime`, `saathi.platform.runtime.PlatformAgentRuntime` |
| **Legacy** | OpenJarvis as “the runtime” (superseded) |

### harness

| Field | Definition |
| --- | --- |
| **Canonical meaning** | **Do not use bare.** Always qualify (ApplicationHarness, AgentHarness design, sandbox harness, red-team harness). |
| **Owning subsystem** | N/A for bare term |
| **Prohibited meanings** | Generic synonym for agent, runtime, or gateway |
| **Related** | application harness, agent harness, agent session adapter |
| **Examples** | “ApplicationHarness adapter”, not “the harness” |
| **Legacy** | Loose milestone language “harness series” |

### application harness

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Argv-only structured CLI tool executor under ExecutionGateway (M17.3+). Single-action process spawn with trust/file-root confinement. |
| **Owning subsystem** | `saathi.application_harness` |
| **Prohibited meanings** | Multi-turn coding driver; unrestricted shell |
| **Related** | tool, command, sandbox |
| **Examples** | FFmpeg/SQLite/jq/zip pilots |
| **Legacy** | “CLI-Anything harness” informal name |

### agent harness

| Field | Definition |
| --- | --- |
| **Canonical meaning** | **Design-only** multi-turn coding/reasoning **driver** contract (M385). Proposes tools; never executes them. |
| **Owning subsystem** | Future controller under orchestration; **not implemented** |
| **Prohibited meanings** | Second ExecutionGateway; credential owner; ApplicationHarness |
| **Related** | agent session adapter, agent_runtime |
| **Examples** | ADR-AGENT-HARNESS `start_session` / `submit_turn` sketches |
| **Legacy** | QM “Harness” TypeScript interface (reference only) |

### agent session adapter

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Existing engineering contract (`AgentSessionAdapter`) for start/poll/stop of a coding session process (e.g. Claude Code adapter, mock). |
| **Owning subsystem** | `saathi.engineering.adapters` |
| **Prohibited meanings** | AgentHarness (design) until FM-C2 reconciles; tool execution authority |
| **Related** | agent harness, session (engineering kind) |
| **Examples** | `ClaudeCodeAdapter`, `MockAgentAdapter` |
| **Legacy** | “engineering orchestrator session” informal |

### provider

| Field | Definition |
| --- | --- |
| **Canonical meaning** | External or local model/service vendor under governance (inference) or connector provider catalog. |
| **Owning subsystem** | `saathi.inference` (models); `saathi.connectors` (integrations); TG provider contracts (research) |
| **Prohibited meanings** | Tool; secret value; automatic production cert |
| **Related** | model, router |
| **Examples** | Ollama local; cloud LLM under policy |
| **Legacy** | Direct SDK “provider” calls outside residual allowlists |

### model

| Field | Definition |
| --- | --- |
| **Canonical meaning** | A specific model identity/revision selected for inference. |
| **Owning subsystem** | Inference catalogue + ModelRouter labels |
| **Prohibited meanings** | Provider account; agent role |
| **Related** | provider, capability |
| **Examples** | `qwen2.5:1.5b` |
| **Legacy** | — |

### router

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Component that selects among alternatives (models, identity providers) **without** granting tool authority. |
| **Owning subsystem** | `ModelRouter`; identity routers |
| **Prohibited meanings** | ExecutionGateway |
| **Related** | model, provider |
| **Examples** | capability-label model routing |
| **Legacy** | — |

### gateway

| Field | Definition |
| --- | --- |
| **Canonical meaning** | **Reserve for ExecutionGateway** in new architecture prose. Qualify all others (`ModelGateway`). |
| **Owning subsystem** | Execution: `saathi.execution` |
| **Prohibited meanings** | Using “gateway” alone for model routing |
| **Related** | execution gateway, ModelGateway (frozen expansion) |
| **Examples** | “submit via ExecutionGateway” |
| **Legacy** | `execution/orchestrators/model_gateway.py` name collision |

### execution gateway

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Sole external-action authority: validate → authorize → risk → approval → credentials → execute → evidence. |
| **Owning subsystem** | `saathi.execution.ExecutionGateway` + `UniversalBoundary` |
| **Prohibited meanings** | Optional helper; UI gate alone |
| **Related** | ToolIntent, approval, tool |
| **Examples** | `submit(ToolIntent)`, `execute_registered_tool` |
| **Legacy** | “Phase 3.2 awaiting implementation” (stale; repaired FM-C1) |

### mission

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Always qualify: **PlatformMission** (mission_runtime hierarchy) vs **ProductMission** (`saathi/missions` content/ops). |
| **Owning subsystem** | platform.mission_runtime vs missions/ |
| **Prohibited meanings** | Equating either with agent_runtime `run` |
| **Related** | run, project, workspace |
| **Examples** | Autonomous Mission Runtime DAG; brand workflow mission |
| **Legacy** | Bare “mission” in mixed docs |

### run

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Agent multi-step execution record in `agent_runtime.RunStore` (or qualified: harness run, browser run, TG job). |
| **Owning subsystem** | agent_runtime RunStore; others when qualified |
| **Prohibited meanings** | Single tool execution record (use execution record) |
| **Related** | session, mission, checkpoint |
| **Examples** | `RunState.RUNNING` |
| **Legacy** | chat `agent_run` dual record (RR-04) |

### session

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Scoped interactive/auth/driver context — **always qualify kind** (auth, credential, computer, browser, voice, engineering, provider, harness-design). |
| **Owning subsystem** | Kind-specific modules |
| **Prohibited meanings** | One global Session table for all concerns |
| **Related** | run, lease |
| **Examples** | `ComputerSession`, credential `SessionLease` |
| **Legacy** | Unqualified “session_id” across APIs |

### workspace

| Field | Definition |
| --- | --- |
| **Canonical meaning** | RBAC tenancy workspace under an organization. |
| **Owning subsystem** | PlatformStore |
| **Prohibited meanings** | Sandbox work_dir; git worktree (qualify those) |
| **Related** | organization, project, scope |
| **Examples** | platform `workspace_id` |
| **Legacy** | QM Slack “scope” as workspace |

### scope

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Authorization boundary composition (org/workspace/project/mission/run/actor). |
| **Owning subsystem** | Platform context + run contracts |
| **Prohibited meanings** | QM multiplayer room scope as SaathiOS control plane |
| **Related** | workspace, permission |
| **Examples** | `PlatformExecutionContext` fields |
| **Legacy** | — |

### sandbox

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Isolated execution environment for tools/connectors/tests (file roots, conformance sandbox, TG broker sandbox). |
| **Owning subsystem** | application_harness roots, connectors/conformance, tg/broker_sandbox |
| **Prohibited meanings** | Entire agent runtime; place to store ambient secrets |
| **Related** | application harness, tool |
| **Examples** | Temporary connector certification sandbox |
| **Legacy** | — |

### tool

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Registered executable capability invoked only via ToolIntent / registered-tool path through ExecutionGateway. |
| **Owning subsystem** | `saathi.tool_runtime` + EG |
| **Prohibited meanings** | Skill pack; freeform shell string |
| **Related** | command, capability, ToolIntent |
| **Examples** | ToolManifest + ToolExecutionService |
| **Legacy** | ad-hoc `execute_tool` bridges under audit |

### command

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Allowlisted argv manifest entry (no `shell=True`). |
| **Owning subsystem** | `tool_runtime.command_manifest` |
| **Prohibited meanings** | User shell; agent freeform bash |
| **Related** | application harness, tool |
| **Examples** | `run_allowlisted_command` |
| **Legacy** | — |

### skill

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Packaged instructions/assets with lifecycle; **not** a permission and **not** a tool. |
| **Owning subsystem** | `platform.skills`, `skills_library`, content trees / `.grok/skills` |
| **Prohibited meanings** | Automatic tool registration authority; marketplace trust |
| **Related** | agent, tool, capability |
| **Examples** | skill package install/upgrade/rollback |
| **Legacy** | “skill” as synonym for agent role |

### capability

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Declared ability label for planning or harness profiles (descriptive). |
| **Owning subsystem** | agent_runtime contracts KNOWN_CAPABILITIES; harness profiles (design) |
| **Prohibited meanings** | RBAC permission; production certification |
| **Related** | permission, authority |
| **Examples** | `code`, `memory_read` |
| **Legacy** | — |

### policy

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Rule set constraining behavior (risk, domain, provider, TG). |
| **Owning subsystem** | Various policy modules |
| **Prohibited meanings** | Permission grant |
| **Related** | permission, approval |
| **Examples** | browser domain policy; provider_policy |
| **Legacy** | — |

### permission

| Field | Definition |
| --- | --- |
| **Canonical meaning** | RBAC `PlatformPermission` (or equivalent enumerated grant). |
| **Owning subsystem** | Platform RBAC |
| **Prohibited meanings** | Capability label; skill install |
| **Related** | role, authority |
| **Examples** | `MISSION_RUN`, `APPROVAL_DECIDE` |
| **Legacy** | — |

### approval

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Human authorization record requestable/decidable/consumable by gates; plane-tagged (`approval_id` + plane). |
| **Owning subsystem** | Platform Approval Center (product); EG bind (execution); domain TG/credential envelopes |
| **Prohibited meanings** | Agent self-approve; UI-only decide without server |
| **Related** | authority, policy |
| **Examples** | platform ApprovalRecord; run AWAITING_APPROVAL |
| **Legacy** | Multiple enum names (normalize in docs by plane) |

### authority

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Right to decide or execute within a named plane. |
| **Owning subsystem** | Explicit owners in freeze/authority maps |
| **Prohibited meanings** | Implied by UI presence or skill content |
| **Related** | permission, approval |
| **Examples** | FINANCIAL_EXECUTION PROHIBITED at contract layer |
| **Legacy** | — |

### evidence

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Structured outcome/proof record (EvidenceStore / packages). |
| **Owning subsystem** | `saathi.evidence` (+ package-local evidence dirs) |
| **Prohibited meanings** | Chat transcript alone; marketing claim |
| **Related** | audit, certification, replay |
| **Examples** | EG Evidence on attempt |
| **Legacy** | — |

### audit

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Security/compliance event trail (append-oriented). |
| **Owning subsystem** | `saathi.security` + platform audit streams |
| **Prohibited meanings** | Full behavioral replay |
| **Related** | evidence, correlation_id |
| **Examples** | SecurityStore events |
| **Legacy** | — |

### replay

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Deterministic re-presentation or constrained re-execution of recorded run/tape/checkpoint. |
| **Owning subsystem** | Domain modules (not one global system) |
| **Prohibited meanings** | Blind mutation retry |
| **Related** | checkpoint, evidence |
| **Examples** | RunStore checkpoint; computer_agent replay |
| **Legacy** | — |

### certification

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Evidence-backed verdict for a **named package/path**, usually WITH_LIMITATIONS. |
| **Owning subsystem** | Domain cert modules + release_check |
| **Prohibited meanings** | Global production readiness without evidence |
| **Related** | maturity, evidence |
| **Examples** | `cert:m303`, connector package cert |
| **Legacy** | Loose “certified” in blogs |

### maturity

| Field | Definition |
| --- | --- |
| **Canonical meaning** | Staged readiness label (implemented < deterministic-tested < … < production). |
| **Owning subsystem** | CAPABILITY_MATURITY_MATRIX + domain CURRENT_MATURITY constants |
| **Prohibited meanings** | Same as certification alone |
| **Related** | certification |
| **Examples** | `OPERATIONALLY_READY_OFFLINE` TG readiness maturity |
| **Legacy** | — |

---

## Quick disambiguation matrix

| Confused pair | Keep separate how |
| --- | --- |
| ApplicationHarness vs AgentHarness | argv tool vs multi-turn driver design |
| AgentHarness vs AgentSessionAdapter | design contract vs existing engineering adapter |
| ExecutionGateway vs ModelGateway | side effects vs residual model entry name |
| PlatformMission vs ProductMission | mission_runtime vs missions/ |
| Run vs execution record | agent multi-step vs single tool attempt |
| Skill vs tool | content/lifecycle vs governed execution |
| Capability vs permission | descriptive vs RBAC |
| Evidence vs audit vs cert | outcome package vs security trail vs verdict |

---

**No production renames in FM-C1.**
