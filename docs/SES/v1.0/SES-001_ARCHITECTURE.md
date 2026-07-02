```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : Architecture
Document ID         : SES-001
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
| 1.0.0 | 2026-07-02 | Ajay Chaulagain | Approved — 10-section complete architecture |

---

## Purpose

This is the single most important technical document in the SaathiAI Engineering Specification.

Every document that follows — SES-002 Agent System, SES-003 Memory, SES-004 Voice OS — describes a subsystem. This document describes the **system those subsystems compose**. It is the map. Every other document is a detailed view of one region on that map.

This document answers ten questions that must be answered before any subsystem is specified or implemented:

1. How does the AI Operating System fit together?
2. How is the codebase organized?
3. What are the services and what do they own?
4. How do subsystems communicate through events?
5. What API surfaces does the platform expose?
6. How are AI providers selected, routed, and replaced?
7. What databases are used and when?
8. How is the system secured?
9. How is the system observed?
10. How is the system deployed?

Every architectural decision made in this document either references an existing ADR or is the trigger for a new one. No significant design choice is left undocumented.

**The Architectural Filter:** Before any subsystem is designed or extended, apply this test:

> *"Does this make SaathiAI a better AI Operating System, or does it only solve one application's problem?"*

If the answer is "only one application," the design requires a deviation ADR that explains why platform-level implementation is not practical at this time.

---

## Audience

| Role | Required Sections | Notes |
|------|------------------|-------|
| All Engineers | All | This document is mandatory context before working in any subsystem |
| AI Coding Agents | All | Treat every section as a constraint. The folder architecture in Part 2 is authoritative. |
| Product Architects | Parts 1–5 | Understand the system before proposing product features |
| DevOps / Infrastructure | Parts 8–10 | Security, observability, and deployment |
| New Contributors | Read in full before touching any code | This is the starting point |

---

## Reading Order

```
SES-000A Document Standard
        │
        ▼
SES-000C Architecture Principles  ← AP-01 through AP-10 are enforced here
        │
        ▼
SES-000F Capability Registry       ← Capabilities described here are defined there
        │
        ▼
SES-001 Architecture               ← You are here
        │
        ▼
SES-002 Agent System
SES-003 Memory & Knowledge Graph
SES-004 Voice OS
SES-005 Research Engine
SES-006 AI Studio
...
```

---

## Document Structure

| Part | Title | The Question It Answers |
|------|-------|------------------------|
| 1 | AI Operating System Architecture | How does the whole system fit together? |
| 2 | Folder Architecture | Where does every file live and who owns it? |
| 3 | Service Architecture | What are the services and what do they own? |
| 4 | Event Architecture | How do subsystems communicate asynchronously? |
| 5 | API Architecture | What surfaces does the platform expose? |
| 6 | AI Provider Layer | How are AI models selected, routed, and replaced? |
| 7 | Data Layer | Which database is used for what, and why? |
| 8 | Security Model | How is the system protected? |
| 9 | Observability | How is the system understood at runtime? |
| 10 | Deployment Architecture | How does code get from development to production? |

---

# Part 1 — AI Operating System Architecture

---

## 1.1 The Architecture Question

Before describing what SaathiAI is built from, this section states what SaathiAI is **for** at the architectural level.

SaathiAI is designed to answer one architectural question correctly: *How do you build five products that are better together than they would be separately, without the complexity of five separate AI stacks?*

The answer is an OS architecture: shared kernel, shared services, product applications on top. The products do not own the infrastructure they run on. The infrastructure is owned by the OS and made available to every product through a defined API.

This means:
- A voice session in pielts and a voice response in Travel use the same Voice OS
- Memory accumulated during a pielts session is available to the Baadar content scheduler
- Research done for HCG Live Signal is available to the Travel research pipeline
- A new product added tomorrow inherits all of this on day one

---

## 1.2 The Full Architecture

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                           MISSION CONTROL                                   ║
║           Dashboard · Telegram Interface · Health Monitor · Alerts           ║
╚══════════════════════════════════════════════════════════════════════════════╝
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
╔═════════════▼══════╗  ╔════════════▼════════╗  ╔══════════▼═══════════╗
║   AGENT PLATFORM   ║  ║  KNOWLEDGE GRAPH    ║  ║    INFRASTRUCTURE    ║
║                    ║  ║                     ║  ║                      ║
║  BMA Loop          ║  ║  Neo4j              ║  ║  FastAPI :8765        ║
║  Sub-Agents (7)    ║  ║  Qdrant vectors     ║  ║  APScheduler         ║
║  Tool Registry     ║  ║  Episodic SQLite    ║  ║  Redis cache         ║
║  SafetyHarness     ║  ║  Working Memory     ║  ║  Firebase Admin      ║
║  AgentMessageBus   ║  ║                     ║  ║  Telegram bot        ║
╚═════════════╤══════╝  ╚════════════╤════════╝  ╚══════════╤═══════════╝
              │                      │                      │
              └──────────────────────┼──────────────────────┘
                                     │ shared services
   ┌──────────────┬──────────────────┼─────────────────┬──────────────┐
   │              │                  │                 │              │
╔══▼══════╗  ╔════▼═════╗  ╔════════▼═══════╗  ╔═════▼═════╗  ╔══════▼═════╗
║ VOICE   ║  ║AI STUDIO ║  ║  AUTOMATION    ║  ║ RESEARCH  ║  ║EVALUATION  ║
║  OS     ║  ║          ║  ║    ENGINE      ║  ║  ENGINE   ║  ║  ENGINE    ║
║         ║  ║ Content  ║  ║                ║  ║           ║  ║            ║
║ STT     ║  ║ Video    ║  ║ Scheduler      ║  ║ Web       ║  ║ Rubric     ║
║ TTS     ║  ║ Social   ║  ║ 25+ Jobs       ║  ║ Crawler   ║  ║ Evaluator  ║
║ Clone   ║  ║ Assets   ║  ║ Notification   ║  ║ Signal    ║  ║ Scorer     ║
╚══╤══════╝  ╚════╤═════╝  ╚════════╤═══════╝  ╚═════╤═════╝  ╚══════╤═════╝
   │              │                  │                 │              │
   └──────────────┴──────────────────┼─────────────────┴──────────────┘
                                     │ application layer
        ┌────────────┬───────────────┼───────────────┬────────────┐
        │            │               │               │            │
   ╔════▼════╗  ╔════▼════╗  ╔═══════▼══════╗  ╔════▼════╗  ╔════▼════╗
   ║ pielts  ║  ║ HCG POS ║  ║ HCG Live Sig ║  ║ Travel  ║  ║Mr. Yeti ║
   ║         ║  ║         ║  ║              ║  ║Platform ║  ║/ Baadar ║
   ╚═════════╝  ╚═════════╝  ╚══════════════╝  ╚═════════╝  ╚═════════╝
```

---

## 1.3 The Subsystem Contract

Every subsystem in the OS Services layer must answer four questions. A subsystem that cannot answer all four has responsibilities that are not well defined.

| Question | What It Forces |
|----------|---------------|
| **Why does it exist?** | The subsystem has a purpose that is not covered by any other subsystem |
| **What capabilities does it own?** | The subsystem's capabilities are listed in SES-000F; nothing it does is duplicated elsewhere |
| **What interfaces does it expose?** | Other subsystems can only interact with it through these defined interfaces — never by importing its internals |
| **What other subsystems may depend on it?** | The dependency graph is explicit; circular dependencies are a design failure |

This contract is applied to every subsystem in Parts 3 and 4 of this document.

---

## 1.4 Subsystem Dependency Graph

