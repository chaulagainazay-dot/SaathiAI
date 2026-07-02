```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : Capability Registry
Document ID         : SES-000F
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
| 0.1.0 | 2026-07-02 | Ajay Chaulagain | Initial registry — all known platform capabilities catalogued |

---

## Purpose

This document is the **single source of truth for what SaathiAI can do**.

Every capability available on the platform — whether used by one product or all five — is registered here. This registry is the enforcement mechanism for Architecture Principle AP-10 (Capability Reuse) and the Platform-First Design Principle (SES-000A Part 7).

Before building any new capability:
1. Check this registry. If it already exists, use it.
2. If it exists but needs extension, extend it at the platform level and update this registry.
3. If it does not exist, build it at the platform level and register it here.

**The Capability Registry is organized by capability, not by product.** This is the core insight: in a product-first view, you ask "what does pielts have?" In a capability-first view, you ask "what can the platform do, and which products benefit?" The second framing prevents duplication.

---

## Audience

| Role | Required Sections | Notes |
|------|------------------|-------|
| Software Engineers | All | Check before building anything new |
| AI Coding Agents | All | Do not implement a capability listed here without reading its SES document first |
| Product Architects | All | Use to understand the capability surface before designing a new product |
| Stakeholders | Part 1 (Summary Matrix) | High-level view of platform capabilities and product coverage |

---

## Reading Order

```
SES-000A Document Standard (Part 7 — Platform-First Design Principle)
        │
        ▼
SES-000C Architecture Principles (AP-10 — Capability Reuse)
        │
        ▼
