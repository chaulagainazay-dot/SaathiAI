```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : Repository Index
Document ID         : SES-000E
Version             : 0.1.0
Status              : Draft
Maturity            : L1
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
| 0.1.0 | 2026-07-02 | Ajay Chaulagain | Initial draft — master index of integrated and evaluated repositories |

---

## Purpose

This document is the master index of every external repository evaluated for integration into SaathiAI. It is the enforcement mechanism for Engineering Value EV-07 (record major decisions using ADRs) and Architecture Principle AP-10 (Capability Reuse).

Before integrating any new external repository, an engineer must:
1. Check this index to confirm it has not already been evaluated
2. Add a record to this index when beginning evaluation
3. Complete the record with an integration level and rationale before closing the evaluation

This document supersedes the ADR entries in `docs/DECISIONS.md` for repository-specific decisions. DECISIONS.md remains as a historical record.

The detailed specification for what each field means is in SES-000A Part 9 (Repository Integration Standard).

---

## Audience

| Role | Required Sections | Notes |
|------|------------------|-------|
| Software Engineers | All | Check before adding any new dependency |
| AI Coding Agents | All | Do not import a repository not listed here as Core or Optional |
| Product Architects | All | Use to understand the full dependency surface |

---

## Reading Order

```
SES-000A Document Standard (Part 9 — Repository Integration Standard)
        │
        ▼