The allowed dependency directions. An arrow from A to B means A may depend on B. Reverse dependencies are architectural violations.

```
Application Layer
        │
        ▼ (depends on)
OS Services Layer (Voice OS, AI Studio, Automation, Research, Evaluation)
        │
        ▼ (depends on)
Agent Platform + Knowledge Graph
        │
        ▼ (depends on)
Infrastructure Layer (FastAPI, SQLite, Redis, Firebase, R2)
        │
        ▼ (depends on)
AI Provider Layer (Groq, Claude, Gemini, Grok, Kimi, Local LLM)
```

**Circular dependencies are prohibited.** No infrastructure component may import from an OS Service. No Agent Platform component may import from an Application.

---

# Part 2 — Folder Architecture

---

## 2.1 Repository Root

```
~/SaathiAI/
├── app/                    ← SaathiAI OS platform code
├── apps/                   ← Product-specific code
├── docs/                   ← SES specification
│   ├── SES/v1.0/           ← All SES documents
│   ├── decisions/          ← ADR files
│   ├── appendix/           ← Appendices A–G
│   ├── CHANGELOG.md
│   └── DECISIONS.md        ← Historical index (superseded by decisions/)
├── tests/                  ← All tests, mirroring app/ and apps/ structure
├── scripts/                ← Utility scripts (not importable)
├── client/                 ← Frontend assets (animations, static files)
├── .env                    ← Secrets (gitignored)
├── firebase-admin.json     ← Firebase credentials (gitignored)
├── requirements.txt        ← Pinned Python dependencies
├── pyproject.toml          ← Tool configuration (mypy, black, isort, pytest)
└── main.py                 ← Entry point: uvicorn app.main:app
```

---

## 2.2 Platform Code: `app/`

```
app/
├── main.py                 ← FastAPI app creation, router mounting, lifespan
│
├── core/                   ← Cross-cutting platform utilities
│   ├── config.py           ← All environment variable loading (one place)
│   ├── response.py         ← api_success(), api_error(), standard envelope
│   ├── logging.py          ← Structured logging configuration
│   └── exceptions.py       ← SaathiAI-specific exception classes
│
├── providers/              ← All external provider abstractions (AP-02)
│   ├── llm_provider.py     ← Model Router: Groq / Claude / Gemini / Grok / Kimi / Local
│   ├── tts_provider.py     ← OmniVoice abstraction
│   ├── stt_provider.py     ← Whisper abstraction
│   ├── storage_provider.py ← R2 / local file storage
│   ├── search_provider.py  ← Web search (Brave / SerpAPI)
│   └── db_provider.py      ← SQLite / Postgres connection management
│
├── agents/                 ← BMA Agent System (SES-002)
│   ├── bma.py              ← Main BMA loop orchestrator
│   ├── bus.py              ← AgentMessageBus
│   ├── safety.py           ← SafetyHarness
│   ├── sub_agents/         ← One file per sub-agent
│   │   ├── writing.py
│   │   ├── speaking.py
│   │   ├── reading.py
│   │   ├── listening.py
│   │   ├── grammar.py
│   │   ├── vocabulary.py
│   │   └── pronunciation.py
│   └── orchestrator.py     ← Top-level coordination
│
├── memory/                 ← Three-Tier Memory (SES-003)
│   ├── working.py          ← deque(maxlen=20) working memory
│   ├── episodic.py         ← SQLite interaction log
│   ├── semantic.py         ← Pattern extraction + ChromaDB / Qdrant
│   └── knowledge_graph.py  ← Neo4j interface (Phase 4)
│
├── voice/                  ← Voice OS (SES-004)
│   ├── stt.py              ← Speech-to-text (Whisper)
│   ├── tts.py              ← Text-to-speech (OmniVoice)
│   ├── clone.py            ← Voice profile management
│   └── pipeline.py         ← Real-time STT → LLM → TTS pipeline (Phase 2)
│
├── studio/                 ← AI Studio (SES-005)
│   ├── content.py          ← Content generator
│   ├── video.py            ← HyperFrames video renderer
│   ├── publisher.py        ← Social platform publisher
│   └── assets.py           ← Asset manager (Phase 3)
│
├── research/               ← Research Engine (SES-006)
│   ├── engine.py           ← Main research orchestrator
│   ├── crawler.py          ← Crawl4AI web content extraction
│   ├── browser.py          ← Browser agent (Playwright)
│   └── signal.py           ← Signal monitor for HCG Live Signal
│
├── evaluation/             ← Evaluation Engine (SES-007)
│   ├── engine.py           ← General evaluation framework
│   └── rubrics/            ← Injected rubrics (product-specific)
│       ├── ielts_writing.py
│       ├── ielts_speaking.py
│       ├── ielts_reading.py
│       └── ielts_listening.py
│
├── automation/             ← Automation Engine (SES-008)
│   ├── scheduler.py        ← APScheduler setup and job registration
│   ├── jobs/               ← One file per scheduled job
│   │   ├── content_daily.py
│   │   ├── analytics_refresh.py
│   │   ├── dashboard_generate.py
│   │   └── backup_daily.py
│   └── notification.py     ← Notification service (Telegram, email)
│
├── analytics/              ← Analytics Engine (SES-009)
│   ├── collector.py        ← Metrics collection
│   └── reporter.py         ← Report generation
│
├── observability/          ← Observability (SES-010)
│   ├── tracing.py          ← Opik + OpenObserve trace wrapper
│   ├── metrics.py          ← Platform metrics
│   └── health.py           ← Health check endpoints
│
├── tools/                  ← Tool Registry (SES-002)
│   ├── registry.py         ← TOOL_REGISTRY dict — all tools registered here
│   ├── research/
│   │   ├── research_web.py
│   │   └── extract_content.py
│   ├── communication/
│   │   ├── send_telegram.py
│   │   └── send_email.py
│   ├── content/
│   │   ├── generate_content.py
│   │   └── publish_social.py
│   ├── data/
│   │   ├── query_memory.py
│   │   └── update_knowledge.py
│   └── system/
│       ├── schedule_job.py
│       └── get_metrics.py
│
├── db/                     ← Database access layer
│   ├── schema.py           ← init_db() — all table definitions
│   ├── connection.py       ← get_connection() context manager, WAL setup
│   └── models/             ← One file per data model
│       ├── memory.py
│       ├── jobs.py
│       ├── analytics.py
│       └── content.py
│
├── prompts/                ← All prompt templates
│   ├── memory.py
│   ├── evaluation.py
│   ├── content.py
│   └── research.py
│
├── routers/                ← FastAPI route definitions
│   ├── agents.py           ← /api/v1/agents/
│   ├── memory.py           ← /api/v1/memory/
│   ├── voice.py            ← /api/v1/voice/
│   ├── studio.py           ← /api/v1/studio/
│   ├── research.py         ← /api/v1/research/
│   ├── evaluation.py       ← /api/v1/eval/
│   ├── automation.py       ← /api/v1/scheduler/
│   ├── analytics.py        ← /api/v1/analytics/
│   ├── notify.py           ← /api/v1/notify/
│   └── health.py           ← /api/v1/health/
│
└── security/               ← Security controls
    ├── auth.py             ← API key validation, JWT for pielts
    ├── rate_limit.py       ← Per-endpoint rate limiting
    └── validation.py       ← Input sanitization
```

---

## 2.3 Product Code: `apps/`

