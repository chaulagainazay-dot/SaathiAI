# SaathiAI OS — Master Roadmap
## The Constitution

**Document:** `00_MASTER_ROADMAP.md`
**Classification:** Constitutional — supersedes all other documents in case of conflict
**Version:** 1.1.0
**Status:** Living Document — ratified 2026-07-02
**Author:** Ajay Chaulagain, Chief Software Architect
**Document Series:** SaathiAI Engineering Specification v1.0

> *"This document does not describe what SaathiAI does today.*
> *It describes what SaathiAI is — and must remain — as it grows."*

---

## How to Use This Document

This is the **constitutional document** of the SaathiAI platform. Every other document in `docs/` derives its scope and authority from the boundaries defined here.

When a decision conflicts with another document, this document wins.
When two engineers disagree on direction, they cite this document.
When a new product is being added to the platform, this document tells them what the platform's rules are.

**Reading order for a new engineer:**
1. This document — understand what SaathiAI *is*
2. `01_ARCHITECTURE.md` — understand how it is built
3. `02_AGENT_SYSTEM.md` — understand how it thinks
4. The product spec relevant to their assignment (`17_PRODUCTS.md`)

**Do not skip the Philosophy chapter.** The technical decisions throughout this codebase are direct consequences of the philosophy. Without understanding the philosophy, the technical choices appear arbitrary.

---

## Table of Contents

