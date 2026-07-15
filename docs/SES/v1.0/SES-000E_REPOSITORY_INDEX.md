```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : Repository Index
Document ID         : SES-000E
Version             : 0.2.0
Status              : Draft
Maturity            : L1
Classification      : Internal
Owner               : SaathiAI Architecture Team
Primary Repository  : github.com/chaulagainazay/SaathiAI
Created             : 2026-07-02
Last Updated        : 2026-07-15
Next Review         : 2026-10-02
================================================================================
```

---

## Revision History

| Version | Date | Author | Summary of Changes |
|---------|------|--------|--------------------|
| 0.1.0 | 2026-07-02 | Ajay Chaulagain | Initial draft — master index of integrated and evaluated repositories |
| 0.2.0 | 2026-07-15 | Ajay Chaulagain / ECP M17.24 | External Capability Program register (Priority 1–3); honest non-integrated status; skills foundation |
| 0.2.1 | 2026-07-15 | Ajay Chaulagain / M17.25 | MCP governance; Continuum remains BLOCKED_LICENSE; saathi-codebase-memory canonical |
| 0.2.2 | 2026-07-15 | Ajay Chaulagain / M18.3 | InsForge PILOT_APPROVED_READ_ONLY adapter registration |

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
| Part 6 | External Capability Program (Priority 1–3 register) |
| Part 7 | Honest status corrections (discovery ≠ integrated) |

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

---

# Part 6 — External Capability Program (ECP) Register

**Program:** SaathiOS External Capability Integration (Priority 1, 2, 3)
**Foundation milestone:** ECP M17.24 (docs + skills only; no runtime services)
**Status ladder:** EVALUATED → REGISTERED → BOUNDARY_DEFINED → PILOT_INSTALLED → CONFIGURED → FOCUSED_TESTED → INTEGRATED → STAGING_READY → PRODUCTION_APPROVAL_REQUIRED

**Important:** Naming collision — browser governance commits on this branch already used labels M17.24–M17.26. ECP milestones use the same numbers in the *program* document; git history for browser work is separate. This Part is **ECP register only**.

None of the following repositories is `INTEGRATED` as of 2026-07-15. Maximum status after foundation: **REGISTERED** (with BOUNDARY_DEFINED notes). Skills adapted for GSAP and Loop Engineering do **not** count as upstream runtime integration.

## Part 6.1 — Summary matrix

| Repository | Priority | Integration type | Current status | Local Mac suitability | Program pilot |
|------------|----------|------------------|----------------|----------------------|---------------|
| greensock/gsap-skills | P1 | Skill | REGISTERED | ON_DEMAND_LOCAL (skill only) | Skills foundation |
| pouyahasanamreji/continuum | P1 | MCP Server | REGISTERED + **BLOCKED_LICENSE** | ON_DEMAND_LOCAL | Deferred (licence); M17.25 governance uses saathi-codebase-memory |
| braedonsaunders/codeflow | P1 | CLI Tool | REGISTERED | ON_DEMAND_LOCAL | ECP M17.26 |
| cobusgreyling/loop-engineering | P1 | Skill | REGISTERED | ON_DEMAND_LOCAL (skill only) | Skills foundation |
| tracewayapp/traceway | P2 | External Service | REGISTERED | OPTIONAL_EXPERIMENT / evaluate vs OpenObserve | ECP M17.27 |
| VersusControl/versus-incident | P2 | External Service | REGISTERED | ON_DEMAND_LOCAL | ECP M17.28 |
| gtsteffaniak/filebrowser | P2 | External Service | REGISTERED | ON_DEMAND_LOCAL | ECP M17.29 |
| Leantime/leantime | P2 | External Service | REGISTERED | OPTIONAL_EXPERIMENT | ECP M17.30 |
| ATH-MaaS/Pixelle-Video | P3 | Adapter Pattern / External Service | REGISTERED | NOT_SUITABLE_FOR_8GB_MAC (likely) | Later P3 |
| Moh4696/freecut | P3 | Adapter Pattern | REGISTERED | OPTIONAL_EXPERIMENT | Later P3 |
| walterlow/freecut | P3 | External Service (browser editor) | REGISTERED | OPTIONAL_EXPERIMENT | Later P3 |
| mwakidenis/WebCheck-OSINT | P3 | CLI Tool / External Service | REGISTERED | ON_DEMAND_LOCAL | Later P3 |
| SendWithSES/Drag-and-Drop-Email-Designer | P3 | External Service / Adapter | REGISTERED | ON_DEMAND_LOCAL | Later P3 |
| Blotato-Inc/blotato-skills | P3 | Skill (partly) | REGISTERED | ON_DEMAND_LOCAL | Later P3 |
| AHS12/thoth-blueprint | P3 | External Service | REGISTERED | ON_DEMAND_LOCAL | Later P3 |
| HKUDS/Vibe-Trading | P3 | Adapter Pattern (research only) | REGISTERED | OPTIONAL_EXPERIMENT | Later P3 — **no live trading** |
| Fincept-Corporation/FinceptTerminal | P3 | External Service (UI research) | REGISTERED | OPTIONAL_EXPERIMENT | Later P3 — **no live trading** |

