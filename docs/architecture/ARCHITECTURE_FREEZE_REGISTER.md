# SaathiOS Architecture Freeze Register (FM-C1)

**Status:** AUTHORITATIVE
**Date:** 2026-08-06
**Originating decisions:** ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION · ADR-QM · ADR-AGENT-HARNESS · M48 residual risk · Agents.md Trading Guardian
**Purpose:** Explicit list of expansion freezes until named authorities unfreeze them.

Unfreezing **requires** the authority and prerequisites listed. Informal “just ship it” is insufficient.

---

## Freeze catalog

### FZ-01 — AgentHarness implementation

| Field | Value |
| --- | --- |
| **Frozen subject** | Production types, packages, adapters for AgentHarness; FakeInMemoryHarness; LocalModelHarness |
| **Reason** | Design-only (M385); implementation not yet authorized (relationship now decided in FM-C2) |
| **Originating decision** | ADR-AGENT-HARNESS; consolidation D3/D4; FM-C1; **amended FM-C2** |
| **Authority to unfreeze** | Owner + **separate implementation milestone** (FM-I1: fake + types + controller test double only) |
| **Prerequisite** | **FM-C2 relationship ADR accepted** (satisfied 2026-08-06); freezes FZ-04, FZ-05, FZ-07 still held |
| **Prohibited work** | Any `saathi/**` AgentHarness code until FM-I1 authorization; commercial CLI adapters; CI claiming adapters exist |
| **Review condition** | After explicit FM-I1 owner authorization — **not** auto-started by FM-C2 |
| **FM-C2 disposition** | **RETAINED** (relationship prerequisite met; implementation freeze remains) |

### FZ-02 — New AgentSessionAdapter variants

| Field | Value |
| --- | --- |
| **Frozen subject** | New commercial or multi-turn session adapters under `saathi.engineering.adapters` |
| **Reason** | Engineering plane must not become a second platform multi-agent control plane; commercial CLI residual side effects |
| **Originating decision** | Consolidation R-04; FM-C1; **amended FM-C2** (plane separation) |
| **Authority to unfreeze** | Security ADR + package certification; platform drivers must implement **AgentHarness**, not new eng ABC product variants |
| **Prerequisite** | FM-C2 accepted (satisfied); FZ-07 for any commercial CLI |
| **Prohibited work** | New Claude/Codex/OpenCode adapters; new ABC subclasses for product/platform use |
| **Allowed without unfreeze** | Existing `mock` / `claude_code` classes; tests; dry_run; eng settings allowlist as today |
| **Review condition** | Only with security ADR elevating a process driver under AgentHarness bridge |
| **FM-C2 disposition** | **RETAINED / AMENDED** (scope clarified; freeze not removed) |

### FZ-03 — New bare Orchestrator modules

| Field | Value |
| --- | --- |
| **Frozen subject** | New top-level `*Orchestrator` classes as general control planes |
| **Reason** | Name/authority collision (agent_runtime, engineering, TG research, mission_runtime) |
| **Originating decision** | Consolidation M391/M388 |
| **Authority to unfreeze** | Architecture ADR naming a single owner and disambiguated type name |
| **Prerequisite** | Terminology compliance |
| **Prohibited work** | Parallel multi-agent orchestrators outside agent_runtime / PlatformAgentRuntime |
| **Review condition** | Documented need + naming ADR |

### FZ-04 — New generic Harness modules

| Field | Value |
| --- | --- |
| **Frozen subject** | New modules named only `harness` / `Harness` without typed prefix |
| **Reason** | Terminology overload (Application / Agent / sandbox / red-team) |
| **Originating decision** | CANONICAL_TERMINOLOGY; consolidation |
| **Authority to unfreeze** | Doc review + typed name (ApplicationHarness-family or AgentHarness after FZ-01) |
| **Prerequisite** | Glossary compliance |
| **Prohibited work** | Ambiguous harness packages |
| **Review condition** | Continuous |

### FZ-05 — ModelGateway expansion

| Field | Value |
| --- | --- |
| **Frozen subject** | Expanding `saathi.execution.orchestrators.model_gateway.ModelGateway` as public entry for new callers |
| **Reason** | Partial duplication with `saathi.inference` + ModelRouter |
| **Originating decision** | Consolidation M388/M392 |
| **Authority to unfreeze** | Provider-architecture ADR proving residual need |
| **Prerequisite** | Inference path inventory / residual allowlist update |
| **Prohibited work** | New product callers to ModelGateway; documenting it as preferred path |
| **Review condition** | Provider consolidation design |