```
apps/
├── pielts/                 ← pielts product-specific code
│   ├── scoring.py          ← IELTS band score calculation
│   ├── sessions.py         ← Speaking session management
│   └── firebase.py         ← Firebase RTDB write operations
│
├── hcg_pos/                ← HCG POS product-specific code
│   ├── menu.py             ← Menu and pricing management
│   ├── sales.py            ← Sales recording
│   └── inventory.py        ← Inventory deduction logic
│
├── hcg_live_signal/        ← HCG Live Signal product-specific code
│   ├── monitor.py          ← Real-time canteen monitoring
│   └── dashboard.py        ← Live operations dashboard
│
├── travel/                 ← Travel Platform (Phase 3)
│   └── README.md           ← Architecture reserved; implementation Phase 3
│
└── mr_yeti/                ← Mr. Yeti / Baadar content engine
    ├── persona.py          ← Mr. Yeti character voice and personality
    ├── pipeline.py         ← Daily content generation pipeline
    └── character.py        ← Character system (Phase 2)
```

---

## 2.4 Ownership Table

| Directory | Owner Subsystem | SES Document |
|-----------|----------------|-------------|
| `app/agents/` | Agent Platform | SES-002 |
| `app/memory/` | Knowledge Graph | SES-003 |
| `app/voice/` | Voice OS | SES-004 |
| `app/studio/` | AI Studio | SES-005 |
| `app/research/` | Research Engine | SES-006 |
| `app/evaluation/` | Evaluation Engine | SES-007 |
| `app/automation/` | Automation Engine | SES-008 |
| `app/analytics/` | Analytics Engine | SES-009 |
| `app/observability/` | Observability | SES-010 |
| `app/providers/` | Infrastructure | SES-001 (this document) |
| `app/routers/` | API Gateway | SES-001 (this document) |
| `app/tools/` | Agent Platform | SES-002 |
| `app/db/` | Infrastructure | SES-001 (this document) |
| `app/security/` | Security | SES-001 (this document) |
| `apps/pielts/` | pielts Application | SES-011 |
| `apps/hcg_pos/` | HCG POS Application | SES-012 |
| `apps/hcg_live_signal/` | HCG Live Signal Application | SES-013 |
| `apps/travel/` | Travel Platform | SES-014 |
| `apps/mr_yeti/` | Mr. Yeti / Baadar | SES-015 |

**Rule:** A file belongs to exactly one owner. A file that serves two owners should be split into two files or moved to `app/core/`.

---

# Part 3 — Service Architecture

---

## 3.1 Service Registry

Every service answers the four-question subsystem contract: Why / What / Interfaces / Dependencies.

---

### SERVICE-01: Agent Platform (BMA)

**Why it exists:** The Agent Platform is the cognitive core of SaathiAI. Every request that requires reasoning, tool use, or multi-step processing goes through the BMA loop.

**What capabilities it owns:**
- 4-phase BMA loop (Perception → Decision → Action → Reflection)
- 7 sub-agents (Writing, Speaking, Reading, Listening, Grammar, Vocabulary, Pronunciation)
- Tool Registry with 70+ tool modules
- SafetyHarness (validates actions before execution)
- AgentMessageBus (sub-agent communication)

**Interfaces it exposes:**
```
POST /api/v1/agents/run        — Execute a BMA cycle
POST /api/v1/agents/tool       — Invoke a specific tool
GET  /api/v1/agents/tools      — List available tools
GET  /api/v1/agents/status     — Current agent state
```

**What may depend on it:** All OS Services, all Applications

**What it depends on:** Memory (SES-003), Model Router (Part 6), Tool modules, SafetyHarness

---

### SERVICE-02: Memory System

**Why it exists:** Persistent context is what separates an intelligent system from a stateless API. The Memory System ensures that every interaction on SaathiAI improves the platform's understanding of its users and products.

**What capabilities it owns:**
- Working Memory (in-process deque, current session)
- Episodic Memory (SQLite, full interaction log)
- Semantic Memory (extracted patterns, Qdrant vectors in Phase 4)
- Knowledge Graph (Neo4j, entity relationships in Phase 4)

**Interfaces it exposes:**
```
GET  /api/v1/memory/working              — Current session context
POST /api/v1/memory/working/add          — Add to working memory
GET  /api/v1/memory/episodic             — Retrieve interaction history
POST /api/v1/memory/episodic/log         — Log an interaction
GET  /api/v1/memory/semantic/search      — Semantic pattern search
POST /api/v1/knowledge/entity            — Add/update knowledge graph entity
GET  /api/v1/knowledge/relate            — Query entity relationships
```

**What may depend on it:** Agent Platform, all OS Services, all Applications

**What it depends on:** SQLite, Qdrant (Phase 4), Neo4j (Phase 4), Model Router (for summarization)

---

### SERVICE-03: Voice OS

**Why it exists:** Voice is a platform capability. Any product that needs voice interaction — pielts Speaking practice, Travel booking, Mr. Yeti narration — uses the same Voice OS rather than embedding its own voice stack.

**What capabilities it owns:**
- Speech-to-Text (Whisper, local)
- Text-to-Speech (OmniVoice, self-hosted :8920)
- Voice Clone management
- Real-time voice pipeline (STT → LLM → TTS, Phase 2)

**Interfaces it exposes:**
```
POST /api/v1/voice/stt                   — Transcribe audio
POST /api/v1/voice/tts                   — Synthesize speech
POST /api/v1/voice/clone/create          — Create voice clone
GET  /api/v1/voice/clone/list            — List voice profiles
WS   /api/v1/voice/session               — Real-time voice session (Phase 2)
```

**What may depend on it:** pielts (Speaking), Travel Platform, Mr. Yeti

**What it depends on:** OmniVoice (TTS provider), Whisper (STT provider), Model Router (LLM in pipeline)

---

### SERVICE-04: AI Studio

**Why it exists:** Content creation at scale requires a dedicated service. The AI Studio handles every step of the content pipeline: generation, video rendering, and social publishing. It serves Mr. Yeti / Baadar today and will serve all products in the future.

**What capabilities it owns:**
- Content Generator (text, scripts, captions, blog posts)
- Video Renderer (HyperFrames composition to MP4)
- Social Publisher (Facebook, Instagram, YouTube, TikTok, LinkedIn)
- Asset Manager (R2-backed media storage, Phase 3)

**Interfaces it exposes:**
```
POST /api/v1/studio/content              — Generate content
POST /api/v1/studio/video/render         — Render video from composition
POST /api/v1/studio/publish              — Publish to social platform
POST /api/v1/studio/publish/queue        — Queue for 8pm daily post
GET  /api/v1/studio/assets               — List assets (Phase 3)
POST /api/v1/studio/assets/upload        — Upload asset (Phase 3)
```

**What may depend on it:** Mr. Yeti / Baadar, pielts (content recommendations, Phase 3)

**What it depends on:** Model Router, Research Engine (content research), HyperFrames, R2 Storage

---

### SERVICE-05: Research Engine

**Why it exists:** Autonomous systems need to know what is happening in the world. The Research Engine provides the platform's ability to gather, extract, and synthesize information from external sources.

**What capabilities it owns:**
- Web search and content extraction (Crawl4AI)
- Browser agent (Playwright-based, for JavaScript-rendered pages)
- Signal Monitor (continuous monitoring of data sources)
- Research synthesis (LLM-powered summarization of gathered content)

**Interfaces it exposes:**
```
POST /api/v1/research/web                — Search and extract web content
POST /api/v1/research/browse             — Navigate a specific URL
POST /api/v1/research/synthesize         — Synthesize multiple sources
POST /api/v1/research/signal/register    — Register a signal to monitor
GET  /api/v1/research/signal/{id}        — Get latest signal state
```

**What may depend on it:** HCG Live Signal, Travel Platform, Mr. Yeti / Baadar, Agent Platform (via tool modules)