SES-000F Capability Registry  ← You are here
```

---

## Document Structure

| Section | Title | Summary |
|---------|-------|---------|
| Part 1 | Capability Summary Matrix | One-line view of all capabilities and product coverage |
| Part 2 | Core Platform Capabilities | Foundation capabilities used by all products |
| Part 3 | Voice Capabilities | Voice input, output, cloning, real-time pipeline |
| Part 4 | AI Studio Capabilities | Content creation, video, social, research |
| Part 5 | Research Capabilities | Web research, signal monitoring, data processing |
| Part 6 | Product-Specific Capabilities | Capabilities that are genuinely product-specific |
| Part 7 | Planned Capabilities | Not yet built — reserved and documented |

---

# Part 1 — Capability Summary Matrix

| Capability | Department | API Endpoint | pielts | HCG POS | HCG Live Signal | Travel | Mr. Yeti | Status | SES Doc |
|------------|-----------|-------------|--------|---------|-----------------|--------|----------|--------|---------|
| Agent System (BMA) | Core Platform | `/api/v1/agents/` | ✓ | ✓ | ✓ | ✓ | ✓ | Active | SES-002 |
| Working Memory | Core Platform | `/api/v1/memory/working` | ✓ | ✓ | ✓ | ✓ | ✓ | Active | SES-003 |
| Episodic Memory | Core Platform | `/api/v1/memory/episodic` | ✓ | ✓ | ✓ | ✓ | ✓ | Active | SES-003 |
| Semantic Memory | Core Platform | `/api/v1/memory/semantic` | ✓ | — | — | ✓ | — | Partial | SES-003 |
| Knowledge Graph | Core Platform | `/api/v1/knowledge/` | Planned | Planned | Planned | Planned | Planned | Planned | SES-003 |
| Model Router | Core Platform | `/api/v1/llm/` | ✓ | ✓ | ✓ | ✓ | ✓ | Active | SES-002 |
| Tool Registry | Core Platform | `/api/v1/tools/` | ✓ | ✓ | ✓ | ✓ | ✓ | Active | SES-002 |
| Notification Service | Core Platform | `/api/v1/notify/` | ✓ | ✓ | ✓ | ✓ | ✓ | Active | SES-010 |
| Scheduler | Core Platform | `/api/v1/scheduler/` | ✓ | ✓ | ✓ | ✓ | ✓ | Active | SES-010 |
| Observability | Core Platform | `/api/v1/metrics/` | ✓ | ✓ | ✓ | ✓ | ✓ | Partial | SES-008 |
| Voice Input (STT) | Voice | `/api/v1/voice/stt` | ✓ | — | — | ✓ | — | Active | SES-004 |
| Voice Output (TTS) | Voice | `/api/v1/voice/tts` | ✓ | — | — | ✓ | ✓ | Active | SES-004 |
| Voice Clone | Voice | `/api/v1/voice/clone` | — | — | — | — | ✓ | Active | SES-004 |
| Real-Time Voice Pipeline | Voice | `/api/v1/voice/session` | ✓ | — | — | ✓ | — | Planned | SES-004 |
| Content Generator | AI Studio | `/api/v1/studio/content` | — | — | — | — | ✓ | Active | SES-006 |
| Video Renderer | AI Studio | `/api/v1/studio/video` | — | — | — | — | ✓ | Active | SES-006 |
| Social Publisher | AI Studio | `/api/v1/studio/publish` | — | — | — | — | ✓ | Active | SES-006 |
| Asset Manager | AI Studio | `/api/v1/studio/assets` | — | — | — | ✓ | ✓ | Planned | SES-006 |
| Research Engine | Research | `/api/v1/research/` | — | — | ✓ | ✓ | ✓ | Partial | SES-005 |
| Browser Agent | Research | `/api/v1/research/browse` | — | — | ✓ | ✓ | — | Partial | SES-005 |
| Signal Monitor | Research | `/api/v1/research/signal` | — | — | ✓ | — | — | Partial | SES-005 |
| Evaluation Engine | Core Platform | `/api/v1/eval/` | ✓ | — | — | — | — | Active | SES-009 |
| Analytics Engine | Core Platform | `/api/v1/analytics/` | ✓ | ✓ | ✓ | ✓ | ✓ | Partial | SES-011 |
| Payment Service | Core Platform | `/api/v1/payment/` | Planned | ✓ | — | ✓ | — | Planned | SES-012 |
| Deployment Engine | Infrastructure | `/api/v1/deploy/` | ✓ | — | — | — | — | Planned | SES-013 |

**Legend:** ✓ = Uses this capability | — = Does not use | Planned = Will use in future phase

---

# Part 2 — Core Platform Capabilities

These capabilities are foundational infrastructure. Every product either uses them now or will use them.

---

## CAP-001: Agent System (BMA)

| Field | Value |
|-------|-------|
| Capability ID | CAP-001 |
| Name | Agent System — Baadar Multi-Agent Architecture |
| Department | Core Platform |
| API Endpoint | `/api/v1/agents/` |
| SES Document | SES-002 Agent System |
| Status | Active |
| Maturity | L3 |
| Products Using | All |
| Description | The 4-phase agent loop (Perception → Decision → Action → Reflection) that processes all complex requests on SaathiAI. Coordinates sub-agents, invokes tools, manages the BMA cycle. |
| Key Sub-Capabilities | SafetyHarness, AgentMessageBus, Sub-agent coordination, Tool invocation |
| What It Is NOT | A product. A chatbot. A single LLM call. The BMA is the operating system layer that orchestrates all of the above. |

---

## CAP-002: Memory System

| Field | Value |
|-------|-------|
| Capability ID | CAP-002 |
| Name | Three-Tier Memory System |
| Department | Core Platform |
| API Endpoint | `/api/v1/memory/` |
| SES Document | SES-003 Memory & Knowledge Graph |
| Status | Active (Tiers 1 & 2); Partial (Tier 3) |
| Maturity | L3 |
| Products Using | All |
| Description | Working Memory (in-process deque), Episodic Memory (SQLite interaction log), Semantic Memory (extracted patterns + ChromaDB planned). Each tier is independently upgradeable. |
| Key Sub-Capabilities | Context retrieval, Interaction logging, Pattern extraction, Cross-session persistence |
| What It Is NOT | A simple cache. The three tiers serve different timescales and use different storage backends. |

---

## CAP-003: Model Router

| Field | Value |
|-------|-------|
| Capability ID | CAP-003 |
| Name | Model Router |
| Department | Core Platform |
| API Endpoint | `/api/v1/llm/` |
| SES Document | SES-002 Agent System |
| Status | Active |
| Maturity | L3 |
| Products Using | All |
| Description | Routes LLM requests to the appropriate provider based on task label (screening / standard / reasoning / multimodal / private). Handles fallback, retry, and cost tracking. |
| Provider Map | `screening` → Shimmy (TinyLlama 1.1B local), `standard` → Groq llama-3.3-70b-versatile, `reasoning` → Claude (Anthropic), `multimodal` → Gemini, `private` → Ollama |
| What It Is NOT | A direct LLM client. Business logic never selects a specific provider — only a task label. |

---

## CAP-004: Notification Service

| Field | Value |
|-------|-------|
| Capability ID | CAP-004 |
| Name | Notification Service |
| Department | Core Platform |
| API Endpoint | `/api/v1/notify/` |
| SES Document | SES-010 Automation Engine |
| Status | Active |
| Maturity | L2 |
| Products Using | All |
| Description | Sends notifications across channels: Telegram (primary), email, in-app. Supports scheduling, templating, and priority levels. Two-way Telegram: receives commands from Ajay and responds. |
| Channels | Telegram (bot @AjayGmailbot), Email (SMTP), In-app panel |
| What It Is NOT | A product-level notification system. All products route notifications through this service. |

---

## CAP-005: Scheduler

| Field | Value |
|-------|-------|
| Capability ID | CAP-005 |
| Name | Automation Scheduler |
| Department | Core Platform |
| API Endpoint | `/api/v1/scheduler/` |
| SES Document | SES-010 Automation Engine |
| Status | Active |
| Maturity | L2 |
| Products Using | All |
| Description | APScheduler-based job scheduler managing 25+ autonomous jobs across all products. Cron, interval, and one-shot schedules. Jobs are isolated from each other — one failure does not crash the scheduler. |
| Current Jobs | Content generation (8pm daily), Analytics refresh (hourly), Dashboard generation (daily), Backup (daily), pielts blog auto-publish |
| What It Is NOT | n8n. APScheduler handles code-heavy jobs; n8n handles webhook-triggered workflows. |

---

## CAP-006: Evaluation Engine

| Field | Value |
|-------|-------|
| Capability ID | CAP-006 |
| Name | Evaluation Engine |
| Department | Core Platform |
| API Endpoint | `/api/v1/eval/` |
| SES Document | SES-009 Evaluation Engine |
| Status | Active |
| Maturity | L2 |
| Products Using | pielts (primary); planned for all products |
| Description | Evaluates AI-generated outputs against rubrics. Currently used for IELTS band score evaluation (Writing, Speaking, Reading, Listening). Designed as a general evaluation framework. |
| Key Feature | IELTS rubric evaluation is pielts-specific; the framework is platform-level |
| What It Is NOT | Pielts-specific code. The rubric is injected; the evaluation engine is product-agnostic. |

---

# Part 3 — Voice Capabilities

## CAP-010: Voice Input (STT)

| Field | Value |
|-------|-------|
| Capability ID | CAP-010 |
| Name | Speech-to-Text |
| Department | Voice |
| API Endpoint | `/api/v1/voice/stt` |
| SES Document | SES-004 Voice OS |
| Status | Active |
| Products Using | pielts (IELTS Speaking practice), Travel Platform (planned) |
| Description | Transcribes audio to text. Uses Whisper (local) as primary; cloud STT as fallback for languages Whisper handles poorly. |

## CAP-011: Voice Output (TTS)

| Field | Value |
|-------|-------|
| Capability ID | CAP-011 |
| Name | Text-to-Speech |
| Department | Voice |
| API Endpoint | `/api/v1/voice/tts` |
| SES Document | SES-004 Voice OS |
| Status | Active |
| Products Using | pielts (feedback playback), Mr. Yeti (character voice), Travel Platform (planned) |
| Description | Converts text to speech via OmniVoice (self-hosted). Sub-100ms latency. Supports multiple voices. |

## CAP-012: Voice Clone

| Field | Value |
|-------|-------|
| Capability ID | CAP-012 |
| Name | Voice Clone |
| Department | Voice |
| API Endpoint | `/api/v1/voice/clone` |
| SES Document | SES-004 Voice OS |
| Status | Active |
| Products Using | Mr. Yeti (Baadar persona voice) |
| Description | Creates and manages cloned voice profiles. Cloning is one-time; usage is zero marginal cost. Voice data stays on-device (biometric constraint). |

---

# Part 4 — AI Studio Capabilities

## CAP-020: Content Generator

| Field | Value |
|-------|-------|
| Capability ID | CAP-020 |
| Name | Content Generator |
| Department | AI Studio |
| API Endpoint | `/api/v1/studio/content` |
| SES Document | SES-006 AI Studio |
| Status | Active |
| Products Using | Mr. Yeti / Baadar social content pipeline |
| Description | Generates platform-formatted content (posts, captions, scripts, blog articles) using the Model Router. Supports templated generation and persona-aware generation (Mr. Yeti voice). |

## CAP-021: Video Renderer

| Field | Value |
|-------|-------|
| Capability ID | CAP-021 |
| Name | Video Renderer |
| Department | AI Studio |
| API Endpoint | `/api/v1/studio/video` |
| SES Document | SES-006 AI Studio |
| Status | Active |
| Products Using | Mr. Yeti video pipeline |
| Description | Renders HyperFrames compositions to MP4. Handles assembly of Google Flow 8-second clips into 60-second Shorts with captions, transitions, and B-roll. |

## CAP-022: Social Publisher

| Field | Value |
|-------|-------|
| Capability ID | CAP-022 |
| Name | Social Publisher |
| Department | AI Studio |
| API Endpoint | `/api/v1/studio/publish` |
| SES Document | SES-006 AI Studio |
| Status | Active |
| Products Using | Baadar (Facebook, Instagram, YouTube, TikTok, LinkedIn) |
| Description | Publishes content across social platforms. Manages 8pm daily post queue. Supports draft mode with human review gate before publishing. |

---

# Part 5 — Research Capabilities

## CAP-030: Research Engine

| Field | Value |
|-------|-------|
| Capability ID | CAP-030 |
| Name | Research Engine |
| Department | Research |
| API Endpoint | `/api/v1/research/` |
| SES Document | SES-005 Research Engine |
| Status | Partial |
| Products Using | HCG Live Signal (canteen monitoring), Travel Platform (planned), Mr. Yeti (content research) |
| Description | Web research pipeline: web search → content extraction (Crawl4AI) → LLM synthesis → structured output. Supports scheduled research runs and on-demand queries. |

## CAP-031: Signal Monitor

| Field | Value |
|-------|-------|
| Capability ID | CAP-031 |
| Name | Signal Monitor |
| Department | Research |
| API Endpoint | `/api/v1/research/signal` |
| SES Document | SES-005 Research Engine |
| Status | Partial |
| Products Using | HCG Live Signal |
| Description | Monitors data sources for changes and triggers alerts or analysis workflows. Used for real-time canteen analytics and operations monitoring. |

---

# Part 6 — Product-Specific Capabilities

These capabilities exist at the product layer because they are genuinely irreducible to a single product. Each entry includes a note on the Platform Promotion Path — the plan to generalize it if evidence emerges that another product could use it.

## CAP-100: IELTS Rubric Evaluator (pielts)

| Field | Value |
|-------|-------|
| Capability ID | CAP-100 |
| Name | IELTS Rubric Evaluator |
| Product | pielts |
| Status | Active |
| Description | Evaluates student IELTS responses against official band descriptors for Writing, Speaking, Reading, and Listening. Returns Band Score (1–9) with detailed feedback. |
| Why Product-Specific | IELTS rubrics are specific to the IELTS examination board. No other SaathiAI product needs IELTS evaluation. |
| Platform Promotion Path | If SaathiAI adds other exam preparation products, the evaluation framework generalizes. The rubric (IELTS-specific) remains product-specific; the framework (inject-a-rubric, return-a-score) promotes to CAP-006 Evaluation Engine. |

## CAP-101: Canteen Menu Manager (HCG POS)

| Field | Value |
|-------|-------|
| Capability ID | CAP-101 |
| Name | Canteen Menu Manager |
| Product | HCG POS |
| Status | Active |
| Description | Manages daily menu items, pricing, inventory deductions, and sales recording for HCGMS canteen. |
| Why Product-Specific | Canteen operations data model is specific to HCG POS. No other product manages a canteen. |
| Platform Promotion Path | If SaathiAI adds other POS products, the menu/inventory model could promote to a Platform Commerce capability. |

---

# Part 7 — Planned Capabilities

Capabilities that are architecturally anticipated and reserved, but not yet built.

| Capability | Department | Target Phase | Products | Notes |
|------------|-----------|-------------|---------|-------|
| Knowledge Graph | Core Platform | Phase 4 | All | Neo4j evaluation ongoing (SES-000E). Will extend Semantic Memory. |
| Payment Service | Core Platform | Phase 3 | pielts premium, Travel | Stripe integration for pielts premium tier and Travel bookings |
| Asset Manager | AI Studio | Phase 3 | Mr. Yeti, Travel | Centralized media storage and retrieval; R2-backed |
| Real-Time Voice Pipeline | Voice | Phase 2 | pielts Speaking, Travel | Full STT → LLM → TTS WebRTC pipeline via Pipecat (under evaluation) |
| Deployment Engine | Infrastructure | Phase 3 | pielts | Automated CI/CD pipeline for pielts Firebase deployment |
| Multi-Language Support | Core Platform | Phase 5 | All | Nepali-language support across all products |
| Emotion Recognition | Voice | Phase 5 | pielts | Detect stress/confidence in IELTS Speaking responses |

---

# Acceptance Criteria

| # | Criterion | Verification Method | Priority |
|---|-----------|---------------------|----------|
| AC-001 | Every tool module in `app/tools/` maps to a capability registered here | Cross-reference tool registry against CAP entries | Must Have |
| AC-002 | No product-layer code duplicates a capability listed as Active in this registry | Code review + grep for duplicate logic | Must Have |
| AC-003 | Every new API endpoint added to SaathiAI has a corresponding CAP entry before being marked L4 | Review process check | Should Have |
| AC-004 | The Capability Summary Matrix in Part 1 is updated whenever a new product or capability is added | Documentation review on PR | Must Have |

---

# Implementation Checklist

**Phase 1 — Registry Population**
- [x] Document all currently active capabilities
- [x] Document all product-specific capabilities
- [x] Document all planned capabilities
- [ ] Cross-reference against tool registry (`app/tools/registry.py`) for completeness

**Phase 2 — Enforcement**
- [ ] Add "update CAP entry" to the PR checklist for any new tool module or endpoint

---

# Risks

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R-001 | Registry becomes stale as new tools are added | High | Medium | Add registry update to the PR checklist |
| R-002 | Product teams build product-specific versions of platform capabilities | Medium | High | The registry is the check — engineers must consult it before building |

---

# Dependencies

**Internal:** SES-000A (Platform-First Design Principle), SES-000C (AP-10 Capability Reuse)

**External:** None.

---

# Related Documents

| Document ID | Title | Relationship |
|-------------|-------|-------------|
| SES-000A | Document Standard | Platform-First Design Principle governs this registry |
| SES-000C | Architecture Principles | AP-10 (Capability Reuse) enforced through this registry |
| SES-002 | Agent System | Core capability CAP-001, CAP-003 |
| SES-003 | Memory & Knowledge Graph | Core capability CAP-002 |
| SES-004 | Voice OS | Voice capabilities CAP-010 through CAP-012 |
| SES-005 | Research Engine | Research capabilities CAP-030, CAP-031 |
| SES-006 | AI Studio | Studio capabilities CAP-020 through CAP-022 |

---

*End of SES-000F Capability Registry — Version 0.1.0*

*Status: Draft (L1)*

*Next: [`SES-000_MASTER_ROADMAP.md`](SES-000_MASTER_ROADMAP.md)*