### FZ-06 — New scheduler implementations

| Field | Value |
| --- | --- |
| **Frozen subject** | New independent product schedulers / cron loops |
| **Reason** | Fragmented ownership (`scheduler.py`, harness schedulers, TG ExperimentScheduler) |
| **Originating decision** | Consolidation M388 score scheduling 48 |
| **Authority to unfreeze** | Scheduler policy design ADR (future FM after C2) |
| **Prerequisite** | Inventory of existing runners |
| **Prohibited work** | Fourth+ global job loop without platform context design |
| **Review condition** | Ops/architecture review |
| **Note** | Existing schedulers may run; expansion of **new** systems frozen |

### FZ-07 — Commercial CLI adapters as control plane

| Field | Value |
| --- | --- |
| **Frozen subject** | Claude Code / Codex / OpenCode / similar as SaathiOS authority surface |
| **Reason** | Credential, process, and gateway-bypass risk; M385 D10/D11 |
| **Originating decision** | ADR-AGENT-HARNESS; ADR-QM; consolidation |
| **Authority to unfreeze** | Separate security ADR + package certification + EG tool-proposal path |
| **Prerequisite** | FZ-01 unfreeze path; FakeInMemory + local first |
| **Prohibited work** | Wiring commercial CLIs above ExecutionGateway |
| **Review condition** | Security + cert gates |

### FZ-08 — Ambient credential models

| Field | Value |
| --- | --- |
| **Frozen subject** | Long-lived plaintext secrets in agent/sandbox environments as primary model |
| **Reason** | Conflicts with lease governance; QM pattern rejected |
| **Originating decision** | ADR-QM; credentials M35+; Agents.md |
| **Authority to unfreeze** | **None anticipated** without replacing credential architecture ADR |
| **Prerequisite** | Stronger security ADR than current lease model |
| **Prohibited work** | Agent-owned secret stores; harness secret fields |
| **Review condition** | Only with credential architecture supersession |

### FZ-09 — QM source integration

| Field | Value |
| --- | --- |
| **Frozen subject** | Import, vendor, deploy, or plugin-integrate yc-software/qm |
| **Reason** | ADR-QM `ADAPT_SELECTED_PATTERNS` only |
| **Originating decision** | ADR-QM |
| **Authority to unfreeze** | New ADR superseding ADR-QM with stronger security evidence |
| **Prerequisite** | Explicit owner decision |
| **Prohibited work** | npm dependency, Docker/Fly control plane, Slack-as-core |
| **Review condition** | Optional re-eval if QM tip changes (analysis-only) |

### FZ-10 — Live broker connectivity

| Field | Value |
| --- | --- |
| **Frozen subject** | Real broker login/OAuth/transport |
| **Reason** | TG series max states paper/research/sandbox; REAL_PROVIDER_TRANSPORT_FORBIDDEN patterns |
| **Originating decision** | TG maturity matrix; Agents.md |
| **Authority to unfreeze** | Owner ceremony + connectivity ADRs + Guardian + EG trade path cert |
| **Prerequisite** | Paper graduation evidence; readiness packages |
| **Prohibited work** | Live connectivity code activation |
| **Review condition** | Explicit owner authorization package |

### FZ-11 — Live trading credentials / live orders

| Field | Value |
| --- | --- |
| **Frozen subject** | Live trading credentials; live order placement; leverage enablement |
| **Reason** | Trading Guardian LIVE disabled; FINANCIAL_EXECUTION PROHIBITED |
| **Originating decision** | Agents.md TG; contracts.py; trading_guardian.py |
| **Authority to unfreeze** | Owner + multi-milestone live activation ceremony |
| **Prerequisite** | FZ-10; paper ops; kill switch drills |
| **Prohibited work** | Weakening Guardian defaults; agent trade_execute capabilities |
| **Review condition** | Never auto |

### FZ-12 — HTTP / production skip_contract paths

| Field | Value |
| --- | --- |
| **Frozen subject** | Using `skip_contract=True` outside pytest; exposing skip on HTTP/API/chat/CLI |
| **Reason** | M48.2 legacy boundary; orchestrator pytest-only guard |
| **Originating decision** | M48.2 / M48.4 |
| **Authority to unfreeze** | Agent-runtime ADR + security review |
| **Prerequisite** | Equivalent fail-closed guarantees |
| **Prohibited work** | API flag to skip contracts |
| **Review condition** | Residual risk reclassification |