## Part 6.2 — Detailed records (ECP template)

Each record uses the ECP required fields. **Test evidence / adapter / health** are empty until pilot milestones.

### P1 — Developer productivity

#### greensock/gsap-skills

| Field | Value |
|-------|-------|
| Repository | github.com/greensock/gsap-skills |
| Priority | 1 |
| Capability | Frontend / HyperFrames animation guidance for agents |
| Current status | REGISTERED (+ skill adapted → `.grok/skills/frontend-gsap/`) |
| Integration type | Skill |
| Authoritative role | Coding-agent skill only |
| What it must not replace | HyperFrames runtime, render directors, ExecutionGateway |
| License | MIT (skills repo); GSAP library terms separate |
| Commercial-use implications | Skill text MIT; verify GSAP runtime licensing for production distribution |
| Runtime requirements | None for skill; browser/Chromium for HyperFrames renders |
| Credentials required | None |
| Data handled | None (skill markdown) |
| Security classification | Low |
| Local Mac suitability | ON_DEMAND_LOCAL |
| Deployment model | In-repo skill |
| SaathiOS adapter | N/A (skill); HyperFrames tool remains separate |
| Health check | Skill file presence (see tests) |
| Test evidence | `tests/test_m17_24_external_capability_foundation.py` |
| Rollback / disable method | Grok `[skills] disabled = ["frontend-gsap"]` or remove skill dir |
| Owner | SaathiOS Architecture |
| Deferred risks | GSAP Club plugins; CDN license review |

#### pouyahasanamreji/continuum

| Field | Value |
|-------|-------|
| Repository | github.com/pouyahasanamreji/continuum |
| Priority | 1 |
| Capability | Shared engineering knowledge memory for coding agents |
| Current status | REGISTERED + **BLOCKED_LICENSE** (BOUNDARY: not run ledger / CEO / TG memory; not installed) |
| Integration type | MCP Server |
| Authoritative role | **Non-authoritative** engineering lessons only (when/if licensed) |
| What it must not replace | Run ledger, CEO OS memory, SecurityStore, Trading Guardian ledger, user personal memory |
| License | **Unclear / not declared on GitHub API** — pilot blocked until clarified |
| Commercial-use implications | `REQUIRES_HUMAN_DECISION` before commercial redistribute |
| Runtime requirements | TBD pilot; keep project-path storage only |
| Credentials required | TBD |
| Data handled | Architecture lessons; **no secrets** |
| Security classification | Medium (memory poisoning risk) |
| Local Mac suitability | ON_DEMAND_LOCAL |
| Deployment model | Project MCP pilot |
| SaathiOS adapter | **Not installed** — M17.25 keeps BLOCKED_LICENSE; governance uses saathi-codebase-memory only |
| Health check | N/A until licence cleared |
| Test evidence | `tests/test_m17_25_mcp_governance.py` asserts BLOCKED_LICENSE / no dependency |
| Rollback / disable method | Do not enable; keep out of project MCP config |
| Owner | SaathiOS Architecture |
| Deferred risks | Missing license; namespace isolation; secret leakage |
| Operational status | **BLOCKED_LICENSE** (see docs/EXTERNAL_CAPABILITY_STATUS.md) |