**What it depends on:** Model Router, Crawl4AI, Playwright, SQLite (signal state)

---

### SERVICE-06: Evaluation Engine

**Why it exists:** Quality assessment at the platform level enables any product to evaluate AI-generated outputs against a rubric. pielts uses IELTS rubrics. Future products could inject different rubrics.

**What capabilities it owns:**
- General evaluation framework (inject-a-rubric, return-a-score)
- IELTS rubrics (Writing, Speaking, Reading, Listening)
- Band score calculation (1–9, 0.5 increments)
- Detailed feedback generation

**Interfaces it exposes:**
```
POST /api/v1/eval/score                  — Evaluate a response against a rubric
POST /api/v1/eval/feedback               — Generate detailed feedback
GET  /api/v1/eval/rubrics                — List available rubrics
POST /api/v1/eval/rubrics/register       — Register a new rubric
```

**What may depend on it:** pielts, future exam-preparation products

**What it depends on:** Model Router (LLM evaluation), prompts/evaluation.py

---

### SERVICE-07: Automation Engine

**Why it exists:** A SaathiAI without autonomous operation is not an OS — it is a library. The Automation Engine runs 25+ scheduled jobs that make the platform self-operating.

**What capabilities it owns:**
- APScheduler job registry and lifecycle management
- Notification Service (Telegram, email, in-app)
- Two-way Telegram interface (receive commands, send responses)
- Job failure handling and alerting

**Interfaces it exposes:**
```
GET  /api/v1/scheduler/jobs              — List all registered jobs
POST /api/v1/scheduler/jobs/run          — Trigger a job manually
GET  /api/v1/scheduler/jobs/{id}/status  — Get job execution history
POST /api/v1/notify/telegram             — Send Telegram notification
POST /api/v1/notify/email                — Send email notification
POST /api/v1/notify/queue                — Queue notification for delivery
```

**What may depend on it:** All products (via scheduled jobs), Mission Control

**What it depends on:** All OS Services (jobs call them), python-telegram-bot, SQLite (job history)

---

### SERVICE-08: Analytics Engine

**Why it exists:** Without measurement, there is no improvement. The Analytics Engine aggregates business metrics across all products and makes them queryable.

**What capabilities it owns:**
- Event collection (lightweight, SQLite-backed)
- Metric aggregation (daily, weekly, monthly)
- Product-specific dashboards (pielts scores, canteen sales, content reach)
- CEO Morning Dashboard (cross-product summary)

**Interfaces it exposes:**
```
POST /api/v1/analytics/event             — Record a business event
GET  /api/v1/analytics/metrics           — Query aggregated metrics
GET  /api/v1/analytics/dashboard/{product} — Product dashboard data
GET  /api/v1/analytics/dashboard/ceo     — CEO morning summary
```

**What may depend on it:** Mission Control, all products

**What it depends on:** SQLite (metrics store), Model Router (dashboard narrative generation)

---

### SERVICE-09: Mission Control

**Why it exists:** A single operator running five products needs a single point of visibility and control. Mission Control is the operator's interface to the entire platform.

**What capabilities it owns:**
- Platform health monitor
- Cross-product metric dashboard
- Telegram command interface (two-way)
- Alert management
- Manual job triggering

**Interfaces it exposes:**
```
GET  /api/v1/health                      — Platform health status
GET  /api/v1/health/detail               — Per-service health detail
GET  /api/v1/mission/status              — Full platform status summary
POST /api/v1/mission/command             — Execute operator command
```

**What may depend on it:** Nothing — Mission Control is the top-level operator layer

**What it depends on:** All OS Services (reads their health), Automation Engine (Telegram), Analytics Engine (metrics)

---

# Part 4 — Event Architecture

---

## 4.1 Why Events

Subsystems that communicate through direct synchronous calls create tight coupling. When subsystem A calls subsystem B directly, a failure in B can block A. Changing B's interface requires changing A.

Events invert this: A publishes that something happened. B reacts when it's ready. Neither knows about the other.

SaathiAI uses events for cross-subsystem communication at two levels:
1. **In-process events** (AgentMessageBus) — synchronous within a single BMA cycle
2. **Persistent events** (event log in SQLite, Phase 3: Redis Streams) — asynchronous across cycles and jobs

---

## 4.2 In-Process Event Bus

The AgentMessageBus is a Python-native in-process message bus active during a BMA cycle.

```
Orchestrator
    │ publishes BMAEvent(type="task_assigned", sub_agent="writing", payload={...})
    │
    ▼
AgentMessageBus.publish(event)
    │
    ├──► writing_agent.handle(event)
    ├──► safety_harness.monitor(event)
    └──► observability.trace(event)
```

**Event types in the BMA cycle:**

| Event Type | Publisher | Subscribers | When |
|------------|-----------|-------------|------|
| `cycle.started` | Orchestrator | Observability | BMA cycle begins |
| `task.assigned` | Orchestrator | Sub-agent, Safety | Sub-agent receives task |
| `tool.invoked` | Sub-agent | Safety, Observability | Tool is called |
| `tool.completed` | Tool module | Sub-agent, Memory | Tool returns result |
| `tool.failed` | Tool module | Sub-agent, Notification | Tool raises exception |
| `safety.blocked` | SafetyHarness | Orchestrator, Observability | Action rejected |
| `task.completed` | Sub-agent | Orchestrator, Memory | Sub-agent finishes |
| `cycle.completed` | Orchestrator | Memory, Observability | Full BMA cycle done |
| `cycle.failed` | Orchestrator | Notification, Observability | Unrecoverable failure |

---

## 4.3 Persistent Event Log

For events that need to outlive a single BMA cycle — cross-product intelligence, job completion tracking, audit trails — events are persisted to SQLite (Phase 1) and migrated to Redis Streams (Phase 3 when throughput demands it).

**Schema:**

```sql
CREATE TABLE platform_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    source      TEXT NOT NULL,      -- subsystem or product that published
    payload     TEXT NOT NULL,      -- JSON
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    processed   INTEGER DEFAULT 0,  -- 0=pending, 1=processed
    processed_at DATETIME
);
```

**Key persistent events:**

| Event Type | Publisher | Subscriber | Purpose |
|------------|-----------|------------|---------|
| `job.completed` | Automation Engine | Analytics, Mission Control | Job execution audit |
| `job.failed` | Automation Engine | Notification, Mission Control | Immediate alert |
| `content.published` | AI Studio | Analytics | Content reach tracking |
| `evaluation.scored` | Evaluation Engine | pielts, Analytics | Score history |
| `signal.triggered` | Research Engine | HCG Live Signal | Alert generation |
| `memory.pattern_found` | Memory System | Analytics | Semantic insight |
| `user.session_ended` | pielts | Memory, Analytics | Session close |

---

## 4.4 Retry Policy and Dead-Letter

Every event handler that processes persistent events must implement:

```python
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = [5, 30, 300]   # exponential-ish backoff

async def process_event(event: PlatformEvent) -> None:
    for attempt in range(MAX_RETRIES):
        try:
            await handler(event)
            await mark_processed(event.id)
            return
        except RetryableError as e:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY_SECONDS[attempt])
            else:
                await send_to_dead_letter(event, str(e))
        except FatalError as e:
            await send_to_dead_letter(event, str(e))
            return
```

Dead-letter queue: `platform_events_dead_letter` table in SQLite. Mission Control monitors this table and alerts via Telegram when dead-letter items accumulate.

---

# Part 5 — API Architecture

---

## 5.1 API Surfaces

SaathiAI exposes five API surfaces:

| Surface | Protocol | Port | Consumers |
|---------|---------|------|----------|
| REST API | HTTP/HTTPS | 8765 | All products, external integrations |
| WebSocket | WS/WSS | 8765 (same server) | pielts real-time sessions, voice |
| MCP Server | stdio / HTTP | TBD | Claude Code, AI coding agents |
| Internal RPC | Python function calls | In-process | Sub-agents, tool modules |
| Telegram | Telegram Bot API | Outbound | Ajay (operator commands) |

---

## 5.2 REST API Design

**Base URL:** `http://localhost:8765/api/v1/` (development)

**URL Pattern:**
```
POST /api/v1/{subsystem}/{action}
GET  /api/v1/{subsystem}/{resource}/{id}
```

**Standard Response Envelope** (every endpoint, no exceptions):

```json
{
    "status": "success",
    "data": { ... },
    "error": null,
    "request_id": "uuid4",
    "duration_ms": 142
}
```

**Error Response:**

```json
{
    "status": "error",
    "data": null,
    "error": "Human-readable error message",
    "error_code": "MEMORY_NOT_FOUND",
    "request_id": "uuid4",
    "duration_ms": 12
}
```

**Authentication:**
- Internal platform calls: `X-SaathiAI-Token: {SAATHI_TOKEN}` header
- pielts frontend: Firebase JWT token validated by `app/security/auth.py`
- Telegram bot: validated by `BAADAR_PASSWORD` environment variable

---

## 5.3 WebSocket API

Used for real-time sessions. Two WebSocket endpoints:

```
WS /api/v1/voice/session         — Real-time voice pipeline (Phase 2)
WS /api/v1/eval/session/speaking — pielts Speaking practice session
```

**WebSocket message envelope:**

```json
{
    "type": "audio_chunk | text | control",
    "payload": { ... },
    "session_id": "uuid4",
    "sequence": 42
}
```

---

## 5.4 MCP Server

SaathiAI exposes an MCP server that makes platform capabilities available to AI coding agents (Claude Code) and external AI applications.

**MCP tools exposed:**

```
saathai_run_agent         — Run a BMA cycle
saathai_search_memory     — Query episodic and semantic memory
saathai_research          — Run a research query
saathai_generate_content  — Generate platform content
saathai_get_metrics       — Query platform analytics
saathai_send_notification — Send notification
```

MCP server implementation: `app/mcp/server.py` (Phase 2).

---

## 5.5 Full Endpoint Registry

**Agent Platform**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/agents/run` | Execute a BMA cycle |
| POST | `/api/v1/agents/tool/{name}` | Invoke a specific tool |
| GET | `/api/v1/agents/tools` | List registered tools |

**Memory**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/memory/working` | Get working memory context |
| POST | `/api/v1/memory/working/add` | Add message to working memory |
| GET | `/api/v1/memory/episodic` | Get interaction history |
| POST | `/api/v1/memory/episodic/log` | Log an interaction |
| GET | `/api/v1/memory/semantic/search` | Semantic pattern search |

**Voice OS**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/voice/stt` | Speech-to-text transcription |
| POST | `/api/v1/voice/tts` | Text-to-speech synthesis |
| WS | `/api/v1/voice/session` | Real-time voice pipeline |

**AI Studio**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/studio/content` | Generate content |
| POST | `/api/v1/studio/video/render` | Render video composition |
| POST | `/api/v1/studio/publish` | Publish to social platform |
| POST | `/api/v1/studio/publish/queue` | Queue for scheduled publishing |

**Research Engine**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/research/web` | Web search and extraction |
| POST | `/api/v1/research/synthesize` | Multi-source synthesis |
| POST | `/api/v1/research/signal/register` | Register a signal monitor |

**Evaluation Engine**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/eval/score` | Evaluate against a rubric |
| POST | `/api/v1/eval/feedback` | Generate detailed feedback |

**Automation Engine**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/scheduler/jobs` | List all scheduled jobs |
| POST | `/api/v1/scheduler/jobs/run/{name}` | Manually trigger a job |
| POST | `/api/v1/notify/telegram` | Send Telegram message |

**Analytics**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/analytics/event` | Record a business event |
| GET | `/api/v1/analytics/metrics` | Query metrics |
| GET | `/api/v1/analytics/dashboard/ceo` | CEO morning dashboard |

**Health / Mission Control**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Platform health status |
| GET | `/api/v1/mission/status` | Full operator status |

---

# Part 6 — AI Provider Layer

---

## 6.1 Architecture

The Model Router is the single point of contact for all LLM, TTS, and STT calls in the platform. Business logic never references a specific provider. It references a task label.

```
Business Logic
    │
    │  llm.complete(prompt, model="standard")
    ▼
Model Router (app/providers/llm_provider.py)
    │
    ├── "screening"  ──► Shimmy (TinyLlama 1.1B, Ollama local)
    ├── "standard"   ──► Groq (llama-3.3-70b-versatile)
    ├── "reasoning"  ──► Claude (claude-sonnet-4-6 or latest)
    ├── "multimodal" ──► Gemini (gemini-2.5-flash or pro)
    ├── "fast"       ──► Grok (xAI, speed-optimized tasks)
    ├── "long"       ──► Kimi (Moonshot AI, long-context documents)
    └── "private"    ──► Ollama (local, data-sensitive tasks)
```

---

## 6.2 Provider Registry

| Label | Provider | Model | Use Case | Cost Profile |
|-------|---------|-------|---------|-------------|
| `screening` | Ollama (Shimmy) | TinyLlama 1.1B | Binary classification, high-volume filtering | Near-zero |
| `standard` | Groq | llama-3.3-70b-versatile | Most tasks: content, evaluation, research synthesis | Low |
| `reasoning` | Anthropic | claude-sonnet-4-6 | Complex multi-step reasoning, architecture decisions | Medium |
| `multimodal` | Google | gemini-2.5-flash | Image analysis, audio processing, video understanding | Low-Medium |
| `fast` | xAI | grok-3-mini | Speed-sensitive tasks where standard latency matters | Low |
| `long` | Moonshot AI (Kimi) | moonshot-v1-128k | Long document analysis (128k context) | Medium |
| `private` | Ollama (local) | Configurable | Data that must not leave the device | Zero |

---

## 6.3 Routing Logic

```python
PROVIDER_MAP = {
    "screening": ShimmyProvider,
    "standard":  GroqProvider,
    "reasoning": ClaudeProvider,
    "multimodal": GeminiProvider,
    "fast":      GrokProvider,
    "long":      KimiProvider,
    "private":   OllamaProvider,
}

FALLBACK_CHAIN = {
    "standard":  ["fast", "reasoning"],     # if Groq is down
    "reasoning": ["standard"],              # if Claude is down
    "fast":      ["standard"],              # if Grok is down
    "multimodal": ["reasoning"],            # if Gemini is down
    "long":      ["reasoning"],             # if Kimi is down
}
```

---

## 6.4 Fallback Logic

```python
async def complete(prompt: str, model: str, **kwargs) -> LLMResponse:
    primary = PROVIDER_MAP[model]
    chain = [primary] + [PROVIDER_MAP[fb] for fb in FALLBACK_CHAIN.get(model, [])]

    for provider in chain:
        try:
            response = await provider.complete(prompt, **kwargs)
            opik_trace(provider=provider.name, model=model, tokens=response.usage)
            return response
        except ProviderUnavailable as e:
            log_provider_failure(provider.name, str(e))
            continue

    raise AllProvidersUnavailable(f"All fallback providers failed for model={model}")
```

---

## 6.5 Provider Abstraction Interface

All providers implement `BaseLLMProvider`:

