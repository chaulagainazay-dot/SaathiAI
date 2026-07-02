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

---

## 5b. Development Rule #1 — Documentation Stays One Milestone Ahead, Not One Year Ahead

The permanent working discipline for the Engineering Phase:

1. **Document what you're about to build** (the current milestone's slice).
2. **Build it.**
3. **Test it.**
4. **Update the documentation with what actually changed.**

Do NOT document entire future systems months before implementation — it produces specs that drift from reality. SES-001 through SES-020 exist as a roadmap; only the milestone in flight gets detailed, reconciled-against-code specification. Progress is judged by **running, tested code**, not by document count.

> **Phase marker (2026-07-02):** SaathiAI has moved from the **Architecture Phase** to the **Engineering Phase**. From here, `BUILD_STATUS.md` is the source of truth for what is real; SES docs describe intent.

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

*Last updated: 2026-07-02*
*Next update: After SES-005 and SES-010 complete*