#### braedonsaunders/codeflow

| Field | Value |
|-------|-------|
| Repository | github.com/braedonsaunders/codeflow |
| Priority | 1 |
| Capability | On-demand architecture maps, blast radius, cycles |
| Current status | REGISTERED |
| Integration type | CLI Tool |
| Authoritative role | Advisory architecture reports only |
| What it must not replace | ADRs, SES decisions, harness trust decisions |
| License | **Unclear / not declared** — clarify before pilot |
| Commercial-use implications | `REQUIRES_HUMAN_DECISION` if license remains missing |
| Runtime requirements | Node/browser on demand |
| Credentials required | None for public analysis |
| Data handled | Repo structure graphs (path-allowlisted) |
| Security classification | Medium |
| Local Mac suitability | ON_DEMAND_LOCAL |
| Deployment model | CLI adapter |
| SaathiOS adapter | Planned ECP M17.26 |
| Health check | Planned |
| Test evidence | None yet |
| Rollback / disable method | Env disable on adapter |
| Owner | SaathiOS Architecture |
| Deferred risks | Path escape; large-repo OOM on 8 GB |

#### cobusgreyling/loop-engineering

| Field | Value |
|-------|-------|
| Repository | github.com/cobusgreyling/loop-engineering |
| Priority | 1 |
| Capability | Autonomous development-loop methodology |
| Current status | REGISTERED (+ skill adapted → `.grok/skills/saathios-loop-engineering/`) |
| Integration type | Skill |
| Authoritative role | Methodology for agent loops |
| What it must not replace | Mission engine, approvals, run ledger, ExecutionGateway |
| License | MIT |
| Commercial-use implications | Permissive; do not bulk-vendor without attribution |
| Runtime requirements | None for skill; optional upstream CLIs are **out of foundation** |
| Credentials required | None |
| Data handled | None |
| Security classification | Low |
| Local Mac suitability | ON_DEMAND_LOCAL |
| Deployment model | In-repo skill |
| SaathiOS adapter | N/A |
| Health check | Skill file presence |
| Test evidence | `tests/test_m17_24_external_capability_foundation.py` |
| Rollback / disable method | Disable skill name |
| Owner | SaathiOS Architecture |
| Deferred risks | Upstream `loop-init` scaffold pollution if run without milestone |

### P2 — Production operations

#### tracewayapp/traceway

| Field | Value |
|-------|-------|
| Repository | github.com/tracewayapp/traceway |
| Priority | 2 |
| Capability | Observability (logs/traces/metrics/session) evaluation |
| Current status | REGISTERED — must compare to OpenObserve plan before authority |
| Integration type | External Service |
| Authoritative role | Candidate operational observability backend (**not yet selected**) |
| What it must not replace | Opik specialized LLM eval without decision; dual-authority with OpenObserve forbidden |
| License | MIT |
| Commercial-use implications | MIT OK; check telemetry data residency |
| Runtime requirements | Container/service; measure 8 GB impact |
| Credentials required | TBD |
| Data handled | Logs, traces, metrics, possible session replay |
| Security classification | High (PII/session) |
| Local Mac suitability | OPTIONAL_EXPERIMENT / possibly NOT_SUITABLE continuous |
| Deployment model | Isolated eval env |
| SaathiOS adapter | Planned ECP M17.27 evaluation only |
| Health check | Planned |
| Test evidence | None — evaluation ≠ integration |
| Rollback / disable method | Stop container; do not set as default exporter |
| Owner | SaathiOS Architecture |
| Deferred risks | Resource cost; session replay masking |

#### VersusControl/versus-incident