```python
class BaseLLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> LLMResponse:
        ...

class LLMResponse(BaseModel):
    text: str
    provider: str
    model: str
    usage: TokenUsage
    latency_ms: int
```

---

# Part 7 — Data Layer

---

## 7.1 Database Philosophy

SaathiAI uses the simplest database that correctly solves each problem. Different problems call for different databases. Using one database for everything creates friction in some cases; using too many databases creates operational complexity.

The current data layer:

```
┌─────────────────────────────────────────────────────────┐
│                    DATA LAYER                           │
│                                                         │
│  SQLite (primary)     Firebase RTDB (pielts)            │
│  ├── episodic_memory  ├── results/{uid}                 │
│  ├── platform_events  └── sessions/{uid}                │
│  ├── jobs                                               │
│  ├── analytics                                          │
│  └── content                                            │
│                                                         │
│  Redis (Phase 3)      Qdrant (Phase 4)                  │
│  ├── session cache    └── semantic_vectors              │
│  └── event streams                                      │
│                                                         │
│  Neo4j (Phase 4)      Supabase/Neon (Phase 3)           │
│  └── knowledge_graph  └── cloud Postgres (migration)    │
│                                                         │
│  Cloudflare R2                                          │
│  └── media assets, video, backups                       │
└─────────────────────────────────────────────────────────┘
```

---

## 7.2 Database Decision Matrix

| Data Type | Database | Phase | Why |
|-----------|---------|-------|-----|
| All server-side state (memory, jobs, events, analytics) | SQLite | 1 | Zero ops, WAL concurrency, trivially backed up |
| pielts student scores and session data | Firebase RTDB | 1 | Real-time sync to React frontend, Firebase Auth |
| Static assets, videos, rendered frames | Cloudflare R2 | 1 | Cost-effective object storage, CDN-ready |
| Session cache, rate-limit counters | Redis | 3 | Sub-millisecond key-value; SQLite too slow for hot cache |
| Event streaming (high-volume async events) | Redis Streams | 3 | When SQLite event log becomes a bottleneck |
| Semantic vector search | Qdrant | 4 | Purpose-built vector DB; ChromaDB evaluated first |
| Entity relationships (knowledge graph) | Neo4j | 4 | Native graph queries; Cypher is expressive |
| Cloud-scalable relational DB | Supabase (Neon) | 3 | When platform requires always-on cloud deployment |

---

## 7.3 SQLite Schema Overview

All tables defined in `app/db/schema.py` under `init_db()`.

```sql
-- Core memory tables
episodic_memory (id, user_id, product, role, content, metadata, created_at)
semantic_patterns (id, pattern_key, pattern_value, source_product, confidence, created_at)

-- Platform event log
platform_events (id, event_type, source, payload, created_at, processed, processed_at)
platform_events_dead_letter (id, event_id, error, created_at)

-- Automation
scheduler_jobs (id, name, schedule, last_run, last_status, run_count, error_count)
scheduler_job_log (id, job_name, started_at, completed_at, status, output, error)

-- Analytics
analytics_events (id, event_type, product, user_id, metadata, created_at)
analytics_daily (id, date, product, metric, value, computed_at)

-- Content pipeline
content_queue (id, product, platform, content_type, content, scheduled_at, status)
content_published (id, queue_id, published_at, platform_id, reach, engagement)
```

---

## 7.4 Data Residency Rules

| Data | Stays On-Device | May Leave Device | Never Leaves Device |
|------|----------------|-----------------|---------------------|
| Episodic memory | SQLite | — | Always on-device |
| pielts student scores | Firebase (cloud) | — | Firebase is the canonical store |
| Voice data (recordings) | Processed locally | — | Raw audio never stored |
| Voice clone profile | OmniVoice :8920 | — | Biometric — never leaves device |
| Content before publishing | SQLite | — | — |
| Published content | — | Social platforms | By design |
| LLM prompts | — | Groq, Claude, Gemini, Grok, Kimi | Provider's data policy applies |
| Private-mode LLM prompts | Ollama local | — | Never sent to cloud |

---

# Part 8 — Security Model

---

## 8.1 Authentication Architecture

```
External Request
        │
        ▼
FastAPI Middleware (app/security/auth.py)
        │
        ├── /api/v1/*  ──── X-SaathiAI-Token header ──── validate against SAATHI_TOKEN env
        │
        ├── /api/v1/pielts/* ─── Firebase JWT ──── validate via Firebase Admin SDK
        │
        └── /api/v1/health ─── No auth required (read-only health check)
```

---

## 8.2 Authorization Model

| Actor | What They May Do |
|-------|----------------|
| Operator (Ajay via Telegram) | All platform operations — full access |
| pielts frontend | pielts endpoints only; student's own data only |
| AI coding agents (Claude Code) | Read-only platform inspection; no production data writes |
| HCG POS client | HCG POS endpoints only |
| Automation jobs | Any endpoint they are configured to call; logged |

---

## 8.3 Secrets Management

All secrets in `.env`. Never in source code, never in logs.

**Currently managed secrets:**

```
SAATHI_TOKEN          — Platform API authentication
BAADAR_PASSWORD       — Telegram command authentication
GROQ_API_KEY          — Groq LLM provider
ANTHROPIC_API_KEY     — Claude provider
GOOGLE_API_KEY        — Gemini provider
XAI_API_KEY           — Grok provider
KIMI_API_KEY          — Kimi provider
TELEGRAM_BOT_TOKEN    — Telegram bot
FIREBASE_PROJECT_ID   — Firebase project
R2_ACCESS_KEY         — Cloudflare R2
R2_SECRET_KEY         — Cloudflare R2
OPIK_API_KEY          — Observability
```

**`.gitignore` mandatory entries:**
```
.env
firebase-admin.json
*.pem
*.key
```

---

## 8.4 Voice Authentication (Phase 2)

Voice-controlled operator commands (Telegram voice messages) require speaker verification before executing privileged actions:

```
Incoming voice command
        │
        ▼
STT transcription
        │
        ▼
Speaker verification (voice fingerprint vs stored clone profile)
        │
        ├── Match (>95% confidence) ──► Execute command
        └── No match               ──► Reject + alert
```

---

## 8.5 Input Validation Rules

All user input validated at the API boundary (Pydantic models). No raw input reaches business logic.

Validation rules:
- String length limits on all text fields (max 10,000 characters for content inputs)
- Enum validation on all categorical inputs (product, platform, model label)
- File type validation on audio uploads (wav, mp3, m4a only)
- Rate limiting on all endpoints (see Part 8.6)

---

## 8.6 Rate Limiting

| Endpoint Category | Limit | Window | Error Code |
|-------------------|-------|--------|------------|
| Evaluation (`/api/v1/eval/`) | 10 requests | Per minute | 429 |
| Content generation (`/api/v1/studio/content`) | 20 requests | Per minute | 429 |
| Voice STT (`/api/v1/voice/stt`) | 30 requests | Per minute | 429 |
| Research (`/api/v1/research/`) | 5 requests | Per minute | 429 |
| All other endpoints | 100 requests | Per minute | 429 |

Rate limiting implemented via `app/security/rate_limit.py` using in-memory counters (Phase 1) and Redis (Phase 3).

---

# Part 9 — Observability

---

## 9.1 Observability Stack

```
┌──────────────────────────────────────────────────────┐
│                  OBSERVABILITY LAYER                 │
│                                                      │
│  Opik (LLM traces)        OpenObserve (metrics/logs) │
│  ├── Every LLM call       ├── Platform metrics       │
│  ├── Token counts         ├── Structured logs        │
│  ├── Latency per call     ├── Error rates            │
│  └── Quality scores       └── Job success rates      │
│                                                      │
│  SQLite (business metrics — always available)        │
│  ├── Evaluation scores                               │
│  ├── Content published                               │
│  └── Job execution history                           │
└──────────────────────────────────────────────────────┘
```

