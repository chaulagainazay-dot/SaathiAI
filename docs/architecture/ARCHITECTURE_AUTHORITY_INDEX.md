# SaathiOS Architecture Authority Index

**Status:** AUTHORITATIVE (FM-C1 baseline; **updated FM-C2** 2026-08-06)
**Companion baseline:** [`FM_C1_DOCUMENTATION_BASELINE_REPORT.md`](./FM_C1_DOCUMENTATION_BASELINE_REPORT.md)
**Top-level architecture ADR:** [`docs/adr/ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION.md`](../adr/ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION.md)
**Driver relationship ADR:** [`docs/adr/ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP.md`](../adr/ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP.md)

This index tells a competent engineer **which documents to trust**, which are historical, and where source ownership lives. Prefer this file over scattered milestone headers when claims conflict.

---

## 1. How to use this index

| Need | Start here |
| --- | --- |
| Current architecture map + freezes | ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION + freeze register |
| Execution / side effects | ADR-EXECUTIONGATEWAY + ADR-TOOLINTENT + `saathi/execution/` |
| Multi-agent runs | `docs/agent-runtime/M48_*` + `saathi/agent_runtime/` |
| Platform tenancy / RBAC / mission runtime | `saathi/platform/` + CAPABILITY_MATURITY_MATRIX rows |
| Providers / models | `saathi/inference/` + M21–M25 docs |
| AgentHarness design + FM-I1 fake proof | ADR-AGENT-HARNESS-INTERFACE + `saathi/agent_runtime/harness/` (**internal; not production**) |
| **AgentSessionAdapter ↔ AgentHarness relationship** | **ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP** + [`FM_C2_…RECONCILIATION.md`](./FM_C2_AGENT_SESSION_ADAPTER_HARNESS_RECONCILIATION.md) |
| Engineering process adapters | `saathi/engineering/adapters/` — **engineering plane only** |
| What is frozen | [`ARCHITECTURE_FREEZE_REGISTER.md`](./ARCHITECTURE_FREEZE_REGISTER.md) |
| Terminology | [`CANONICAL_TERMINOLOGY.md`](./CANONICAL_TERMINOLOGY.md) |
| Contradictions | [`FM_C1_CONTRADICTION_REGISTER.md`](./FM_C1_CONTRADICTION_REGISTER.md) (CX-05 closed in FM-C2) |
| Next authorized implementation | **FM-I5 only after separate owner authorization** — FM-I4 harness governor is internal/in-process; providers/CLIs remain frozen |

**Document class legend:** AUTHORITATIVE · SUPPORTING · HISTORICAL · SUPERSEDED · DRAFT · DESIGN_ONLY · REJECTED · STALE_REQUIRES_REPAIR

---

## 2. Authoritative top-level set (read these first)

| Topic | Authoritative document | Class | Source module(s) |
| --- | --- | --- | --- |
| Architecture consolidation / control plane | `docs/adr/ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION.md` | AUTHORITATIVE | (docs map over `saathi/`) |
| Consolidation evidence | `docs/architecture/M386_M393_ARCHITECTURE_CONSOLIDATION_REVIEW.md` | AUTHORITATIVE | full inventory |
| This authority index | `docs/architecture/ARCHITECTURE_AUTHORITY_INDEX.md` | AUTHORITATIVE | — |
| Canonical terminology | `docs/architecture/CANONICAL_TERMINOLOGY.md` | AUTHORITATIVE | — |
| Freeze register | `docs/architecture/ARCHITECTURE_FREEZE_REGISTER.md` | AUTHORITATIVE | — |
| Contradiction register | `docs/architecture/FM_C1_CONTRADICTION_REGISTER.md` | AUTHORITATIVE | — |
| AgentSessionAdapter ↔ AgentHarness | `docs/adr/ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP.md` | AUTHORITATIVE design | `saathi/engineering/adapters/` (eng only) |
| FM-C2 reconciliation evidence | `docs/architecture/FM_C2_AGENT_SESSION_ADAPTER_HARNESS_RECONCILIATION.md` | AUTHORITATIVE design | — |
| Roadmap (current top entries) | `docs/AUTONOMOUS_ROADMAP.md` | AUTHORITATIVE for sequencing | — |
| Capability maturity (capability rows) | `docs/CAPABILITY_MATURITY_MATRIX.md` | AUTHORITATIVE for maturity claims | packages listed per row |
| Project operating rules | `Agents.md` | AUTHORITATIVE for agent ops / TG rules | — |

