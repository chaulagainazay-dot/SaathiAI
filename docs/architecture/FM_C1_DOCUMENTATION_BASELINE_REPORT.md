# FM-C1 — Documentation Baseline Report

| Field | Value |
| --- | --- |
| **Milestone** | FM-C1 |
| **Date** | 2026-08-06 |
| **Terminal verdict** | `ARCHITECTURE_DOCUMENTATION_BASELINE_FROZEN_WITH_LIMITATIONS` |
| **Starting SHA** | `e9581f43848cf90283c7c4e1c0dbfbad65a4a531` |
| **Branch** | `milestone/m377-m385-qm-agent-harness-design` |
| **Mode** | Documentation only |

---

## Integrity statement

FM-C1:

- inspected current source for implementation-status claims;
- repaired stale ADR statuses (especially ExecutionGateway and ToolIntent);
- published authority index, terminology, freeze register, contradiction register;
- normalized roadmap next-pointers;
- **did not** change `saathi/`, tests, dependencies, CI, providers, credentials, or authority behavior;
- **did not** implement AgentHarness, FakeInMemoryHarness, AgentSessionAdapter changes, policy floors, or skill promotion;
- **did not** begin FM-C2.

---

## FM-C1.1 — Documentation inventory (architecture-related)

Classification is **exactly one** of: AUTHORITATIVE · SUPPORTING · HISTORICAL · SUPERSEDED · DRAFT · DESIGN_ONLY · REJECTED · STALE_REQUIRES_REPAIR.

### ADRs (`docs/adr/`)

| Path | Title | Claimed status (pre) | Actual source status | Origin | Class (post FM-C1) | Contradictions | Action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION.md | Architecture consolidation | ACCEPTED analysis | Docs-only map | M386–M393 | **AUTHORITATIVE** / DESIGN_ONLY for impl | Renumbering noted | Status normalized |
| ADR-EXECUTIONGATEWAY-SPECIFICATION.md | ExecutionGateway | awaiting implementation | **Implemented** | Phase 3.2 / M17.22 | **AUTHORITATIVE** ACCEPTED_IMPLEMENTED | CX-01 | **Repaired** |
| ADR-TOOLINTENT-IMMUTABLE-CONTRACT.md | ToolIntent | ACCEPTED | Implemented frozen dataclass | Phase 3.1 | **AUTHORITATIVE** ACCEPTED_IMPLEMENTED | CX-02 | **Repaired** |
| ADR-AGENT-HARNESS-INTERFACE.md | AgentHarness | design-only | No code | M385 | **DESIGN_ONLY** AUTHORITATIVE design | CX-04 | Status normalized; blocked |
| ADR-QM-MULTI-AGENT-RUNTIME.md | QM gap | analysis accepted | No QM code | M377–M384 | **DESIGN_ONLY** AUTHORITATIVE decision | CX-03,15 | Status + renumber note |
| ADR-OPENJARVIS-LOCAL-RUNTIME.md | OpenJarvis | superseded in part | Not runtime | early | **SUPERSEDED** | CX-12 | Normalized |
| ADR-VIDEO-BACKEND-POLICY.md | Video backend policy | ACCEPTED | Policy under EG | Phase 3.2 | **SUPPORTING** ACCEPTED_WITH_LIMITATIONS | — | Normalized |
| ADR-OPENMONTAGE-SEPARATE-SERVICE.md | OpenMontage service | APPROVED Stage 1 | Isolation decision | M5.1 | **SUPPORTING** ACCEPTED_WITH_LIMITATIONS | — | Normalized |
| ADR-CLAUDE-VIDEO-ADAPTER.md | Video adapter | Proposed | Non-control-plane | 2026-07-10 | **DRAFT**/PROPOSED | — | Normalized |
| ADR-CLAUDEVIDEO-RENDERING.md | claude-video vs OM | discovery | Historical | 2026-07-10 | **DRAFT**/HISTORICAL | — | Normalized |

### Architecture package (`docs/architecture/`)

| Path | Class | Notes |
| --- | --- | --- |
| M386_M393_ARCHITECTURE_CONSOLIDATION_REVIEW.md | AUTHORITATIVE evidence | Full inventory/maps |
| ARCHITECTURE_AUTHORITY_INDEX.md | AUTHORITATIVE | FM-C1 |
| CANONICAL_TERMINOLOGY.md | AUTHORITATIVE | FM-C1 |
| ARCHITECTURE_FREEZE_REGISTER.md | AUTHORITATIVE | FM-C1 |
| FM_C1_CONTRADICTION_REGISTER.md | AUTHORITATIVE | FM-C1 |
| FM_C1_DOCUMENTATION_BASELINE_REPORT.md | AUTHORITATIVE | This report |
| README.md | AUTHORITATIVE index stub | Updated |

### Roadmap / maturity / loop

| Path | Class | Notes |
| --- | --- | --- |
| docs/AUTONOMOUS_ROADMAP.md | AUTHORITATIVE sequencing | FM-C1 top entry |
| docs/CAPABILITY_MATURITY_MATRIX.md | AUTHORITATIVE maturity labels | Not bulk-edited |
| docs/AUTONOMOUS_LOOP_STATE.json | SUPPORTING / HISTORICAL loop state | Not modified |
| Agents.md | AUTHORITATIVE agent ops + TG | Not modified |

