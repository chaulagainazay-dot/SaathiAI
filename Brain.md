# Brain.md — The Living Brain of SaathiAI

> **What this document is:** The canonical living constitution of SaathiAI. It summarizes platform state, vision, active priorities, architectural principles, core capabilities, known limitations, and strategic decisions. It is the first document any human or coding agent should read before working on SaathiAI. It does not replace the SES documents — it points to them.
>
> **What this document is not:** A technical specification. Engineering specs live in `docs/SES/v1.0/`. This document tells you *what we are building and why*. The SES documents tell you *exactly how*.
>
> **Update cadence:** After every significant decision, capability addition, or architectural change. Not after every commit.

---

## 1. The One-Line Vision

SaathiAI is an AI Operating System — a platform that runs autonomous departments, manages its own memory, produces multimedia content, learns from every outcome, and gets smarter with every day it operates.

---

## 2. What SaathiAI Is

SaathiAI is not a chatbot. It is not a content scheduler. It is not a collection of scripts.

It is a **platform** — one set of shared capabilities (agents, memory, voice, studio, discovery) deployed across multiple products, continuously improving itself through a learning loop that feeds production outcomes back into platform intelligence.

**The test for every new feature:** "Does this make SaathiAI a better AI Operating System, or does it solve only one product's problem?"

If the answer is the latter, the feature belongs in the product layer, not the platform. If the answer is the former, it belongs in the shared platform and all products benefit.

---

## 3. Current Platform State

**As of 2026-07-02**

| Layer | Status | Key Documents |
|-------|--------|--------------|
| Foundation & Standards | ✅ Complete (L3) | SES-000 series (A–F) |
| Architecture | ✅ Complete (L3) | SES-001 |
| Agent System | ✅ Complete (L3) | SES-002 |
| Memory & Knowledge Graph | ✅ Complete (L3) | SES-003 |
| Voice OS | ✅ Complete (L3) | SES-004 |
| Execution Infrastructure | ✅ Complete (L1) | Phase 3.1 ToolIntent, Phase 3.2 ExecutionGateway |
| AI Studio | 🔄 Writing | SES-005 |
| Autonomous Engineering | 📋 Queued | SES-006 |
| Mission Control | 📋 Queued | SES-007 |
| Business OS | 📋 Queued | SES-008 |
| Learning OS | 📋 Queued | SES-009 |
| Discovery Engine | 🔄 Writing | SES-010 |
| Security & Guardrails | 📋 Queued | SES-011 |
| Event Fabric | 📋 Queued | SES-012 |
| Compliance & Governance | 📋 Queued | SES-013 |
| Product Framework | 📋 Queued | SES-014 |
| Financial Intelligence | 📋 Queued | SES-015 |
| Research Engine | 📋 Queued | SES-016 |
| World Model | 📋 Queued | SES-017 |
| Dream Engine | 📋 Queued | SES-018 |
| Deployment & Infrastructure | 📋 Queued | SES-019 |
| Future Roadmap | 📋 Queued | SES-020 |

**Overall specification maturity: ~25%**
Foundation is solid. The creative engine (AI Studio), autonomous engineering, and mission control are the next milestone.

---

## 4. Products

SaathiAI is the platform. These are the products built on it.

| Product | Purpose | Status | Domain |
|---------|---------|--------|--------|
| **pielts** | Free IELTS practice with instant band scores | Live | pielts.web.app |
| **Mr. Yeti** | IELTS content creator (YouTube, TikTok, Instagram) | Building | @pieltsapp |
| **HCG POS** | Hospital canteen point-of-sale | Live | Internal |
| **HCG Live Signal** | Real-time canteen analytics (NOT crypto) | Live | Internal |
| **Travel Platform** | Nepal travel booking | Future | TBD |

Every product capability that can be generalized belongs in the platform. Every platform capability is available to all products.

---

## 5. Long-Term Vision

SaathiAI evolves through five phases:

**Phase 1 — Personal AI OS** *(now)*
One operator (Ajay). Five products. Core platform capabilities: agents, memory, voice, studio, discovery. The system learns from every interaction and improves over time.

**Phase 2 — Autonomous Company**
The platform runs multiple departments autonomously: Engineering, Studio, Discovery, Research, Finance. Human operator sets strategy and approves high-stakes decisions. Agents handle execution.

**Phase 3 — Multi-Operator Platform**
Multiple operators can run their own SaathiAI instance. Organization-level memory, permission management, federated knowledge (platform rules shared; personal data isolated).

**Phase 4 — AI-Native Business Infrastructure**
SaathiAI becomes the operating system for AI-native businesses — complete with financial intelligence, legal compliance, HR, customer intelligence, and strategic planning.

**Phase 5 — World Model + Dream Engine**
SaathiAI develops a persistent model of the external world (SES-017) and a Dream Engine (SES-018) that sets long-horizon goals, decomposes them into strategies, and autonomously pursues them across all departments.

---

## 6. Architectural Principles

These ten principles govern every engineering decision. When in doubt, ask which principle applies.

