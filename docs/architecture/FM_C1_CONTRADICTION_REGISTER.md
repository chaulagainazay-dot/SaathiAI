# FM-C1 Contradiction Register

**Status:** AUTHORITATIVE for known doc/source contradictions
**Date:** 2026-08-06
**Inspected SHA:** `e9581f43848cf90283c7c4e1c0dbfbad65a4a531`
**Severity:** P0 authority/security · P1 implementation-status · P2 ownership/architecture · P3 terminology/discoverability

---

## Register

### CX-01 — ExecutionGateway “awaiting implementation”

| Field | Value |
| --- | --- |
| **ID** | CX-01 |
| **Documents involved** | `docs/adr/ADR-EXECUTIONGATEWAY-SPECIFICATION.md` (pre-repair header + footer); M386–M393 review; consolidation ADR note |
| **Source evidence** | `saathi/execution/gateway.py` `class ExecutionGateway` + `submit`; `universal.py` `UniversalBoundary.submit`; `execute_registered_tool` |
| **Severity** | **P1** |
| **Corrected interpretation** | ExecutionGateway is **ACCEPTED_IMPLEMENTED**. Sole external-action authority remains in force. |
| **Files repaired** | ADR-EXECUTIONGATEWAY-SPECIFICATION.md (header + footer status); consolidation ADR supersession note; this register |
| **Unresolved remainder** | Some historical Phase 3.2 prose inside ADR body still reads as future-tense planning (archival weeks 1–8). Treat as historical narrative, not status. |

### CX-02 — ToolIntent “mutable fields for approval”

| Field | Value |
| --- | --- |
| **ID** | CX-02 |
| **Documents involved** | ADR-TOOLINTENT-IMMUTABLE-CONTRACT (pre-repair immutability + rationale paragraphs) |
| **Source evidence** | `@dataclass(frozen=True)` on `ToolIntent`; deep-copy parameters/metadata; no in-place approval rewrite API |
| **Severity** | **P1** (authority-adjacent: mutation would break approval binding) |
| **Corrected interpretation** | All ToolIntent fields immutable after construction. Approval state lives in **separate** records. Action changes require a new ToolIntent. |
| **Files repaired** | ADR-TOOLINTENT-IMMUTABLE-CONTRACT.md |
| **Unresolved remainder** | Older root `TOOLINTENT_SPEC.md` / PHASE3 reports may still echo mutable wording — classified HISTORICAL; not bulk-edited |

### CX-03 — Milestone number collision (M386/M387)

| Field | Value |
| --- | --- |
| **ID** | CX-03 |
| **Documents involved** | ADR-QM future table; ADR-AGENT-HARNESS future table; M385 “do not start M386”; M386–M393 consolidation |
| **Source evidence** | N/A (docs only); roadmap now records renumber |
| **Severity** | **P2** |
| **Corrected interpretation** | M386–M393 = architecture consolidation. Policy floors / skill promotion **deferred** under new future IDs (FZ-16/FZ-17). |
| **Files repaired** | ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION; ADR-QM header fields; roadmap; freeze register |
| **Unresolved remainder** | Embedded future tables inside QM/M385 design docs still list old numbers — **annotated as superseded numbering** via ADR headers; full prose rewrite of every mention deferred (P3) |

### CX-04 — AgentHarness “approved” misread as implemented

| Field | Value |
| --- | --- |
| **ID** | CX-04 |
| **Documents involved** | ADR-AGENT-HARNESS; M385 design; roadmap |
| **Source evidence** | `rg class AgentHarness|FakeInMemoryHarness saathi` → no matches |
| **Severity** | **P1** |
| **Corrected interpretation** | ACCEPTED_DESIGN_ONLY; blocked by FZ-01 until FM-C2 + impl authorization |
| **Files repaired** | ADR-AGENT-HARNESS status normalization; freeze register; authority index |
| **Unresolved remainder** | None material |

### CX-05 — AgentHarness vs AgentSessionAdapter dual design

