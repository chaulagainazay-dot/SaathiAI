```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : Master Roadmap
Document ID         : SES-000
Version             : 1.0.0
Status              : Approved
Maturity            : L3
Classification      : Internal
Owner               : SaathiAI Architecture Team
Primary Repository  : github.com/chaulagainazay/SaathiAI
Created             : 2026-07-02
Last Updated        : 2026-07-02
Next Review         : 2026-10-02
================================================================================
```

---

## Revision History

| Version | Date | Author | Summary of Changes |
|---------|------|--------|--------------------|
| 0.1.0 | 2026-07-02 | Ajay Chaulagain | Initial draft |
| 1.0.0 | 2026-07-02 | Ajay Chaulagain | Approved — three-part structure (Strategic Foundation / Platform Blueprint / Execution Roadmap) |

---

## Purpose

This document is the **strategic anchor** of the SaathiAI Engineering Specification.

It answers three questions that every other SES document assumes you already know:

1. **Why does SaathiAI exist?** — the mission, the problem it solves, the people it serves
2. **What is SaathiAI?** — the platform, its products, its capabilities, its position in the market
3. **Where is SaathiAI going?** — the development phases, the long-term vision, the milestones that signal progress

This document is not the place for technical specifications — those live in SES-001 through SES-020. This document is the place for decisions that shape everything else: why this platform exists, what principles govern it, what products it serves, and what success looks like.

A stakeholder who does not write code should be able to read this document and understand the entire SaathiAI vision. An AI coding agent who has never been briefed on the project should be able to read this document and understand what it is being asked to build and why.

---

## Audience

| Role | Required Sections | Notes |
|------|------------------|-------|
| All Engineers | All | Read before working on any SaathiAI subsystem |
| AI Coding Agents | All | Use as the primary context document for all implementation work |
| Product Architects | All | This document governs product scope and platform boundaries |
| Stakeholders / Decision-Makers | Part 1 (Strategic Foundation) | The technical detail lives in later SES documents |
| New Contributors | Read in full before reading any other SES document | Start here |

---

## Reading Order

```
SES-000A Document Standard   ← Must be read first
        │
        ▼
SES-000B Glossary             ← Defines all terms used here
        │
        ▼
SES-000C Architecture Principles  ← Governs all design decisions referenced here
        │
        ▼
SES-000 Master Roadmap        ← You are here
        │
        ▼
SES-000D Coding Standard      ← Read before writing any code
SES-000E Repository Index     ← Read before adding any dependency
SES-000F Capability Registry  ← Read before building any new capability
        │
        ▼
SES-001 Architecture          ← The technical specification
```

---

## Document Structure

| Part | Title | What It Answers |
|------|-------|----------------|
| Part 1 | Strategic Foundation | Why does SaathiAI exist? Who does it serve? What is the mission? |
| Part 2 | Platform Blueprint | What is SaathiAI? What are its products? How is it structured? |
| Part 3 | Execution Roadmap | How is SaathiAI built? What are the phases? What does success look like? |
| Appendix A | Document Maturity Dashboard | Current L1–L5 status of every SES document |
| Appendix B | Foundation Document Index | Quick-reference guide to the SES-000 series |

---

# Part 1 — Strategic Foundation

---

## 1.1 The Problem SaathiAI Solves

SaathiAI was built to solve a specific problem that many solo operators and small teams face: **they have multiple products that need intelligent, autonomous behavior, but they cannot afford to build and maintain separate AI infrastructure for each product.**

Most AI-powered products are built as silos. A voice feature built for one product cannot be reused by another. A memory system written for one agent cannot store context from a different product. A research pipeline built for one use case cannot serve another. The result is duplicated code, fragmented intelligence, and a platform that is more expensive and harder to maintain with every new product added.

SaathiAI was designed as the inverse of this pattern. Instead of building AI capabilities inside each product, SaathiAI builds AI capabilities once at the platform level and makes them available to every product. Voice, memory, research, scheduling, content creation, evaluation — these are platform capabilities, not product features. A new product added to SaathiAI gets access to all of them on day one.

