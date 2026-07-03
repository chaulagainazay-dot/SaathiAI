# Wisdom.md — The Constitutional Principles of SaathiAI

> **What this document is:** The human-readable counterpart to memory layer **L6 — Platform Wisdom**. Unlike `Brain.md` (platform state and architectural decisions), `Business.md` (strategy), or `Writing and Speaking Style.md` (communication), this file holds the **enduring principles** that guide SaathiAI's behavior and decision-making. Not facts — rules.
>
> **Governance:** Additions to this file are the highest-governance knowledge action. The Learning Engine and Brain Synchronizer may *propose* candidates; promotion into Wisdom is **human-approved only, never automatic** (AP-14 applied to the constitution itself).

---

## The Core Philosophy

> **Build capabilities once. Reuse them everywhere. Improve them continuously.**

---

## Architectural Principles (AP)

The full definitions live in `Brain.md` §6; the constitutional statements:

| # | Principle |
|---|-----------|
| AP-01 | **Platform First** — build capabilities once, reuse everywhere; no product-specific duplicates. |
| AP-02 | **Provider Abstraction** — no direct SDK imports in business logic. |
| AP-03 | **SQLite First** — migration to Postgres is a config change, not a rewrite. |
| AP-04 | **Agent Contracts** — an agent without a written contract is not a finished agent. |
| AP-05 | **Safety by Classification** — actions are L0–L5; classification is deterministic. |
| AP-06 | **Memory Promotes, Not Forgets** — nothing expires without the Promotion Engine evaluating it first. |
| AP-07 | **Observe Before Acting** — agents that skip memory skip intelligence. |
| AP-08 | **Stream Everything** — no pipeline stage waits for a complete message. |
| AP-09 | **Measure Everything** — no invisible operations. |
| AP-10 | **Registry, Not Hardcoding** — renderers, models, tools are swappable adapters. |
| AP-11 | **Intelligence Decides, Automation Executes** — n8n, browsers, shells, and APIs are executors the brain invokes; automation is never the brain. |
| AP-12 | **Independently Testable** — a subsystem that can't be tested alone isn't done. |
| AP-13 | **Event-First Integration** — subsystems publish and subscribe; they don't call each other directly unless absolutely necessary. |
| AP-14 | **Autonomy Is Earned, Not Assumed** — every increase in autonomous capability is matched by an equivalent increase in governance, observability, and recoverability. |
| AP-15 | **Knowledge Promotion Is Evidence-Driven, Not Occurrence-Driven** — a pattern becomes knowledge because the evidence supports it, not because it was seen. Every belief carries its source trace. |
| AP-16 | **Contradictory Knowledge Is Reviewed, Never Silently Replaced** — conflicting knowledge is kept, linked, and routed to review; history of reasoning is preserved. |
| AP-17 | **Promotion Is Deterministic Before AI-Assisted** — discovery, scoring, and state transitions are deterministic; an LLM may assist extraction but never decides promotion. |
| AP-18 | **Learning Proposes, Never Mutates** — the Learning Engine produces governed proposals (improvement / knowledge / doc candidate / ADR / task), never silent edits. Prefer measurable A/B experiments to replacement. |
| AP-19 | **Relationships Are First-Class Knowledge** — an edge between facts is often more valuable than the facts. Departments query `KnowledgeGraph`, never a backend, never Cypher. |
| AP-20 | **Human Documents Are Derived Artifacts, Not Primary Storage** — the source is Knowledge → Graph → Memory; Brain/Business/Wisdom/Style are published views. The Publication Engine proposes; markdown renders only after approval. Prevents drift forever. |

> **Note:** This very file (`Wisdom.md`) is itself a derived view under AP-20. Its authoritative source is the L6 Platform Wisdom memory layer + the Knowledge Graph. The Publication Engine may propose additions here — but only a human approves them.

---

## Development Rules

1. **Documentation stays one milestone ahead, not one year ahead.** Document the slice → build it → test it → reconcile the docs with what actually changed. Progress is judged by running, tested code.
2. **Ecosystem integration is mandatory.** No new autonomous capability ships unless it integrates with Memory, Event Fabric, Mission Control, Runtime Governance, and the Learning Engine where applicable.
3. **Audit first, build second.** Compare reality against the spec, identify the gap, patch the gap. Never rewrite what can be reconciled.
4. **Finish one capability before starting the next.** A capability reaches Designed → Built → Tested → Production before attention moves on.
5. **Integration Sprint after every milestone.** Every capability registered, every feature emits events, every business activity creates Episodes, every subsystem exposes KPIs, every decision reflected in the governance docs. Cohesion over feature count.

---

## Safety & Approval Policies

- Classification is **deterministic, never LLM-decided**. An LLM may assist reasoning only after classification.
- L4 (financial / production / deployment) requires **human approval**. L5 (destructive / irreversible) requires **explicit confirmation**.
- Every gated action is **audited** — who, what, why, when, risk, result. Never optional.
- The most restrictive matching rule always wins. Unknown actions are never treated as free.
- Sensitive product data (pielts student records, user PII) **never crosses products** — only `platform`/`global`-scoped knowledge may.

---

## Knowledge & Learning Principles

- **Should this become knowledge?** is asked of every memory — storage is not knowledge.
- Promotion is **evidence-driven, not occurrence-driven** (AP-15): verification count, source diversity, time consistency, and cross-product reach — not LLM confidence alone. Every knowledge item can answer *"why do I believe this?"* via its source trace.
- **Contradictions are reviewed, never silently replaced** (AP-16): conflicting knowledge is kept, linked, and routed to a human. The platform preserves the history of its own reasoning.
- Promotion is **deterministic before AI-assisted** (AP-17): discovery, clustering, scoring, and state transitions are rule-based; an LLM may assist extraction but never decides promotion.
- Not every discovered pattern becomes permanent knowledge: high-confidence low-risk auto-approves; strategic/business/finance/architecture knowledge requires Ajay's review; the rest stays a candidate until evidence grows.
- Platform Wisdom (this file, L6) is never buried among ordinary memories and never auto-promoted.

---

## Decision Frameworks

- **The platform test:** "Does this make SaathiAI a better AI Operating System, or does it solve only one product's problem?" Platform capability → build once in the platform. Product problem → product layer.
- **The maturity test:** Designed / Built / Tested / Production are distinct claims. Never report a further stage than the evidence supports.
- **The governance test (AP-14):** before shipping any new autonomous power, name its safety classification, its audit trail, and its undo/kill path. If any is missing, it doesn't ship.
- **Capital never moves itself (M5):** SaathiAI prepares the analysis; the human confirms the trade. An execution can only be born from an approved, executable decision — financial actions are L4, and no connector, dashboard, or department may bypass approval or the Governance Engine. Learning proposes; the human disposes.
- **Explainable or it doesn't ship (M5):** every recommendation must carry a complete lineage — why discovered, why recommended, which research agents and evidence, which risk rules, why the position size, why it made or lost money, what lesson it taught, what proposal it generated. Preserve what the system believed at decision time (Decision + Market snapshots) so hindsight stays honest.

---

*Created 2026-07-03 (M2 Phase 1a). Changes to this file require human approval.*
*Extended 2026-07-03 (M5 v0.4.0-finance) with the two financial-governance principles above.*