**Part I — Identity**
- [Chapter 1 — Executive Summary](#chapter-1--executive-summary)
- [Chapter 2 — Vision & Mission](#chapter-2--vision--mission)
- [Chapter 3 — Core Philosophy](#chapter-3--core-philosophy)

**Part II — The Platform**
- [Chapter 4 — Product Ecosystem](#chapter-4--product-ecosystem)
- [Chapter 5 — Architecture Overview](#chapter-5--architecture-overview)
- [Chapter 6 — AI Departments](#chapter-6--ai-departments)

**Part III — Engineering**
- [Chapter 7 — Development Philosophy](#chapter-7--development-philosophy)
- [Chapter 8 — Technology Stack](#chapter-8--technology-stack)
- [Chapter 9 — Repository Strategy](#chapter-9--repository-strategy)

**Part IV — Execution**
- [Chapter 10 — Roadmap & Phases](#chapter-10--roadmap--phases)
- [Chapter 11 — Coding Standards](#chapter-11--coding-standards)
- [Chapter 12 — Success Metrics](#chapter-12--success-metrics)
- [Chapter 13 — Future Vision](#chapter-13--future-vision)

**Appendices**
- [Document Index](#document-index)
- [Glossary](#glossary)

---

# Part I — Identity

---

## Chapter 1 — Executive Summary

SaathiAI is an **AI operating system** built and owned by one person — Ajay Chaulagain, Kathmandu, Nepal. It is the infrastructure layer on which every product, business function, and autonomous workflow in Ajay's life runs.

### What SaathiAI Is

SaathiAI is not an app. It is not a chatbot. It is not a collection of scripts.

SaathiAI is an operating system for a one-person company. It has:

- **A kernel**: the FastAPI server (`saathi/server.py`) that runs all workloads
- **A scheduler**: 25+ autonomous jobs that run without human input
- **A memory system**: three-tier persistent knowledge about every product, student, customer, and interaction
- **An agent loop**: a 4-phase perceive-decide-act-reflect cycle for every AI interaction
- **A tool registry**: 70+ modules that give the system hands — it can control the Mac, write code, post content, query databases, and send messages
- **A voice interface**: Baadar, the bilingual AI operator who can speak, listen, and control the computer
- **An application layer**: products that run on top of this infrastructure

```
┌─────────────────────────────────────────────────────────────────┐
│                        SaathiAI OS                              │
│                                                                 │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐  ┌────────┐  │
│  │  HCG POS   │  │   pielts   │  │  Live Signal │  │ Travel │  │
│  │  Canteen   │  │   IELTS    │  │  HCG Monitor │  │Platform│  │
│  └────────────┘  └────────────┘  └──────────────┘  └────────┘  │
│  ─────────────────── Application Layer ────────────────────────  │
│  Agent System │ Memory │ Scheduler │ Voice │ Tools │ Studio    │
│  ─────────────────── OS Services Layer ────────────────────────  │
│  FastAPI Server │ SQLite │ Firebase │ Telegram │ R2 Storage    │
│  ─────────────────── Infrastructure Layer ─────────────────────  │
└─────────────────────────────────────────────────────────────────┘
```

### Why It Was Built

Ajay Chaulagain is a solo operator running multiple businesses simultaneously:

1. A hospital canteen (HCG) requiring daily operations monitoring
2. An IELTS preparation platform (pielts) requiring student support, content, and marketing
3. A content character (Mr. Yeti) requiring daily video, social posting, and audience growth
4. A canteen management software product (HCGMS) requiring sales and support

No single human can do all of this at the level required to make each business grow. SaathiAI is the force multiplier that makes this possible: it handles execution, the human handles strategy.

### Current State

As of v1.1 (July 2026):

| Component | Status |
|---|---|
| Core FastAPI server (60+ endpoints) | ✅ Production |
| Baadar agent (bilingual, voice, Mac control) | ✅ Production |
| Scheduler (25+ autonomous jobs) | ✅ Production |
| pielts web app (pielts.web.app) | ✅ Production |
| Mr. Yeti content pipeline | ✅ Working |
| BMA multi-agent IELTS loop | ✅ Built, 30 tests passing |
| 3-tier memory (Working/Episodic/Semantic) | ✅ Built |
| HCG POS integration | 🔄 Planned |
| HCG Live Signal monitoring | 🔄 Planned |
| Travel Platform | 🔄 Future |
| Cloud deployment (always-on) | 🔄 Planned |

---

## Chapter 2 — Vision & Mission

### 2.1 The Vision

> **SaathiAI becomes the first AI operating system that lets a single person run a portfolio of businesses at the output quality of a funded team.**

This is not hyperbole. This is the engineering target.

Every feature decision, every technology choice, every architectural trade-off is evaluated against one question: *does this bring us closer to that target?*

The long-term vision extends further: SaathiAI becomes a **deployable template** — other solo operators can license the OS and run their own applications on it. Ajay's instance is the proof-of-concept and the primary revenue-generating deployment.

### 2.2 The Mission

SaathiAI's mission has three parts, in priority order:

**1. Remove Ajay from repeatable execution**
Every task that happens on a schedule, follows a known pattern, or can be described as a rule should be automated. Ajay's time is for relationships, strategy, and decisions that require human judgment. Not for copy-pasting content to five platforms or checking yesterday's revenue.

**2. Generate compounding returns**
Every action the system takes should leave the system smarter than before. Every student interaction improves the IELTS coaching model. Every content post feeds the analytics loop. Every business decision is logged and becomes training data for the next decision. Returns compound over time.

**3. Demonstrate the template**
SaathiAI is the proof that a single developer with AI infrastructure can out-execute a small team. The documentation, architecture, and lessons from this project should be publishable and replicable.

### 2.3 The Commitment

This constitution commits to the following:

- **No product will be built that requires hiring a human to operate it.** If a product cannot be operated autonomously or with minimal human oversight, it is out of scope.
- **Every product must share infrastructure.** No product gets its own agent loop, its own memory, its own scheduler. Products are applications; the OS serves them all.
- **The system will be observable by design.** Nothing runs that cannot be measured. No failure is silent.
- **The system will be explainable.** Every decision the AI makes should be traceable to a cause. Black boxes are not acceptable in a system that affects Ajay's business and his students' education.

---

## Chapter 3 — Core Philosophy

This chapter is the most important in the document. The technical choices in every other chapter are *consequences* of these principles. A reader who understands this chapter will be able to infer the right decision in any ambiguous technical situation.

### 3.1 Autonomous First

**Rule:** Every feature should work at 2am without human input.

This is not about convenience. It is about reliability. A system that requires human intervention to function is a system that stops when Ajay is asleep, sick, or busy. SaathiAI's value comes from its ability to operate continuously.

**Implication for design:** Features are designed for autonomous operation first, human override second. Schedulers are the default trigger. Human input is the exception, not the requirement.

**What this means in code:**
- Every scheduled job is self-sufficient — it gathers its own inputs, makes its own decisions, handles its own errors
- Human approval workflows exist for *irreversible* actions (posting to public channels), not for *routine* ones (gathering data, generating drafts)
- Alert-then-act, not ask-then-act

### 3.2 Compound Memory

**Rule:** Every interaction makes the system smarter.

A system that processes 100 student interactions and is no wiser than after the first one is a wasted opportunity. SaathiAI's memory system ensures that every interaction contributes to a growing body of knowledge.

**Implication for design:** Memory is not a log — it is a knowledge base. Raw interactions are stored (episodic). Patterns are extracted (semantic). The semantic layer drives future decisions.

**What this means in code:**
- Every BMA interaction is stored in episodic memory immediately after completion
- The nightly `memory_reflector` job extracts patterns and updates semantic memory
- The CEO dashboard is informed by accumulated analytics, not just yesterday's data

### 3.3 Fail Loud, Recover Quietly

**Rule:** Errors surface to the operator. The system self-heals.

SaathiAI is a production system. Production systems fail. The question is not whether they fail — it is whether the operator knows about the failure and whether the system continues operating.

**Implication for design:**
- Every error is logged to SQLite and (for critical failures) sent to Telegram
- No failure is silent
- Every job is wrapped in try/except — a failed job does not crash the scheduler
- Recovery actions (retry, fallback provider, skip and continue) are built into the error handlers

**What this means in code:**
- The model router tries Groq first, then Claude, then Ollama — it does not crash if Groq is down
- Scheduled jobs catch exceptions, log them, and continue to the next job
- The health endpoint reports the status of every subsystem

### 3.4 Observability by Default

**Rule:** Nothing runs that cannot be measured.

A system that cannot be measured cannot be improved. SaathiAI's observability is not an afterthought — it is built in from the start.

**Three layers of observability:**
1. **LLM tracing:** Every LLM call is traced via Opik (prompt, response, latency, cost)
2. **Job execution:** Every scheduled job logs its start, completion, and outcome
3. **Business metrics:** CEO dashboard aggregates across all products daily

**What this means in code:**
- `tools/opik_tracer.py` wraps every LLM call
- Scheduler jobs write to the activity log
- Firebase analytics are queried and summarised daily

### 3.5 Voice Is First-Class

**Rule:** Every critical workflow is accessible via spoken command.

Ajay is the primary operator. Ajay speaks Nepali and English. Ajay sometimes needs to check the canteen revenue while his hands are occupied. The voice interface is not a demo feature — it is a primary access path.

**Implication for design:**
- Every API endpoint has a natural-language equivalent that Baadar can invoke
- Voice responses are concise (< 30 seconds) — long reports are summarised, not read aloud
- Speaker verification protects privileged operations from non-Ajay voices

### 3.6 Cost-Aware Scaling

**Rule:** Never pay for infrastructure that a local Mac can handle.

SaathiAI is a one-person operation. The infrastructure cost must be proportional to the revenue it generates. A system that costs $500/month in cloud infrastructure but generates $100/month in revenue is a failure.

**The cost ladder (cheapest first):**
1. Mac (already paid for) — SQLite, local files, Ollama
2. Free tiers — Firebase, Groq free, Cloudflare R2 10GB free
3. Low-cost cloud — Fly.io/Railway at $5-20/month for always-on deployment
4. Paid services — only when free tier is exhausted and revenue justifies it

**Implication for design:**
- Local-first: run on the Mac until the Mac is a bottleneck
- SQLite before Postgres; Ollama before paid APIs for screening tasks
- Shimmy (TinyLlama 1.1B) handles classification at near-zero cost

### 3.7 One System, Multiple Products

**Rule:** Products share infrastructure. Infrastructure does not duplicate for products.

This is the OS principle. When pielts adds a new feature that needs an LLM call, it uses the model router. It does not instantiate its own OpenAI client. When HCG Live Signal needs to send an alert, it uses the Telegram tool. It does not build its own messaging system.

**Implication for design:**
- Every new product is a set of routes on the existing FastAPI server
- Every new product reads from and writes to the shared memory system
- Every new product's jobs run in the shared APScheduler
- Products are isolated by namespace (`/api/v1/<product>/`) not by process

---

# Part II — The Platform

---

## Chapter 4 — Product Ecosystem

SaathiAI OS currently serves four products and has two in design. Each product is an application on the OS — it uses shared infrastructure and does not duplicate it.

### 4.1 The Product Map

```
                        SaathiAI OS
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────┴─────┐      ┌──────┴────┐       ┌──────┴──────┐
    │ Education │      │  Business │       │   Content   │
    │           │      │ Operations│       │   & Media   │
    └────┬─────┘      └──────┬────┘       └──────┬──────┘
         │                   │                   │
    ┌────┴───┐        ┌──────┴────┐       ┌──────┴──────┐
    │ pielts │        │  HCG POS  │       │  Mr. Yeti   │
    │  IELTS │        │  Canteen  │       │   Studio    │
    │Practice│        │Management │       │  Pipeline   │
    └────────┘        └──────┬────┘       └─────────────┘
                             │
                      ┌──────┴──────────────┐
                      │  HCG Live Signal    │
                      │  Real-time Monitor  │
                      └─────────────────────┘

    ┌─────────────────────────────────────────────┐
    │              Travel Platform                │
    │     (Planned — Phase 4+)                    │
    └─────────────────────────────────────────────┘
```

---

### 4.2 Product: Baadar (The OS Operator)

**Classification:** OS Service, not Application
**Status:** Production

Baadar is not a product sold to customers. Baadar is the primary human-to-OS interface. He is the voice of SaathiAI OS — a bilingual (Nepali/English) AI operator who can speak, listen, control the Mac, monitor all products, and execute any OS capability on command.

**Core capabilities:**
- Natural language command interface (voice + text)
- Speaker verification — privileged actions require Ajay's voice
- Mac control via AppleScript and shell
- Cross-product awareness — can answer questions about any product
- Proactive briefings via Telegram (CEO dashboard, alerts, digests)
- Autonomous decision-making within defined boundaries

**Persona characteristics:**
- Warm and direct — no corporate speak
- Bilingual — responds in the language of the query
- Proactive — tells Ajay what he needs to know, not just what he asks
- Opinionated — offers recommendations, not just information

**Technical location:** `saathi/agent.py`, `saathi/persona.py`, `saathi/voice.py`

---

### 4.3 Product: pielts (IELTS Practice Platform)

**Classification:** Application — Education
**Status:** Production
**URL:** pielts.web.app
**Revenue model:** Freemium — 3 tests/month free; Premium unlimited + AI coaching

**What it is:** A free IELTS practice platform with AI-powered scoring and coaching. Students practice all four IELTS skills and receive instant band score estimates and feedback from Mr. Yeti, the IELTS coaching character.

**User journey:**
```
Student discovers pielts (SEO, YouTube, social)
    │
    ├── Free tier: 3 practice tests/month
    │   ├── Listening (auto-scored offline)
    │   ├── Reading (auto-scored offline)
    │   ├── Writing (heuristic band + Mr. Yeti feedback)
    │   └── Speaking (Web Speech API + Mr. Yeti response)
    │
    └── Premium tier: Unlimited + full AI coaching
        ├── Detailed writing correction (BMA loop)
        ├── Speaking evaluation (band + phoneme analysis)
        ├── Daily missions (personalised weak-area targeting)
        └── Band certificate
```

**Technical stack:**
- Frontend: React + Vite + Zustand + Firebase Auth
- Scoring: `src/utils/scoring.js` (offline, rule-based, zero latency)
- AI coaching: SaathiAI BMA loop via `/api/v1/bma/chat`
- Student data: Firebase RTDB (`results/{uid}`)
- Location: `~/Downloads/ielts-practice-app`

**AI coaching path (BMA):**
```
Student submits essay
    │
    ▼
POST /api/v1/bma/chat (skill=writing)
    │
    ▼
BMA Master Loop
    ├── WritingSubAgent: task response, coherence, grammar band
    ├── GrammarSubAgent: sentence-level corrections
    └── VocabularySubAgent: lexical resource suggestions
    │
    ▼
Structured response: band_estimate + corrections + feedback
    │
    ▼
Mr. Yeti interface: renders corrections with character voice
```

---

### 4.4 Product: Mr. Yeti Studio (Content Platform)

**Classification:** Application — Content & Media
**Status:** Working (pipeline operational, scaling in progress)

**What it is:** An autonomous content engine that creates, schedules, posts, and optimises IELTS educational content across YouTube, TikTok, Instagram, Facebook, LinkedIn, Reddit, and Twitter/X — every day, without human intervention.

**The character:** Mr. Yeti is a friendly, white-furred Yeti in round glasses and a teacher's tweed suit who teaches IELTS tips. He is warm, slightly self-deprecating, and deeply effective at making grammar feel manageable. He is the face of pielts on social media.

**The content machine (fully autonomous daily cycle):**
```
7:00am NPT — mr_yeti_7am job fires
    │
    ├── trend_hunter.py: scan YouTube/TikTok for IELTS keywords
    │
    ├── content_studio.py: fuse IELTS topic + trending format
    │
    ├── script_writer.py: generate 60-second script + hook
    │
    ├── google_flow.py: 8-second clip per scene (AI video)
    │
    ├── hyperframes.py: assemble clips → full video
    │
    ├── subtitles.py: generate SRT captions
    │
    ├── thumbnail_maker.py: 5 concept variants
    │   thumbnail.py: score variants → pick winner
    │
    ├── [Auto-approve if confidence > threshold]
    │   └── Publish: YouTube + TikTok + Instagram + Facebook
    │
    └── [Manual review needed]
        └── Telegram to Ajay: "Video ready for review"
            └── Ajay: approve → publish
```

**Repeat at 12pm, 5pm, 8pm NPT.**

**Technical location:** `saathi/tools/mr_yeti_pipeline.py`, `content_studio.py`, `google_flow.py`, `hyperframes.py`

---

### 4.5 Product: HCG POS (Canteen Management)

**Classification:** Application — Business Operations
**Status:** External app (HCGMS) + SaathiAI monitoring integration
**Context:** Hamro Chamena Griha — hospital canteen at Sushma Koirala Memorial Hospital, Kathmandu

**What it is:** A Point of Sale and canteen management system with SaathiAI OS providing the intelligent monitoring layer.

**SaathiAI's role:**
- Daily revenue monitoring vs. NPR 30,000 target
- Credit limit alerts (NPR 3,000 per account)
- Staff performance reporting
- Baadar voice queries: "What was today's revenue?"
- Evening summary to Telegram (7pm NPT)

**Technical location:** `saathi/tools/canteen.py`, `saathi/tools/hcg_voice.py`, `saathi/skills/canteen-ops/`

---

### 4.6 Product: HCG Live Signal (Real-Time Monitor)

**Classification:** Application — Business Operations
**Status:** Planned (Phase 3)

**What it is:** A real-time dashboard and alert system that monitors HCG canteen operations as they happen — not daily summaries, but live transaction alerts, inventory signals, and anomaly detection.

**Planned capabilities:**
- Live transaction feed (every sale as it occurs)
- Revenue velocity tracking (on-pace / below-pace / above-pace vs. daily target)
- Inventory depletion alerts ("Rice stock < 2 days remaining")
- Anomaly detection ("No transactions for 45 minutes during lunch hour")
- Staff clock-in/out tracking
- Telegram push alerts for critical events

**Integration point:** The HCGMS app sends webhooks to SaathiAI OS; Live Signal processes and acts on them.

**Technical plan:**
```
HCGMS event → POST /api/v1/hcg/event
    │
    ▼
Event classifier (Shimmy — cheap, fast)
    │
    ├── ROUTINE: log to SQLite, update dashboard
    ├── ALERT: send Telegram notification
    └── CRITICAL: call Baadar, escalate
```

---

### 4.7 Product: Travel Platform

**Classification:** Application — Commerce
**Status:** Future (Phase 4+)

**What it is:** An AI-powered travel booking and advisory platform serving Nepal-specific travel (inbound and outbound). The initial focus is on the corridor Ajay knows: Nepal → abroad (study visa advisory, travel planning) and tourism into Nepal.

**Why SaathiAI OS enables this:**
- The research tools (`tools/research.py`, Crawl4AI, Firecrawl) can scrape and synthesise travel information
- The content pipeline can create travel content (Mr. Yeti pivot or new character)
- The memory system can build traveller profiles
- The booking logic can be implemented as new tools on the existing registry
- Voice interface allows natural-language travel queries

**This product is not being designed now.** It is listed here to demonstrate the extensibility of the OS architecture. When the time comes, it will be added as new routes and tools — not as a new system.

---

## Chapter 5 — Architecture Overview

### 5.1 The OS Model

SaathiAI is structured as an operating system. This is not a metaphor — it reflects how the system is actually designed.

| OS Concept | SaathiAI Equivalent |
|---|---|
| Kernel | FastAPI server (`saathi/server.py`) |
| Process scheduler | APScheduler + 25+ jobs |
| File system | SQLite + Firebase + R2 |
| System calls | Tool registry (70+ modules) |
| Shell | Baadar agent + voice interface |
| Applications | pielts, Mr. Yeti, HCG POS, Live Signal, Travel |
| Device drivers | Platform integrations (Telegram, Firebase, YouTube, TikTok) |
| Memory management | 3-tier memory (Working → Episodic → Semantic) |

### 5.2 Layered Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Application Layer                                 │
│                                                                             │
│  pielts (IELTS)    Mr. Yeti Studio    HCG POS    Live Signal    Travel     │
│  routes/pielts     routes/studio      routes/hcg  routes/signal  routes/tx  │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ uses
┌────────────────────────────────▼────────────────────────────────────────────┐
│                             OS Services Layer                               │
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Agent System│  │   Memory    │  │  Scheduler   │  │  Tool Registry   │  │
│  │             │  │   System    │  │              │  │                  │  │
│  │ BMA Loop    │  │ Working     │  │ 25+ jobs     │  │ 70+ modules      │  │
│  │ Baadar Core │  │ Episodic    │  │ APScheduler  │  │ mac_control      │  │
│  │ Safety      │  │ Semantic    │  │ cron-based   │  │ social_post      │  │
│  │ Harness     │  │             │  │              │  │ content_studio   │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘  └──────────────────┘  │
│         │                │                │                                 │
│  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴───────┐                        │
│  │ Model Router│  │  Voice OS   │  │  AI Studio   │                        │
│  │             │  │             │  │              │                        │
│  │ Groq        │  │ STT/TTS     │  │ Research     │                        │
│  │ Claude      │  │ Speaker     │  │ Scripts      │                        │
│  │ Gemini      │  │ Verify      │  │ Video        │                        │
│  │ Ollama      │  │ Wake Word   │  │ Thumbnails   │                        │
│  │ Shimmy      │  │             │  │              │                        │
│  └─────────────┘  └─────────────┘  └──────────────┘                        │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ reads/writes
┌────────────────────────────────▼────────────────────────────────────────────┐
│                          Infrastructure Layer                               │
│                                                                             │
│  FastAPI:8765  │  SQLite (local)  │  Firebase RTDB  │  Cloudflare R2      │
│  Telegram Bot  │  OmniVoice:8920  │  Ollama:11434    │  Shimmy:11435       │
│  n8n:5678      │  Opik Tracer     │  Fly.io/Railway  │  Neon (planned)     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Request Routing

Three categories of request enter the OS:

**Human-Initiated:**
```
Voice / Text / Telegram / Web UI
    │
    ▼
Auth middleware (X-Saathi-Token or localhost bypass)
    │
    ▼
Intent Router
    ├─► IELTS request → BMA Master Loop → memory store
    ├─► General query → Baadar Agent → tool dispatch → response
    ├─► Mac action → Baadar Agent → mac_control tool → confirmation
    └─► Product query → product route handler → data retrieval
```

**Scheduler-Initiated:**
```
APScheduler fires job (cron expression)
    │
    ▼
Job function runs autonomously
    ├─► Gather inputs (web, APIs, databases)
    ├─► Process (AI call, analysis, generation)
    ├─► Act (post, send, store)
    └─► Notify (Telegram if noteworthy; log always)
```

**Webhook-Initiated:**
```
External event (Firebase new user, HCGMS transaction, YouTube comment)
    │
    ▼
Webhook endpoint receives and validates
    │
    ▼
Event classified and routed
    ├─► Log to SQLite
    ├─► Trigger relevant action (referral check, alert, reply queue)
    └─► Telegram notification if critical
```

### 5.4 The BMA Agent Loop (Core AI Engine)

The Baadar Multi-Agent Architecture is the core AI processing engine for all complex tasks. It processes any input through four phases:

```
Student/User Input (text or voice)
         │
         ▼
┌─────────────────┐
│  Phase 1:       │  ← Keyword heuristic + LLM for ambiguous cases
│  PERCEPTION     │    Detect skill, parse intent, load context
│                 │    from Working memory + last 5 Episodic records
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Phase 2:       │  ← Select strategy, choose sub-agents
│  DECISION       │    Check cross-skill patterns from bus
│                 │    Determine intervention if needed
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Phase 3:       │  ← SafetyHarness monitors entire execution
│  ACTION         │    Sub-agents execute in sequence
│                 │    ContentFilter + PedagogyChecker validate output
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Phase 4:       │  ← Store to HierarchicalMemory
│  REFLECTION     │    Publish to AgentMessageBus
│                 │    Update cross-skill patterns
└─────────────────┘
         │
         ▼
    ActionResult → client
```

**Sub-agents available:**

| Sub-agent | Skills |
|---|---|
| WritingSubAgent | Task 1/Task 2 evaluation, coherence, structure |
| SpeakingSubAgent | Fluency, pronunciation, lexical resource |
| ReadingSubAgent | Socratic guidance, comprehension, strategy |
| ListeningSubAgent | Prediction, note-taking, form completion |
| GrammarSubAgent | Sentence-level corrections, tense, agreement |
| VocabularySubAgent | Lexical resource, collocations, range |
| PronunciationSubAgent | Phoneme feedback, stress patterns |

---

## Chapter 6 — AI Departments

SaathiAI OS is organised into functional departments. Each department has a clear responsibility and maps to one or more spec documents.

### Department Map

```
SaathiAI OS
│
├── 🧠 Intelligence  ──── Agent System, Memory, Model Router, Evaluation
│   └── docs: 02, 03, 11, 14
│
├── 🎙️ Interaction   ──── Voice OS, Mission Control, Baadar persona
│   └── docs: 04, 09
│
├── 🎬 Creation      ──── AI Studio, Video Pipeline, Character System
│   └── docs: 05, 06, 07
│
├── 🤖 Autonomy      ──── Scheduler, Automation, Autonomous Company
│   └── docs: 08, 12
│
├── 📦 Products      ──── pielts, HCG POS, Mr. Yeti, Live Signal, Travel
│   └── docs: 17
│
└── 🏗️ Platform      ──── Architecture, Infrastructure, Security, Deployment,
                          Observability, Dev Guide, Design Principles
    └── docs: 01, 10, 13, 15, 16, 18, 21
```

### 6.1 Intelligence Department

**Owns:** How SaathiAI thinks, remembers, and evaluates.

**Components:**
- BMA Master Loop — the 4-phase agent cycle
- 3-tier memory — Working, Episodic, Semantic
- Model router — Groq / Claude / Gemini / Ollama / Shimmy selection
- IELTS evaluation engine — writing, speaking, reading, listening rubrics
- Safety harness — content filtering, band clamping, bias detection

**KPIs:**
- BMA response latency < 3 seconds for standard tasks
- IELTS band estimate within ±0.5 of official score
- Memory context relevance ≥ 90% (correct recent context surfaced)
- Safety filter false positive rate < 2%

### 6.2 Interaction Department

**Owns:** How humans talk to SaathiAI.

**Components:**
- Voice OS — STT, TTS, speaker verification, wake word detection
- Baadar persona — system prompt, language rules, tone guidelines
- Telegram bot — bidirectional control channel
- Mission control — CEO dashboard, alert routing, briefing schedule

**KPIs:**
- Voice recognition accuracy ≥ 95% for Nepali-English code-switching
- Speaker verification false accept rate < 0.1%
- CEO dashboard delivered by 8:15am NPT every day
- Telegram alert latency < 30 seconds from event to message

### 6.3 Creation Department

**Owns:** How SaathiAI makes content.

**Components:**
- AI Studio — research, scripting, trend fusion
- Video pipeline — Google Flow → HyperFrames → subtitle → thumbnail
- Character system — Mr. Yeti memory, personality, voice consistency

**KPIs:**
- Daily content cycle complete in < 30 minutes
- Thumbnail CTR improvement ≥ 10% over baseline (A/B tested)
- Zero missed scheduled posts over 30 consecutive days
- Video quality score ≥ 4/5 on Ajay's review when manual approval needed

### 6.4 Autonomy Department

**Owns:** How SaathiAI operates without humans.

**Components:**
- APScheduler — 25+ jobs, cron-based
- n8n workflows — webhook-triggered automations
- Auto-post system — draft → approve → publish pipeline

**KPIs:**
- Scheduler uptime ≥ 99% (when Mac is on)
- Zero data loss from failed jobs (all failures logged and recoverable)
- Auto-approved content rate ≥ 70% (reduces manual review burden)

---

# Part III — Engineering

---

## Chapter 7 — Development Philosophy

### 7.1 The Karpathy Principle

SaathiAI development follows a disciplined minimalism inspired by Andrej Karpathy's approach to AI systems:

> *"Don't build what you can avoid building. Understand before you abstract. Test before you ship."*

**In practice, this means:**

**Do not add features that are not asked for.** A bug fix is a bug fix. It does not need refactoring, cleanup, or additional error handling for scenarios that cannot happen. Adding unrequested features is scope creep, even when the additions seem "obviously useful."

**Do not abstract prematurely.** Three similar lines of code is not a problem. It becomes a problem at five or more, and only then should a helper be extracted. Premature abstraction creates complexity that must be maintained forever.

**Understand before you build.** Read the existing code for the feature area before writing a single line. Understand what already exists. Understand why it is structured the way it is. Then decide whether to extend it or replace it.

**Test at system boundaries.** Don't test internal implementation details. Test the behaviour that external callers depend on.

### 7.2 Test-Driven Development (Where Appropriate)

SaathiAI uses TDD for:
- All BMA sub-agents and the master loop
- All scoring functions in pielts
- Any function that handles money, scores, or makes decisions that affect users

SaathiAI does not use TDD for:
- Scheduled jobs (integration-tested via manual trigger)
- Tool modules that primarily wrap external APIs (mocked APIs test nothing useful)
- One-off scripts

**Test structure:**
```
tests/
├── test_bma.py            # BMA agent loop, sub-agents, safety harness, memory, bus
├── test_intelligence.py   # CEO dashboard, analytics, Firebase queries
├── test_referral.py       # Referral engine, band improvement tracking
├── test_scoring.py        # pielts scoring (all question types)
└── test_voice.py          # Speaker verification, STT accuracy
```

**Current coverage:** 30 tests, 30/30 passing.

### 7.3 The One-Direction Rule

**Data flows in one direction through layers:**

```
Application Layer
    ↓ calls
OS Services Layer
    ↓ calls
Infrastructure Layer
```

An OS service never directly imports from an application. An infrastructure component never imports from an OS service. Violations of this rule create circular dependencies and coupling that makes the system impossible to reason about.

### 7.4 Configuration is Not Code

**Rule:** No magic numbers, no hardcoded paths, no credentials in code.

All configuration lives in:
- `.env` — credentials, API keys, secrets
- `saathi/config.py` — typed, documented constants derived from `.env`
- `saathi/agents/config/agent_config.yaml` — agent behaviour tuning

**Never:**
- Hardcode a file path (use `config.ROOT` or `os.path.join`)
- Hardcode a model name in a tool (use `config.MODEL_FAST`, `config.MODEL_SMART`)
- Put a credential in source code
- Put a `.env` value directly in a route handler (read it through `config.py`)

### 7.5 Comments Are For the Why, Not the What

**Write comments only when the WHY is non-obvious.**

**Write a comment for:**
- A workaround for a specific external API bug
- A constraint that is not visible from the code
- A non-obvious invariant that must be maintained
- A deliberate performance trade-off

**Do not write a comment for:**
- What a function does (the name explains that)
- What a variable holds (the type annotation explains that)
- The current task ("Added for the BMA loop refactor" — this rots immediately)

---

## Chapter 8 — Technology Stack

### 8.1 Decision Framework

Every technology choice in SaathiAI is evaluated against five criteria, in this order:

1. **Does it serve the philosophy?** (Chapter 3)
2. **What is its cost at scale?** (Zero-cost preferred; metered acceptable; fixed monthly only for core)
3. **Can a single person operate it?** (No dedicated DBA, no DevOps team)
4. **Does it have a local fallback?** (System must work without internet)
5. **Is it already being used?** (Existing dependency preferred over new)

### 8.2 Stack Reference

#### Language & Runtime
| Layer | Technology | Version | Rationale |
|---|---|---|---|
| Primary language | Python | 3.12 | AI ecosystem is Python-first; async support |
| Package manager | pip + setuptools | — | Simplest; pyproject.toml for declaration |
| Frontend (pielts) | React + Vite | 18 / 5 | Fast dev server, SPA, large ecosystem |
| Frontend state | Zustand | 4 | Lightweight; no Redux boilerplate |
| Frontend styling | Tailwind CSS | 3 | Utility-first; consistent with existing pielts code |

#### Server
| Layer | Technology | Rationale |
|---|---|---|
| Web framework | FastAPI | Native async, auto-docs, Pydantic |
| ASGI server | Uvicorn | Recommended for FastAPI, production-ready |
| Task scheduler | APScheduler | Embedded, no external queue needed |
| Auth | X-Saathi-Token header | Simple, single-operator system |

#### AI / LLM
| Role | Provider | Model | When |
|---|---|---|---|
| Primary inference | Groq | llama-3.3-70b-versatile | All standard tasks |
| Complex reasoning | Anthropic | claude-sonnet-4-6 | Architecture, analysis |
| Multimodal / vision | Google | gemini-2.5-flash-lite | Images, thumbnails, video |
| Local / offline | Ollama | qwen2.5:3b | Privacy-sensitive, offline |
| Screening / cheap | Shimmy | tinyllama-1.1b | Classification, filtering |

**Model selection logic:**
```
ULTRA (screening, classification, routing)
  └─► Shimmy (:11435) — near-zero cost

FAST (content generation, standard tool calls, chat)
  └─► Groq llama-3.3-70b-versatile

SMART (long-context reasoning, writing evaluation, architecture)
  └─► Anthropic claude-sonnet-4-6

MULTIMODAL (image analysis, thumbnail scoring, video understanding)
  └─► Gemini gemini-2.5-flash-lite

PRIVATE (user data analysis, speaker data, anything that must stay local)
  └─► Ollama qwen2.5:3b
```

#### Data Storage
| Use Case | Technology | Location |
|---|---|---|
| Primary server state | SQLite | `data/saathi.db` |
| BMA episodic memory | SQLite | `data/baadar_episodic.db` |
| BMA semantic patterns | SQLite | `data/baadar_semantic.db` |
| pielts student scores | Firebase RTDB | Cloud (Firebase) |
| pielts user auth | Firebase Auth | Cloud (Firebase) |
| File/video storage | Cloudflare R2 | Cloud (R2) |
| Vector search (Phase 6) | ChromaDB | Local file (`data/chroma/`) |
| Cloud Postgres (Phase 3) | Neon | Cloud (Neon) |

#### Voice
| Layer | Technology | Port |
|---|---|---|
| TTS (cloned voices) | OmniVoice | :8920 |
| STT (server-side) | Whisper (local) | In-process |
| STT (browser) | Web Speech API | Browser |
| Speaker verification | Resemblyzer | In-process |

#### Infrastructure & Ports
| Port | Service |
|---|---|
| 8765 | SaathiAI FastAPI (primary) |
| 8920 | OmniVoice TTS |
| 11434 | Ollama (local LLMs) |
| 11435 | Shimmy (TinyLlama 1.1B) |
| 8788 | Cheap LLM proxy |
| 5678 | n8n workflow engine |

#### Social Platform Integrations
| Platform | Tool | Auth |
|---|---|---|
| YouTube | YouTube Data API v3 | OAuth2 service account |
| TikTok | TikTok Content API | OAuth2 (client key in .env) |
| Instagram / Facebook | Meta Graph API | Long-lived page token |
| LinkedIn | LinkedIn API | OAuth2 (client secret in .env) |
| Twitter/X | Twitter API v2 | Bearer token |
| Telegram | Bot API | Bot token |

### 8.3 What We Deliberately Do Not Use

| Technology | Why Not |
|---|---|
| Kubernetes | Over-engineered for single-server, single-operator deployment |
| Celery | APScheduler is sufficient; Celery adds Redis dependency for no current benefit |
| GraphQL | REST is sufficient; GraphQL adds tooling overhead |
| Microservices | Monolith is correct at this scale; distributed system overhead is pure cost |
| Message queue (Kafka/RabbitMQ) | SQLite-based job queue is sufficient |

---

## Chapter 9 — Repository Strategy

### 9.1 Monorepo Philosophy

SaathiAI OS is a monorepo. All products, tools, agents, and infrastructure code live in `~/SaathiAI/`.

**Why monorepo:**
- Single import namespace (`from saathi.tools.content import ...`)
- Shared configuration, shared tests, shared dependency management
- No inter-repository dependency management overhead
- Single deployment artifact

**Exception:** pielts frontend lives in `~/Downloads/ielts-practice-app/` — a separate React SPA deployed to Firebase Hosting. It calls SaathiAI OS via API.

### 9.2 Directory Contract

| Directory | Responsibility |
|---|---|
| `saathi/` | Core Python package — the OS |
| `saathi/agents/` | BMA agent system |
| `saathi/memory/` | 3-tier memory system |
| `saathi/models/` | Shared data models (Pydantic + dataclasses) |
| `saathi/tools/` | Tool registry — all 70+ tool modules |
| `saathi/skills/` | Claude Code skill packs |
| `data/` | Local SQLite databases and data files |
| `static/` | Static assets served by FastAPI |
| `tests/` | All test files |
| `docs/` | This engineering specification |
| `docs/v1.0/` | v1.0 specification (this version) |
| `docs/Appendix/` | Reference documents (schema, API, events, etc.) |
| `n8n-workflows/` | n8n workflow JSON exports |
| `scripts/` | Utility scripts (maintenance, migration) |
| `deploy/` | Deployment configs |
| `videos_output/` | Rendered video output (gitignored except .gitkeep) |
| `research_cache/` | Research result cache (gitignored) |

### 9.3 Branching Strategy

```
main          — stable, deployed
│
├── feature/  — new features (branch from main, PR to main)
├── fix/      — bug fixes
└── spec/     — documentation updates
```

**Commit message convention:**
```
feat: add HCG Live Signal webhook endpoint
fix: correct form_completion blank-answer scoring in scoreListening()
spec: add 01_ARCHITECTURE.md to v1.0 docs
refactor: extract band-clamp logic to SafetyHarness.validate_output()
test: add 4 tests for EpisodicMemory.get_weakness_summary()
chore: update requirements.txt with pytest-asyncio
```

### 9.4 What Is Never Committed

| File / Pattern | Reason |
|---|---|
| `.env` | Contains all secrets |
| `firebase-admin.json` | Service account credentials |
| `data/*.db` | Local SQLite — too large, machine-specific |
| `videos_output/*.mp4` | Binary, too large |
| `__pycache__/`, `*.pyc` | Build artifacts |
| `.venv/` | Virtual environment |

---

# Part IV — Execution

---

## Chapter 10 — Roadmap & Phases

### 10.1 Phase Overview

```
Phase 1 — Foundation        [COMPLETE]
Phase 2 — Intelligence      [COMPLETE]
Phase 3 — Quality & Scale   [IN PROGRESS — 2026 Q3]
Phase 4 — Expansion         [PLANNED — 2026 Q4]
Phase 5 — Platform          [FUTURE — 2027+]
```

### 10.2 Phase 1 — Foundation (Complete)

**Delivered:**
- [x] FastAPI server with token auth (60+ endpoints)
- [x] Baadar agent with bilingual persona
- [x] Voice OS (STT + TTS + speaker verification on Mac)
- [x] Telegram bot (bidirectional control)
- [x] pielts web app (all 4 IELTS skills, scoring, Firebase)
- [x] Scheduler with 10+ autonomous jobs
- [x] HCGMS canteen monitoring integration

### 10.3 Phase 2 — Intelligence Layer (Complete)

**Delivered:**
- [x] BMA (Baadar Multi-Agent Architecture) — 4-phase loop, 7 sub-agents
- [x] 3-tier memory (Working ring buffer, Episodic SQLite, Semantic SQLite)
- [x] Safety Harness (ContentFilter, PedagogyChecker, BiasDetector)
- [x] Agent Message Bus (cross-skill escalation)
- [x] 30 tests passing (BMA + intelligence + referral)
- [x] Mr. Yeti content pipeline (trends → script → video → post)
- [x] CEO morning dashboard (Firebase + Telegram)
- [x] Opik LLM observability integration

### 10.4 Phase 3 — Quality & Scale (Current — 2026 Q3)

- [ ] Cloud deployment — SaathiAI runs 24/7 on Fly.io or Railway
- [ ] pielts Premium tier — payment integration, access gating
- [ ] ChromaDB semantic memory — vector search for pattern retrieval
- [ ] DeepEval IELTS benchmark — automated regression testing
- [ ] OpenObserve metrics — structured metrics dashboard
- [ ] HCG Live Signal v1 — real-time canteen event webhook processing
- [ ] Test coverage expansion — 30 → 80+ tests

**Definition of Done:**
- SaathiAI server running on cloud, uptime ≥ 99% over 30 days
- pielts Premium processing at least 1 paid subscription
- IELTS scoring accuracy within ±0.5 bands on 20-essay benchmark
- HCG Live Signal alerting on critical events

### 10.5 Phase 4 — Expansion (Planned — 2026 Q4)

- [ ] pielts mobile app (React Native)
- [ ] Mr. Yeti 3D character upgrade
- [ ] Pipecat voice pipeline (streaming, low-latency)
- [ ] Firecrawl integration (production web intelligence)
- [ ] HCGMS productisation (sell to other canteen operators)
- [ ] Travel Platform v0 (first routes and tools)

### 10.6 Phase 5 — Platform (Future — 2027+)

- [ ] Multi-operator deployment (other solo operators run their own instance)
- [ ] Developer SDK for building applications on SaathiAI OS
- [ ] Open-source release
- [ ] Published case study

---

## Chapter 11 — Coding Standards

These are enforced rules. A code review that finds a violation should block the merge.

### 11.1 Python Standards

**Type annotations are mandatory for all public functions:**
```python
async def get_history(student_id: str, limit: int = 50) -> list[dict]:
    ...
```

**All async functions use `async def`. No `asyncio.run()` inside route handlers.**

**No bare except clauses — always catch specific exception types.**

**Imports are sorted: stdlib → third-party → local.**

### 11.2 FastAPI Standards

- All routes have explicit `response_model`
- All route handlers are < 30 lines (business logic in service modules)
- All routes are in routers, not in `server.py` directly
- `server.py` mounts routers; it does not define routes

### 11.3 AI / LLM Standards

**Never hardcode model names in tool modules:**
```python
# Always
from saathi.config import MODEL_FAST
response = client.chat.completions.create(model=MODEL_FAST, ...)
```

**All LLM calls go through Opik tracing.**

**All LLM responses are validated and clamped before use:**
```python
try:
    parsed = json.loads(raw)
    band = float(parsed["band_estimate"])
    band = max(1.0, min(9.0, band))  # always clamp to valid IELTS range
except (json.JSONDecodeError, KeyError, ValueError):
    band = 5.0  # safe default
```

### 11.4 Security Standards

- Secrets are never in code or logs
- All student data is scoped to `student_id`
- File paths are sanitised before use (no path traversal)
- Speaker verification is required for privileged voice actions

### 11.5 Tool Module Standards

Every tool module in `saathi/tools/` must:
1. Export a clear public API with type annotations
2. Handle its own errors — never let exceptions propagate to the agent loop uncaught
3. Log its own activity (`logger = logging.getLogger(__name__)`)
4. Not import from other tools (use `tools/_llm_helper.py` for shared logic)
5. Be testable in isolation (no dependency on a running server)

---

## Chapter 12 — Success Metrics

### 12.1 Platform Health (Monthly)

| Metric | Target |
|---|---|
| Server uptime (when Mac on) | ≥ 99% |
| Scheduler job success rate | ≥ 98% |
| Test pass rate | 100% |
| LLM call success rate | ≥ 99.5% |
| Average BMA response latency | < 3 seconds |

### 12.2 pielts (Monthly)

| Metric | Target |
|---|---|
| Registered users | +200/month |
| Active users (≥ 1 practice test) | ≥ 40% of registered |
| Free → Premium conversion | ≥ 3% |
| Premium revenue (NPR) | ≥ 50,000/month |
| IELTS scoring accuracy | Within ±0.5 bands |

### 12.3 Mr. Yeti Content (Monthly)

| Metric | Target |
|---|---|
| YouTube subscribers | +500/month |
| TikTok followers | +1,000/month |
| Posts published (all platforms) | ≥ 120/month |
| Content pipeline failures | 0 |
| Average video CTR | ≥ 4% |

### 12.4 HCG Canteen (Daily)

| Metric | Target |
|---|---|
| Revenue vs. NPR 30,000 target | ≥ 90% achievement |
| Credit alerts delivered | ≤ 30 min after threshold |
| Daily summary delivered | By 7:15pm NPT |

### 12.5 AI Quality (Quarterly)

| Metric | Target |
|---|---|
| Writing eval correlation with human examiner | ≥ 0.75 Pearson |
| Cross-skill pattern detection accuracy | ≥ 85% |
| Safety filter false positive rate | < 2% |
| Memory context relevance | ≥ 90% |

---

## Chapter 13 — Future Vision

### 13.1 The 3-Year Picture

**Year 1 (2026):** Proof of concept — one operator, four products, autonomous operation
- SaathiAI runs on cloud (not Mac-dependent)
- pielts at 10,000 registered users, sustainable Premium revenue
- Mr. Yeti at 50,000 YouTube subscribers
- HCG Live Signal running autonomously

**Year 2 (2027):** Productisation — the OS becomes a product
- First external operator runs their own SaathiAI instance
- SDK released for building applications on SaathiAI OS
- HCGMS sold to 10+ canteen operators
- Travel Platform at revenue-generating stage

**Year 3 (2028):** Platform — SaathiAI as a company
- 10+ operators running SaathiAI instances
- Open-source core released as reference architecture
- Published case study (academic + practitioner)
- AI coaching (pielts model) licensed to language schools

### 13.2 The Architecture That Gets Us There

The decisions made in v1.0 were made with this trajectory in mind:

**FastAPI + monorepo:** New products are new routes. No microservices decomposition needed until operators × products demands it.

**3-tier memory:** The semantic tier scales to vector databases without breaking the interface. `HierarchicalMemory.get_context()` callers don't change when SQLite moves to ChromaDB moves to a cloud vector DB.

**Model router:** Adding a new LLM provider is a one-line config change. The system degrades gracefully when any provider is unavailable.

**Tool registry:** Adding a new capability is a new file in `saathi/tools/`. The agent loop picks it up automatically.

**OS framing:** New products are new route namespaces. They share everything. They cost near-zero to add once the OS is running.

### 13.3 What Will Not Change

Some decisions are fixed for the life of this platform:

1. **Python.** The AI ecosystem requires Python.
2. **Single-server monolith until scale demands otherwise.** Distributed systems are expensive in both ops cost and engineering complexity.
3. **Operator-controlled AI.** Ajay approves irreversible AI actions. Auto-approve can be granted per action type, but the capability for human override is never removed.
4. **Privacy by default.** Voice data, student data, and business data do not leave the Mac unless there is a specific, justified reason.

---

## Document Index

| # | Document | Summary | Status |
|---|---|---|---|
| 00 | `00_MASTER_ROADMAP.md` | **This document** — the constitution | ✅ v1.1 |
| 01 | `01_ARCHITECTURE.md` | FastAPI server, agent loop, component boundaries | 🔄 Next |
| 02 | `02_AGENT_SYSTEM.md` | BMA, sub-agents, harness, bus | Planned |
| 03 | `03_MEMORY_AND_KNOWLEDGE_GRAPH.md` | 3-tier memory, ChromaDB, knowledge graph | Planned |
| 04 | `04_VOICE_OS.md` | STT, TTS, speaker verify, Pipecat roadmap | Planned |
| 05 | `05_AI_STUDIO.md` | Research, scripting, content studio | Planned |
| 06 | `06_VIDEO_PIPELINE.md` | Google Flow, HyperFrames, subtitles | Planned |
| 07 | `07_CHARACTER_SYSTEM.md` | Mr. Yeti persona, memory, voice consistency | Planned |
| 08 | `08_AUTONOMOUS_COMPANY.md` | Scheduler, autopost, autonomous decision loop | Planned |
| 09 | `09_MISSION_CONTROL.md` | Telegram, CEO dashboard, alert routing | Planned |
| 10 | `10_INFRASTRUCTURE.md` | Firebase, SQLite, R2, Fly.io, Neon | Planned |
| 11 | `11_MODEL_ROUTER.md` | LLM provider selection, cost optimisation | Planned |
| 12 | `12_AUTOMATION.md` | n8n workflows, webhook design | Planned |
| 13 | `13_OBSERVABILITY.md` | Opik, OpenObserve, metrics, alerting | Planned |
| 14 | `14_EVALUATION.md` | IELTS scoring benchmark, DeepEval | Planned |
| 15 | `15_SECURITY.md` | Auth, speaker verify, data isolation, secrets | Planned |
| 16 | `16_DEPLOYMENT.md` | Dockerfile, Fly.io, Railway, CI/CD | Planned |
| 17 | `17_PRODUCTS.md` | pielts, Mr. Yeti, HCG POS, Live Signal, Travel | Planned |
| 18 | `18_DEVELOPMENT_GUIDE.md` | Dev setup, pyproject.toml, tests, workflow | Planned |
| 19 | `19_GITHUB_RESEARCH.md` | All researched repos, integration status | Planned |
| 20 | `20_FUTURE_ROADMAP.md` | Roadmap beyond v1.1 | Planned |

**Appendix:**

| # | Document | Contents |
|---|---|---|
| A | `Appendix/A_REPOSITORY_INDEX.md` | Complete file tree with one-line descriptions |
| B | `Appendix/B_DATABASE_SCHEMA.md` | All SQLite + Firebase schemas, full SQL |
| C | `Appendix/C_API_REFERENCE.md` | All 60+ endpoints, request/response schemas |
| D | `Appendix/D_EVENT_CATALOG.md` | All scheduler jobs, webhook events |
| E | `Appendix/E_AGENT_CAPABILITIES.md` | All 70+ tools with input/output contracts |
| F | `Appendix/F_CONFIGURATION.md` | All config keys, env vars, YAML config |
| G | `Appendix/G_GLOSSARY.md` | All terms used across the specification |

**Meta-documents (docs root):**

| File | Purpose |
|---|---|
| `CHANGELOG.md` | All significant changes, by version |
| `DECISIONS.md` | Architectural Decision Records (ADRs) |

---

## Glossary

| Term | Definition |
|---|---|
| **SaathiAI OS** | The operating system layer — FastAPI server + all services. Everything else runs on top of it. |
| **Baadar** | The primary human-to-OS interface. Bilingual AI operator (voice + text + Mac control). OS service, not a product. |
| **Application** | A product that runs on SaathiAI OS: pielts, Mr. Yeti, HCG POS, Live Signal, Travel. |
| **OS Service** | Shared infrastructure available to all applications: agent system, memory, scheduler, voice, tools. |
| **BMA** | Baadar Multi-Agent Architecture — the 4-phase AI processing loop (Perception → Decision → Action → Reflection). |
| **Sub-agent** | A specialised LLM agent within BMA for one IELTS skill. |
| **Master Loop** | The `MasterAgentLoop` class — coordinator of all 4 BMA phases. |
| **Safety Harness** | Pre/post validation wrapper: ContentFilter (regex), PedagogyChecker (band clamp), BiasDetector. |
| **Agent Message Bus** | Cross-skill event system — detects when the same error type appears in 2+ skills and escalates. |
| **Working Memory** | In-process `deque(maxlen=20)` — current session context. Zero latency. Lost on restart. |
| **Episodic Memory** | SQLite log of all past interactions. Async write, queryable history. |
| **Semantic Memory** | Pattern-extracted long-term knowledge: error types, weakness profiles, skill patterns. |
| **HierarchicalMemory** | Coordinator class writing to all three tiers and providing `get_context()`. |
| **Tool Registry** | `saathi/tools/registry.py` — unified schema for all 70+ tool modules. |
| **Model Router** | Logic in `config.py` that selects the right LLM provider per task type. |
| **Shimmy** | TinyLlama 1.1B local model at :11435 — cheapest classification tier. |
| **OmniVoice** | Custom TTS server with cloned voices at :8920. |
| **APScheduler** | Embedded job scheduler running 25+ autonomous jobs in-process. |
| **CEO Dashboard** | Morning briefing sent to Telegram at 8am NPT: pielts metrics, social stats, canteen status. |
| **pielts** | IELTS practice web app at pielts.web.app. |
| **Mr. Yeti** | The IELTS coaching character — white Yeti, round glasses, teacher suit. Mascot and content vehicle. |
| **HCG POS** | The canteen Point of Sale integration — Hamro Chamena Griha. |
| **HCG Live Signal** | Planned real-time canteen monitoring and alerting application. |
| **NPT** | Nepal Standard Time (UTC+5:45). |
| **Band score** | IELTS score on a 1.0–9.0 scale in 0.5 increments. |
| **SAATHI_TOKEN** | API authentication secret. Never exposed in responses, logs, or code. |
| **ADR** | Architectural Decision Record — documented in `docs/DECISIONS.md`. |
| **Constitution** | This document. Supersedes all other documents in case of conflict. |

---

*End of `00_MASTER_ROADMAP.md` — v1.1.0*

*This document is the constitution of SaathiAI OS. Ratified 2026-07-02.*
*It remains in effect until superseded by a new major version.*

*Next: [`01_ARCHITECTURE.md`](01_ARCHITECTURE.md)*

---

**Document Control**

| Field | Value |
|---|---|
| Document | 00_MASTER_ROADMAP.md |
| Version | 1.1.0 |
| Classification | Constitutional |
| Authors | Ajay Chaulagain (Chief Software Architect), Claude Sonnet 4.6 (Technical Writer) |
| Supersedes | v1.0/00_MASTER_ROADMAP.md (July 2026 — initial survey) |
| Location | `~/SaathiAI/docs/v1.0/00_MASTER_ROADMAP.md` |
| Next | `01_ARCHITECTURE.md` |
