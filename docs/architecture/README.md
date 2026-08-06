# SaathiOS Architecture Documentation

**Baseline:** FM-C1 documentation freeze (2026-08-06)
**Verdict:** `ARCHITECTURE_DOCUMENTATION_BASELINE_FROZEN_WITH_LIMITATIONS`

## Start here (authoritative)

| Order | Document | Purpose |
| --- | --- | --- |
| 1 | [`ARCHITECTURE_AUTHORITY_INDEX.md`](./ARCHITECTURE_AUTHORITY_INDEX.md) | What is authoritative vs historical |
| 2 | [`../adr/ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION.md`](../adr/ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION.md) | Top-level architecture ADR |
| 3 | [`M386_M393_ARCHITECTURE_CONSOLIDATION_REVIEW.md`](./M386_M393_ARCHITECTURE_CONSOLIDATION_REVIEW.md) | Full inventory, maps, scorecard |
| 4 | [`CANONICAL_TERMINOLOGY.md`](./CANONICAL_TERMINOLOGY.md) | Glossary |
| 5 | [`ARCHITECTURE_FREEZE_REGISTER.md`](./ARCHITECTURE_FREEZE_REGISTER.md) | What must not expand |
| 6 | [`FM_C1_CONTRADICTION_REGISTER.md`](./FM_C1_CONTRADICTION_REGISTER.md) | Known contradictions |
| 7 | [`FM_C1_DOCUMENTATION_BASELINE_REPORT.md`](./FM_C1_DOCUMENTATION_BASELINE_REPORT.md) | FM-C1 closeout |

## Core domain ADRs

| Topic | Path | Status |
| --- | --- | --- |
| ExecutionGateway | [`../adr/ADR-EXECUTIONGATEWAY-SPECIFICATION.md`](../adr/ADR-EXECUTIONGATEWAY-SPECIFICATION.md) | **ACCEPTED_IMPLEMENTED** |
| ToolIntent | [`../adr/ADR-TOOLINTENT-IMMUTABLE-CONTRACT.md`](../adr/ADR-TOOLINTENT-IMMUTABLE-CONTRACT.md) | **ACCEPTED_IMPLEMENTED** |
| AgentHarness (design) | [`../adr/ADR-AGENT-HARNESS-INTERFACE.md`](../adr/ADR-AGENT-HARNESS-INTERFACE.md) | **ACCEPTED_DESIGN_ONLY** — blocked pending FM-C2 |
| QM reference | [`../adr/ADR-QM-MULTI-AGENT-RUNTIME.md`](../adr/ADR-QM-MULTI-AGENT-RUNTIME.md) | **ACCEPTED_DESIGN_ONLY** — no import |

## Related (not control-plane supersession)

| Topic | Path |
| --- | --- |
| Agent runtime contracts | `docs/agent-runtime/` |
| Capability maturity | `docs/CAPABILITY_MATURITY_MATRIX.md` |
| Roadmap | `docs/AUTONOMOUS_ROADMAP.md` |
| Agent ops / TG rules | `Agents.md` |

## Rules

1. **ExecutionGateway** is the sole external side-effect path.
2. **AgentHarness is not implemented** and must not be started before FM-C2.
3. Prefer this directory + authority index over stale milestone headers.
4. Historical reports are evidence, not status truth.
5. **Next design milestone: FM-C2 only** (AgentSessionAdapter ↔ AgentHarness relationship). Do not auto-start implementation.

**Do not** implement AgentHarness, FakeInMemoryHarness, commercial CLI adapters, policy floors, or skill promotion from this folder alone.