---

## 3. Domain architecture pointers

### 3.1 Execution architecture

| Role | Document | Class | Source |
| --- | --- | --- | --- |
| ExecutionGateway ADR | `docs/adr/ADR-EXECUTIONGATEWAY-SPECIFICATION.md` | **AUTHORITATIVE** (`ACCEPTED_IMPLEMENTED`) | `saathi/execution/gateway.py`, `universal.py` |
| ToolIntent ADR | `docs/adr/ADR-TOOLINTENT-IMMUTABLE-CONTRACT.md` | **AUTHORITATIVE** (`ACCEPTED_IMPLEMENTED`) | `saathi/execution/toolintent.py` |
| Tool runtime contracts | M49 docs / tool_runtime closure notes | SUPPORTING | `saathi/tool_runtime/` |
| Historical Phase 3 narrative | `TOOLINTENT_SPEC.md`, root readiness reports | HISTORICAL | — |

### 3.2 Agent runtime architecture

| Role | Document | Class | Source |
| --- | --- | --- | --- |
| Canonical runtime map | `docs/agent-runtime/M48_1_CANONICAL_RUNTIME_MAP.md` | AUTHORITATIVE (runtime map) | `saathi/agent_runtime/` |
| Runtime inventory | `docs/agent-runtime/M48_1_RUNTIME_INVENTORY.md` | SUPPORTING (may lag new modules) | same |
| Contracts / lifecycle / residual risk | `docs/agent-runtime/M48_*` | SUPPORTING / AUTHORITATIVE for residual RR-01..10 | same |
| AgentHarness design | ADR-AGENT-HARNESS + M385 design | **DESIGN_ONLY** | **not in source** |
| Engineering sessions | engineering package docs (if any) | SUPPORTING | `saathi/engineering/adapters/` |

### 3.3 Provider architecture

| Role | Document | Class | Source |
| --- | --- | --- | --- |
| Inference / provider governance | `docs/M21_*`, `docs/M24_*`, `docs/M25_*` (as present) | SUPPORTING + maturity matrix | `saathi/inference/` |
| Model routing helper | M48.1 model routing contract | SUPPORTING | `saathi/model_router.py` |
| ModelGateway (exec orch) | — | **FROZEN expansion** (not preferred public entry) | `saathi/execution/orchestrators/model_gateway.py` |
| OpenJarvis ADR | ADR-OPENJARVIS-LOCAL-RUNTIME | **SUPERSEDED** | conceptual only |

### 3.4 Approval architecture

| Role | Document | Class | Source |
| --- | --- | --- | --- |
| Platform approvals / RBAC enums | platform models + M50 narratives | AUTHORITATIVE for product plane | `saathi/platform/models.py`, `service.py` |
| Execution approval binding | ExecutionGateway / universal boundary | AUTHORITATIVE for exec plane | `saathi/execution/universal.py` |
| Agent run approval records | M48.1 authority contract | SUPPORTING | `saathi/agent_runtime/contracts.py` |
| Credential approval envelopes | M35 docs | SUPPORTING | `saathi/credentials/m35.py` |
| TG domain approvals | trading docs M192+ | SUPPORTING domain | `saathi/platform/tg/**` |

### 3.5 Credential architecture

| Role | Document | Class | Source |
| --- | --- | --- | --- |
| Credential leases / sessions | M35–M46 docs under `docs/` | SUPPORTING | `saathi/credentials/` |
| Rule | Secrets leased at EG; never in ToolIntent | AUTHORITATIVE principle | ADR-EG + ToolIntent |

### 3.6 Trading Guardian architecture

