```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : Architecture Principles
Document ID         : SES-000C
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
| 0.1.0 | 2026-07-02 | Ajay Chaulagain | Initial draft |

---

## Purpose

This document defines the **architectural constraints** that govern every system built on SaathiAI. These principles are not preferences or guidelines — they are constraints. A design that violates a principle in this document is not an acceptable design, regardless of how convenient the violation might be.

The distinction between this document and the Engineering Values in SES-000A:
- **Engineering Values** (SES-000A) govern how work is done — the process, the documentation discipline, the mindset.
- **Architecture Principles** (this document) govern what is built — the structural decisions that must be true of every system.

Every SES document from SES-001 onwards must reference the principles in this document when making architectural decisions. Every ADR that deviates from a principle must explicitly name the principle being deviated from and provide a documented rationale.

---

## Audience

| Role | Required Sections | Notes |
|------|------------------|-------|
| Software Engineers | All | These principles constrain every implementation decision |
| AI Engineers | All | Apply before designing any agent architecture |
| AI Coding Agents | All | These are hard constraints — flag a violation rather than proceeding |
| Product Architects | All | Use as the first filter on any design proposal |
| DevOps / Infrastructure | AP-05, AP-07, AP-08 | Observability, security, and API principles are particularly relevant |

---

## Reading Order

```
SES-000A Document Standard
        │
        ▼
SES-000B Glossary
        │
        ▼
SES-000C Architecture Principles  ← You are here
        │
        ▼
SES-000 Master Roadmap
        │
        ▼
SES-001 Architecture
```

---

## Document Structure

| Section | Title | Summary |
|---------|-------|---------|
| Part 1 | AP-01: Platform-First | Every capability is built for the platform before the product |
| Part 2 | AP-02: Provider Abstraction | No external provider is referenced directly in business logic |
| Part 3 | AP-03: Modular Architecture | Every subsystem has one clear responsibility |
| Part 4 | AP-04: Event-Driven Communication | Subsystems communicate through events, not direct calls |
| Part 5 | AP-05: Observability-First | Every significant operation is observable |
| Part 6 | AP-06: Testability | Every subsystem is independently testable |
| Part 7 | AP-07: Security-by-Design | Security is designed in, not added later |
| Part 8 | AP-08: API-First | Every capability is exposed through a defined API |
| Part 9 | AP-09: Backward Compatibility | Existing integrations are protected across versions |
| Part 10 | AP-10: Capability Reuse | No capability is duplicated across products |
| Appendix | Principle Compliance Matrix | Cross-reference of principles against each SES document |

---

# Part 1 — AP-01: Platform-First

**Principle:** Before implementing any capability for an individual product, ask whether this capability belongs in the shared SaathiAI platform. If yes, implement it once at the platform level.

**What this means in practice:**

```
New feature request arrives
        │
        ▼
Can this serve more than one product?
        │
        ├── YES ──► Build in the platform layer (~/SaathiAI/app/)
        │           Document in SES-000F Capability Registry
        │           Expose via /api/v1/<capability>/
        │
        └── NO ───► Build in the product layer (~/SaathiAI/apps/<product>/)
                    Document the reason it is product-specific
                    Open a Future Improvement to evaluate platform promotion
```

**Violation examples:**
- Building a research pipeline inside `apps/pielts/` that could serve `apps/hcg_live_signal/`
- Implementing Telegram notifications in `apps/hcg_pos/` when a Notification Service already exists
- Adding a scheduling function inside a product module when APScheduler is the platform scheduler

**Approved deviation path:** Write an ADR referencing AP-01. State what the platform-level solution would look like and set a target date for migration.

---

# Part 2 — AP-02: Provider Abstraction

**Principle:** No external provider — LLM, TTS, storage, database, or cloud service — is referenced directly in business logic. All external calls go through an abstraction layer.

**Layer structure:**

```
Business Logic (agents, tools, schedulers)
        │
        ▼
Abstraction Layer (~/SaathiAI/app/providers/)
        │
        ├── llm_provider.py       ← groq, claude, gemini, ollama
        ├── tts_provider.py       ← omnivoice, elevenlabs (fallback)
        ├── storage_provider.py   ← r2, local
        └── db_provider.py        ← sqlite, postgres (migration target)
        │
        ▼