The consequence: every product makes SaathiAI smarter. When pielts evaluates a student's speaking response, that interaction enters the shared memory system. When HCG Live Signal monitors canteen operations, those patterns are available to the analytics engine used by all products. When Mr. Yeti generates a piece of content, the research that informed it is available to every other product that needs similar context.

This is the core hypothesis of SaathiAI: **intelligence compounds when it is shared.**

---

## 1.2 Mission

> **SaathiAI exists to make high-quality AI infrastructure accessible to small operators who are building multiple products, by providing a shared platform where every new product benefits from all previous work.**

This mission has three components:

**"High-quality AI infrastructure"** — not toy demos. Production-grade memory, reasoning, voice, research, and content systems that work reliably at the scale of a real business.

**"Accessible to small operators"** — the current architecture runs on a single Mac, costs near-zero for LLM inference (via Groq and local Ollama), uses SQLite instead of cloud databases, and avoids subscription services where self-hosted alternatives are sufficient. The operational complexity must be manageable by a single person.

**"Every new product benefits from all previous work"** — this is the Platform-First Design Principle (SES-000A Part 7) expressed as a mission outcome. It is the test by which every architectural decision is judged.

---

## 1.3 Who SaathiAI Serves

SaathiAI currently serves one operator: Ajay Chaulagain, Kathmandu.

The five products running on SaathiAI serve three distinct end-user populations:

| End User | Product | What They Need |
|----------|---------|----------------|
| IELTS students worldwide | pielts (pielts.web.app) | Free, instant IELTS practice with band score feedback |
| HCGMS canteen staff and management | HCG POS, HCG Live Signal | Real-time canteen operations and monitoring |
| IELTS content consumers | Mr. Yeti / Baadar | IELTS tips, practice questions, motivation on YouTube/TikTok/Instagram |
| Future travel customers | Travel Platform | AI-assisted travel planning (Phase 3) |

The platform's scale today (single server, SQLite, one operator) is appropriate to the current user volume. The architecture is designed to scale when the user volume requires it — not before.

---

## 1.4 Core Commitments

These are the commitments that SaathiAI makes to every product built on it. They are not aspirational — they are design requirements.

**1. Every capability built for one product is available to all products.**
If voice is built for pielts, it is the same voice system that serves HCG POS, Travel, and Mr. Yeti. A new product inherits all capabilities on day one.

**2. The platform knows about all products simultaneously.**
Memory is shared. A context from a pielts session is available to the scheduler that generates Mr. Yeti content. The research that informs HCG Live Signal is the same research engine that supports the Travel Platform. Intelligence compounds because it is never siloed.

**3. The operational cost is bounded.**
New products do not require new servers, new databases, or new monitoring systems. They run on the same server, the same database engine, and the same scheduler. This is enforced by the OS architecture — applications run on the OS, they do not bring their own OS.

**4. Every decision is documented.**
The reason SaathiAI uses Groq instead of OpenAI, SQLite instead of Postgres, APScheduler instead of Celery — these decisions are in ADRs that outlive any conversation about them. When circumstances change, the rationale is available to inform whether the original decision still holds.

---

## 1.5 Vision

> **SaathiAI will become the most capable AI operating system that a single operator in South Asia can run — one that turns local products into world-class experiences through shared intelligence, and demonstrates that the advantages of large AI teams are accessible to determined individuals.**

This vision is grounded, not generic. It names a specific context (a single operator in South Asia), a specific mechanism (shared intelligence across products), and a specific proof point (turning local products into world-class experiences).

The long-term ambition is that SaathiAI evolves from a private platform into a reusable framework — so that other operators in Nepal, India, and the broader region can run their own version of SaathiAI for their own constellation of products.

That evolution is Phase 5 and beyond. The work of Phase 1 and 2 is to prove the model works for one operator first.

---

# Part 2 — Platform Blueprint

---

## 2.1 SaathiAI as an Operating System