| # | Principle | The Rule |
|---|-----------|---------|
| AP-01 | Platform First | Build capabilities once. Reuse everywhere. No product-specific duplicates. |
| AP-02 | Provider Abstraction | All LLM, TTS, STT, storage calls through `app/providers/`. No direct SDK imports in business logic. |
| AP-03 | SQLite First | SQLite for all server-side state. Migration to Postgres is a config change, not a rewrite. |
| AP-04 | Agent Contracts | Every agent declares a 13-field contract before implementation. No contract = no agent. |
| AP-05 | Safety by Classification | Actions are L1–L5. Classification is deterministic. Approval gates are automatic. |
| AP-06 | Memory Promotes, Not Forgets | Nothing expires without the Promotion Engine evaluating it first. |
| AP-07 | Observe Before Acting | Context Assembly runs before every significant LLM call. Agents that skip memory skip intelligence. |
| AP-08 | Stream Everything | No pipeline stage waits for the previous stage to complete. Streaming end-to-end. |
| AP-09 | Measure Everything | Opik traces all LLM calls. OpenObserve receives all structured logs. No invisible operations. |
| AP-10 | Renderer Registry | Rendering backends, LLM providers, TTS providers — all are swappable without business logic changes. |
| AP-11 | Intelligence Decides, Automation Executes | The SaathiAI brain makes decisions; n8n, browser automation, shell, cloud deploys, and APIs are executors it invokes. Automation is never the brain. n8n executes workflows the brain designs — it does not decide. |
| AP-12 | Independently Testable | Every subsystem is unit-, integration-, load-, and failure-recovery-testable in isolation, and observable. Dependencies are injected, not imported. A subsystem that can't be tested alone isn't done. |
| AP-13 | Event-First Integration | Subsystems publish events and subscribe to events; they do not call each other directly unless absolutely necessary. Storage → Event Fabric → {Mission Control, Telegram, Analytics, Learning Engine}, not Storage → Mission Control. Keeps SaathiAI loosely coupled as it grows. |
| AP-14 | Autonomy Is Earned, Not Assumed | Every increase in autonomous capability must be matched by an equivalent increase in **governance, observability, and recoverability**. A new autonomous power ships only with its safety classification, its audit trail, and its undo/kill path. Capability without governance is a regression, not progress. |
| AP-15 | Knowledge Promotion Is Evidence-Driven, Not Occurrence-Driven | A pattern becomes knowledge because the *evidence* supports it (verification count, source diversity, time consistency, cross-product reach) — not merely because it was observed. Seeing something once, or a hundred times from one source, is not the same as knowing it. Every knowledge item carries its source trace and can answer *"why do I believe this?"* |
| AP-16 | Contradictory Knowledge Is Reviewed, Never Silently Replaced | When new knowledge conflicts with existing promoted knowledge, both are kept and linked, and the conflict is routed to review. History of reasoning is preserved; the platform never quietly overwrites what it used to believe. |
| AP-17 | Promotion Is Deterministic Before AI-Assisted | Candidate discovery, clustering, evidence scoring, and state transitions are deterministic and testable. An LLM may *assist* pattern extraction, but it never decides promotion, contradiction, or state. Governance stays predictable and auditable. |
| AP-18 | Learning Proposes, Never Mutates | The Learning Engine never edits a prompt, a config, or a core document directly. It produces explicit, governed **proposals** — a capability improvement, a knowledge candidate, a Brain/Business/Wisdom candidate, an ADR candidate, or an engineering task — that a human (or an approval policy) accepts. Improvement is measurable and reversible: prefer an A/B experiment to a silent replacement. |
| AP-19 | Relationships Are First-Class Knowledge | A fact is valuable; a relationship between facts is often more valuable. The Knowledge Graph models edges (ACHIEVED_BY, GOVERNS, CONTRIBUTES_TO, SUPERSEDES, DERIVED_FROM …) as first-class, so the platform can answer questions no isolated memory can — *which capabilities contribute to the financial goal, which ADR introduced this rule, why do we use Renderer Y now.* Departments query `KnowledgeGraph`, never a backend, never Cypher (AP-02). |
| AP-20 | Human Documents Are Derived Artifacts, Not Primary Storage | The authoritative source is Knowledge → Graph → Memory. `Brain.md`, `Business.md`, `Wisdom.md`, and the style guide are **published views** rendered from that source, never the database. The Publication Engine proposes structured updates a human approves; markdown renders only after approval. This prevents document drift forever. |

---

## 5b. Development Rule #1 — Documentation Stays One Milestone Ahead, Not One Year Ahead

The permanent working discipline for the Engineering Phase:

1. **Document what you're about to build** (the current milestone's slice).
2. **Build it.**
3. **Test it.**
4. **Update the documentation with what actually changed.**

Do NOT document entire future systems months before implementation — it produces specs that drift from reality. SES-001 through SES-020 exist as a roadmap; only the milestone in flight gets detailed, reconciled-against-code specification. Progress is judged by **running, tested code**, not by document count.

> **Phase marker (2026-07-02):** SaathiAI has moved from the **Architecture Phase** to the **Engineering Phase**. From here, `BUILD_STATUS.md` is the source of truth for what is real; SES docs describe intent.

> **Phase marker (2026-07-03):** M1 — AI OS Core **complete** (`v0.1.0-alpha`). Six production platform capabilities. Now in **M2 — Learning Runtime**: SaathiAI learns from completed work and measurably improves future decisions without manual prompt edits.

---

## 5c. Development Rule #2 — Ecosystem Integration Is Mandatory

> No new autonomous capability may be implemented unless it integrates with **Memory, Event Fabric, Mission Control, Runtime Governance, and the Learning Engine** where applicable.

Every future capability becomes part of the ecosystem rather than an isolated feature. A capability that publishes no events, records no memory, surfaces nothing to Mission Control, and bypasses governance is a silo — and silos violate AP-01 (Platform-First). Build capabilities once, reuse everywhere, improve continuously.

---

## 5d. Development Rule #3 — Integration Sprint After Every Milestone

The platform's biggest risk is no longer missing features — it's staying cohesive as it grows. After every major milestone, run an Integration Sprint that requires:

1. Every capability registered in the **Platform Capability Registry**.
2. Every new feature emits standardized events to the **Event Fabric**.
3. Every business activity creates **Episodes** for the Learning Runtime where appropriate.
4. Every major subsystem exposes **KPIs** to Mission Control.
5. Every significant architectural decision reflected in the governance docs (`Brain.md`, `Business.md`, `Wisdom.md`, Writing & Speaking Style).

This keeps SaathiAI a unified AI operating system, not a collection of disconnected modules.

---

## 6b. Memory Layer L6 — Platform Wisdom (the constitution)

Beyond the ordinary memory tiers (L0 working → L5 archive), SaathiAI has a **constitutional** layer that must never be buried among ordinary memories:

