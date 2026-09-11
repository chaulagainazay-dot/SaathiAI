# ADR: SaathiOS Architecture Consolidation (M386–M393)

| Field | Value |
| --- | --- |
| **ID** | ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION |
| **Date** | 2026-08-06 |
| **Status** | **ACCEPTED_DESIGN_ONLY** (analysis + design; no implementation authorized) |
| **Milestone** | M386–M393 |
| **Repository tip inspected** | `e9581f43848cf90283c7c4e1c0dbfbad65a4a531` |
| **Branch** | `milestone/m377-m385-qm-agent-harness-design` |
| **Full evidence** | [`docs/architecture/M386_M393_ARCHITECTURE_CONSOLIDATION_REVIEW.md`](../architecture/M386_M393_ARCHITECTURE_CONSOLIDATION_REVIEW.md) |
| **Parent decisions** | ADR-QM-MULTI-AGENT-RUNTIME · ADR-AGENT-HARNESS-INTERFACE · ADR-EXECUTIONGATEWAY-SPECIFICATION · ADR-TOOLINTENT-IMMUTABLE-CONTRACT |
| **Implementation status** | **Documentation only — no production code, adapters, migrations, or providers** |
| **Authority impact** | Freezes expansion of parallel planes; reaffirms ExecutionGateway sole side-effect path; does not weaken TG/RBAC/Approval |
| **Supersedes** | Sequencing that would implement AgentHarness immediately after M385; provisional QM ADR numbers for M386/M387 policy floors / skill promotion |
| **Superseded by** | None (still authoritative architecture map). **FM-C1** freezes and indexes are the operational baseline. |
| **Follow-on** | FM-C1 documentation baseline → **FM-C2** AgentSessionAdapter ↔ AgentHarness design ADR (not started) |

---

## Context

After M48 agent-runtime hardening, M50+ platform tenancy, M17 execution/harness series,
M21–M25 provider governance, M35–M46 credentials, Trading Guardian paper/research series,
and M377–M385 QM/AgentHarness design, SaathiOS has a **strong intended governance spine**
and a **large surface of parallel product/domain modules**.

M385 approved an **AgentHarness design contract** (not implemented). Before any further
foundational runtime abstraction is built, this review answers:

> **What should the authoritative SaathiOS architecture be before any new foundational
> runtime abstraction is implemented?**

### Milestone renumbering (authoritative)

Earlier ADRs (QM / AgentHarness) reserved **M386** for scope/policy floors and **M387**
for skill promotion. This milestone **reclaims M386–M393** for architecture consolidation
review. Deferred QM-pattern design work is **not cancelled**; it is **renumbered**:

| Prior provisional ID | Topic | New disposition |
| --- | --- | --- |
| M386 (QM ADR) | Scope / policy floor composition design | **Deferred** — after consolidation freezes; future design ADR |
| M387 (QM ADR) | Skill promotion lifecycle design | **Deferred** — after skills/agents/tools glossary freeze |
| M388 (QM ADR) | Optional QM re-eval | Unchanged: analysis-only if QM tip changes |

This ADR supersedes informal sequencing that would start AgentHarness types, FakeInMemoryHarness,
policy floors, or skill promotion **before** consolidation decisions are applied.

---

## Decision

### Terminal verdict

**`SAATHIOS_ARCHITECTURE_READY_WITH_CONSOLIDATION_REQUIRED`**

The governance control plane is identifiable and must be preserved. Parallel product
layers, overloaded terminology, and dual session/run/approval surfaces create
**maintainability and future-bypass risk**. New foundational abstractions (including
AgentHarness implementation) must wait for named freezes and a small set of
**design-only reconciliation** steps. No emergency authority defect was found that
requires weakening or replacing ExecutionGateway, Approval, RBAC, or Trading Guardian.

### Required decisions (1–12)