SaathiAI is structured as an operating system. This framing is deliberate, not metaphorical.

An operating system provides:
- A kernel (shared infrastructure all applications rely on)
- A process model (how applications execute)
- Memory management (how state is stored and retrieved)
- A file system (where assets live)
- A scheduler (when tasks run)
- An I/O system (how data moves in and out)

SaathiAI provides the AI equivalent of each:

| OS Concept | SaathiAI Equivalent | SES Document |
|------------|-------------------|-------------|
| Kernel | BMA Agent Loop | SES-002 |
| Process Model | Tool Registry + Task Execution | SES-002 |
| Memory | Three-Tier Memory (Working / Episodic / Semantic) | SES-003 |
| File System | Asset Manager + R2 Storage | SES-006 |
| Scheduler | APScheduler (25+ autonomous jobs) | SES-010 |
| I/O System | FastAPI endpoints + Telegram + Voice | SES-007, SES-004 |

Applications (products) run on this OS. They call OS-level APIs. They do not embed their own memory systems, schedulers, or agent loops.

---

## 2.2 The Layer Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        APPLICATION LAYER                             │
│                                                                      │
│   pielts         HCG POS       HCG Live Signal   Travel   Mr. Yeti  │
│   (IELTS app)    (Canteen POS)  (Monitoring)     (Travel)  (Content) │
└──────────────────────────────────────────────────────────────────────┘
                              │ calls
┌──────────────────────────────────────────────────────────────────────┐
│                       PLATFORM API LAYER                             │
│                                                                      │
│   FastAPI :8765  ·  REST + WebSocket  ·  Pydantic models             │
│   /api/v1/<subsystem>/<action>                                       │
└──────────────────────────────────────────────────────────────────────┘
                              │ routes