| Field | Value |
| --- | --- |
| **ID** | CX-05 |
| **Documents involved** | M385 design; engineering adapters; consolidation review; **FM-C2 ADR + reconciliation** |
| **Source evidence** | `saathi/engineering/adapters/base.py` `AgentSessionAdapter`; no AgentHarness class |
| **Severity** | **P2** (design dualism) |
| **Corrected interpretation** | **FM-C2 decision: ALTERNATIVE F.** Plane separation — AgentHarness = future platform multi-turn driver; AgentSessionAdapter = engineering-only process session ABC. Neither wraps/implements the other in v1. Platform path uses HarnessSessionController; eng uses EngineeringOrchestrator. ToolIntent construction never on either driver. |
| **Files repaired** | `ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP.md`; `FM_C2_AGENT_SESSION_ADAPTER_HARNESS_RECONCILIATION.md`; freeze FZ-01/02 amended; authority index; roadmap |
| **Unresolved remainder** | **Closed for relationship ambiguity.** Residual: eng Claude CLI unobserved FS risk (documented; FZ-02/07); implementation still frozen (FZ-01). |
| **Disposition** | **CLOSED (relationship)** — residual security risk tracked under freezes, not open dual-design ambiguity |

### CX-06 — ModelGateway vs inference ownership

| Field | Value |
| --- | --- |
| **ID** | CX-06 |
| **Documents involved** | Older exec orchestrator docs; consolidation review |
| **Source evidence** | `ModelGateway` in `execution/orchestrators/model_gateway.py`; primary plane `saathi/inference/` |
| **Severity** | **P2** |
| **Corrected interpretation** | Prefer inference governance + ModelRouter. ModelGateway expansion **frozen** (FZ-05). |
| **Files repaired** | freeze register; authority index; terminology |
| **Unresolved remainder** | Residual callers may remain; no code migration in FM-C1 |

### CX-07 — Multiple approval type systems

| Field | Value |
| --- | --- |
| **ID** | CX-07 |
| **Documents involved** | platform models; agent contracts; credentials m35; TG approvals; execution state |
| **Source evidence** | Multiple `Approval*` classes across packages (grep inventory) |
| **Severity** | **P2** |
| **Corrected interpretation** | Intentional multi-plane records if correlated; human decide must not be agent self-approve; product SoT = platform Approval Center; execution bind = EG |
| **Files repaired** | terminology; authority index; freeze does not merge schemas |
| **Unresolved remainder** | **Correlation design** remains future (not FM-C2 scope unless included); open |

### CX-08 — missions/ vs mission_runtime naming

| Field | Value |
| --- | --- |
| **ID** | CX-08 |
| **Documents involved** | Various mission docs; consolidation |
| **Source evidence** | `saathi/missions/` vs `saathi/platform/mission_runtime/` |
| **Severity** | **P3** |
| **Corrected interpretation** | ProductMission vs PlatformMission (glossary) |
| **Files repaired** | CANONICAL_TERMINOLOGY; authority index |
| **Unresolved remainder** | Source module names unchanged (by design) |

### CX-09 — Scheduler ownership fragmented

| Field | Value |
| --- | --- |
| **ID** | CX-09 |
| **Documents involved** | consolidation review; ops docs |
| **Source evidence** | `saathi/scheduler.py`; `application_harness/scheduler*.py`; `platform/tg/research_orchestrator/scheduler.py` |
| **Severity** | **P2** |
| **Corrected interpretation** | Multi-runner accepted short-term; **new** schedulers frozen (FZ-06) |
| **Files repaired** | freeze register; authority index |
| **Unresolved remainder** | No unified policy design yet |

### CX-10 — Dual chat agent_run + RunStore

| Field | Value |
| --- | --- |
| **ID** | CX-10 |
| **Documents involved** | M48.5 RR-04; consolidation |
| **Source evidence** | M48 residual register; chat store bridge |
| **Severity** | **P2** |
| **Corrected interpretation** | Accepted residual; expansion frozen (FZ-13) |
| **Files repaired** | freeze register |
| **Unresolved remainder** | Migration not done |