### FZ-13 — New dual chat/run stores expansion

| Field | Value |
| --- | --- |
| **Frozen subject** | Expanding dual write of chat `agent_run` + RunStore without migration plan |
| **Reason** | RR-04 accepted but must not grow |
| **Originating decision** | M48.5 residual; consolidation |
| **Authority to unfreeze** | Chat/UI consolidation milestone with migration |
| **Prerequisite** | Correlation plan; single SoT design |
| **Prohibited work** | New dual-ID fields or second ledgers for multi-agent |
| **Review condition** | Chat consolidation design |

### FZ-14 — Side-effect paths outside ExecutionGateway

| Field | Value |
| --- | --- |
| **Frozen subject** | New external side-effect entry points that do not create ToolIntent / registered-tool path |
| **Reason** | Core invariant 1 of ADR-EG |
| **Originating decision** | ADR-EG; consolidation D1 |
| **Authority to unfreeze** | **Never** for general product; only documented test/host-operator exceptions |
| **Prerequisite** | — |
| **Prohibited work** | Direct connector SDK from agents; shell=True tools; browser open bypass of EG family |
| **Review condition** | Continuous gateway audits |

### FZ-15 — IELTS / legacy domain as general multi-agent runtime

| Field | Value |
| --- | --- |
| **Frozen subject** | Expanding `saathi.agents` IELTS stack into general multi-agent platform |
| **Reason** | RR-01 accepted isolation |
| **Originating decision** | M48.2; consolidation freeze list |
| **Authority to unfreeze** | Domain adapter ADR migrating onto agent_runtime contracts |
| **Prerequisite** | Gateway-bound path |
| **Prohibited work** | Using IELTS agents as default OS runtime |
| **Review condition** | Domain migration milestone |

### FZ-16 — Policy floor composition implementation

| Field | Value |
| --- | --- |
| **Frozen subject** | Implementing org policy floors (old provisional M386) |
| **Reason** | Deferred design after consolidation freezes |
| **Originating decision** | ADR-QM future table; consolidation renumber |
| **Authority to unfreeze** | Separate design ADR after FM-C2 baseline |
| **Prerequisite** | Terminology + freeze compliance |
| **Prohibited work** | Dangerous postures; auto-start from this freeze |
| **Review condition** | Post FM-C2 backlog |

### FZ-17 — Skill promotion lifecycle implementation

| Field | Value |
| --- | --- |
| **Frozen subject** | Org-wide skill promotion / marketplace promotion (old provisional M387) |
| **Reason** | Deferred; skills≠tools must stay clear |
| **Originating decision** | ADR-QM; consolidation |
| **Authority to unfreeze** | Skill promotion design ADR |
| **Prerequisite** | CANONICAL_TERMINOLOGY adoption |
| **Prohibited work** | Auto-promote skills to permissions |
| **Review condition** | Post freezes |

---

## Freeze summary table

| ID | Subject | Severity if violated |
| --- | --- | --- |
| FZ-01 | AgentHarness implementation | P1 architecture |
| FZ-02 | New AgentSessionAdapter variants | P1 |
| FZ-03 | New bare Orchestrator modules | P2 |
| FZ-04 | Generic Harness modules | P3 |
| FZ-05 | ModelGateway expansion | P2 |
| FZ-06 | New schedulers | P2 |
| FZ-07 | Commercial CLI control plane | P0/P1 security |
| FZ-08 | Ambient credentials | P0 security |
| FZ-09 | QM integration | P0 governance |
| FZ-10 | Live broker | P0 |
| FZ-11 | Live trading credentials/orders | P0 |
| FZ-12 | skip_contract production | P0/P1 |
| FZ-13 | Dual chat/run expansion | P2 |
| FZ-14 | EG bypass side effects | P0 |
| FZ-15 | IELTS as general runtime | P1 |
| FZ-16 | Policy floors impl | P2 premature |
| FZ-17 | Skill promotion impl | P2 premature |

---

## Unfreeze protocol

1. Cite freeze ID.
2. Produce prerequisite ADR/design.
3. Human owner authorization recorded in roadmap.
4. Implementation milestone with tests + cert gates.
5. Update this register (remove or mark SUPERSEDED freeze).

**FM-C1 does not unfreeze any implementation freeze.**