| # | Question | Decision |
| --- | --- | --- |
| 1 | One clear control plane? | **Yes, intended — with bounded parallel domain planes.** Canonical multi-agent control plane = **platform surfaces → `agent_runtime` / `PlatformAgentRuntime` → ExecutionGateway**. Domain planes (IELTS, engineering session adapters, TG research, product chat) may exist only as **explicitly bounded** specializations that do not mint tool/trading authority. |
| 2 | ExecutionGateway sole execution gateway? | **Yes — remains the sole external-action authority** via immutable ToolIntent / registered-tool path. Family handlers (connector, CLI, local, MCP, browser, application harness) execute **under** the gateway. No second gateway may be introduced. |
| 3 | Is AgentHarness still required? | **Conditionally yes as an internal driver contract — not as a new authority.** M385 design remains valid **if and only if** it is reconciled with existing `saathi.engineering.adapters.AgentSessionAdapter` and does not become a third harness plane. Implementation is **not authorized** until freeze + relationship ADR items below complete. |
| 4 | ApplicationHarness vs AgentHarness overlap? | **Intentional specialization, not merge.** ApplicationHarness (M17.3) = single-action argv CLI tool execution under gateway. AgentHarness (M385 design) = multi-turn coding/reasoning **driver** that may only **propose** tools. Names must stay distinct; shared word “harness” requires glossary discipline. |
| 5 | Multiple run/session models remain? | **Yes, but with ownership labels.** Keep distinct: agent `RunStore` runs, platform executions, credential sessions, computer/browser sessions, chat sessions, provider sessions, engineering agent sessions. Prohibit inventing new session types without mapping to this catalog. |
| 6 | Provider vs model routing separated? | **Mostly yes; residual dual surface.** `saathi.inference` + provider governance (M21–M25) is the durable provider plane; `ModelRouter` and `execution/orchestrators/model_gateway.py` are compatibility/legacy-adjacent. Routing decisions must not grant credentials or tool authority. |
| 7 | Memory / evidence / audit / replay ownership? | **Distinct owners required and reaffirmed.** Memory = knowledge/state for agents; Evidence = universal outcome records; Audit = security/platform event trail; Replay = deterministic re-execution/reproduction of runs or tapes. Must not collapse into one store. |
| 8 | Scheduler unified? | **No — not unified today.** `saathi/scheduler.py` (product cron jobs), application_harness schedulers, TG research ExperimentScheduler, fleet/mission timers are separate. Target: **one scheduling *policy* surface**, multiple specialized runners — do not force a single implementation in the next milestone. |
| 9 | Skills / commands / tools / agents separated? | **Partially.** Tools = governed executable units (ToolRegistry + ToolIntent). Commands = allowlisted argv manifests. Skills = packaged capability content/lifecycle (`platform.skills`, `skills_library`, `.grok/skills`). Agents = roles/runtimes that plan and propose. Boundaries must freeze before skill promotion design. |
| 10 | Legacy subsystems frozen from expansion? | **Yes — freeze expansion** of: IELTS `saathi.agents` as general runtime; ad-hoc dual approval inventing; new commercial CLI adapters outside AgentHarness design; new parallel orchestrators; new “gateway-like” facades. Domain isolation (RR-01) remains accepted **without new authority**. |
| 11 | What must be consolidated before implementation resumes? | See P0–P1 roadmap. Minimum before AgentHarness code: (a) freeze list enforced in docs, (b) engineering vs AgentHarness relationship decision, (c) approval owner catalog, (d) glossary published, (e) ADR-EXECUTIONGATEWAY status text corrected. |
| 12 | Safest next implementation milestone? | **Not implementation of AgentHarness.** Next authorized work after this review: **documentation-only freeze enforcement + contradiction fixes**, then optionally a **narrow design ADR** reconciling `AgentSessionAdapter` ↔ AgentHarness. First code milestone only after human authorization: FakeInMemoryHarness **or** authority-preserving micro-fixes — never commercial CLIs first. |

### D-series decisions

| ID | Decision |
| --- | --- |
| **D1** | Preserve fail-closed ExecutionGateway + ToolIntent + Approval + RBAC + Trading Guardian + audit/evidence/certification. No recommendation may weaken these. |
| **D2** | Authoritative multi-agent path remains M48 contracts + Orchestrator/RunLifecycle + gateway_exec; platform multi-agent path remains PlatformAgentRuntime → `execute_registered_tool`. Both must continue to bottom out at ExecutionGateway. |
| **D3** | AgentHarness (if implemented later) sits **under** agent_runtime / platform controller as untrusted driver; tool proposals only; never credentials, approvals, or finance. |
| **D4** | Do **not** assume AgentHarness is mandatory for all coding work — extending `AgentSessionAdapter` + binding it to ToolIntent proposals is an allowed alternative if a future ADR proves lower risk. |
| **D5** | QM remains conceptual reference only (ADR-QM). No import, deploy, or plugin integration. |
| **D6** | Policy floor composition and skill promotion remain **design-deferred** (not started in M386–M393). |
| **D7** | Production readiness claims remain evidence-gated; TG stays research/paper/sandbox only unless separately authorized. |

---

## Alternatives considered

| Option | Outcome |
| --- | --- |
| Declare architecture ready; implement AgentHarness immediately | **Rejected** — would deepen harness/session dualism with `engineering.AgentSessionAdapter` and risk dual tool paths |
| Full runtime rewrite / single mega-orchestrator | **Rejected** — high risk, duplicates work, weakens proven gateway spine |
| Merge ApplicationHarness into AgentHarness | **Rejected** — different trust and lifecycle models |
| Adopt QM core | **Rejected** — ADR-QM already `ADAPT_SELECTED_PATTERNS` only |
| Analysis-only without freeze list | **Rejected** — without freezes, next agents will keep adding parallel planes |
| **Map architecture, freeze expansion, consolidate by priority** | **Accepted** |

---

## Authority boundaries (reaffirmed)