| Field | Value |
|-------|-------|
| Repository | github.com/VersusControl/versus-incident |
| Priority | 2 |
| Capability | Incident command / escalation (above monitoring) |
| Current status | REGISTERED |
| Integration type | External Service |
| Authoritative role | Incident command candidate; SaathiOS monitoring delivery remains authoritative substrate |
| What it must not replace | Telemetry backend; automatic repair; ToolIntent creation |
| License | MIT |
| Commercial-use implications | MIT |
| Runtime requirements | Separate process; training/shadow first |
| Credentials required | Webhook secrets |
| Data handled | Incident payloads (redact) |
| Security classification | High |
| Local Mac suitability | ON_DEMAND_LOCAL |
| Deployment model | Separate service |
| SaathiOS adapter | Planned ECP M17.28 |
| Health check | Planned |
| Test evidence | None yet |
| Rollback / disable method | Disable webhook; training mode |
| Owner | SaathiOS Architecture |
| Deferred risks | Alert storms; unauthorized repair paths |

#### gtsteffaniak/filebrowser

| Field | Value |
|-------|-------|
| Repository | github.com/gtsteffaniak/filebrowser |
| Priority | 2 |
| Capability | Human project/media file workspace UI |
| Current status | REGISTERED |
| Integration type | External Service |
| Authoritative role | Human browsing only |
| What it must not replace | Agent FS policy, Evidence, semantic index, backups, agent authz |
| License | Apache-2.0 |
| Commercial-use implications | Apache-2.0 NOTICE obligations if redistributed |
| Runtime requirements | Isolated mount of dedicated workspace only |
| Credentials required | Strong auth / OIDC |
| Data handled | Project assets |
| Security classification | High if mis-mounted |
| Local Mac suitability | ON_DEMAND_LOCAL |
| Deployment model | Container; **never mount $HOME** |
| SaathiOS adapter | Planned ECP M17.29 via ExecutionGateway for agent ops |
| Health check | Planned |
| Test evidence | None yet |
| Rollback / disable method | Stop service; revoke tokens |
| Owner | SaathiOS Architecture |
| Deferred risks | Path escape; anonymous share |

#### Leantime/leantime

| Field | Value |
|-------|-------|
| Repository | github.com/Leantime/leantime |
| Priority | 2 |
| Capability | Human PM (Kanban/Gantt/timesheets) |
| Current status | REGISTERED |
| Integration type | External Service |
| Authoritative role | Human planning surface only |
| What it must not replace | Missions, approvals, run ledger, CEO OS, autonomous execution |
| License | **AGPL-3.0** |
| Commercial-use implications | **Network/copyleft** — separate service + API only; no core embed; legal review before commercial SaaS |
| Runtime requirements | PHP stack / container; heavy for 8 GB continuous |
| Credentials required | App auth |
| Data handled | Human tasks/docs |
| Security classification | Medium |
| Local Mac suitability | OPTIONAL_EXPERIMENT |
| Deployment model | Separate service (AGPL boundary) |
| SaathiOS adapter | Planned ECP M17.30 |
| Health check | Planned |
| Test evidence | None yet |
| Rollback / disable method | Stop service |
| Owner | SaathiOS Architecture |
| Deferred risks | AGPL; dual PM confusion |

### P3 — Business product modules

#### ATH-MaaS/Pixelle-Video

| Field | Value |
|-------|-------|
| Repository | github.com/ATH-MaaS/Pixelle-Video |
| Priority | 3 |
| Capability | Automated short-video engine |
| Current status | REGISTERED |
| Integration type | Adapter Pattern / External Service |
| Authoritative role | Optional video backend candidate |
| What it must not replace | HyperFrames primary path without decision; OpenMontage boundary |
| License | Apache-2.0 |
| Commercial-use implications | Apache-2.0 |
| Runtime requirements | Likely GPU/heavy — 8 GB Mac unsuitable for continuous |
| Credentials required | Model/API keys TBD |
| Data handled | Scripts, media |
| Security classification | Medium |
| Local Mac suitability | NOT_SUITABLE_FOR_8GB_MAC (default assumption until measured) |
| Deployment model | Remote/on-demand |
| SaathiOS adapter | Deferred P3 |
| Health check | None |
| Test evidence | None |
| Rollback / disable method | Adapter off |
| Owner | SaathiOS Architecture |
| Deferred risks | Overlap with OpenMontage/HyperFrames/freecut |