┌──────────────────────────────────────────────────────────────────────┐
│                        OS SERVICES LAYER                             │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ Agent System │  │    Memory    │  │  Scheduler   │               │
│  │    (BMA)     │  │ (3-tier)     │  │  (APScheduler│               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │   Voice OS   │  │  AI Studio   │  │   Research   │               │
│  │  (OmniVoice) │  │ (HyperFrames)│  │   Engine     │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │  Model Router│  │ Notification │  │  Evaluation  │               │
│  │  (Groq/Claude│  │  (Telegram)  │  │   Engine     │               │
│  │  /Gemini/    │  │              │  │              │               │
│  │   Ollama)    │  │              │  │              │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
└──────────────────────────────────────────────────────────────────────┘
                              │ persists to
┌──────────────────────────────────────────────────────────────────────┐
│                      INFRASTRUCTURE LAYER                            │
│                                                                      │
│   SQLite (primary DB)     Firebase RTDB (pielts)    R2 (assets)      │
│   Cloudflare R2           Firebase Hosting           Telegram         │
│   OmniVoice :8920         Opik (observability)       Git/GitHub       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2.3 The Five Products

### pielts — pielts.web.app

pielts is a free IELTS practice platform for students worldwide. It provides:
- Full practice tests for all four IELTS skills (Listening, Reading, Writing, Speaking)
- Instant band score feedback using the Evaluation Engine (SES-009)
- Speaking practice via WebRTC voice sessions
- An AI teacher character (Mr. Yeti) for coaching and motivation
- A premium tier (planned Phase 3) for extended practice and AI essay feedback

The technology: React SPA on Firebase Hosting, Firebase Auth, Firebase RTDB for student scores. The SaathiAI server handles evaluation, speaking sessions, and AI feedback.

**Why pielts exists:** IELTS preparation resources are expensive or low-quality. pielts makes high-quality practice free and accessible to students in Nepal and beyond.

---

### HCG POS — Canteen Management System

HCG POS is the point-of-sale and management system for the HCGMS canteen. It provides:
- Daily menu management and pricing
- Real-time sales recording
- Inventory tracking and deduction
- End-of-day reporting
- Integration with HCG Live Signal for real-time monitoring

**Why HCG POS exists:** The canteen serves students and staff at HCGMS. Manual cash management creates errors and has no data trail for analysis.

---

### HCG Live Signal — Real-Time Canteen Monitoring

HCG Live Signal provides real-time monitoring and analytics for HCGMS canteen operations. It provides:
- Live sales dashboard
- Inventory level alerts
- Demand pattern analysis
- Operational anomaly detection
- Reports for canteen management

Note: HCG Live Signal is a **real-time canteen operations monitoring system**. It is not a financial trading product.

**Why HCG Live Signal exists:** Canteen management needs operational visibility — when to restock, which items sell fastest, when peak demand occurs.

---

### Mr. Yeti / Baadar — Content and Social Engine

Mr. Yeti is the AI teacher character for pielts. Baadar is the AI agent that creates and publishes content across social media platforms as Mr. Yeti.

The content pipeline:
- Daily IELTS tips and practice questions
- Short-form video (YouTube Shorts, TikTok, Instagram Reels)
- Blog posts (auto-published to pielts via Firebase)
- Social media posts (Facebook, Instagram, LinkedIn)

The Baadar agent (`~/SaathiAI`) runs this pipeline autonomously, publishing at 8pm daily via APScheduler.

**Why Baadar exists:** Organic distribution of pielts requires consistent, high-quality content that builds trust and drives traffic. Manual content production at this frequency is not sustainable for a solo operator.

---

### Travel Platform — AI-Assisted Travel (Phase 3)

A planned product for AI-assisted travel planning and booking. Serves travelers from Nepal and South Asia planning international travel.

Status: Architected but not yet built. All platform capabilities (research, voice, memory, scheduling) are available to it from day one when development begins.

---

## 2.4 The Four Departments

SaathiAI's capabilities are organized into four departments. Each department owns a set of platform capabilities and is responsible for their quality, performance, and evolution.

| Department | Capabilities | Products Served | SES Documents |
|------------|-------------|-----------------|---------------|
| **Core Platform** | Agent System, Memory, Model Router, Scheduler, Notification, Evaluation, Analytics | All | SES-002, SES-003, SES-008, SES-009, SES-010, SES-011 |
| **Voice** | STT, TTS, Voice Clone, Real-Time Pipeline | pielts, Travel, Mr. Yeti | SES-004 |
| **AI Studio** | Content Generator, Video Renderer, Social Publisher, Asset Manager | Mr. Yeti / Baadar | SES-006 |
| **Research** | Research Engine, Browser Agent, Signal Monitor | HCG Live Signal, Travel, Mr. Yeti | SES-005 |

---

## 2.5 Technology Stack

The following decisions are documented in full in their respective ADRs. This section provides the summary view.

| Layer | Technology | Reason | ADR |
|-------|-----------|--------|-----|
| Web Framework | FastAPI | Async, OpenAPI, Pydantic | ADR-0001 |
| Primary DB | SQLite + aiosqlite | Zero ops, WAL concurrency | ADR-0002 |
| LLM (standard) | Groq llama-3.3-70b-versatile | Speed and cost | ADR-0003 |
| LLM (reasoning) | Claude (Anthropic) | Complex reasoning | ADR-0003 |
| LLM (screening) | Shimmy / TinyLlama 1.1B | Near-zero cost | ADR-0003 |
| LLM (multimodal) | Gemini | Vision and audio | ADR-0003 |
| LLM (private) | Ollama | On-device, no data egress | ADR-0003 |
| Scheduler | APScheduler (embedded) | No external deps | ADR-0004 |
| Student DB | Firebase RTDB | Real-time sync to React | ADR-0005 |
| TTS | OmniVoice (self-hosted) | Zero cost, biometric privacy | ADR-0008 |
| Video | HyperFrames | HTML/CSS layout for video | ADR-0010 |
| Object Storage | Cloudflare R2 | Cost-effective at scale | — |
| Observability | Opik | LLM trace-native | — |
| Frontend | React + Firebase Hosting | pielts only | ADR-0005 |

---

# Part 3 — Execution Roadmap

---

## 3.1 Development Philosophy

SaathiAI follows the Karpathy principle of software development:

> **The best code is the simplest code that solves the actual problem. Every abstraction must earn its place.**

In practice this means:
- No feature is built speculatively. Features are built when a product needs them.
- No infrastructure is added until the existing infrastructure is insufficient.
- Every complexity introduced has a documented reason in an ADR.
- The system runs on the smallest possible stack — one server, one database engine, one scheduler — until that constraint breaks.

This philosophy is why SaathiAI uses SQLite instead of Postgres, APScheduler instead of Celery, and self-hosted OmniVoice instead of cloud TTS. These are not compromises — they are correct choices for the current scale, with documented migration paths for when scale demands them.

---

## 3.2 Development Phases

### Phase 1 — Platform Foundation (Current)

**Objective:** A stable, documented, and observable platform that all five products can build on.

**What must be complete:**
- [ ] All SES-000 foundation documents at L3 (Architecture Approved)
- [ ] SES-001 Architecture at L4 (Implementation Ready)
- [ ] SES-002 Agent System at L4 — BMA fully operational
- [ ] SES-003 Memory at L4 — Working and Episodic tiers stable
- [ ] SES-004 Voice OS at L3 — STT and TTS operational
- [ ] SES-007 API Gateway at L4 — all endpoints documented and typed
- [ ] SES-008 Observability at L3 — Opik tracing all LLM calls
- [ ] SES-009 Evaluation Engine at L4 — IELTS band scoring stable
- [ ] SES-010 Automation Engine at L3 — all 25+ jobs running reliably
- [ ] pielts live at pielts.web.app with stable scoring
- [ ] Baadar publishing daily content autonomously

**Success signal for Phase 1:** The platform runs for 30 consecutive days without a critical failure. Every LLM call, every scheduled job, and every evaluation produces an Opik trace. The SES-000 series is at L3 or above.

---

### Phase 2 — Product Deepening

**Objective:** Make each product significantly better using platform capabilities already built in Phase 1.

**What this means for each product:**

| Product | Phase 2 Goal |
|---------|-------------|
| pielts | Real-time Speaking practice sessions via Voice OS; pielts premium tier with AI essay feedback |
| HCG POS | Full inventory deduction from sales; predictive restocking alerts |
| HCG Live Signal | Real-time dashboard accessible from mobile; demand anomaly alerts |
| Mr. Yeti | 3D animated character videos; consistent daily publishing across 5 platforms |
| Travel Platform | Architecture finalized; MVP scope defined |

**Success signal for Phase 2:** pielts has 500 active monthly users. Mr. Yeti has 1,000 YouTube subscribers. HCG canteen management uses SaathiAI data for weekly planning decisions.

---

### Phase 3 — Platform Scalability

**Objective:** Prepare the platform for growth beyond single-server, single-operator constraints.

**What changes in Phase 3:**
- Payment Service — Stripe integration for pielts premium and Travel bookings
- Cloud deployment target — Neon (Postgres) migration path prepared; cloud scheduler (Celery / Cloud Tasks) architecture documented
- Travel Platform MVP — first external product on SaathiAI
- Asset Manager — centralized media storage for all products
- Deployment Engine — automated CI/CD for pielts

**Success signal for Phase 3:** pielts processes its first paid subscription. Travel Platform serves its first customer. The platform runs in a cloud environment alongside the Mac-based development environment.

---

### Phase 4 — Intelligence Deepening

**Objective:** Make SaathiAI's intelligence capabilities meaningfully more powerful.

**What this means:**
- Knowledge Graph — Neo4j integration for cross-product entity relationships
- Semantic Memory — ChromaDB vector search for long-term pattern retrieval
- Cross-product intelligence — Memory from one product genuinely informs another
- Emotion Recognition — detect student stress in IELTS Speaking responses
- Multi-language — Nepali language support across all products

**Success signal for Phase 4:** The Knowledge Graph surfaces a non-obvious insight that directly influences a product decision. Semantic Memory enables a response that was impossible with SQL-only retrieval.

---

### Phase 5 — Platform as Product

**Objective:** SaathiAI evolves from a private platform to a framework that other operators can run.

**What this means:**
- Documentation for external deployment
- Configuration system that does not require code changes to set up for a new operator
- A second operator running their own SaathiAI instance

**Success signal for Phase 5:** One operator outside of Kathmandu runs a SaathiAI instance serving their own products. The documentation is sufficient for them to set it up without assistance.

---

## 3.3 Governance Principles

**Who makes architectural decisions:** Ajay Chaulagain, with ADR documentation required for all major decisions.

**How decisions are made:** Any decision that involves a technology choice, a provider selection, or a design pattern that will constrain future implementation requires an ADR. The ADR is written before the implementation begins, not after.

**How the specification evolves:** The SES evolves through versioned documents. Breaking changes to the architecture result in a new SES version (e.g., v1.0 → v2.0). Additive changes result in a new minor version (v1.0 → v1.1). Corrections result in a patch version (v1.0.0 → v1.0.1).

**What AI coding agents are authorized to do:** AI coding agents (Claude Code, Codex, Cursor) are authorized to implement any task described in an L4-or-above SES document. They are authorized to propose ADRs but not to approve them. They are not authorized to deviate from architecture principles (SES-000C) without a documented ADR.

---

## 3.4 Success Metrics

The following metrics define what success looks like for SaathiAI as a platform. Product-specific metrics are defined in each product's SES document.

| Metric | Phase 1 Target | Phase 3 Target | Measurement |
|--------|---------------|---------------|-------------|
| Platform uptime | 95% | 99% | Uptime robot or self-monitoring |
| LLM call observability | 100% of calls traced | 100% | Opik trace coverage |
| Scheduled job reliability | 95% success rate | 99% | Job completion logs |
| Evaluation accuracy | Band score within 0.5 of human examiner | Within 0.5 | Manual calibration sample |
| Documentation maturity | All SES-000 docs at L3 | All SES-001 through SES-010 at L4 | Maturity Dashboard (Appendix A) |
| New capability adoption time | < 1 week from idea to L3 | < 3 days | Git history |

---

# Appendix A — Document Maturity Dashboard

Current maturity level of every SES document. Updated whenever any document advances a level.

Last updated: 2026-07-02

| Document ID | Title | Version | Status | Maturity |
|-------------|-------|---------|--------|----------|
| SES-000 | Master Roadmap | 1.1.0 | Approved | L3 |
| SES-000A | Document Standard | 1.1.0 | Approved | L3 |
| SES-000B | Glossary | 0.1.0 | Draft | L1 |
| SES-000C | Architecture Principles | 0.1.0 | Draft | L1 |
| SES-000D | Coding Standard | 0.1.0 | Draft | L1 |
| SES-000E | Repository Index | 0.1.0 | Draft | L1 |
| SES-000F | Capability Registry | 0.1.0 | Draft | L1 |
| SES-001 | Architecture | 1.0.0 | Approved | L3 |
| SES-002 | Agent System | 1.0.0 | Approved | L3 |
| SES-003 | Memory & Knowledge Graph | 1.0.0 | Approved | L3 |
| SES-004 | Voice OS | 1.0.0 | Approved | L3 |
| SES-005 | AI Studio | — | In Progress | — |
| SES-006 | Autonomous Engineering | — | Not Started | — |
| SES-007 | Mission Control | — | Not Started | — |
| SES-008 | Business OS | — | Not Started | — |
| SES-009 | Learning OS | — | Not Started | — |
| SES-010 | Discovery Engine | — | In Progress | — |
| SES-011 | Security & Guardrails | — | Not Started | — |
| SES-012 | Event Fabric | — | Not Started | — |
| SES-013 | Compliance & Governance | — | Not Started | — |
| SES-014 | Product Framework | — | Not Started | — |
| SES-015 | Financial Intelligence | — | Not Started | — |
| SES-016 | Research Engine | — | Not Started | — |
| SES-017 | World Model | — | Not Started | — |
| SES-018 | Dream Engine | — | Not Started | — |
| SES-019 | Deployment & Infrastructure | — | Not Started | — |
| SES-020 | Future Roadmap | — | Not Started | — |

---

# Appendix B — Foundation Document Index

Quick-reference guide to the SES-000 series. Read in this order.

| Document | Purpose | Read Before |
|----------|---------|------------|
| [SES-000A Document Standard](SES-000A_DOCUMENT_STANDARD.md) | How every SES document must be structured. The governing standard for this document. | Everything |
| [SES-000B Glossary](SES-000B_GLOSSARY.md) | Definitions of every SaathiAI-specific term | All content documents |
| [SES-000C Architecture Principles](SES-000C_ARCHITECTURE_PRINCIPLES.md) | The 10 constraints that govern every system built on SaathiAI | SES-001 through SES-020 |
| [SES-000D Coding Standard](SES-000D_CODING_STANDARD.md) | Conventions for every line of code written for SaathiAI | Any implementation work |
| [SES-000E Repository Index](SES-000E_REPOSITORY_INDEX.md) | Every external repository evaluated for integration | Adding any dependency |
| [SES-000F Capability Registry](SES-000F_CAPABILITY_REGISTRY.md) | Every capability on the platform and which products use it | Building any new capability |

---

# Acceptance Criteria

| # | Criterion | Verification Method | Priority |
|---|-----------|---------------------|----------|
| AC-001 | A non-technical reader can understand SaathiAI's mission, products, and goals from Part 1 alone | User review | Must Have |
| AC-002 | An AI coding agent can read Parts 1 and 2 and correctly identify which product a new feature request belongs to | Test with Claude Code | Must Have |
| AC-003 | The Maturity Dashboard in Appendix A is updated whenever any SES document changes maturity level | Process check on every SES document update | Must Have |
| AC-004 | Every product in Section 2.3 has a corresponding SES document listed in Appendix A | Cross-reference check | Must Have |
| AC-005 | The Platform Blueprint (Part 2) does not contradict any principle in SES-000C | Architecture review | Must Have |

---

# Implementation Checklist

**Phase 1 — Foundation Document Series**
- [x] Write SES-000A Document Standard
- [x] Write SES-000B Glossary (Draft L1)
- [x] Write SES-000C Architecture Principles (Draft L1)
- [x] Write SES-000D Coding Standard (Draft L1)
- [x] Write SES-000E Repository Index (Draft L1)
- [x] Write SES-000F Capability Registry (Draft L1)
- [x] Write SES-000 Master Roadmap
- [ ] Advance SES-000B through SES-000F to L2 (review pass)
- [ ] Advance SES-000B through SES-000F to L3 (architecture approval)

**Phase 1 — Core Platform Specs (SES-001 through SES-004)**
- [x] Write SES-001 Architecture (L3 Approved)
- [x] Write SES-002 Agent System (L3 Approved)
- [x] Write SES-003 Memory & Knowledge Graph (L3 Approved)
- [x] Write SES-004 Voice OS (L3 Approved)

**Phase 2 — Creative & Intelligence Specs (SES-005 through SES-010)**
- [ ] Write SES-005 AI Studio (In Progress)
- [ ] Write SES-006 Autonomous Engineering
- [ ] Write SES-007 Mission Control
- [ ] Write SES-008 Business OS
- [ ] Write SES-009 Learning OS
- [ ] Write SES-010 Discovery Engine (In Progress)

**Phase 3 — Governance & Infrastructure Specs (SES-011 through SES-015)**
- [ ] Write SES-011 Security & Guardrails (includes Policy Engine)
- [ ] Write SES-012 Event Fabric (NATS nervous system)
- [ ] Write SES-013 Compliance & Governance
- [ ] Write SES-014 Product Framework
- [ ] Write SES-015 Financial Intelligence

**Phase 4 — Intelligence & Vision Specs (SES-016 through SES-020)**
- [ ] Write SES-016 Research Engine
- [ ] Write SES-017 World Model (shared external intelligence layer)
- [ ] Write SES-018 Dream Engine (highest-level orchestrator)
- [ ] Write SES-019 Deployment & Infrastructure
- [ ] Write SES-020 Future Roadmap (then architecture freezes → ADRs only)

---

# Risks

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R-001 | Specification grows too large to be practical | Medium | High | Cap each SES document at 10,000 words; split when necessary |
| R-002 | Platform-First principle is abandoned under time pressure, leading to siloed products | Medium | High | The Capability Registry (SES-000F) is the enforcement check — every engineer must consult it before building |
| R-003 | HCG Live Signal definition remains ambiguous (canteen monitor vs. other) | Low | Medium | Resolved in this document: HCG Live Signal = real-time canteen operations monitoring system |

---

# Dependencies

**Internal:** SES-000A, SES-000B, SES-000C, SES-000D, SES-000E, SES-000F

**External:** None. This is a strategic document with no external dependencies.

---

# Decision References

| ADR | Title | Decision Summary | Status |
|-----|-------|-----------------|--------|
| ADR-0001 | FastAPI over Django/Flask | FastAPI for all API endpoints | Accepted |
| ADR-0002 | SQLite-First Database Strategy | SQLite as primary DB | Accepted |
| ADR-0003 | Multi-Provider LLM Strategy | Groq primary, Claude reasoning, Shimmy screening | Accepted |
| ADR-0004 | APScheduler Embedded | In-process job scheduling | Accepted |
| ADR-0005 | Firebase RTDB for pielts | Real-time student data sync | Accepted |
| ADR-0006 | SaathiAI as OS | Platform OS architecture | Accepted |
| ADR-0007 | Three-Tier Memory | Working → Episodic → Semantic | Accepted |
| ADR-0008 | OmniVoice Self-Hosted TTS | Zero cost, biometric privacy | Accepted |
| ADR-0009 | Versioned Documentation | `docs/SES/v1.0/` structure | Accepted |
| ADR-0010 | HyperFrames for Video | HTML/CSS video composition | Accepted |

---

# Open Questions

| # | Question | Owner | Target Date | Status |
|---|----------|-------|-------------|--------|
| OQ-001 | Should SES-000B through SES-000F go through a formal L2 review before advancing to L3? Or can Ajay approve the L3 transition directly? | Ajay Chaulagain | 2026-07-15 | Open |
| OQ-002 | Is the five-product scope (pielts, HCG POS, HCG Live Signal, Travel, Mr. Yeti) complete for Phase 1 and 2? Or are additional products anticipated? | Ajay Chaulagain | 2026-08-01 | Open |

---

# Future Improvements

| # | Improvement | Target Phase | Notes |
|---|-------------|-------------|-------|
| FI-001 | Interactive HTML version of the Maturity Dashboard with links to each SES document | Phase 2 | Could be auto-generated from document headers |
| FI-002 | A "SaathiAI in 5 minutes" executive summary document derived from this roadmap | Phase 2 | For external stakeholders and potential partners |
| FI-003 | Multi-language version of the Strategic Foundation (Part 1) in Nepali | Phase 4 | When the platform expands to Nepali-speaking operators |

---

# Related Documents

| Document ID | Title | Relationship |
|-------------|-------|-------------|
| SES-000A | Document Standard | Governing standard for this document |
| SES-000B | Glossary | Defines all terms used here |
| SES-000C | Architecture Principles | Governs all design decisions referenced in Part 2 |
| SES-000F | Capability Registry | Defines the capability surface described in Section 2.3 |
| SES-001 | Architecture | The technical specification this document contextualizes |

---

# References

None. This document is the strategic anchor of the SES. It references only SES documents, not external standards.

---

*End of SES-000 Master Roadmap — Version 1.0.0*

*Status: Approved (L3)*

*Next: [`SES-001_ARCHITECTURE.md`](SES-001_ARCHITECTURE.md)*