| Role | Document | Class | Source |
| --- | --- | --- | --- |
| Guardian engine | trading / platform TG docs + maturity matrix rows | AUTHORITATIVE posture: paper/research/sandbox | `saathi/platform/trading_guardian.py`, `saathi/platform/tg/` |
| Agents.md TG section | `Agents.md` | AUTHORITATIVE policy constraints | — |
| Live trading | — | **PROHIBITED** without separate owner ceremony | freeze register |

### 3.7 Memory, evidence, audit, replay

| Concern | Authoritative owner | Class | Must not merge with |
| --- | --- | --- | --- |
| Memory | `saathi/memory/engine` | AUTHORITATIVE for agent memory | Evidence |
| Evidence | `saathi/evidence` | AUTHORITATIVE universal outcomes | Memory |
| Security audit | `saathi/security` | AUTHORITATIVE security trail | Certification marketing |
| Replay | domain modules (run checkpoints, computer_agent replay) | SUPPORTING / fragmented | Live retry |

### 3.8 Certification architecture

| Role | Document | Class |
| --- | --- | --- |
| Maturity matrix | `docs/CAPABILITY_MATURITY_MATRIX.md` | AUTHORITATIVE labels |
| Domain cert packages | `docs/**/cert*`, `docs/trading/m*_evidence/` | SUPPORTING per package |
| Inference production cert | M25 docs | AUTHORITATIVE that production_certified requires evidence |

### 3.9 Platform / product layers

| Role | Document | Source |
| --- | --- | --- |
| Platform missions | CAPABILITY matrix M69–M72 | `saathi/platform/mission_runtime/` |
| Product missions | mission audits | `saathi/missions/` (**different plane**) |
| Orchestration compile | matrix M95–M102 | `saathi/platform/orchestration/` |
| Skills runtime | matrix M112–M120 | `saathi/platform/skills/` |
| ApplicationHarness | M17.3+ docs | `saathi/application_harness/` |

---

## 4. ADR catalog (normalized statuses)

| ADR | Normalized status | Notes |
| --- | --- | --- |
| ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION | ACCEPTED_DESIGN_ONLY | Top architecture map |
| ADR-EXECUTIONGATEWAY-SPECIFICATION | ACCEPTED_IMPLEMENTED | FM-C1 repaired from “awaiting implementation” |
| ADR-TOOLINTENT-IMMUTABLE-CONTRACT | ACCEPTED_IMPLEMENTED | FM-C1 repaired immutability wording |
| ADR-AGENT-HARNESS-INTERFACE | ACCEPTED_DESIGN_ONLY | Relationship decided FM-C2; impl still FZ-01 |
| ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP | ACCEPTED_DESIGN_ONLY | FM-C2; Alternative F |
| ADR-QM-MULTI-AGENT-RUNTIME | ACCEPTED_DESIGN_ONLY | ADAPT_SELECTED_PATTERNS; no import |
| ADR-VIDEO-BACKEND-POLICY | ACCEPTED_WITH_LIMITATIONS | Video routing under EG |
| ADR-OPENMONTAGE-SEPARATE-SERVICE | ACCEPTED_WITH_LIMITATIONS | AGPL isolation |
| ADR-OPENJARVIS-LOCAL-RUNTIME | SUPERSEDED | Use `saathi.inference` |
| ADR-CLAUDE-VIDEO-ADAPTER | PROPOSED | Historical / non-control-plane |
| ADR-CLAUDEVIDEO-RENDERING | DRAFT | Historical discovery |

Allowed status vocabulary: `PROPOSED` · `ACCEPTED_DESIGN_ONLY` · `ACCEPTED_IMPLEMENTED` · `ACCEPTED_WITH_LIMITATIONS` · `SUPERSEDED` · `REJECTED` · `DEPRECATED`

---

## 5. Historical / superseded / do-not-trust-for-status

| Pattern | Class | Guidance |
| --- | --- | --- |
| Milestone audit reports (`docs/M17_*`, `docs/M48_*` thin narratives) | HISTORICAL / SUPPORTING | Use for evidence; verify against source before authority claims |
| Root `PHASE3.1_*`, old readiness PDFs/MD | HISTORICAL | Do not use for “is it implemented?” |
| QM “future M386 policy floors” tables | SUPERSEDED numbering | Consolidation reclaimed M386–M393; floors deferred |
| Claims that AgentHarness is available | REJECTED | Design-only; no Python class |
| Claims that ExecutionGateway is unimplemented | REJECTED (repaired) | Source implements it |