### Agent runtime docs

| Path pattern | Class | Notes |
| --- | --- | --- |
| docs/agent-runtime/M48_* | SUPPORTING / residual AUTHORITATIVE for RR | Verify before “missing feature” claims |
| docs/agent-runtime/M385_* | DESIGN_ONLY | AgentHarness design |
| docs/agent-runtime/M377_M384_* | DESIGN_ONLY analysis | QM |

### Other large doc families (summary)

| Family | Class | Action |
| --- | --- | --- |
| docs/trading/*, TG evidence packs | SUPPORTING cert evidence | Prefer matrix max-state; no live claim |
| docs/M17_* harness series | HISTORICAL + SUPPORTING evidence | ApplicationHarness still active in source |
| docs/M21_*–M25_* inference | SUPPORTING | Source `saathi/inference` |
| docs/M28*, execution | SUPPORTING | Prefer ADR-EG after repair |
| Root TOOLINTENT_*, PHASE3* | HISTORICAL | May lag ADR repairs |
| Certification MD (M25, M30, M35…) | SUPPORTING | Package-scoped |

**Limitation:** Full line-by-line inventory of all ~400+ `docs/` files was not rewritten; high-authority set was repaired. Remaining historical bodies may contain stale future-tense language (registered as residual under CX-01/13/15).

---

## FM-C1.2 — Source-to-documentation verification

| Claim area | Source evidence | Doc disposition |
| --- | --- | --- |
| ExecutionGateway implemented | `class ExecutionGateway`, `submit`, `execute_registered_tool` | ACCEPTED_IMPLEMENTED |
| ToolIntent immutable | `@dataclass(frozen=True)` + deep copy | ACCEPTED_IMPLEMENTED; mutable-field claim repaired |
| UniversalBoundary | `class UniversalBoundary` submit pipeline | Documented under EG |
| ToolExecutionService | `saathi/tool_runtime/service.py` | Active under EG |
| Platform Approval Center | `platform/models.py` ApprovalRecord + API bodies | Active product plane |
| Credential leases | `saathi/credentials/*` | Active |
| Provider governance | `saathi/inference/*` | Active preferred plane |
| ModelRouter | `saathi/model_router.py` | Active helper |
| ModelGateway | `execution/orchestrators/model_gateway.py` | Exists; expansion frozen |
| agent_runtime | full package | Active canonical multi-agent |
| PlatformAgentRuntime | `platform/runtime.py` | Active platform path |
| mission_runtime | `platform/mission_runtime/` | Active platform missions |
| ApplicationHarness | `application_harness/` | Active argv tools |
| AgentSessionAdapter | `engineering/adapters/base.py` | Active engineering; FZ-02 |
| Trading Guardian posture | LIVE disabled; paper non-live only | Unchanged; frozen live |
| Schedulers | multiple modules | Fragmented; FZ-06 |
| Memory/evidence/audit/replay | distinct packages | Separation reaffirmed |
| Certification | multi-domain | Evidence-based culture |
| AgentHarness code | **absent** | DESIGN_ONLY |

---

## FM-C1.3 — ADR status repairs

See ADR files and authority index §4. Key repairs: EG, ToolIntent, status vocabulary normalization across `docs/adr/`.

---

## FM-C1.4–1.7 — Deliverables

| Artifact | Path |
| --- | --- |
| Terminology | CANONICAL_TERMINOLOGY.md |
| Authority index | ARCHITECTURE_AUTHORITY_INDEX.md |
| Freeze register | ARCHITECTURE_FREEZE_REGISTER.md |
| Contradiction register | FM_C1_CONTRADICTION_REGISTER.md |

---

## FM-C1.8 — Roadmap normalization

Top of `docs/AUTONOMOUS_ROADMAP.md` records FM-C1, points **next = FM-C2 only**, keeps AgentHarness / FakeInMemory / policy floors / skill promotion / commercial CLIs blocked.

---

## FM-C1.9 — Validation

See final report §14–17. No project-wide docs CI discovered; local checks performed.

---

## Limitations (honest)

1. Historical milestone prose not fully rewritten.
2. Source module renames not performed (forbidden).
3. Approval-plane schema correlation not designed (future).
4. Scheduler policy design not written (future).
5. FM-C2 not started.
6. Uncommitted docs tree may include prior M386–M393 files from same session.

---

## FM-C2 entry conditions

FM-C2 may start only when:

1. FM-C1 baseline accepted (this report).
2. Freezes FZ-01–FZ-17 recognized.
3. Scope limited to **design-only** AgentSessionAdapter ↔ AgentHarness relationship.
4. No implementation, no commercial CLIs, no EG/TG weaken.

---

## Explicit non-actions

No AgentHarness · no FakeInMemoryHarness · no AgentSessionAdapter code changes · no scheduler/approval/provider/credential/TG/runtime behavior changes · no production code · no providers/credentials connected.