---

## 9.2 Tracing Architecture

Every significant operation is wrapped in a trace. A trace captures: operation name, start time, end time, result (success/failure), and operation-specific metadata.

**LLM traces (Opik):**
```python
from app.observability.tracing import opik_trace

async with opik_trace("evaluation.ielts_writing", model="standard") as trace:
    response = await llm.complete(prompt, model="standard")
    trace.log_tokens(response.usage)
    trace.log_score(band_score)
```

**Job traces (SQLite + OpenObserve):**
```python
@with_job_trace("content_daily")
async def content_daily_job():
    ...
    # decorator records start, end, status, output automatically
```

---

## 9.3 Metrics

**Platform metrics (OpenObserve):**

| Metric | Type | Labels |
|--------|------|--------|
| `saathai.llm.calls.total` | Counter | model, provider, status |
| `saathai.llm.tokens.total` | Counter | model, provider, direction |
| `saathai.llm.latency.ms` | Histogram | model, provider |
| `saathai.job.runs.total` | Counter | job_name, status |
| `saathai.job.duration.ms` | Histogram | job_name |
| `saathai.api.requests.total` | Counter | endpoint, method, status |
| `saathai.api.latency.ms` | Histogram | endpoint |
| `saathai.evaluation.scores` | Histogram | product, skill |

---

## 9.4 Logging Standard

All logs are structured JSON. Fields required on every log entry:

```json
{
    "timestamp": "2026-07-02T08:00:00Z",
    "level": "INFO",
    "service": "automation.content_daily",
    "event": "job.completed",
    "request_id": "uuid4",
    "duration_ms": 4230,
    "metadata": { ... }
}
```

**Log levels:**
- `DEBUG`: Detailed execution trace (development only)
- `INFO`: Normal operation events (job start/complete, LLM calls)
- `WARNING`: Degraded state (fallback provider used, retry occurred)
- `ERROR`: Operation failed (job failed, provider unavailable)
- `CRITICAL`: Platform-level failure (database unavailable, scheduler crashed)

**Never log:** API keys, passwords, tokens, voice data, raw user PII.

---

## 9.5 Health Checks

```
GET /api/v1/health
```

Returns platform health in under 100ms:

```json
{
    "status": "healthy",
    "services": {
        "database": "healthy",
        "scheduler": "healthy",
        "llm_provider": "healthy",
        "tts_provider": "healthy",
        "telegram": "healthy"
    },
    "uptime_seconds": 86400,
    "version": "1.0.0"
}
```

Health check is unauthenticated and monitored by an external uptime monitor (UptimeRobot or equivalent).

---

# Part 10 — Deployment Architecture

---

## 10.1 Environment Definitions

| Environment | Purpose | Where It Runs | Database |
|-------------|---------|--------------|---------|
| **Development** | Active development, experimentation | MacBook Pro (localhost) | SQLite at `~/.saathai/dev.db` |
| **Testing** | Automated tests, CI | MacBook Pro (isolated) | SQLite in-memory or `tests/fixtures/test.db` |
| **Production (local)** | Live platform, all products | MacBook Pro (port 8765) | SQLite at `~/SaathiAI/saathai.db` |
| **Production (cloud)** | Always-on deployment (Phase 3) | VPS or Cloud Run | Postgres via Neon (Supabase) |
| **Edge** | pielts frontend delivery | Firebase Hosting + Cloudflare | Firebase RTDB, CDN assets on R2 |

---

## 10.2 Local Development Setup

```bash
# 1. Clone and enter
git clone https://github.com/chaulagainazay/SaathiAI ~/SaathiAI
cd ~/SaathiAI

# 2. Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Fill in all required values

# 5. Initialize database
python -c "from app.db.schema import init_db; import asyncio; asyncio.run(init_db())"

# 6. Start platform
uvicorn app.main:app --host 0.0.0.0 --port 8765 --reload

# 7. Verify
curl http://localhost:8765/api/v1/health
```

---

## 10.3 Production (Local) Process Management

The platform runs as a background process on the MacBook Pro, managed by `launchd` (macOS):

```xml
<!-- ~/Library/LaunchAgents/com.saathai.platform.plist -->
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.saathai.platform</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/macbookpro/SaathiAI/.venv/bin/uvicorn</string>
        <string>app.main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8765</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/macbookpro/SaathiAI</string>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/Users/macbookpro/SaathiAI/logs/platform.err</string>
    <key>StandardOutPath</key>
    <string>/Users/macbookpro/SaathiAI/logs/platform.out</string>
</dict>
</plist>
```

---

## 10.4 Cloud Deployment Architecture (Phase 3)

```
┌─────────────────────────────────────────────────────────┐
│                   CLOUD DEPLOYMENT                      │
│                                                         │
│   Google Cloud Run (or VPS)                             │
│   ├── SaathiAI Platform container                       │
│   │   └── uvicorn app.main:app                          │
│   ├── OmniVoice container (TTS)                         │
│   └── Ollama container (private LLM)                    │
│                                                         │
│   Neon (Postgres)          Redis (Upstash)              │
│   └── Cloud database       └── Cache + event streams   │
│                                                         │
│   Cloudflare                                            │
│   ├── R2 (object storage)                               │
│   └── CDN (asset delivery)                              │
│                                                         │
│   Firebase (pielts only)                                │
│   ├── Hosting (React SPA)                               │
│   ├── RTDB (student data)                               │
│   └── Auth (student accounts)                           │
└─────────────────────────────────────────────────────────┘
```

**Migration path from local to cloud:**
1. Replace SQLite with Neon Postgres (connection string only change in `app/providers/db_provider.py`)
2. Replace in-memory rate limiting with Redis (one config change)
3. Replace APScheduler embedded with Cloud Tasks (one scheduler adapter swap)
4. OmniVoice: containerize and deploy alongside platform (voice data stays in the cloud instance, not a third-party API)

This migration is designed to be a configuration change, not an architecture change. Every abstraction layer in `app/providers/` was designed for this exact moment.

---

## 10.5 Testing Architecture

```
tests/
├── unit/                   ← app/ mirrored — no external dependencies
│   ├── agents/
│   ├── memory/
│   ├── voice/
│   └── ...
├── integration/            ← Real database, real providers (marked @pytest.mark.integration)
│   ├── test_bma_cycle.py
│   └── test_evaluation_pipeline.py
├── e2e/                    ← Full platform running (marked @pytest.mark.e2e)
│   └── test_pielts_scoring.py
└── fixtures/
    ├── test.db             ← Test database
    └── sample_audio.wav    ← Sample audio for voice tests
```

**CI pipeline (GitHub Actions):**
```
Push → lint (black, isort, mypy) → unit tests → integration tests → deploy (main branch only)
```

---

# Acceptance Criteria

| # | Criterion | Verification Method | Priority |
|---|-----------|---------------------|----------|
| AC-001 | Every subsystem in Part 3 answers all four contract questions | Manual review of SERVICE-01 through SERVICE-09 | Must Have |
| AC-002 | The folder architecture in Part 2 matches the actual repository structure | `find ~/SaathiAI -type d` against Part 2 | Must Have |
| AC-003 | No module outside `app/providers/` imports a specific LLM provider SDK | `grep -r "import groq\|import anthropic\|from groq\|from anthropic" app/ --include="*.py" \| grep -v providers/` | Must Have |
| AC-004 | Every endpoint in Part 5.5 exists in a router file and returns the standard envelope | Integration test of all endpoints | Should Have |
| AC-005 | All event types in Part 4.2 are defined in `app/agents/bus.py` as typed constants | Code review | Should Have |
| AC-006 | `GET /api/v1/health` responds in under 100ms | Load test with `wrk` or equivalent | Must Have |
| AC-007 | The deployment steps in Part 10.2 work on a clean machine with only Python 3.11 and git installed | Test on a fresh environment | Should Have |