#### Moh4696/freecut

| Field | Value |
|-------|-------|
| Repository | github.com/Moh4696/freecut |
| Priority | 3 |
| Capability | Automated video-use style editing (fork; free TTS path) |
| Current status | REGISTERED |
| Integration type | Adapter Pattern |
| Authoritative role | Optional editor automation |
| What it must not replace | Governed browser; ExecutionGateway |
| License | MIT |
| Commercial-use implications | MIT; check upstream browser-use lineage |
| Runtime requirements | Browser automation heavy |
| Credentials required | TBD |
| Data handled | Media |
| Security classification | High (browser automation) |
| Local Mac suitability | OPTIONAL_EXPERIMENT |
| Deployment model | On-demand |
| SaathiOS adapter | Deferred |
| Health check | None |
| Test evidence | None |
| Rollback / disable method | Adapter off |
| Owner | SaathiOS Architecture |
| Deferred risks | Duplicate vs walterlow/freecut |

#### walterlow/freecut

| Field | Value |
|-------|-------|
| Repository | github.com/walterlow/freecut |
| Priority | 3 |
| Capability | Browser-based visual video editor |
| Current status | REGISTERED |
| Integration type | External Service |
| Authoritative role | Human visual editor |
| What it must not replace | Studio directors without boundary |
| License | MIT |
| Commercial-use implications | MIT |
| Runtime requirements | Browser app |
| Credentials required | None/local |
| Data handled | Media |
| Security classification | Medium |
| Local Mac suitability | OPTIONAL_EXPERIMENT |
| Deployment model | On-demand browser |
| SaathiOS adapter | Deferred |
| Health check | None |
| Test evidence | None |
| Rollback / disable method | Do not link |
| Owner | SaathiOS Architecture |
| Deferred risks | Name collision with Moh4696/freecut |

#### mwakidenis/WebCheck-OSINT

| Field | Value |
|-------|-------|
| Repository | github.com/mwakidenis/WebCheck-OSINT |
| Priority | 3 |
| Capability | Website OSINT / recon |
| Current status | REGISTERED |
| Integration type | CLI Tool / External Service |
| Authoritative role | Explicit audit missions only |
| What it must not replace | Governed browser policy; legal authorization for scans |
| License | MIT |
| Commercial-use implications | MIT; **legal** ToS/CFAA risk on targets |
| Runtime requirements | Network recon tools |
| Credentials required | None |
| Data handled | Public recon data |
| Security classification | High (abuse risk) |
| Local Mac suitability | ON_DEMAND_LOCAL |
| Deployment model | Allowlisted targets only |
| SaathiOS adapter | Deferred |
| Health check | None |
| Test evidence | None |
| Rollback / disable method | Capability deny |
| Owner | SaathiOS Architecture |
| Deferred risks | Unauthorized scanning |

#### SendWithSES/Drag-and-Drop-Email-Designer

| Field | Value |
|-------|-------|
| Repository | github.com/SendWithSES/Drag-and-Drop-Email-Designer |
| Priority | 3 |
| Capability | Visual HTML email composition |
| Current status | REGISTERED |
| Integration type | External Service / Adapter Pattern |
| Authoritative role | Email template UI |
| What it must not replace | Send path / SES credentials / approval for outbound mail |
| License | MIT |
| Commercial-use implications | MIT |
| Runtime requirements | Web app |
| Credentials required | None for editor; send is separate |
| Data handled | Templates |
| Security classification | Medium (HTML injection) |
| Local Mac suitability | ON_DEMAND_LOCAL |
| Deployment model | Separate UI |
| SaathiOS adapter | Deferred |
| Health check | None |
| Test evidence | None |
| Rollback / disable method | Unlink UI |
| Owner | SaathiOS Architecture |
| Deferred risks | Name collision with Saathi **SES** engineering specs |

