```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : Glossary
Document ID         : SES-000B
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
| 0.1.0 | 2026-07-02 | Ajay Chaulagain | Initial shell — awaiting content |

---

## Purpose

This document is the single authoritative source of terminology for the entire SaathiAI Engineering Specification. Every term used in SES-000 through SES-020 that is not standard English or common software engineering vocabulary must be defined here.

The purpose of a shared glossary is to eliminate ambiguity. When an AI coding agent reads "BMA", it must find the definition here. When a new engineer reads "Working Memory", the definition here is authoritative — not the definition they may have learned elsewhere.

Rules for this document:
- One term per entry. No grouped definitions.
- Definitions are prescriptive (what the term means in SaathiAI), not descriptive (what it might mean in general).
- If a term is used differently in SaathiAI than in the broader industry, the difference must be explicitly noted.
- Terms are listed alphabetically within each category.

---

## Audience

| Role | Required Sections | Notes |
|------|------------------|-------|
| All Engineers | All | Read before working in any SES document |
| AI Coding Agents | All | Every term is a constraint — use definitions as written |
| New Contributors | All | Start here before reading any other SES document |

---

## Reading Order

```
SES-000A Document Standard
        │
        ▼
SES-000B Glossary  ← You are here
        │
        ▼
SES-000 Master Roadmap
```

---

## Document Structure

| Section | Title | Summary |
|---------|-------|---------|
| Part 1 | Platform Terms | Core SaathiAI OS and architecture vocabulary |
| Part 2 | Agent Terms | BMA, agent roles, agent lifecycle |
| Part 3 | Memory Terms | Three-tier memory system vocabulary |
| Part 4 | Product Terms | HCG POS, pielts, HCG Live Signal, Travel, Mr. Yeti |
| Part 5 | Infrastructure Terms | Deployment, scheduling, monitoring |
| Part 6 | Documentation Terms | SES, ADR, maturity levels |

---

# Part 1 — Platform Terms

| Term | Definition |
|------|------------|
| **SaathiAI** | The AI Operating System that runs all SaathiAI products. Not a single application — an operating system that provides shared AI infrastructure to every product built on it. |
| **SaathiAI OS** | Synonym for SaathiAI used when emphasizing the OS metaphor. The kernel of the platform. |
| **Application** | A product (HCG POS, pielts, HCG Live Signal, Travel Platform) that runs on the SaathiAI OS. Applications consume OS-level capabilities through the SaathiAI API. |
| **Capability** | A platform-level function that any application can use. Examples: voice, memory, research, scheduling. Capabilities are documented in SES-000F. |
| **Department** | A logical grouping of related capabilities owned by a team. The four departments are: Core Platform, Voice, Studio, Research. |
| **Platform-First Design** | The principle that any capability useful to more than one product must be implemented at the platform level, not inside a product. Defined in SES-000A Part 7. |
| **Provider Abstraction** | The pattern of placing all external API calls (LLM providers, TTS providers, storage providers) behind an interface layer so providers can be swapped without changing business logic. |
| **Model Router** | The component that selects which LLM provider to use for a given request based on task type, cost, latency, and fallback rules. |
| **Tool Module** | A Python callable registered in the SaathiAI tool registry, available to AI agents. Named using snake_case. Example: `research_web`, `send_telegram`. |
| **Tool Registry** | The catalogue of all available Tool Modules, their signatures, and their access permissions. |

---

# Part 2 — Agent Terms

| Term | Definition |
|------|------------|
| **BMA** | Baadar Multi-Agent Architecture. The 4-phase agent loop (Perception → Decision → Action → Reflection) that governs how SaathiAI processes requests. Defined in SES-002. |
| **Sub-Agent** | A specialized agent within the BMA responsible for a specific function. The seven sub-agents are: Writing, Speaking, Reading, Listening, Grammar, Vocabulary, Pronunciation. |
| **AgentMessageBus** | The internal message bus that routes messages between sub-agents within a single BMA cycle. |
| **SafetyHarness** | The component that validates every agent action against defined safety rules before execution. Actions that fail validation are rejected and logged. |
| **Perception Phase** | Phase 1 of the BMA loop. The system receives input (text, voice, API call) and classifies intent. |
| **Decision Phase** | Phase 2 of the BMA loop. The system selects which sub-agents and tools to invoke. |
| **Action Phase** | Phase 3 of the BMA loop. Sub-agents execute their tasks, calling tools as needed. |
| **Reflection Phase** | Phase 4 of the BMA loop. The system evaluates the output quality, logs the result, and updates memory. |
| **Orchestrator** | The top-level agent that coordinates the BMA loop. Does not execute tasks directly — delegates to sub-agents. |
| **Autonomous Job** | A scheduled task that runs without user input, governed by APScheduler. |

---

# Part 3 — Memory Terms

| Term | Definition |
|------|------------|
| **Working Memory** | Tier 1 of the three-tier memory system. An in-process Python `deque(maxlen=20)` that holds the current session context. Zero latency. Lost when the process restarts. |
| **Episodic Memory** | Tier 2 of the three-tier memory system. A SQLite database that stores the full interaction log. Persisted across sessions. Queryable by date, product, and agent. |
| **Semantic Memory** | Tier 3 of the three-tier memory system. Extracted patterns and knowledge, stored in SQLite with planned ChromaDB upgrade for vector search. Slow-changing. |
| **Memory Tier** | A specific level of the three-tier memory hierarchy. Referenced as "Working" (Tier 1), "Episodic" (Tier 2), or "Semantic" (Tier 3). |
| **Knowledge Graph** | The planned graph database (Neo4j or equivalent) that will represent relationships between entities across products. Defined in SES-003. |

---

# Part 4 — Product Terms

| Term | Definition |
|------|------------|
| **HCG POS** | HCG Point of Sale. The canteen management system for HCGMS. A SaathiAI application. |
| **HCGMS** | HCG Management System. The parent system for the canteen at Himalayan College of Geomatic Sciences. |
| **pielts** | The IELTS practice web application at pielts.web.app. A SaathiAI application. Uses Firebase for student data and Firebase Hosting for deployment. |
| **HCG Live Signal** | Real-time canteen monitoring and analytics application. A SaathiAI application. Note: NOT a crypto trading product. |
| **Travel Platform** | Planned SaathiAI application for travel planning and booking. Status: Planned (Phase 3). |
| **Mr. Yeti** | The AI teacher character for pielts and SaathiAI content. A friendly Yeti with white fur, round glasses, and a teacher suit. Used across video content, social media, and in-app coaching. |
| **Baadar** | The social media and content engine built on SaathiAI. The name of the main AI agent persona for the SaathiAI platform. Located at `~/SaathiAI`. |
| **Band Score** | The IELTS scoring unit. Range: 1–9 in 0.5 increments. pielts evaluates student responses and returns a Band Score. |

---

# Part 5 — Infrastructure Terms

| Term | Definition |
|------|------------|
| **APScheduler** | Advanced Python Scheduler. The embedded job scheduler running inside the FastAPI process. Manages all 25+ autonomous jobs. |
| **Groq** | The primary LLM inference provider. Uses `llama-3.3-70b-versatile` as the standard model. Selected for speed and cost. |
| **Shimmy** | TinyLlama 1.1B running locally via Ollama. The ultra-low-cost model for high-volume screening tasks. |
| **OmniVoice** | The self-hosted TTS system running on port 8920. Provides voice cloning for Baadar and Mr. Yeti personas. |
| **Firebase RTDB** | Firebase Realtime Database. Used by pielts to store student scores and progress. |
| **R2** | Cloudflare R2 object storage. Used for video assets, exports, and backups. |
| **Opik** | The observability platform for SaathiAI. Records LLM traces, latency metrics, and agent performance. |
| **HyperFrames** | The HTML-to-video rendering tool used by the Mr. Yeti video pipeline. |
| **WAL Mode** | Write-Ahead Logging mode for SQLite. Enables concurrent reads without blocking writes. Enabled on all SaathiAI SQLite databases. |

---

# Part 6 — Documentation Terms

| Term | Definition |
|------|------------|
| **SES** | SaathiAI Engineering Specification. The formal name for the entire documentation system. Governed by SES-000A. |
| **ADR** | Architecture Decision Record. A document that captures a significant architectural decision, its context, rationale, alternatives, and consequences. Stored in `docs/decisions/`. |
| **L1–L5** | The five maturity levels of SES documents. Defined in SES-000A Part 13. L1 = Draft; L5 = Production Validated. |
| **Implementation Checklist** | A sequenced list of verifiable steps in every SES document. A coding agent must be able to execute these steps in order without additional context. |
| **Acceptance Criteria** | Measurable conditions that must be true for a subsystem to be considered complete. Abbreviated AC. |
| **Platform-First Deviation** | A documented exception to the Platform-First Design Principle, approved via ADR, for capabilities that are irreducibly product-specific or where time constraints prevent platform-level implementation. |
| **Foundation Documents** | The SES-000 series (SES-000 through SES-000F). Every other SES document references at least one Foundation Document. |
| **Volume-1** | The first complete version of the SES specification, comprising SES-000 through SES-020 and Appendices A–G. |

---

# Acceptance Criteria

| # | Criterion | Verification Method | Priority |
|---|-----------|---------------------|----------|
| AC-001 | Every term used across SES-000 through SES-020 that is not standard English or common software engineering vocabulary appears in this glossary | Cross-reference scan of all approved SES documents against this glossary | Must Have |
| AC-002 | No term appears in two different SES documents with different definitions | Text search for term usages across all documents | Must Have |
| AC-003 | Every entry has a prescriptive definition (what it means in SaathiAI, not what it might mean in general) | Manual review of each entry | Should Have |

---

# Implementation Checklist

**Phase 1 — Core Terms**
- [x] Platform Terms section
- [x] Agent Terms section
- [x] Memory Terms section
- [x] Product Terms section
- [x] Infrastructure Terms section
- [x] Documentation Terms section

**Phase 2 — Cross-Reference Validation**
- [ ] Read all approved SES documents and add any undefined terms found
- [ ] Verify no term has conflicting definitions across documents

---

# Risks

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R-001 | Glossary falls out of sync as documents are written | High | Medium | Add "update glossary" as a step in every SES document's Implementation Checklist |

---

# Dependencies

**Internal:** None. This document has no internal dependencies — it is a foundation document.

**External:** None.

---

# Decision References

None. No ADRs govern this document's content.

---

# Open Questions

| # | Question | Owner | Target Date | Status |
|---|----------|-------|-------------|--------|
| OQ-001 | Should the Glossary be available as a machine-readable JSON file for AI agent use? | Ajay Chaulagain | 2026-09-01 | Open |

---

# Future Improvements

| # | Improvement | Target Phase | Notes |
|---|-------------|-------------|-------|
| FI-001 | Auto-generate glossary cross-reference links across all SES documents | Phase 3 | Would require a documentation build pipeline |

---

# Related Documents

| Document ID | Title | Relationship |
|-------------|-------|-------------|
| SES-000A | Document Standard | Governing standard for this document |
| SES-000 | Master Roadmap | Uses terms defined here |
| All SES-001 through SES-020 | — | All use terms defined here |

---

# References

None.

---

*End of SES-000B Glossary — Version 0.1.0*

*Status: Draft (L1) — Advance to L2 after cross-reference review of all SES documents*

*Next: [`SES-000C_ARCHITECTURE_PRINCIPLES.md`](SES-000C_ARCHITECTURE_PRINCIPLES.md)*