External Provider APIs
```

**What this means in practice:**
- Never call `groq.chat.completions.create()` in a tool module or agent
- Never call `boto3.client('s3')` in business logic
- Call `llm_provider.complete(prompt, model='standard')` instead
- The provider layer handles routing, fallback, and retry

**Violation examples:**
- `import groq` in a file outside `app/providers/`
- Hard-coded API endpoint URLs in tool modules
- Provider-specific response parsing in agents

---

# Part 3 — AP-03: Modular Architecture

**Principle:** Every subsystem has one clear responsibility and communicates with other subsystems through defined interfaces. No subsystem directly reads another subsystem's internal state.

**Single Responsibility Test:** For any file or module, can you answer the question "what does this module do?" in one sentence without using "and"? If not, it has more than one responsibility.

**Interface Definition Rule:** Every module that is called by another module must define its interface explicitly — function signatures with typed parameters and return types, documented in the relevant SES document.

**Internal State Rule:** Subsystem A may not read from subsystem B's database tables, internal variables, or file system paths. Data crosses subsystem boundaries only through defined interfaces.

**Violation examples:**
- A scheduler job that directly queries the pielts Firebase tables
- An agent that reads `working_memory.deque` directly instead of calling `memory.get_context()`
- A tool module that imports classes from another tool module

---

# Part 4 — AP-04: Event-Driven Communication

**Principle:** Where subsystems need to react to state changes in other subsystems, they do so through events, not through direct polling or synchronous calls.

**Current implementation:** Python-internal event bus (AgentMessageBus) for sub-agent communication within a single BMA cycle.

**Planned implementation:** A persistent event log (Phase 3) for cross-product event propagation.

**What this means in practice:**
- A sub-agent completing its task publishes an event; other sub-agents subscribe
- The Reflection Phase reads event results, not sub-agent return values
- Scheduled jobs emit events when complete so the dashboard can react

**Exception:** Synchronous API calls to external providers (LLM, TTS) are not subject to this principle — latency requirements make event-driven patterns impractical for real-time inference.

---

# Part 5 — AP-05: Observability-First

**Principle:** Every significant operation produces a measurable trace, log, or metric before it is considered complete.

**Three layers of observability:**

| Layer | Tool | What It Captures |
|-------|------|-----------------|
| Traces | Opik | LLM calls, agent cycles, tool invocations with latency and token counts |
| Logs | Python logging (structured JSON) | Scheduler jobs, errors, state transitions |
| Metrics | Custom SQLite tables | Business metrics (scores generated, content published, jobs completed) |

**"Significant operation" definition:** An operation is significant if its failure would go unnoticed without a trace. Every LLM call, every scheduled job, every external API call, every agent cycle is significant.

**Violation examples:**
- A scheduled job that runs silently with no output on success
- An LLM call not wrapped in an Opik trace
- A tool module that swallows exceptions without logging

**Rule:** Every autonomous job must log its start time, end time, outcome (success/failure), and any errors. This log is required, not optional.

---

# Part 6 — AP-06: Testability

**Principle:** Every subsystem can be tested in isolation without starting the full platform. Dependencies are injected, not imported.

**What "isolation" means:**
- A test of the Memory subsystem does not require a running FastAPI server
- A test of a tool module does not require a connected LLM provider
- A test of a scheduler job does not require APScheduler to be running

**How to achieve this:**
- Inject dependencies through function parameters or constructor arguments
- Use provider abstractions (AP-02) that can be replaced with test doubles
- No global state that tests cannot reset between runs

**Test categories:**

| Category | Scope | Tool |
|----------|-------|------|
| Unit | Single function or class | pytest |
| Integration | One subsystem with real dependencies | pytest + SQLite test DB |
| End-to-end | Full BMA cycle | pytest + running FastAPI instance |
| Contract | API interface compliance | pytest |

**Rule:** A subsystem is not implementation-ready (L4) until its unit tests are written and passing.

---

# Part 7 — AP-07: Security-by-Design

**Principle:** Security controls are designed into the system from the beginning. They are not added after implementation.

**Mandatory security controls:**

| Control | Requirement |
|---------|------------|
| Secrets management | All secrets in `.env` files, never in source code, never in logs |
| Authentication | Every external-facing API endpoint requires authentication |
| Input validation | Every user input is validated at the system boundary before processing |
| Rate limiting | Every public API endpoint has rate limiting configured |
| Dependency scanning | All Python dependencies are tracked in `requirements.txt` with pinned versions |
| `.gitignore` | `.env`, `firebase-admin.json`, and all credential files are listed in `.gitignore` |

**Specific SaathiAI secrets that must never appear in source code or logs:**
- `BAADAR_PASSWORD` — never expose
- `SAATHI_TOKEN` — never expose
- Firebase Admin credentials — never commit
- Any API key — stored in `.env` only

**Violation examples:**
- Hard-coded API keys in any Python file
- A log statement that prints a request including authentication headers
- An endpoint that accepts user input without validation

---

# Part 8 — AP-08: API-First

**Principle:** Every platform capability is exposed through a defined API endpoint before any product-level code consumes it.

**API design rules:**
- All endpoints follow REST conventions: `POST /api/v1/<subsystem>/<action>`
- All requests and responses are Pydantic models — no raw dicts across API boundaries
- All endpoints return a consistent response envelope:

```python
{
    "status": "success" | "error",
    "data": { ... },          # present on success
    "error": "message",       # present on error
    "request_id": "uuid",     # always present
    "duration_ms": 123        # always present
}
```

- All endpoints are documented in SES-APP-C (API Reference) before being marked L4

**Violation examples:**
- A product calling a platform function by importing it directly (`from app.memory import get_context`) instead of calling `/api/v1/memory/context`
- An endpoint that returns different shapes depending on whether an error occurred
- An endpoint with no Pydantic request model

---

# Part 9 — AP-09: Backward Compatibility

**Principle:** Existing integrations must not be broken by platform updates.

**Versioning rules:**
- The API version is in the URL: `/api/v1/`, `/api/v2/`
- A new version is introduced when a breaking change is required
- The old version is maintained for a minimum of 3 months after the new version ships
- A breaking change is any change to a request or response shape that requires callers to update

**What constitutes a breaking change:**
- Removing a field from a response
- Changing a field's type
- Renaming a field
- Changing the URL of an endpoint
- Making an optional parameter required

**What does not constitute a breaking change:**
- Adding a new optional field to a response
- Adding a new endpoint
- Changing the default value of an optional parameter

---

# Part 10 — AP-10: Capability Reuse

**Principle:** No capability is implemented more than once across the platform. When a capability exists, all products use the existing implementation.

**The Capability Registry (SES-000F) is the enforcement mechanism for this principle.** Before building any new capability, check SES-000F. If the capability exists, use it. If it needs to be extended, extend it at the platform level.

**Steps before implementing a new capability:**
1. Check SES-000F Capability Registry
2. Check SES-019 GitHub Research for existing open-source implementations
3. If the capability does not exist anywhere, build it at the platform level
4. Register it in SES-000F

**Violation examples:**
- Building a second research pipeline when `ResearchEngine` already exists
- Implementing voice in a product module when `VoiceOS` is a platform capability
- Writing a second Telegram notification function when `NotificationService` handles this

---

# Acceptance Criteria

| # | Criterion | Verification Method | Priority |
|---|-----------|---------------------|----------|
| AC-001 | Every SES document from SES-001 onwards references at least one principle from this document | Cross-reference audit of approved SES documents | Must Have |
| AC-002 | Every ADR that deviates from a principle names the principle being deviated from | Manual review of all ADRs | Must Have |
| AC-003 | No module outside `app/providers/` contains a direct import of an external LLM, TTS, or storage provider (AP-02) | Automated `grep` scan of codebase on CI | Must Have |
| AC-004 | Every public API endpoint returns the standard response envelope (AP-08) | Automated contract test | Should Have |

---

# Implementation Checklist

**Phase 1 — Principle Documentation**
- [x] Define all 10 architecture principles
- [ ] Validate principles against existing codebase (identify current violations)
- [ ] Write violation report as Open Question OQ-001

**Phase 2 — Enforcement**
- [ ] Add AP-02 provider abstraction check to CI pipeline
- [ ] Add AP-07 secrets scan to pre-commit hooks
- [ ] Create principle compliance matrix (see Appendix below)

---

# Risks

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R-001 | Existing codebase has violations of these principles | High | Medium | Document violations in a Technical Debt register; address in Phase 2 |
| R-002 | AI coding agents implement against violations in existing code rather than these principles | Medium | High | Reference this document explicitly in every implementer dispatch prompt |

---

# Dependencies

**Internal:** SES-000A governs the format of this document. SES-000B defines terms used here.

**External:** None.

---

# Decision References

| ADR | Title | Decision Summary | Status |
|-----|-------|-----------------|--------|
| ADR-0001 | Platform-First Architecture | SaathiAI is an OS; all products are applications | Accepted |
| ADR-0003 | Groq as Primary LLM | Provider abstraction enables future provider swaps | Accepted |
| ADR-0007 | Three-Tier Memory | Each tier is independently upgradeable (AP-03) | Accepted |

---

# Open Questions

| # | Question | Owner | Target Date | Status |
|---|----------|-------|-------------|--------|
| OQ-001 | Which existing modules violate AP-02 (provider abstraction)? | Ajay Chaulagain | 2026-08-01 | Open |
| OQ-002 | Should AP-04 (event-driven) apply to scheduled jobs in Phase 1, or only from Phase 3? | Ajay Chaulagain | 2026-08-01 | Open |

---

# Future Improvements

| # | Improvement | Target Phase | Notes |
|---|-------------|-------------|-------|
| FI-001 | Automated architecture compliance linter that checks all 10 principles on every PR | Phase 3 | Requires defining machine-readable principle rules |
| FI-002 | Principle Compliance Dashboard showing which subsystems are compliant with each principle | Phase 3 | Built on top of the CI linter |

---

# Related Documents

| Document ID | Title | Relationship |
|-------------|-------|-------------|
| SES-000A | Document Standard | Governing standard for this document |
| SES-000B | Glossary | Defines terms used here |
| SES-000F | Capability Registry | Enforces AP-10 (Capability Reuse) |
| SES-001 | Architecture | Implements these principles in the system design |
| All ADRs | — | Must reference applicable principles when making design decisions |

---

# References

| # | Title | Source | Notes |
|---|-------|--------|-------|
| REF-001 | The Twelve-Factor App | 12factor.net | Influenced AP-02, AP-05, AP-06 |
| REF-002 | Clean Architecture | Robert C. Martin | Influenced AP-03, AP-08 |

---

*End of SES-000C Architecture Principles — Version 0.1.0*

*Status: Draft (L1)*

*Next: [`SES-000D_CODING_STANDARD.md`](SES-000D_CODING_STANDARD.md)*
