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
| 8 | [`../adr/ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP.md`](../adr/ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP.md) | FM-C2 relationship ADR |
| 9 | [`FM_C2_AGENT_SESSION_ADAPTER_HARNESS_RECONCILIATION.md`](./FM_C2_AGENT_SESSION_ADAPTER_HARNESS_RECONCILIATION.md) | FM-C2 full design |

## Core domain ADRs

| Topic | Path | Status |
| --- | --- | --- |
| ExecutionGateway | [`../adr/ADR-EXECUTIONGATEWAY-SPECIFICATION.md`](../adr/ADR-EXECUTIONGATEWAY-SPECIFICATION.md) | **ACCEPTED_IMPLEMENTED** |
| ToolIntent | [`../adr/ADR-TOOLINTENT-IMMUTABLE-CONTRACT.md`](../adr/ADR-TOOLINTENT-IMMUTABLE-CONTRACT.md) | **ACCEPTED_IMPLEMENTED** |
| AgentHarness (design) | [`../adr/ADR-AGENT-HARNESS-INTERFACE.md`](../adr/ADR-AGENT-HARNESS-INTERFACE.md) | **ACCEPTED_DESIGN_ONLY** — impl FZ-01 / FM-I1 gated |
| Session adapter relationship | [`../adr/ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP.md`](../adr/ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP.md) | **ACCEPTED_DESIGN_ONLY** (FM-C2 Alternative F) |
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
2. **AgentHarness is not implemented**; FM-C2 decided plane separation — implementation still **FZ-01** / **FM-I1** gated.
3. **AgentSessionAdapter** is engineering-only; not the platform multi-turn contract.
4. Prefer this directory + authority index over stale milestone headers.
5. Historical reports are evidence, not status truth.
6. **Next implementation (if authorized):** FM-I1 FakeInMemoryHarness only — not commercial CLIs.

**Do not** implement AgentHarness, FakeInMemoryHarness, commercial CLI adapters, policy floors, or skill promotion without separate owner authorization.