#### Blotato-Inc/blotato-skills

| Field | Value |
|-------|-------|
| Repository | github.com/Blotato-Inc/blotato-skills |
| Priority | 3 |
| Capability | Content marketing agent skills |
| Current status | REGISTERED |
| Integration type | Skill (partly) |
| Authoritative role | Optional marketing skill pack |
| What it must not replace | Publish connectors; n8n credentials; ExecutionGateway |
| License | **Unclear / not declared** |
| Commercial-use implications | `REQUIRES_HUMAN_DECISION`; SaaS terms for Blotato product separate |
| Runtime requirements | Skill install only |
| Credentials required | Blotato SaaS if publishing (separate) |
| Data handled | Skill text |
| Security classification | Low–Medium |
| Local Mac suitability | ON_DEMAND_LOCAL |
| Deployment model | Skill; SaaS remains external |
| SaathiOS adapter | None; n8n Blotato blueprint is **SaaS node**, not this repo |
| Health check | None |
| Test evidence | None |
| Rollback / disable method | Remove skills |
| Owner | SaathiOS Architecture |
| Deferred risks | Confusing SaaS vs skills |

#### AHS12/thoth-blueprint

| Field | Value |
|-------|-------|
| Repository | github.com/AHS12/thoth-blueprint |
| Priority | 3 |
| Capability | Visual database design |
| Current status | REGISTERED |
| Integration type | External Service |
| Authoritative role | Design aid only |
| What it must not replace | Production schemas / migrations without review |
| License | **GPL-3.0** |
| Commercial-use implications | GPL — keep separate; no proprietary embed |
| Runtime requirements | Web app |
| Credentials required | None |
| Data handled | Schema diagrams |
| Security classification | Low |
| Local Mac suitability | ON_DEMAND_LOCAL |
| Deployment model | Separate process |
| SaathiOS adapter | Deferred |
| Health check | None |
| Test evidence | None |
| Rollback / disable method | Stop service |
| Owner | SaathiOS Architecture |
| Deferred risks | GPL contamination if vendored |

#### HKUDS/Vibe-Trading

| Field | Value |
|-------|-------|
| Repository | github.com/HKUDS/Vibe-Trading |
| Priority | 3 |
| Capability | Trading research / agent ideas |
| Current status | REGISTERED — **research / paper / backtest only** |
| Integration type | Adapter Pattern |
| Authoritative role | Non-authoritative research inputs |
| What it must not replace | Trading Guardian; live execution; withdrawals |
| License | MIT |
| Commercial-use implications | MIT; still no live trading authorization |
| Runtime requirements | TBD; may be heavy |
| Credentials required | Market data keys only if ever piloted; **no trade keys** |
| Data handled | Market research |
| Security classification | Critical if mis-wired |
| Local Mac suitability | OPTIONAL_EXPERIMENT |
| Deployment model | Isolated research |
| SaathiOS adapter | Deferred; TG must remain |
| Health check | None |
| Test evidence | None |
| Rollback / disable method | Kill switch; no live keys |
| Owner | SaathiOS Architecture |
| Deferred risks | Accidental live trading |

#### Fincept-Corporation/FinceptTerminal

| Field | Value |
|-------|-------|
| Repository | github.com/Fincept-Corporation/FinceptTerminal |
| Priority | 3 |
| Capability | Finance UI / analytics inspiration |
| Current status | REGISTERED — UI/research only |
| Integration type | External Service / Skill patterns |
| Authoritative role | UI inspiration; not execution authority |
| What it must not replace | Trading Guardian; portfolio execution |
| License | **NOASSERTION / unclear** on GitHub API |
| Commercial-use implications | `REQUIRES_HUMAN_DECISION` before redistribute |
| Runtime requirements | Desktop app likely heavy |
| Credentials required | Market data if used |
| Data handled | Market analytics |
| Security classification | High if credentials |
| Local Mac suitability | OPTIONAL_EXPERIMENT |
| Deployment model | External app |
| SaathiOS adapter | Deferred |
| Health check | None |
| Test evidence | None |
| Rollback / disable method | Do not launch |
| Owner | SaathiOS Architecture |
| Deferred risks | License; live trading feature creep |