---

## 6. Traceability table (module → document → ADR → milestone)

| Source module | Authoritative document | ADR | Milestone band |
| --- | --- | --- | --- |
| `saathi/execution/` | ADR-EG + ToolIntent ADR | ADR-EXECUTIONGATEWAY, ADR-TOOLINTENT | Phase 3 / M17.22 / M28 |
| `saathi/tool_runtime/` | M49 / maturity matrix | (execution ADRs) | M49 |
| `saathi/agent_runtime/` | M48 canonical map + inventory | consolidation ADR | M10, M48 |
| `saathi/platform/runtime.py` | consolidation review; matrix M52 | consolidation | M52 |
| `saathi/platform/mission_runtime/` | matrix M69–M72 | consolidation | M69–M72 |
| `saathi/platform/orchestration/` | matrix M95–M102 | consolidation | M95–M102 |
| `saathi/platform/models.py` (RBAC/approvals) | platform models + consolidation | consolidation | M50+ |
| `saathi/platform/identity.py` | M51 identity | consolidation | M51 |
| `saathi/credentials/` | M35–M46 docs | — | M35–M46 |
| `saathi/inference/` | M21–M25 docs | (OpenJarvis superseded) | M21–M25 |
| `saathi/model_router.py` | M48.1 model routing | — | M48 / earlier |
| `saathi/execution/orchestrators/model_gateway.py` | freeze register (frozen expansion) | consolidation | residual |
| `saathi/application_harness/` | M17.3+ docs | — | M17.3+ |
| `saathi/engineering/adapters/` | FM-C2 reconciliation + freeze register | ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP | engineering M20 / FM-C2 |
| AgentHarness (none) | ADR-AGENT-HARNESS + FM-C2 | ACCEPTED_DESIGN_ONLY; FZ-01 | M385 / FM-C2 |
| `saathi/memory/` | memory docs + consolidation SoT | consolidation | M9 |
| `saathi/evidence/` | evidence docs | consolidation | early |
| `saathi/security/` | security docs | — | M15.2 |
| `saathi/browser/`, `computer_agent/` | M17.23–26 docs | — | M17 |
| `saathi/connectors/` | M15 / M30 | — | M15–M30 |
| `saathi/platform/tg/`, `trading_guardian.py` | trading docs + Agents.md | consolidation | M62+ |
| `saathi/missions/` | product mission docs | consolidation (naming) | pre-M50 |
| `saathi/scheduler.py` | freeze register / consolidation | consolidation | early product |
| `saathi/agents/` (IELTS) | M48.2 legacy boundary | consolidation freeze | domain |
| `saathi/chat/` | M8 / RR-04 | consolidation freeze dual-write | M8 |
| AgentHarness (none) | ADR-AGENT-HARNESS + FM-C2 relationship | ACCEPTED_DESIGN_ONLY; FZ-01 | M385 / FM-C2 |
| QM (none) | ADR-QM | ACCEPTED_DESIGN_ONLY | M377–M384 |

---

## 7. Unauthorized / next work

| Work | Status |
| --- | --- |
| FM-C1 documentation baseline | **Complete** (published baseline) |
| FM-C2 AgentSessionAdapter ↔ AgentHarness relationship | **Complete (design-only)** — Alternative F |
| AgentHarness types / FakeInMemoryHarness | **Unauthorized** until **FM-I1** owner authorization (FZ-01 retained) |
| Policy floors / skill promotion | **Deferred** |
| Commercial CLI adapters | **Blocked** (FZ-07 / FZ-02) |
| Live trading / broker credentials | **Blocked** |

---

## 8. Explicit non-authority documents

The following **must not** be treated as control-plane authority even if useful:

- Video discovery ADRs alone
- Agentdev terminology / qualification reports alone
- UI copy in `saathi-os/`
- External QM README

---

**FM-C1:** Documentation baseline frozen for discoverability. Implementation remains unauthorized beyond freezes.