**L6 — Platform Wisdom** is not facts. It contains the rules that govern how SaathiAI thinks and acts:
- Engineering & Architecture Principles (AP-01 … AP-14)
- Development Rules (#1 docs-one-milestone-ahead, #2 ecosystem-integration)
- Business Principles, Coding Standards, Safety Policies, Decision Frameworks

Examples: *AP-11 — Intelligence Decides, Automation Executes.* *AP-14 — Autonomy is earned, not assumed.*

These are the constitutional rules. The Learning Engine and Brain Synchronizer (M2) may propose **candidates** for L6, but promotion into it is the highest-governance action — human-approved only, never auto-promoted. L6 is where `Brain.md`'s principles live; ordinary learned patterns live in L2 semantic memory and below.

---

## 7. Core Capabilities

### 🏷️ Platform Capabilities at v1.0 (build once, reuse everywhere, improve continuously)

**Storage Intelligence — v1.0 (2026-07-02)** — the first capability to reach this bar. Code-complete, tested (32 tests), reusable. `saathi/storage/`: Disk Watchdog, File Lifecycle Engine (the only sanctioned deleter; PERMANENT files never auto-deleted), Cleanup Engine (executes only Lifecycle-authorized deletions), Predictive Storage Engine (per-renderer temp profiles — LTX/Wan/Open-Sora/ComfyUI/FFmpeg), Telegram Alerts, Storage Database, `storage.*` event vocabulary on the Event Fabric.

> **Reuse mandate:** From v1.0 onward, **every** product — AI Studio, pielts, HCG POS, HCG Live Signal, and any new application — uses the Storage Intelligence service for file management. No product implements its own disk/cleanup/archival logic. This is AP-01 (Platform-First) and AP-10 (Capability Reuse) made real. (Live-wiring into the running process — 1-min watchdog poll + real Telegram + scheduled cleanup — is the remaining deploy step before it is "running in production.")

Current platform capabilities (from SES-000F Capability Registry):

**Agent Capabilities:** Multi-step reasoning, tool use, BMA Loop, parallel workflow execution, human approval gates

**Memory Capabilities:** 6-tier memory (L0–L5), Knowledge Graph (SQLite Phase 1-3, Neo4j Phase 4), Context Assembly, Memory Promotion Engine, Learning Engine

**Voice Capabilities:** 11-stage streaming pipeline, Conversation State Machine (11 states), Speaker Identity (enrollment + verification), Barge-In, Continuous Dialogue, SSML prosody, OmniVoice TTS

**Studio Capabilities (in spec):** AI Director, Storyboard Engine, Character Consistency (IC-LoRA), Renderer Registry, Audio Pipeline, QA Pipeline, Publishing Pipeline, Real-Time Streaming Avatar

**Discovery Capabilities (in spec):** Technical SEO, GEO (AI Search Optimization), Video SEO, Social Discovery, Keyword Intelligence, Backlink Authority, Competitor Intelligence, Reputation Monitoring, Pre-Publish Optimization

**Storage Intelligence Capabilities (in spec, SES-019A):** File Lifecycle Engine (policy-driven Permanent/Archive/Working/Temporary/Disposable classes), Predictive Storage Engine (pre-render safety check), Disk Watchdog (80/90/95% thresholds), Infrastructure Department service ownership, Event-driven storage via Event Fabric (SES-012)

---

## 8. Architecture Decisions (Key)

These are the major decisions already made. They are not up for re-evaluation without a formal ADR.

| Decision | What Was Decided | Why |
|----------|-----------------|-----|
| SQLite as primary database | SQLite with WAL mode for all server-side state | Zero-dependency, fast, local-first; migration to Postgres is a config change |
| Provider abstraction mandatory | No direct LLM SDK imports in business logic | Enables model swapping without rewriting agents |
| 7 LLM labels, not model names | `screening`, `standard`, `reasoning`, `multimodal`, `fast`, `long`, `private` | Agents specify intent, not model; routing is the platform's job |
| BMA Loop as the cognitive loop | 9-phase Observe→Understand→Reason→Plan→Execute→Verify→Evaluate→Learn→Update Memory | Gives agents introspective capability and a formal learning hook |
| SafetyHarness L1–L5 | Deterministic 5-level action classification | No guessing about approval requirements; audit trail automatic |
| Memory tiers L0–L5 | Working → Episodic → Semantic → KG → Org → Archive | Each tier has different lifecycle, access policy, and backend |
| AI Director above Storyboard | Script (what) → AI Director (how) → Storyboard (scenes) → Rendering | Separation makes each layer independently improvable |
| Renderer Registry (not hardcoded) | `BaseRenderer` interface; each backend is a registered adapter | New rendering engines (Runway, Kling, etc.) require only one new file |
| Discovery Engine (not "SEO") | SEO is one channel of seven; Discovery Engine covers all | Future-proof: AI Search, YouTube, Social, App Store all equally important |
| Dream Engine as highest-level orchestrator | Dream→Goals→Strategy→Projects→Departments→Agents→Execution→Evaluation→Learning→Dream | Long-horizon goal setting separated from tactical execution |
| Policy Engine for autonomy governance | Every autonomous action passes through policy evaluation | Broader than safety; governs spending, publishing, data access, deployment |
| Architecture freeze at SES-020 | After SES-020, new ideas become ADRs; existing SES documents evolve incrementally | Prevents constant redesign; lets engineering focus on delivery |
| Storage Intelligence as a formal platform capability | Infrastructure Department owns Disk Watchdog, Lifecycle Engine, Cleanup Engine, Archive Manager, Backup Manager, Cloud Sync, Predictive Storage Engine, Storage Analytics; no other department deletes files directly — they submit lifecycle requests | Prevents the Mac's SSD (or any render node) from filling silently; makes storage measurable and policy-driven instead of ad-hoc cleanup scripts |
| No render starts without a Predictive Storage Engine safety check | Studio Director estimates peak disk usage from the storyboard before entering production; postpones and triggers cleanup if unsafe | A render that runs out of disk mid-job wastes compute and produces nothing; better to know upfront |
| Storage events flow through the Event Fabric (SES-012), not direct calls | `render_started`, `upload_verified`, `cleanup_requested`, `storage_critical`, etc. are published/subscribed, not inline function calls between departments | Decouples "a render finished" from "someone must clean up" — keeps departments independent |
| ToolIntent as universal execution contract (Phase 3.1) | Every external action (connector call, LLM request, publish, email, webhook) is represented as an immutable ToolIntent | Enables idempotency, audit trail, approval workflow, and deterministic authorization; all connectors and agents go through ExecutionGateway, not direct API calls |
| ExecutionGateway as single execution authority (Phase 3.2) | All external actions route through one gateway that validates, authorizes, approves, manages credentials, executes, and records | Prevents authorization bypass; unifies audit trail; enables cost control and retry strategy |
| Immutable identity prevents authorization bypass (Phase 3.1) | Idempotency key computed once at creation; deep copy on input/output isolates external mutation; all approval decisions based on intent state at creation time | If authorization decisions could be invalidated by later mutation, the whole approval workflow becomes unreliable |

---

## 9. Active Priorities

**July 2026**

1. Complete SES-005 (AI Studio) — flagship document, unlocks Mr. Yeti autonomous production
2. Complete SES-010 (Discovery Engine) — ensures all published content is discoverable
3. Write SES-006 (Autonomous Engineering) — platform self-improvement capability
4. Write SES-007 (Mission Control) — single operational interface for all products
5. Write SES-011 (Security & Guardrails) — Policy Engine, prompt injection protection
6. Write SES-012 (Event Fabric) — NATS event bus, the nervous system of the platform

---

## 10. Known Limitations

These are honest gaps. They exist because the platform is being built incrementally.

| Limitation | Impact | Planned Fix |
|-----------|--------|------------|
| Nepali STT accuracy ~85% WER | Voice OS in Nepali is usable but imperfect | Fine-tune Whisper medium on Nepali corpus (Phase 3) |
| Knowledge Graph is SQLite adjacency tables (not Neo4j) | Graph queries are slower; complex traversals limited | Neo4j integration in Phase 4 |
| No vector search yet (Qdrant Phase 4) | L2 Semantic Memory uses keyword search only | Qdrant + nomic-embed-text in Phase 4 |
| Rendering is manual (no IC-LoRA automation yet) | Mr. Yeti character consistency not automated | AI Studio implementation (SES-005) |
| No live Discovery Engine | SEO is manual; no automated crawl/audit | SES-010 implementation |
| Single operator only | No multi-user, no org isolation | Phase 3 |
| No Policy Engine | Autonomy governance relies on SafetyHarness only | SES-011 |
| No Event Fabric | Departments communicate via API, not event bus | SES-012 |

---

## 11. The Three-Layer Operating Model

```
Layer 1: SES Documents (stable engineering specifications)
    docs/SES/v1.0/SES-001 through SES-020
    Authoritative. Versioned. Architecture decisions live here.
    Changes through formal ADR process after SES-020 freeze.

Layer 2: Living Operational Documents (evolve with the project)
    Brain.md        — Platform state, vision, priorities, decisions
    Business.md     — Business strategy, revenue model, market position
    Writing and Speaking Style.md — Communication rules for all agents and content

Layer 3: Codebase (the implementation)
    ~/SaathiAI/
    Implements what SES documents specify.
    Guided by Brain.md for priority and direction.
```

A coding agent should:
1. Read `Brain.md` to understand context and current priorities
2. Read the relevant SES document for the specific subsystem
3. Implement according to the spec, not according to assumptions

---

## 12. World Model Architecture (SES-017 preview)

The World Model is the shared external intelligence layer. Instead of every department running its own external data collection:

```
Internet
    │
    ▼
Research Engine (SES-016) — collects, crawls, synthesizes
    │
    ▼
World Model (SES-017) — shared, deduplicated external knowledge
    │
    ▼
Knowledge Graph (SES-003) — integrates world knowledge with platform knowledge
    │
    ▼
All Departments — access world knowledge without duplicate collection
```

**Benefits:** One source of truth for external world. No duplicate crawling. Consistent context across all agents. Cheaper inference (fewer external API calls).

---

## 13. Dream Engine Architecture (SES-018 preview)

The Dream Engine is the highest-level orchestrator — the part of SaathiAI that sets long-horizon goals and decomposes them into executable strategies.

```
Dream (long-horizon goal: "Mr. Yeti reaches 100k subscribers")
    │
    ▼
Goals (monthly subscriber growth target, content volume target)
    │
    ▼
Strategy (content mix, posting frequency, collaboration plan)
    │
    ▼
Projects (this month's 30 videos, SEO optimization sprint, channel audit)
    │
    ▼
Departments (AI Studio, Discovery Engine, Analytics)
    │
    ▼
Agents (execute production, publish, monitor)
    │
    ▼
Execution (videos published, analytics collected)
    │
    ▼
Evaluation (did we hit the goal? what worked?)
    │
    ▼
Learning (update strategy, update prompts, update KPIs)
    │
    ▼
Next Dream (revised or new long-horizon goal)
```

The Dream Engine is what transforms SaathiAI from a task executor into a long-term collaborator.

---

## 14. Policy Engine (SES-011 preview)

Every autonomous action passes through policy evaluation before execution. This is broader than the SafetyHarness (which classifies actions by safety level). The Policy Engine evaluates:

- **Authorization:** Is this agent permitted to take this action at all?
- **Budget:** Does this action exceed the spending limit?
- **Approval:** Does this context require a human to sign off?
- **Rate:** Has this action type been executed too many times recently?
- **Data access:** Is this agent allowed to access this data scope?
- **Time:** Is it appropriate to execute this at this time of day?

The Policy Engine is the governance layer that makes autonomous operation trustworthy. Without it, autonomous agents are powerful but ungoverned. With it, autonomy is bounded, auditable, and correctable.

---

## 15. SES Document Index

| Document | Title | Maturity |
|----------|-------|---------|
| [SES-000](docs/SES/v1.0/SES-000_MASTER_ROADMAP.md) | Master Roadmap | L3 |
| [SES-000A](docs/SES/v1.0/SES-000A_DOCUMENT_STANDARD.md) | Document Standard | L3 |
| [SES-000B](docs/SES/v1.0/SES-000B_GLOSSARY.md) | Glossary | L1 |
| [SES-000C](docs/SES/v1.0/SES-000C_ARCHITECTURE_PRINCIPLES.md) | Architecture Principles | L1 |
| [SES-000D](docs/SES/v1.0/SES-000D_CODING_STANDARD.md) | Coding Standard | L1 |
| [SES-000E](docs/SES/v1.0/SES-000E_REPOSITORY_INDEX.md) | Repository Index | L1 |
| [SES-000F](docs/SES/v1.0/SES-000F_CAPABILITY_REGISTRY.md) | Capability Registry | L1 |
| [SES-001](docs/SES/v1.0/SES-001_ARCHITECTURE.md) | Architecture | L3 |
| [SES-002](docs/SES/v1.0/SES-002_AGENT_SYSTEM.md) | Agent System | L3 |
| [SES-003](docs/SES/v1.0/SES-003_MEMORY_AND_KNOWLEDGE_GRAPH.md) | Memory & Knowledge Graph | L3 |
| [SES-004](docs/SES/v1.0/SES-004_VOICE_OS.md) | Voice OS | L3 |
| [SES-005](docs/SES/v1.0/SES-005_AI_STUDIO.md) | AI Studio | 🔄 Writing |
| [SES-006](docs/SES/v1.0/SES-006_AUTONOMOUS_ENGINEERING.md) | Autonomous Engineering | 📋 Queued |
| [SES-007](docs/SES/v1.0/SES-007_MISSION_CONTROL.md) | Mission Control | 📋 Queued |
| [SES-008](docs/SES/v1.0/SES-008_BUSINESS_OS.md) | Business OS | 📋 Queued |
| [SES-009](docs/SES/v1.0/SES-009_LEARNING_OS.md) | Learning OS | 📋 Queued |
| [SES-010](docs/SES/v1.0/SES-010_DISCOVERY_ENGINE.md) | Discovery Engine | 🔄 Writing |
| [SES-011](docs/SES/v1.0/SES-011_SECURITY_GUARDRAILS.md) | Security & Guardrails | 📋 Queued |
| [SES-012](docs/SES/v1.0/SES-012_EVENT_FABRIC.md) | Event Fabric | 📋 Queued |
| [SES-013](docs/SES/v1.0/SES-013_COMPLIANCE_GOVERNANCE.md) | Compliance & Governance | 📋 Queued |
| [SES-014](docs/SES/v1.0/SES-014_PRODUCT_FRAMEWORK.md) | Product Framework | 📋 Queued |
| [SES-015](docs/SES/v1.0/SES-015_FINANCIAL_INTELLIGENCE.md) | Financial Intelligence | 📋 Queued |
| [SES-016](docs/SES/v1.0/SES-016_RESEARCH_ENGINE.md) | Research Engine | 📋 Queued |
| [SES-017](docs/SES/v1.0/SES-017_WORLD_MODEL.md) | World Model | 📋 Queued |
| [SES-018](docs/SES/v1.0/SES-018_DREAM_ENGINE.md) | Dream Engine | 📋 Queued |
| [SES-019](docs/SES/v1.0/SES-019_DEPLOYMENT_INFRASTRUCTURE.md) | Deployment & Infrastructure | 📋 Queued |
| [SES-020](docs/SES/v1.0/SES-020_FUTURE_ROADMAP.md) | Future Roadmap | 📋 Queued |

---

## 16. Recently Accepted Decisions

| Date | Decision | Rationale |
|------|----------|----------|
| 2026-07-02 | AI Director placed above Storyboard Engine | Script (what) / AI Director (how) / Storyboard (scenes) separation makes each layer independently improvable |
| 2026-07-02 | SES-010 renamed to Discovery Engine | "SEO" is one channel of seven; platform must cover AI Search, YouTube, Social, App Store equally |
| 2026-07-02 | Renderer Registry mandated for AI Studio | New rendering engines require only one new adapter file; no changes to Studio Director or pipeline logic |
| 2026-07-02 | Dream Engine as highest-level orchestrator | Long-horizon goal setting must be separated from tactical department execution |
| 2026-07-02 | Policy Engine added as SES-011 | Autonomy governance broader than safety; covers spending, publishing, data access, timing, rate |
| 2026-07-02 | World Model as shared external intelligence layer | One source of truth for external world; prevents duplicate crawling across departments |
| 2026-07-02 | Architecture freeze planned after SES-020 | After SES-020, all new ideas become ADRs; SES documents evolve incrementally |
| 2026-07-02 | Brain.md + Business.md + Writing Style.md as three living documents | Operational guidance lives here; SES documents are stable engineering specs |

---

## M5 — Investment Intelligence Department (v0.4.0-finance, 2026-07-03)

The financial specialization of the AI-OS: a governed decision-support platform where every
recommendation is explainable, every execution audited, every outcome preserved, and every
completed trade feeds learning. Built as a chain of deterministic engines (AP-17), all
side-effects injected (AP-12): Research Department (+ Research Confidence Framework) →
Opportunity Intelligence (+ Opportunity Memory) → Investment Pipeline (InvestmentCase) →
Portfolio Intelligence (+ Impact Simulator + Capital Reserve Engine) → Execution Layer
(immutable Intent, broker-independent connectors, paper-first, idempotent recovery) → Trade
Journal (append-only financial Platform Memory) → Investment Learning Runtime (proposes into
M2, never mutates) → Financial Mission Control (consumer) → Executive Financial Integration
(+ Cross-Department Priority Engine). Certified in `docs/M5_INTEGRATION_SPRINT.md`.

**M5 principle (AP-14 applied to capital):** no trade bypasses human approval or the Governance
Engine — financial actions are L4, and an ExecutionIntent can only be born from an approved,
executable InvestmentCase. Learning proposes; the human disposes.

---

*Last updated: 2026-07-03*
*Next update: After the v0.4.0-finance stabilization window (paper-trading + live business data)*

---

## Auto-Repair Loop (reliability spine)

SaathiOS repairs its own recoverable failures through `saathi/repair/` — a
production-safe pipeline: **Failure → Evidence → Classify → Root cause → Policy
→ Rollback point → Minimal patch → Focused tests → Full suite → Verify runtime
→ Local commit → Report**. See `AUTO_REPAIR_LOOP.md`.

- **Failure classification** — 21 categories (IMPORT_ERROR … EXECUTION_BYPASS …
  CONNECTOR_AUTH_ERROR … EVENT_BUS_ERROR … UNKNOWN); each carries confidence,
  subsystem, and suspected files.
- **Evidence model** — read-only capture. Env vars recorded as *presence*
  booleans, never values. All free-text redacted for secrets on ingest.
- **Repair policy** — Level 0 diagnose-only, Level 1 safe-local (edit + local
  commit), Level 2 approval-required, Level 3 prohibited (push/deploy/credential/
  send/trade/history-rewrite — never autonomous).
- **Verification ladder** — focused → subsystem → full suite → server import →
  route-count smoke. Success = target recovered AND no new regressions AND route
  count intact AND secret scan clean; otherwise auto-rollback.
- **Stopping conditions** — secret risk, unsafe git state, external
  credential/payment/deploy needed, 2 failed attempts per fingerprint, low
  confidence, unknown root cause. Never loops infinitely.
- **Rollback** — pre-repair HEAD recorded per incident; unrelated dirty work
  blocks auto-repair; restore via `saathi repair rollback <id>`.
- **Anti-hallucination** — task-execution repairs verify the execution *trace*,
  not the final text. No tool call → "the task was not executed." Missing
  credentials → "connector is not connected or authenticated." Never fabricates.

### Reliability extensions (Repair 3)

- **Critical regression manifest** (`saathi/repair/critical_checks.json`): 11
  blocking checks — event bus API/emission/stream, studio tracking, intake
  tagging, BFF contract + dream pct + regression pack, execution gateway +
  finance trade layer, repair self-tests — plus server import + route count.
- **Quality records**: baseline (`data/repair_baseline.json`, updated only
  after full-ladder success), known-failure registry
  (`data/known_failures.json`, detects new/recurring/resolved/returned/
  signature-changed), journal (`artifacts/repairs/`, secret-redacted JSON+MD).
- **Bounded loop modes**: inspect / diagnose / repair --test / loop
  --max-cycles (1..10, fingerprint no-progress detection) / report / critical.
  Exit codes 0-7 documented in AUTO_REPAIR_RUNBOOK.md.
- **Canonical dream progress**: `financial_mission_control.dream_progress_pct`
  — the single source of truth; percentage semantics (1.0 == 1% of
  DREAM_TARGET), defensive against zero/negative/NaN inputs.
- **CEO Home DI rule**: explicit `Signals` drive the payload (tests/previews);
  no Signals → real recorded Mission revenue. Regression from f80a37f fixed.

---

## M8 — Saathi Chat (central intelligence interface)

`saathi/chat/` — every other subsystem integrates through this chat.

**Architecture (data flow):**
```
user text → ChatEngine.send()
  → memory retrieval (related conversations + mission knowledge, automatic)
  → attachment RAG (chunk scoring → context + citations)
  → project context (project_ref resources)
  → ToolIntent → ExecutionGateway (validate/authorize/risk/approve/queue)
  → ChatLLMAdapter → Model Router (Anthropic/OpenAI/DeepSeek/Qwen/GLM/
    Groq/Gemini/Ollama — provider-extensible)
  → sanitize → evidence → persist (message + execution + citations)
  → rolling summary + auto-checkpoint every 8 messages
```
Models are never called directly by the API layer; every inference and tool
call is a gateway-audited ToolIntent with an execution record.

**Store** (`data/chat.db`, 11 normalized tables): conversation, message
(edit chains = version history), attachment, memory_link, citation,
execution, tool_invocation, summary, project_ref, agent_run, checkpoint.
Soft delete + restore — no conversation is ever hard-lost; checkpoints are
restorable full snapshots.

**API** `/api/v1/chat/*` (auth inherited): conversations CRUD/search/
restore, messages (send + SSE streaming, edit-and-resend, regenerate,
versions, citations), attachments, tools, checkpoints/restore, agents.

**Agents** (Layer 9): planner/researcher/coder/reviewer/architect/writer/ceo
— role-prompted runs recorded in agent_run; delegate() chains agents with
provenance (delegated_by).

**Honesty invariants:** LLM failure → "The task was not executed — …" (never
fabricated replies); unknown tools → status=blocked with reason (never faked
results).

**UI:** `saathi-os/app/chat` — sidebar (search/pinned/recent/folders/project),
streamed messages, agent selector, execution timeline + memory links +
agent runs + checkpoints panel.

**Critical manifest:** `chat.saathi_chat_m8` → tests/test_chat.py (blocking).

---

## M9 — Unified Memory Engine

`saathi/memory/engine/` — production memory behind the M8 ChatEngine's stable
interface. Reuses `platform.py` scopes/retention + `evidence.find_contradictions`.

**Lifecycle:** observe → extract (bounded, deterministic) → classify → store →
embed → link → retrieve → rank → reinforce → decay → forget.

**Retrieval:** hybrid = semantic (local numpy embeddings, real cosine,
vectorized matmul) + keyword + recency + importance + confidence + context +
feedback, one canonical ranking function with per-result explanation and MMR
diversity. Namespace list = the privacy firewall (retrieval only reads listed
scopes). Graph expansion (1-hop relations) complements vectors.

**Embeddings:** provider-neutral. Default = `LocalDeterministicEmbedder`
(numpy, dependency-free, deterministic) → semantic works offline. ST / Ollama
adapters share the contract and `available()`-gate; cloud adapters are the
extension point. `embedding_version` tracked; `reindex` is bounded + resumable.

**Memory types:** working, conversation, episodic, semantic, procedural, user,
business, project, agent, document. Schema: 14 normalized tables in
`data/memory.db` (memory_item/version/source/embedding/relation/access/
feedback/policy/namespace/summary/conflict/tombstone, retrieval_run/result).

**Lifecycle guarantees:** delete = tombstone + embedding drop → never
retrievable (restorable re-embeds). Conflicts (opposing polarity, same topic)
flagged, never auto-resolved. Supersede preserves history. Decay spares pinned
+ semantic/platform_wisdom retention. Stored content is untrusted data with
provenance — never executed (prompt-injection safe).

**Chat integration:** `MemoryEngine.retrieve_for_chat` feeds ChatEngine before
model execution (scope-checked, thresholded, token-budgeted, with citations);
user turns are observed back into memory (bounded extraction). ExecutionGateway
enforcement unchanged; no direct model calls.

**API** `/api/v1/memory/*` (auth inherited): list/search/create/item/update/
pin/feedback/delete/restore/conflicts/reindex/runs/health.
**CLI** `python -m saathi.memory.cli`: inspect/search/health/reindex/conflicts/
stats/export/decay (read-only cmds don't mutate; exit codes 0/1/2).
**Manifest:** `memory.engine_m9` (blocking).

---

## M10 — Multi-Agent Runtime

`saathi/agent_runtime/` — bounded, observable, gateway-only agent orchestration.

**Flow:** objective → strategy → task DAG → memory-scoped agent turns (via
ExecutionGateway) → verify (evidence) → independent review → bounded retry →
checkpoint → outcome. No agent calls a provider/connector/terminal/FS directly.

**8 agents** (config-driven, versioned): planner, researcher, architect,
builder, reviewer, executor, writer, ceo. Each has allowed/denied tools, memory
scopes, risk ceiling, budgets, delegation permissions, output contract.
Planner + CEO cannot self-approve.

**State machine** (durable, validated): created→planning→awaiting_approval→
approved→queued→running→delegated→verifying→reviewing→completed + paused/
cancelled/timed_out/blocked/failed/rolled_back/partially_completed. Illegal
transitions raise; terminal states have no exits.

**Risk model** 0–4 (maps to gateway L0–L4): read-only / local-reversible /
local-mutation / external-side-effect / high-impact. Risk ≥ local-mutation
needs explicit user approval; high-impact stays manual-only. Denied at
tool-check when over an agent's ceiling.

**Delegation:** narrowing-only permissions (child ⊆ parent tools/scopes/risk);
limits on depth (3), children/agent (4), total agents (12), repeats. No loops.

**Budgets:** tokens/cost/wall/steps/tool-calls/retries/delegation-depth/
artifacts/parallel — runs stop safely + report partial. **Retry:** transient +
progress + budget only; no-progress fingerprint stops.

**Memory:** M9 scoped retrieval per agent/task (never widens). **Gateway:**
every action a ToolIntent; a static regression test scans runtime for direct
provider/subprocess bypasses. **Events:** `agentrun.*` on the fabric bus.

**Schema:** 19 tables in `data/agent_runtime.db`. **Strategies:** single/build/
architect_build/document/business/broad_research (config-driven).
**API** `/api/v1/agents/*`, **CLI** `python -m saathi.agent_runtime.cli`,
**Chat:** `ChatEngine.start_orchestration` (multi-agent activates only when
selected/justified; simple asks stay single-turn). **Manifest:**
`agents.runtime_m10` (blocking).

---

## M12 — Voice OS

`saathi/voice_os/` — real-time speech interface for Saathi Chat. Voice never
calls a model provider or tool directly: every final transcript resolves
through `saathi.chat.engine.ChatEngine` (Solo) or `ChatEngine.start_orchestration`
(Team, the M10 Orchestrator), and voice approvals resolve through the same
`Orchestrator.approve()` ownership/expiry-checked path the M11 UI buttons use.

**Canonical flow:** microphone (browser) → VAD → STT → transcript pipeline
(dedupe/normalize/command-detect) → ChatEngine/Orchestrator → response
segmentation → TTS → playback. Barge-in: new speech immediately cancels
`speechSynthesis` playback client-side and records `stop_latency_ms` server-side.

**Session/turn model:** 14-state session state machine (created…completed/
cancelled/failed, validated transitions, illegal raises); voice_turn persists
transcript/response/execution/agent_run linkage. Raw audio is **never**
retained by default — `retain_raw_audio` is opt-in per session.

**Providers (provider-neutral, real-first):**
- STT: `DeterministicSTT` (test) · `FasterWhisperSTT` (**real**, installed,
  verified via a genuine TTS→STT round trip in tests) · `BrowserPassthroughSTT`
  (carries the browser's own real webkitSpeechRecognition output).
- TTS: `DeterministicTTS` (test) · `SayTTS` (**real**, macOS `say`, verified
  producing real audio bytes) · `BrowserSpeechSynthesisTTS` (marker — real
  synthesis happens client-side via `window.speechSynthesis`).
- Cloud adapters (OpenAI/ElevenLabs-compatible) are contract-ready extension
  points only — no keys in this environment, never claimed as tested.

**Commands:** bounded exact-phrase recognition (stop/pause/resume/repeat/
cancel/approve/deny/mute/mode-switch/…) — confidence-gated, never fuzzy;
approval commands still require the full ownership+expiry check, never a
keyword shortcut.

**Segmentation:** strips markdown/code/tables/citations/URLs before TTS;
splits on sentence/clause boundaries within a bounded length.

**API** `/api/v1/voice/*` (HTTP/SSE — no WebSocket; STT/TTS happen
client-side so no bidirectional low-latency channel is needed). **CLI**
`python -m saathi.voice_os.cli` (labels real-adapter vs deterministic-fallback
test results explicitly). **UI:** collapsible `VoiceControl` in Saathi Chat
using real `SpeechRecognition`/`SpeechSynthesis` — optional, never replaces
text chat.

**Backend freshness (Phase 24):** `GET /api/v1/system/version` — the M11 live
smoke test discovered a days-old backend process serving pre-M8 code; this
endpoint exposes commit/process-start/route-count so staleness is detectable.

**Manifest:** `voice.voice_os_m12` (blocking).

**Honesty note:** live browser microphone permission and a real spoken
utterance were not exercised in this sandboxed session (no `getUserMedia`
grant available to the automation). Real local adapters (faster_whisper,
macOS `say`) and the full deterministic pipeline were genuinely tested.

---

## M13 — AI Studio (end-to-end content workflows)

`saathi/studio_os/` — idea → reviewed, exportable, optionally-published content.
Reuses M10 (orchestration + approvals), M9 (memory/learning), M12 (voice/TTS),
ExecutionGateway (all provider/FFmpeg calls), the event bus. NOT a new
orchestrator/memory/approval/agent system.

**Flow:** objective → M10-orchestrated planning/scripting (real ChatEngine) →
real local media stages → versioned checksummed artifacts → review → approval →
export/publish. Every stage persists an artifact + status + cost.

**Project state machine:** 15 states (draft…completed/partially_completed/
cancelled/failed/archived, validated transitions, illegal raises).

**Artifacts:** 25 types, versioned (new supersedes prior latest of same
type+stage), checksummed; media binaries on disk (storage_uri), never in SQLite.

**Real local providers (verified):** Pillow images (genuine PNG), FFmpeg
render/probe/thumbnail/mux (gateway-routed, argument-safe list form — no shell
injection), macOS `say` narration (shared with M12). Cloud image/video
(Flux/Veo/HeyGen/ComfyUI) + real publishing = honest deterministic/dry-run;
capability matrix marks them configured:false, never "tested."

**Disk safety (core, not optional — user has hit disk exhaustion):** real
`shutil.disk_usage` preflight HARD-GATES every generation (refuses if free space
would drop below a 5GB margin or breach the project quota); checksum dedup,
partial/temp cleanup, path confinement (traversal rejected).

**Budget:** dry-run estimate + hard stop — a generation is refused before it
exceeds the project budget; local providers cost $0.

**Publishing:** approval-gated + verified-artifact-gated; idempotency keys stop
duplicates; `live=True` with no configured connector is refused honestly (no
fabricated receipt/URL); dry-run records status='dry_run' with no fake URL.

**Studio agents:** 7 roles (content_strategist/script_writer/storyboard_agent/
visual_director/seo_agent/brand_reviewer/publisher) registered INTO the M10
registry; publisher is EXTERNAL_SIDE_EFFECT + requires_approval.

**API** `/api/v1/studio-os/*` (distinct from the legacy /api/v1/studio
dashboard). **CLI** `python -m saathi.studio_os.cli` (render-smoke does a REAL
ffmpeg render; read-only cmds never mutate; publish enforces approval).
**Manifest:** `studio.studio_os_m13` (blocking).

**Honesty note:** the full short-video workflow was verified end-to-end
producing 11 real artifacts (real PIL image → real FFmpeg video → real say
narration → real muxed final_video → real extracted thumbnail, all ffprobe-
verified). Cloud media generation, real social publishing, and live browser
Studio UX were NOT verified (no keys/accounts/getUserMedia in this environment).

---

## M13.5 — Production Hardening (ops toolkit)

`saathi/ops/` — operations toolkit, read-only by default, mutation explicit:
- **identity.py**: safe runtime identity (commit/branch/api_version/schema_versions/
  route_manifest); `compatible()` lets the frontend detect a stale/incompatible
  backend (the M11 bug). `/api/v1/system/version` (+ `/version/compat`).
- **config_check.py**: env validation, secrets shown only as PRESENT/ABSENT,
  flags a tracked firebase key.
- **storage.py**: global disk report + thresholds (ok/warning/block/critical);
  preview-first cleanup (never deletes user artifacts).
- **db_integrity.py**: real `PRAGMA integrity_check` + fk_check on all 5 app dbs.
- **backup.py**: REAL checksum-verified backup (dbs + redacted config manifest;
  excludes secrets/media); restore into an ISOLATED dir (refuses live-dir
  overwrite + path-traversal archives); verify re-checks checksums + integrity +
  schema. **Real drill passed**: 5 dbs, all checksums match, all integrity ok.
- **release_gate.py**: `release-check` with stable exit codes 0-12; runs
  storage/config/db/**backup+restore**/strong-credential-secret-scan gates.
- **process.py**: backend listener + stale-process detection (running commit vs
  working tree); never kills unknown processes.
- **cli.py** / `python -m saathi.ops`: status/health/config-check/storage/cleanup/
  db-check/backup/restore/verify-restore/release-check/identity.

**Frontend**: AI Studio workspace (`/studio-os`) on the real /api/v1/studio-os/*
(no mock data); STUDIO_OS dock entry. Version-mismatch compat endpoint.

**Manifest**: `ops.hardening_m13_5` (blocking). Docs: readiness matrix +
release gates + security + DR + deploy + perf + ops runbook.

**Verdict: STAGING READY.** Env-blocked (honest): authenticated browser
workflows, live approval click, cloud media providers, real social publishing,
real staging deploy + live rollback. Everything locally verifiable is
implemented, tested, and (backup/restore) recovery-proven.

---

## M14 — CEO OS (unified operating + decision layer)

`saathi/ceo/` — orchestrates existing systems; NOT a separate AI brain, NOT a
new dashboard fork. Reuses M10 (mission execution + approvals), M9 (memory),
M13 (studio), ExecutionGateway, event bus, and the verified BFF/`dream_pct`
contracts (both now in the critical manifest so they can't regress).

**Source-of-truth decisions:** canonical entities live in `data/ceo_os.db`
(business/goal/kpi/metric_observation/decision/risk/opportunity/budget/
financial_entry/review/alert/brief). Missions are NOT a new entity — a CEO
mission IS an M10 orchestration run.

**Evidence requirement:** every value carries an `EvidenceTier` — observed /
calculated / inferred / forecast / recommended / unavailable. A recommendation
is never presented as a verified fact. A KPI with no observation returns
UNAVAILABLE, never a guessed value.

**Deterministic priority rules:** `priority.score` is a transparent weighted
sum with a per-factor explanation (`PRIORITY_WEIGHTS`). An LLM may only
recommend weight adjustments; deterministic logic controls execution.

**KPI percentage convention:** reuses the verified `dream_progress_pct`
(1.0 == 1% of DREAM_TARGET); regular KPIs use value/target*100. Ratio-vs-pct
regression guarded by tests.

**Financial semantics:** actual / estimated / forecast / unknown are SEPARATE
states — an estimate is never summed into actual revenue. Personal vs business
scopes are explicitly labeled.

**Authorization boundaries:** CEO Agent (M10 `ceo`, READ_ONLY, can_self_approve
=False) only PROPOSES decisions (status=proposed); protected states
(approve/reject/implement) require an authenticated user via the API — an agent
has no user identity to reach them. No CEO-direct execution; no self-approval;
no fabricated metrics.

**API** `/api/v1/ceo/*` (routes 304→305). **CLI** `python -m saathi.ceo.cli`
(read-only lists + brief; mission/decision/budget mutations are API-only,
authz-gated). **Frontend**: CEO OS workspace `/ceo` (real API, evidence tiers
visible, no mock data). **Manifest**: `ceo.ceo_os_m14` + `bff.contract_pack`.

## M15 — Universal Connector Platform + Spec-Driven Governance

`saathi/connectors/platform/`: one governed integration layer. Canonical
connector/tool/result models with a non-downgradable risk floor (0–4),
provider-neutral capability catalog, registry seeding 11 connectors / 28 tools
with **honest integration-status labels** (live-tested | deterministic-adapter-
tested | contract-ready | environment-blocked). Credential **references** only
(metadata; secrets resolved in-process, redacted from errors). Durable store
`data/connectors.db` (accounts, cred refs, executions with unique idempotency,
approvals bound to the exact-action input hash, webhook dedup, sync checkpoints,
rate buckets, failures).

**ExecutionEngine is the sole execution boundary** — every action routes through
the ExecutionGateway (governance pass recorded as `provenance.gateway_ref`),
then connector-native enforcement: lifecycle gate (only executable states),
approval binding (risk ≥ 3, single-use, expiring; risk 4 manual-only),
idempotency replay, rate limits, failure classification, and the hard rule that
**uncertain / non-idempotent failures never auto-retry**. Health platform
(no creds → environment-blocked, never faked green), webhook platform
(HMAC + freshness + replay defense), resumable checkpointed sync, and MCP tools
ingested as **untrusted** connectors (risk clamped UP, gateway-routed, cannot
self-approve).

**Objective B — governance.** Native offline Spec Kit wrapper (NOT vendored;
gstack is a SaaS starter, not Spec Kit): `.specify/memory/constitution.md` (v1.0,
8 articles), `.specify/presets/saathios/`, `saathi/specs/{traceability,cli}.py`
(`python -m saathi.specs.cli version|health|init|validate|converge`),
`specs/m15-universal-connectors/` (spec/plan/tasks/traceability.json/convergence).
Convergence gate: every requirement mapped to an artifact + a passing test.
**M15 verdict: CONVERGED (19/19), DEVELOPMENT READY** — core spine test-green;
live authenticated connector workflows unverified (no creds), connector API + UI
remain. Ops: `connectors.db` in backup/db-integrity APP_DBS, schema `connectors:m15`,
critical manifest → m15. Tests: `tests/test_m15_connectors.py`, `tests/test_m15_specs.py`.