---

# Part 7 — Honest status corrections (discovery ≠ integrated)

The following third-party tracks had **discovery/docs** that used the word “Complete” while adapters remain stubs. Correct classification:

| Track | Prior claim | Correct status (2026-07-15) | Evidence |
|-------|-------------|----------------------------|----------|
| OpenMontage | WRAP ✅ Complete | DISCOVERY_COMPLETE / adapter **stub** | `saathi/execution/adapters/openmontage_adapter.py` TODO health/execute |
| OpenJarvis | WRAP ✅ Complete | DISCOVERY_COMPLETE / adapter **stub** | `openjarvis_adapter.py` TODO |
| claude-video | WRAP ✅ Complete | DISCOVERY_COMPLETE / adapter **stub** | `claude_video_adapter.py` TODO |
| HyperFrames (SES Core) | Integrated | PARTIAL — tool path exists; not full Studio productization | `saathi/tools/hyperframes.py` |
| OpenAI SDK (SES Rejected as primary) | Rejected primary | Still in `requirements.txt` as dependency — SES wording is “not primary”, not “purged” | requirements |
| ElevenLabs (SES Rejected) | Rejected | Still documented in `.env.example` as optional cloud path | env example |

Authoritative decision file corrections: `docs/integrations/REPOSITORY_DECISIONS.md` (ECP M17.24).

---



---

## Part 6.x — InsForge (M18.3 pilot)

| Field | Value |
|-------|-------|
| Repository | github.com/InsForge/InsForge |
| Priority | Optional product-backend infrastructure |
| Capability | Postgres, product auth, storage, edge functions, logs (read-only pilot) |
| Current status | **PILOT_APPROVED_READ_ONLY** (BOUNDARY_DEFINED) |
| Integration type | Adapter Pattern / External Service |
| Authoritative role | **Non-authoritative data plane** for product backends only |
| What it must not replace | Mission engine, ExecutionGateway, memory, Model Router, scheduler, event bus, SES, Trading Guardian |
| License | **Apache-2.0** |
| Commercial-use implications | Permissive; retain notice |
| Runtime requirements | Prefer cloud/remote; local Docker not default on 8 GB Mac |
| Credentials required | Optional `SAATHI_INSFORGE_API_KEY`; never commit |
| Data handled | Product backend metadata/logs (sanitized) |
| Security classification | Medium (admin APIs exist upstream — adapter allowlists reads only) |
| Local Mac suitability | ON_DEMAND_REMOTE / CLOUD preferred |
| Deployment model | External; SaathiOS does not vendor full stack |
| SaathiOS adapter | `saathi/providers/insforge` (GET-only) |
| Health check | `InsForgeProvider.health()` |
| Test evidence | `tests/test_m18_3_insforge_provider.py` |
| Rollback / disable method | `SAATHI_INSFORGE_ENABLED=0` (default) |
| Owner | SaathiOS Architecture |
| Deferred risks | Writes; raw MCP; dual memory/schedules; resource cost of local compose |
| Blocked interfaces | migrations, secrets write, memory, schedules, AI gateway as Model Router, trading, unrestricted MCP |


*End of SES-000E Repository Index — Version 0.2.0*

*Status: Draft (L1)*

*Next: [`SES-000F_CAPABILITY_REGISTRY.md`](SES-000F_CAPABILITY_REGISTRY.md)*
*ECP companion: [`docs/integrations/MCP_PROJECT_INVENTORY.md`](../../integrations/MCP_PROJECT_INVENTORY.md)*
*ECP validation: [`docs/M17_24_EXTERNAL_CAPABILITY_FOUNDATION.md`](../../M17_24_EXTERNAL_CAPABILITY_FOUNDATION.md)*