| Authority | Sole owner (target) | Must not be owned by |
| --- | --- | --- |
| External side effects | ExecutionGateway (+ UniversalBoundary) | Agents, harnesses, skills, consoles |
| Tool authorization binding | Platform bindings + gateway permission/risk/approval | AgentHarness adapters |
| Approvals (human authorization lifecycle) | Platform Approval Center (canonical product) + gateway ApprovalGate (execution binding) | UI-only decisions; agent self-approve |
| RBAC / tenancy | Platform identity + PlatformStore | Domain modules inventing roles |
| Credentials | `saathi.credentials` leases | Harnesses, sandboxes as ambient secret owners |
| Trading veto | Trading Guardian | Research agents, harnesses |
| Model/provider policy | Inference governance (M21–M25) | Free-form SDK calls outside residual allowlist |
| Certification verdicts | Evidence-backed cert modules | Marketing docs alone |
| Multi-agent run lifecycle | `agent_runtime` (general) / Mission Runtime + PlatformAgentRuntime (platform missions) | Commercial CLI processes |

---

## Implementation status

**Analysis and design documentation only.**

This ADR does **not** authorize:

- AgentHarness types or FakeInMemoryHarness
- Policy floor composition or skill promotion implementation
- Production code, schema, CI, dependency, credential, or provider changes
- Deletion or migration of modules
- Weakening of any governance boundary
- Commercial CLI adapters (Claude Code / Codex / OpenCode) as SaathiOS control plane

---

## Consequences

### Positive

- Single authoritative map before more foundational abstractions
- Explicit freezes reduce shadow control planes
- AgentHarness necessity is **reconsidered** with source evidence, not assumed
- QM deferred work renumbered cleanly

### Negative / constraints

- Engineering/AgentHarness reconciliation still requires a follow-on design ADR before code
- Scheduler remains multi-runner (accepted short-term)
- Legacy domain runtimes remain until adapters or permanent isolation ADRs
- Documentation volume is high; discoverability depends on this ADR + main review

### Explicit non-consequences

- No production readiness claim
- No Trading Guardian live activation
- No claim that all residual risks are closed (M48.5 RR-01..RR-10 remain relevant)

---

## Supersession

- Supersedes sequencing that would start AgentHarness implementation immediately after M385 without consolidation.
- Does **not** supersede ADR-EXECUTIONGATEWAY, ToolIntent immutability, Trading Guardian policy, provider certification gates, or ADR-QM decision `ADAPT_SELECTED_PATTERNS`.
- Supersedes **milestone number assignment** of M386/M387 as policy floors / skill promotion (those topics deferred under new IDs later).
- Status line of ADR-EXECUTIONGATEWAY (“awaiting implementation”) was a **documentation contradiction**; **repaired in FM-C1** to `ACCEPTED_IMPLEMENTED` with source evidence.

---

## Future work (prioritized classes)

| Priority | Class | Examples |
| --- | --- | --- |
| **P0** | Authority / security defect | Any new bypass of gateway; dual approval that can self-approve; TG weaken; credential ambient exposure |
| **P1** | Architectural conflict | Engineering `AgentSessionAdapter` vs AgentHarness; dual multi-agent orchestrators without binding map; stale ADR status |
| **P2** | Duplication / maintainability | Multiple approval enums; multiple RunStores; scheduler sprawl; dual identity modules |
| **P3** | Terminology / docs | Glossary adoption; harness naming; maturity matrix discoverability |
| **P4** | Optional enhancement | Multi-harness commercial adapters (after cert); distributed leases |

Detailed milestone definitions live in the full review §M393.

---

## Compliance checklist (M386–M393)

| Criterion | Status |
| --- | --- |
| Current source inspected | ✓ |
| Documentation claims verified against source | ✓ |
| Major components inventoried | ✓ |
| Authority ownership mapped | ✓ |
| Duplicate control planes identified | ✓ |
| State sources of truth identified | ✓ |
| End-to-end paths traced | ✓ |
| Terminology conflicts documented | ✓ |
| Target architecture defined | ✓ |
| AgentHarness necessity reconsidered | ✓ |
| No production code changed | ✓ (docs only) |
| No implementation began | ✓ |
| No provider/credential connected | ✓ |
| No authority weakened | ✓ |
| Prioritized consolidation roadmap produced | ✓ |
| Next milestone justified by evidence | ✓ |

---

## References

- Full review: `docs/architecture/M386_M393_ARCHITECTURE_CONSOLIDATION_REVIEW.md`
- ADR-QM-MULTI-AGENT-RUNTIME
- ADR-AGENT-HARNESS-INTERFACE
- ADR-EXECUTIONGATEWAY-SPECIFICATION
- ADR-TOOLINTENT-IMMUTABLE-CONTRACT
- M48.* agent-runtime contracts and residual risk register
- docs/CAPABILITY_MATURITY_MATRIX.md
- Agents.md Trading Guardian invariants