---

# Implementation Checklist

**Phase 1 — Core Architecture**
- [ ] Create `app/` directory structure per Part 2.2
- [ ] Create `apps/` directory structure per Part 2.3
- [ ] Implement `app/core/response.py` — standard response envelope
- [ ] Implement `app/providers/llm_provider.py` — Model Router with all 7 labels
- [ ] Implement `app/providers/` — TTS, STT, storage, search, DB providers
- [ ] Implement `app/db/schema.py` — `init_db()` with all 10 tables
- [ ] Implement `app/db/connection.py` — `get_connection()` with WAL mode
- [ ] Implement `app/security/auth.py` — SAATHI_TOKEN + Firebase JWT validation
- [ ] Implement `app/security/rate_limit.py` — per-endpoint rate limiting
- [ ] Implement `app/observability/tracing.py` — Opik + OpenObserve integration
- [ ] Implement `app/observability/health.py` — `/api/v1/health` endpoint
- [ ] Mount all routers in `app/main.py`
- [ ] Write unit tests for providers, response envelope, auth

**Phase 2 — Event Architecture**
- [ ] Implement `app/agents/bus.py` — AgentMessageBus with all event types
- [ ] Create `platform_events` SQLite table in `init_db()`
- [ ] Implement retry policy and dead-letter queue
- [ ] Add event publishing to all subsystems

**Phase 3 — Cloud Readiness**
- [ ] Add Redis provider to `app/providers/db_provider.py`
- [ ] Implement `launchd` plist for production process management
- [ ] Write cloud deployment documentation
- [ ] Validate Postgres migration path in staging

---

# Risks

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R-001 | Folder structure diverges from Part 2.2 as the codebase grows | High | Medium | Add `find app/ -type d` check to CI that fails if unexpected directories appear |
| R-002 | Circular dependencies develop between subsystems | Medium | High | Define dependency direction rules in CI linter; flag any import that goes against the graph in Part 1.4 |
| R-003 | Cloud migration is more complex than the abstraction layer allows | Low | High | Test the Postgres migration path in Phase 2 staging before Phase 3 requires it |
| R-004 | Grok or Kimi providers have different API contracts than expected | Medium | Low | Provider abstraction isolates the impact to one file per provider |

---

# Dependencies

**Internal:** SES-000A, SES-000B, SES-000C (all Architecture Principles enforced here), SES-000F (Capability Registry maps to the services in Part 3)

**External:**

| Dependency | Version | Purpose | Phase |
|------------|---------|---------|-------|
| FastAPI | 0.111+ | Web framework | 1 |
| Pydantic | 2.x | Request/response validation | 1 |
| aiosqlite | 0.20+ | Async SQLite access | 1 |
| APScheduler | 3.10+ | Job scheduling | 1 |
| python-telegram-bot | 21+ | Telegram integration | 1 |
| opik | latest | LLM observability | 1 |
| crawl4ai | latest | Web content extraction | 1 |
| Playwright | 1.44+ | Browser automation | 1 |
| Redis | 5.x (client) | Cache + streams | 3 |
| qdrant-client | 1.9+ | Vector search | 4 |
| neo4j | 5.x | Knowledge graph | 4 |

---

# Decision References

| ADR | Title | Relevant Section |
|-----|-------|-----------------|
| ADR-0001 | FastAPI over Django/Flask | Part 5 (API Architecture) |
| ADR-0002 | SQLite-First Database Strategy | Part 7 (Data Layer) |
| ADR-0003 | Multi-Provider LLM Strategy | Part 6 (AI Provider Layer) |
| ADR-0004 | APScheduler Embedded | Part 3, SERVICE-07 |
| ADR-0005 | Firebase RTDB for pielts | Part 7.2 |
| ADR-0006 | SaathiAI as OS | Part 1.1 |
| ADR-0007 | Three-Tier Memory | Part 3, SERVICE-02 |
| ADR-0008 | OmniVoice Self-Hosted TTS | Part 6 (Provider Registry) |
| ADR-0009 | Versioned Documentation | — |
| ADR-0010 | HyperFrames for Video | Part 3, SERVICE-04 |

---

# Open Questions

| # | Question | Owner | Target Date | Status |
|---|----------|-------|-------------|--------|
| OQ-001 | Should Qdrant replace ChromaDB as the Phase 4 vector database, or should both be evaluated in parallel? | Ajay Chaulagain | 2026-09-01 | Open |
| OQ-002 | Should the MCP server (Part 5.4) be implemented in Phase 1 or Phase 2? | Ajay Chaulagain | 2026-08-01 | Open |
| OQ-003 | Is OpenObserve self-hosted or cloud? If self-hosted, what is the resource overhead on the MacBook Pro? | Ajay Chaulagain | 2026-08-01 | Open |
| OQ-004 | Should Grok (xAI) replace Groq as the `fast` label provider, given their similar latency profiles? Confirm naming: Groq (inference company) vs Grok (xAI model). | Ajay Chaulagain | 2026-07-15 | Open |

---

# Future Improvements

| # | Improvement | Target Phase | Notes |
|---|-------------|-------------|-------|
| FI-001 | API versioning (`/api/v2/`) when first breaking change requires it | Phase 3 | AP-09 (Backward Compatibility) requires maintaining v1 for 3 months minimum |
| FI-002 | GraphQL layer over the REST API for complex cross-subsystem queries | Phase 4 | Evaluate when query complexity warrants it |
| FI-003 | Service mesh (Consul or Kubernetes) when the platform moves beyond a single-machine deployment | Phase 5 | Not needed until multi-node deployment |
| FI-004 | Formal API gateway (Kong or AWS API Gateway) when external developer access is needed | Phase 5 | When SaathiAI becomes a platform-as-product |

---

# Related Documents

| Document ID | Title | Relationship |
|-------------|-------|-------------|
| SES-000 | Master Roadmap | Strategic context for every decision in this document |
| SES-000C | Architecture Principles | All 10 principles are implemented or enforced in this document |
| SES-000F | Capability Registry | All capabilities in Part 3 are registered in SES-000F |
| SES-002 | Agent System | Detailed specification of SERVICE-01 |
| SES-003 | Memory & Knowledge Graph | Detailed specification of SERVICE-02 |
| SES-004 | Voice OS | Detailed specification of SERVICE-03 |
| SES-005 | AI Studio | Detailed specification of SERVICE-04 |
| SES-006 | Research Engine | Detailed specification of SERVICE-05 |

---

# References

| # | Title | Source | Notes |
|---|-------|--------|-------|
| REF-001 | The Twelve-Factor App | 12factor.net | Config, processes, disposability |
| REF-002 | Clean Architecture | Robert C. Martin | Dependency inversion, boundary design |
| REF-003 | Building Microservices | Sam Newman | Service boundary design |
| REF-004 | OpenTelemetry Specification | opentelemetry.io | Tracing standards adapted for Opik |

---

*End of SES-001 Architecture — Version 1.0.0*

*Status: Approved (L3)*

*Next: [`SES-002_AGENT_SYSTEM.md`](SES-002_AGENT_SYSTEM.md)*