SES-000E Repository Index  ← You are here
```

---

## Document Structure

| Section | Content |
|---------|---------|
| Part 1 | Master Integration Matrix (summary table) |
| Part 2 | Core Repositories — detailed records |
| Part 3 | Optional Repositories — detailed records |
| Part 4 | Research Repositories — under evaluation |
| Part 5 | Rejected Repositories — evaluated and declined |

---

# Part 1 — Master Integration Matrix

| Repository | Category | Level | Subsystem | Status | ADR |
|------------|----------|-------|-----------|--------|-----|
| FastAPI | Web Framework | Core | SES-007 | Integrated | ADR-0001 |
| Pydantic v2 | Validation | Core | SES-007 | Integrated | — |
| SQLite (stdlib) | Database | Core | SES-003 | Integrated | ADR-0002 |
| APScheduler | Scheduling | Core | SES-010 | Integrated | ADR-0004 |
| Groq SDK | LLM | Core | SES-002 | Integrated | ADR-0003 |
| Anthropic SDK | LLM | Core | SES-002 | Integrated | ADR-0003 |
| Ollama | LLM | Core | SES-002 | Integrated | ADR-0003 |
| Firebase Admin | Auth/DB | Core | pielts | Integrated | ADR-0005 |
| HyperFrames | Video | Core | SES-006 | Integrated | ADR-0010 |
| OmniVoice | TTS | Core | SES-004 | Integrated | ADR-0008 |
| Opik | Observability | Core | SES-008 | Integrated | — |
| ChromaDB | Vector Search | Optional | SES-003 | Planned (Phase 6) | — |
| Pipecat | Voice Pipeline | Research | SES-004 | Under Evaluation | — |
| Crawl4AI | Web Scraping | Research | SES-005 | Partial | — |
| Neo4j | Graph DB | Research | SES-003 | Under Evaluation | — |
| ElevenLabs | TTS | Rejected | SES-004 | Rejected | ADR-0008 |
| OpenAI SDK | LLM | Rejected | SES-002 | Rejected (cost) | ADR-0003 |

---

# Part 2 — Core Repositories

## FastAPI

| Field | Value |
|-------|-------|
| Repository | github.com/fastapi/fastapi |
| Purpose | Async web framework powering all SaathiAI API endpoints |
| Integration Level | Core |
| Subsystem | SES-007 API Gateway |
| Reason for Selection | Native async/await, automatic OpenAPI docs, Pydantic integration, WebSocket support |
| Alternatives Considered | Django, Flask, Quart |
| Why Alternatives Were Rejected | Django: ORM and template overhead not needed. Flask: no native async. |
| Dependencies Introduced | Starlette, uvicorn |
| Migration Complexity | High (would require full rewrite) |
| Owner | Ajay Chaulagain |
| Status | Integrated |
| ADR Reference | ADR-0001 |

## SQLite (Python stdlib)

| Field | Value |
|-------|-------|
| Repository | Python standard library (aiosqlite for async access) |
| Purpose | Primary database for all server-side state, episodic memory, job logs, analytics |
| Integration Level | Core |
| Subsystem | SES-003 Memory & Knowledge Graph |
| Reason for Selection | Zero ops overhead, WAL mode concurrency, trivially backed up, sufficient for single-server |
| Alternatives Considered | Postgres (local), Supabase |
| Why Alternatives Were Rejected | Postgres: higher ops burden at current scale. Supabase: cost and complexity before product-market fit. |
| Dependencies Introduced | aiosqlite |
| Migration Complexity | Medium (schema migration to Postgres via Neon is the planned path) |
| Owner | Ajay Chaulagain |
| Status | Integrated |
| ADR Reference | ADR-0002 |

## Groq SDK

| Field | Value |
|-------|-------|
| Repository | github.com/groq/groq-python |
| Purpose | Primary LLM inference provider — llama-3.3-70b-versatile for standard tasks |
| Integration Level | Core |
| Subsystem | SES-002 Agent System |
| Reason for Selection | Fastest inference available; llama-3.3-70b-versatile matches GPT-4o quality at lower cost |
| Alternatives Considered | OpenAI, Anthropic as primary |
| Why Alternatives Were Rejected | OpenAI: 5-10× higher cost. Anthropic: higher cost; reserved for reasoning tasks. |
| Dependencies Introduced | groq |
| Migration Complexity | Low (abstracted behind provider layer) |
| Owner | Ajay Chaulagain |
| Status | Integrated |
| ADR Reference | ADR-0003 |

## APScheduler

| Field | Value |
|-------|-------|
| Repository | github.com/agronholm/apscheduler |
| Purpose | Embedded job scheduler for 25+ autonomous scheduled jobs |
| Integration Level | Core |
| Subsystem | SES-010 Automation Engine |
| Reason for Selection | No external dependencies (no Redis/Celery), shares process memory, simple API |
| Alternatives Considered | Celery + Redis, n8n, Cloud Tasks |
| Why Alternatives Were Rejected | Celery: infrastructure overhead. n8n: better for webhook workflows, not code-heavy jobs. Cloud Tasks: requires cloud deployment not yet needed. |
| Dependencies Introduced | APScheduler 3.x |
| Migration Complexity | Medium (Celery migration path when scaling to cloud) |
| Owner | Ajay Chaulagain |
| Status | Integrated |
| ADR Reference | ADR-0004 |

## HyperFrames

| Field | Value |
|-------|-------|
| Repository | Internal — `~/.claude/skills/hyperframes/` |
| Purpose | HTML/CSS to video rendering for Mr. Yeti video pipeline |
| Integration Level | Core |
| Subsystem | SES-006 AI Studio |
| Reason for Selection | HTML/CSS layout eliminates FFmpeg filter graph complexity; compositions are version-controlled |
| Alternatives Considered | FFmpeg direct, MoviePy |
| Why Alternatives Were Rejected | FFmpeg: extremely verbose for text-heavy video. MoviePy: adds abstraction without solving layout problem. |
| Dependencies Introduced | Chromium (via Playwright), FFmpeg |
| Migration Complexity | Low |
| Owner | Ajay Chaulagain |
| Status | Integrated |
| ADR Reference | ADR-0010 |

## OmniVoice

| Field | Value |
|-------|-------|
| Repository | Self-hosted on port 8920 |
| Purpose | TTS and voice cloning for Baadar persona and Mr. Yeti character |
| Integration Level | Core |
| Subsystem | SES-004 Voice OS |
| Reason for Selection | Zero per-character cost; biometric voice data stays on-device; ~50ms latency vs 200-400ms for cloud TTS |
| Alternatives Considered | ElevenLabs, OpenAI TTS |
| Why Alternatives Were Rejected | ElevenLabs: recurring cost; voice data leaves device. OpenAI TTS: no custom voice clone; data leaves device. |
| Dependencies Introduced | OmniVoice server (self-hosted) |
| Migration Complexity | Low |
| Owner | Ajay Chaulagain |
| Status | Integrated |
| ADR Reference | ADR-0008 |

---

# Part 3 — Optional Repositories

## ChromaDB

| Field | Value |
|-------|-------|
| Repository | github.com/chroma-core/chroma |
| Purpose | Vector database for Semantic Memory tier — enabling similarity search over long-term knowledge |
| Integration Level | Optional |
| Subsystem | SES-003 Memory & Knowledge Graph |
| Reason for Selection | Purpose-built for embedding storage and similarity search; embeds easily into Python process |
| Alternatives Considered | Pinecone, Weaviate, pgvector |
| Why Alternatives Were Rejected | Pinecone: cloud-only, cost. Weaviate: heavy for current scale. pgvector: not yet available in SQLite. |
| Dependencies Introduced | chromadb |
| Migration Complexity | Low (Semantic Memory tier degrades to SQL pattern-count without it) |
| Owner | Ajay Chaulagain |
| Status | Planned — Phase 6 |
| ADR Reference | ADR-0007 (parent decision) |

---

# Part 4 — Research Repositories

## Pipecat

| Field | Value |
|-------|-------|
| Repository | github.com/pipecat-ai/pipecat |
| Purpose | Real-time voice pipeline framework — STT → LLM → TTS as a composable pipeline |
| Integration Level | Research |
| Subsystem | SES-004 Voice OS |
| Reason for Selection | Open-source; handles WebRTC, STT, LLM, TTS pipeline composition; active development |
| Alternatives Considered | LiveKit Agents, direct WebRTC |
| Why Alternatives Were Rejected | Under evaluation |
| Dependencies Introduced | pipecat, Daily.co or WebRTC provider |
| Migration Complexity | Medium |
| Owner | Ajay Chaulagain |
| Status | Under Evaluation |
| ADR Reference | — (ADR to be written after evaluation) |
| Notes | Key question: does Pipecat integrate with OmniVoice for local TTS? Evaluate before Phase 2. |

## Crawl4AI

| Field | Value |
|-------|-------|
| Repository | github.com/unclecode/crawl4ai |
| Purpose | LLM-optimized web scraper for Research Engine — extracts structured content from web pages |
| Integration Level | Research |
| Subsystem | SES-005 Research Engine |
| Reason for Selection | Optimized for LLM consumption; handles JavaScript-rendered pages; returns clean markdown |
| Alternatives Considered | BeautifulSoup, Playwright direct, Firecrawl |
| Why Alternatives Were Rejected | BeautifulSoup: no JS rendering. Playwright direct: requires more code for content extraction. |
| Dependencies Introduced | crawl4ai, Playwright |
| Migration Complexity | Low |
| Owner | Ajay Chaulagain |
| Status | Partial integration |
| Notes | Currently used ad-hoc in research tools. Formalize as a Core tool module in Phase 2. |

## Neo4j

| Field | Value |
|-------|-------|
| Repository | neo4j.com / github.com/neo4j/neo4j-python-driver |
| Purpose | Graph database for Knowledge Graph — representing relationships between entities across products |
| Integration Level | Research |
| Subsystem | SES-003 Memory & Knowledge Graph |
| Reason for Selection | Native graph storage and traversal; Cypher query language; strong Python driver |
| Alternatives Considered | ArangoDB, TigerGraph, DGraph |
| Why Alternatives Were Rejected | Under evaluation |
| Dependencies Introduced | neo4j (driver), Neo4j server (self-hosted or AuraDB) |
| Migration Complexity | High (new infrastructure component) |
| Owner | Ajay Chaulagain |
| Status | Under Evaluation — Phase 4 |
| Notes | SQLite can represent simple graph relationships via adjacency tables. Evaluate Neo4j only when graph queries become complex enough to justify the overhead. |

---

# Part 5 — Rejected Repositories

## ElevenLabs

| Field | Value |
|-------|-------|
| Repository | github.com/elevenlabs/elevenlabs-python |
| Purpose | Cloud TTS with voice cloning |
| Integration Level | Rejected |
| Subsystem | SES-004 Voice OS |
| Reason for Rejection | Per-character cost becomes significant at scale. Voice data (biometric) leaves the device. Latency 200-400ms vs 50ms local. |
| Replacement | OmniVoice (self-hosted) |
| ADR Reference | ADR-0008 |

## OpenAI SDK (as primary provider)

| Field | Value |
|-------|-------|
| Repository | github.com/openai/openai-python |
| Purpose | GPT-4o LLM inference |
| Integration Level | Rejected |
| Subsystem | SES-002 Agent System |
| Reason for Rejection | 5-10× higher cost than Groq for equivalent quality on standard tasks |
| Replacement | Groq (llama-3.3-70b-versatile) as primary; Anthropic Claude for reasoning tasks |
| ADR Reference | ADR-0003 |
| Notes | OpenAI is not ruled out permanently — may be re-evaluated if GPT-5 offers meaningfully better quality at competitive pricing |

---

# Acceptance Criteria

| # | Criterion | Verification Method | Priority |
|---|-----------|---------------------|----------|
| AC-001 | Every Python package in `requirements.txt` that is not standard library has an entry in this index | Cross-reference `requirements.txt` with Part 1 | Must Have |
| AC-002 | Every rejected repository has a documented reason for rejection | Review Part 5 for completeness | Must Have |
| AC-003 | No `import` statement in `app/` references a repository listed as "Rejected" or "Research" | Grep scan of imports against rejected/research list | Must Have |

---

# Implementation Checklist

**Phase 1 — Index Population**
- [x] Populate all currently integrated repositories (Core)
- [x] Document all rejected repositories with rationale
- [ ] Add remaining research repositories currently in use
- [ ] Cross-reference against `requirements.txt` for completeness

**Phase 2 — Maintenance**
- [ ] Add "update SES-000E" to the checklist for any PR that adds a new dependency

---

# Dependencies

**Internal:** SES-000A Part 9 (Repository Integration Standard — the format this document uses)

**External:** None.

---

# Related Documents

| Document ID | Title | Relationship |
|-------------|-------|-------------|
| SES-000A | Document Standard | Part 9 defines the record format used here |
| SES-019 | GitHub Research | Companion document with deeper research notes on evaluated repositories |
| All ADRs | — | Repository-specific ADRs are referenced here |

---

*End of SES-000E Repository Index — Version 0.1.0*

*Status: Draft (L1)*

*Next: [`SES-000F_CAPABILITY_REGISTRY.md`](SES-000F_CAPABILITY_REGISTRY.md)*