### CX-11 — ADR status vocabulary inconsistent

| Field | Value |
| --- | --- |
| **ID** | CX-11 |
| **Documents involved** | All `docs/adr/*` pre-FM-C1 |
| **Source evidence** | Mixed: Proposed, APPROVED, SUPERSEDED IN PART, SPECIFICATION, ACCEPTED |
| **Severity** | **P3** |
| **Corrected interpretation** | Normalize to FM-C1 allowed set (see authority index §4) |
| **Files repaired** | All ADRs under docs/adr/ status headers touched in FM-C1 |
| **Unresolved remainder** | Body prose may still use older words |

### CX-12 — OpenJarvis as local runtime

| Field | Value |
| --- | --- |
| **ID** | CX-12 |
| **Documents involved** | ADR-OPENJARVIS |
| **Source evidence** | `saathi.inference` is native plane; OJ not control plane |
| **Severity** | **P2** (was already partially superseded) |
| **Corrected interpretation** | SUPERSEDED; inference owns local models |
| **Files repaired** | ADR-OPENJARVIS status normalization |
| **Unresolved remainder** | None |

### CX-13 — Production readiness overclaim risk

| Field | Value |
| --- | --- |
| **ID** | CX-13 |
| **Documents involved** | Older readiness reports; some cert language |
| **Source evidence** | CAPABILITY_MATURITY_MATRIX; `production_certified=false` patterns; TG max states |
| **Severity** | **P1** if misread as live-ready |
| **Corrected interpretation** | Prefer matrix + package cert + limitations; never claim live trading/prod without evidence |
| **Files repaired** | authority index guidance; freeze FZ-10/11 |
| **Unresolved remainder** | Historical docs remain HISTORICAL |

### CX-14 — skip_contract “low-level” vs production risk

| Field | Value |
| --- | --- |
| **ID** | CX-14 |
| **Documents involved** | M48.2 legacy boundary |
| **Source evidence** | `orchestrator.create_run(skip_contract=...)` pytest-only guard |
| **Severity** | **P1** if docs encourage production use |
| **Corrected interpretation** | Test-only; FZ-12 freezes production/HTTP skip |
| **Files repaired** | freeze register |
| **Unresolved remainder** | None if guards hold |

### CX-15 — QM future milestones vs consolidation sequencing

| Field | Value |
| --- | --- |
| **ID** | CX-15 |
| **Documents involved** | ADR-QM; M385; consolidation |
| **Source evidence** | Docs only |
| **Severity** | **P3** |
| **Corrected interpretation** | Pattern adaptation still valid; implementation sequencing gated by freezes + FM-C2 |
| **Files repaired** | ADR-QM status block; roadmap |
| **Unresolved remainder** | Inline “M386 policy floor” lines inside long QM design files may remain; treat as superseded numbering |

---

## Summary counts

| Severity | Count | Closed in FM-C1 | Open residual |
| --- | --- | --- | --- |
| P0 | 0 newly discovered active doc→weakening-claim | — | Live trading freezes prevent P0 drift |
| P1 | 5 (CX-01,02,04,13,14) | Repaired / clarified | Historical docs |
| P2 | 7 (CX-03,05,06,07,09,10,12) | CX-05 relationship **closed in FM-C2**; others partial | approval correlation, scheduler design, migrations; FZ residual |
| P3 | 3 (CX-08,11,15) | Glossary + ADR status | Source renames deferred |

**No P0 documentation claim that ExecutionGateway is optional or TG is live was left unrepaired in authoritative ADR set.**

---

## Honest open items (not hidden)

1. ~~**CX-05** needs FM-C2.~~ **Closed** (FM-C2 Alternative F).
2. **CX-07** needs future approval-plane correlation design.
3. **CX-09** needs future scheduler policy design.
4. **CX-10** needs chat dual-record migration.
5. Historical milestone bodies not bulk-rewritten.
6. **FZ-01** implementation freeze remains until separately authorized **FM-I1**.
