```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : SES Document Standard
Document ID         : SES-000A
Version             : 1.0.0
Status              : Approved
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
| 1.0.0 | 2026-07-02 | Ajay Chaulagain | Approved as governing standard |
| 1.1.0 | 2026-07-02 | Ajay Chaulagain | Added: SES-000 document hierarchy, L1–L5 maturity model, SES-000F Capability Registry |

---

## Purpose

This document defines the **SaathiAI Engineering Specification (SES)** — the formal standard that governs every engineering document in the SaathiAI repository.

Every SES document is a governed engineering artifact, not a markdown file. The difference is accountability: a governed document has an owner, a version, a review date, and measurable acceptance criteria. A markdown file has none of these.

This standard exists to ensure that:

- All 20 Volume-1 documents and 7 appendices follow a consistent structure
- AI coding agents (Claude Code, Codex, Gemini CLI, Cursor) can parse any SES document and extract actionable implementation instructions
- Human engineers can navigate the specification without prior knowledge of the project
- Architectural decisions are traceable to specific documents and ADRs
- The specification can evolve across versions without losing historical context

Every document created for SaathiAI — from `SES-000 Master Roadmap` to `SES-020 Future Roadmap` — must comply with this standard before it is considered complete.

---

## Audience

| Role | Required Sections | Notes |
|------|------------------|-------|
| Software Engineers | All | Treat Acceptance Criteria and Implementation Checklist as implementation requirements |
| AI Engineers | All | Pay particular attention to Interface and Architecture sections |
| DevOps / Infrastructure Engineers | Infrastructure, Deployment, Dependencies | Focus on external dependency declarations |
| Product Architects | Purpose, Architecture, Design Decisions, Future Improvements | Use this document to understand platform boundaries |
| AI Coding Agents | **All sections** | Every section is a constraint. Do not infer intent — read what is written |
| Future Contributors | Start with Purpose, then Document Structure, then the chapter relevant to the task | Read SES-000 before any other document |

---

## Reading Order

This document must be read before any other SES document is created or modified.

```
SES-000A Document Standard  ← You are here
        │
        ▼
SES-000 Master Roadmap
        │
        ▼
SES-001 Architecture
        │
        ▼
SES-002 Agent System
        │
        ▼
SES-003 Memory & Knowledge Graph
        │
        ▼
SES-004 Voice OS
        │
        ▼
SES-005 AI Studio
        │
        ▼
...
        │
        ▼
SES-020 Future Roadmap
```

Appendices (`A` through `G`) may be read in any order after `SES-000`.

---

## Document Structure

| Section | Title | Summary |
|---------|-------|---------|
| Part 1 | SES Header Standard | The mandatory metadata block for every document |
| Part 2 | Document Governance Sections | Revision History, Purpose, Audience, Reading Order |
| Part 3 | Chapter Template | Standard section structure for every chapter |
| Part 4 | Writing Conventions | Tense, voice, length, prohibited language |
| Part 5 | Naming Standards | File names, document IDs, section numbers |
| Part 6 | Diagram Conventions | ASCII standards, flow diagrams, architecture diagrams |
| Part 7 | Platform-First Design Principle | The governing philosophy for all feature decisions |
| Part 8 | Engineering Values | The ten values every contributor must follow |
| Part 9 | Repository Integration Standard | How to document every integrated repository |
| Part 10 | Architecture Decision Records | ADR format, lifecycle, and numbering |
| Part 11 | Versioning Strategy | How the SES evolves across versions |
| Part 12 | Review and Approval Workflow | Draft to Approved lifecycle |

---

# Part 1 — SES Header Standard

Every SES document must begin with the following header block, rendered in a fenced code block so it is visible in both Markdown renderers and raw text editors.

---

### 1.1 Mandatory Header Format

````
```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : [Full Title]
Document ID         : SES-[NNN] or SES-[NNN]A
Version             : [MAJOR].[MINOR].[PATCH]
Status              : Draft | Under Review | Approved | Deprecated
Classification      : Internal
Owner               : SaathiAI Architecture Team
Primary Repository  : github.com/chaulagainazay/SaathiAI
Created             : YYYY-MM-DD
Last Updated        : YYYY-MM-DD
Next Review         : YYYY-MM-DD
================================================================================
```
````

---

### 1.2 Field Definitions

| Field | Required | Description |
|-------|----------|-------------|
| Document Title | Yes | Full human-readable title matching the filename |
| Document ID | Yes | Unique identifier. Format: `SES-NNN` or `SES-NNNA` for sub-documents |
| Version | Yes | Semantic version. `1.0.0` = first approved version |
| Status | Yes | One of: `Draft`, `Under Review`, `Approved`, `Deprecated` |
| Classification | Yes | Always `Internal` for now. May expand to `Confidential` or `Public` |
| Owner | Yes | Always `SaathiAI Architecture Team` unless a specific engineer is assigned |
| Primary Repository | Yes | Always the canonical GitHub repository path |
| Created | Yes | ISO 8601 date of initial creation |
| Last Updated | Yes | ISO 8601 date of most recent change |
| Next Review | Yes | ISO 8601 date of scheduled review. Default: 3 months from Last Updated |

---

### 1.3 Version Numbering

SES documents follow Semantic Versioning independently of the codebase version.

| Increment | When to Use | Example |
|-----------|-------------|---------|
| MAJOR | Architectural redesign that makes previous version incompatible | `1.0.0 → 2.0.0` |
| MINOR | New sections, significant additions, or revised design decisions | `1.0.0 → 1.1.0` |
| PATCH | Corrections, typos, clarifications that do not change decisions | `1.0.0 → 1.0.1` |

A document at `Draft` status begins at `0.1.0`. It becomes `1.0.0` when first approved.

---

### 1.4 Status Definitions

| Status | Meaning | Who Can Change It |
|--------|---------|------------------|
| Draft | Being written. Not yet reviewed. Do not implement from a Draft. | Author |
| Under Review | Complete draft awaiting review. Feedback may require revisions. | Author after review request |
| Approved | Reviewed and accepted. Implementation may proceed. | Architecture Team |
| Deprecated | Superseded by a newer version. Kept for historical reference only. | Architecture Team |

**Rule:** AI coding agents must not implement from a `Draft` document. Only `Approved` documents are implementation-authoritative.

---

# Part 2 — Document Governance Sections

Every SES document must include the following governance sections immediately after the header, in this exact order.

---

### 2.1 Revision History

A table tracking every version of the document.

| Version | Date | Author | Summary of Changes |
|---------|------|--------|--------------------|
| 0.1.0 | YYYY-MM-DD | Name | Initial draft |
| 1.0.0 | YYYY-MM-DD | Name | Approved |

**Rule:** Every commit that modifies an SES document must increment the version and add a row to this table.

---

### 2.2 Purpose

Three to five paragraphs answering:

1. Why does this document exist?
2. What architectural decisions does it govern?
3. Which problems does it solve?
4. Which future documents depend on it?

**Rule:** Purpose must be specific to this document. Generic statements such as "this document describes the system" are not acceptable.

---

### 2.3 Audience

A table listing every reader type and which sections they are required to read. See `1.1` of this document for the standard audience table format.

**Rule:** AI Coding Agents must always appear in the audience table. Their required sections are always "All."

---

### 2.4 Reading Order

A visual diagram showing which documents must be read before this one. Use the ASCII arrow format shown in this document.

---

### 2.5 Document Structure

A table listing every Part and Section in the document with a one-line summary. This allows a reader to navigate without reading the full document.

---

# Part 3 — Chapter Template

Every chapter (Part) inside an SES document follows this standard section sequence.

Not every section will contain content in every chapter. Sections that do not apply must still appear with the notation: `Not applicable to this document.`

This prevents a reader from wondering whether a section was forgotten or intentionally omitted.

---

### 3.1 Standard Section Sequence

For every major topic within an SES document:

```
## [N]. [Section Title]

### [N].1 Purpose
Why this section exists.

### [N].2 Background
Context required to understand this section.
What existed before. What problem it solves.

### [N].3 Goals
What this subsystem or capability must achieve.
Written as measurable objectives, not wishes.

### [N].4 Scope
What is in scope. What is explicitly out of scope.

### [N].5 Architecture
How it is built. ASCII diagrams required.
Component responsibilities. Data flows.

### [N].6 Design Decisions
Decisions made in this section and why.
Reference ADR numbers where applicable.

### [N].7 Interfaces
APIs, events, function signatures, data contracts.
Exact types required. No "TBD" allowed in Approved documents.

### [N].8 Repository Integration
Which external repositories are used here.
Integration level (Core / Optional / Research).
Reference the Repository Integration Table (SES-019).

### [N].9 Implementation Strategy
Phases of implementation.
What must exist before this can be built.
Estimated complexity (Low / Medium / High).
```

---

### 3.2 Mandatory Closing Sections

Every SES document must close with these sections, in this order, after all content chapters.

```
## Acceptance Criteria
## Implementation Checklist
## Risks
## Dependencies
## Decision References
## Open Questions
## Future Improvements
## Related Documents
## References
```

Each section is defined in detail in Part 3.3 through 3.11 below.

---

### 3.3 Acceptance Criteria

Defines when this subsystem is considered complete for v1.0.

**Rules:**
- Every criterion must be verifiable. If it cannot be tested or measured, it is not an acceptance criterion.
- No aspirational language ("should work well"). Only measurable outcomes ("response latency < 3 seconds measured by Opik").
- Priority must be assigned: `Must Have`, `Should Have`, or `Nice to Have`.

**Format:**

| # | Criterion | Verification Method | Priority |
|---|-----------|---------------------|----------|
| AC-001 | [Measurable statement] | [How to verify] | Must Have |

---

### 3.4 Implementation Checklist

A sequenced list of verifiable steps. A coding agent must be able to execute these in order without additional context.

**Rules:**
- Steps must be in dependency order. A step must not reference something not yet created.
- Each step is a single action. No compound steps ("create and test and deploy").
- Phase labels group steps into logical implementation phases.

**Format:**

```
**Phase 1 — [Phase Name]**
- [ ] Create [specific file or component]
- [ ] Implement [specific function with signature]
- [ ] Write test: [specific test description]
- [ ] Verify: [how to confirm this step is done]

**Phase 2 — [Phase Name]**
- [ ] ...
```

---

### 3.5 Risks

**Format:**

| # | Risk Description | Probability | Impact | Mitigation |
|---|------------------|-------------|--------|------------|
| R-001 | [Specific risk] | Low / Medium / High | Low / Medium / High | [Specific action] |

**Rule:** "Unknown" is not acceptable as Probability or Impact. If a risk is too uncertain to classify, it belongs in Open Questions.

---

### 3.6 Dependencies

Two subsections: Internal (other SaathiAI subsystems) and External (third-party libraries, APIs, services).

**Internal Format:**

| Subsystem | Document | Dependency Type | Notes |
|-----------|----------|-----------------|-------|
| [Name] | SES-XXX | Hard / Soft | [Notes] |

*Hard dependency:* This component cannot function without it.
*Soft dependency:* This component degrades gracefully without it.

**External Format:**

| Dependency | Version | Purpose | Fallback | License |
|------------|---------|---------|---------|---------|
| [Name] | [Version] | [Purpose] | [Fallback or None] | [License] |

---

### 3.7 Decision References

Lists every ADR that governed decisions in this document. Provides traceability from document to decision.

| ADR | Title | Decision Summary | Status |
|-----|-------|-----------------|--------|
| ADR-0001 | [Title] | [One-line summary] | Accepted |

---

### 3.8 Open Questions

Questions that must be resolved before or during implementation. An `Approved` document may still have Open Questions — but they must have an assigned owner and a target date.

| # | Question | Owner | Target Date | Status |
|---|----------|-------|-------------|--------|
| OQ-001 | [Question] | [Name] | YYYY-MM-DD | Open |

---

### 3.9 Future Improvements

Capabilities explicitly deferred to a future phase. These must not be architecturally prevented by the current design.

| # | Improvement | Target Phase | Notes |
|---|-------------|-------------|-------|
| FI-001 | [Description] | Phase 3 | [Notes] |

---

### 3.10 Related Documents

| Document ID | Title | Relationship |
|-------------|-------|-------------|
| SES-XXX | [Title] | Depends on / Referenced by / Extends |

---

### 3.11 References

External references: papers, specifications, repositories, standards.

| # | Title | URL / Source | Notes |
|---|-------|-------------|-------|
| REF-001 | [Title] | [URL] | [Notes] |

---

# Part 4 — Writing Conventions

These rules apply to every word written in every SES document.

---

### 4.1 Tense

| Situation | Tense | Example |
|-----------|-------|---------|
| Describing what exists now | Present | "The agent loop processes every request through four phases." |
| Describing what will be built | Future | "Phase 3 will introduce ChromaDB for vector search." |
| Describing a decision that was made | Past | "We chose Groq because its inference speed was 3× faster than the alternatives at the time of evaluation." |
| Writing Acceptance Criteria | Present | "Response latency is below 3 seconds." |
| Writing Implementation Checklist | Imperative | "Create the EpisodicMemory class." |

---

### 4.2 Voice

Active voice is preferred. Passive voice is permitted only when the actor is genuinely unknown or irrelevant.

| Prohibited | Preferred |
|------------|-----------|
| "Requests are processed by the agent." | "The agent processes requests." |
| "Data is stored in SQLite." | "The system stores data in SQLite." |
| "This should be noted." | "Note: [specific observation]." |

---

### 4.3 Prohibited Language

The following terms weaken the specification and are not permitted in `Approved` documents:

| Prohibited Term | Why | Replacement |
|----------------|-----|-------------|
| "good" | Subjective | Specify the metric: "latency under 200ms" |
| "fast" | Unmeasurable | "Processes 100 requests per second" |
| "modern" | Marketing language | Name the technology |
| "easy" | Subjective | Remove or describe why |
| "simple" | Subjective | Remove or describe the actual complexity |
| "TBD" | Incomplete | Either fill it in or move to Open Questions with an owner and date |
| "etc." | Lazy enumeration | Complete the list |
| "and so on" | Lazy enumeration | Complete the list |
| "as needed" | Vague governance | Specify the condition that triggers the action |
| "whenever practical" | Escape clause | Remove the qualifier or define when it does not apply |

---

### 4.4 Length Guidelines

| Section | Target Length | Maximum |
|---------|--------------|---------|
| Purpose | 3–5 paragraphs | 1 page |
| Background | 2–4 paragraphs | 1 page |
| Goals | 5–10 bullet points | Half a page |
| Architecture | Diagram + explanation | As needed |
| Acceptance Criteria | 5–15 rows | No limit |
| Implementation Checklist | 10–40 steps | No limit |
| Open Questions | As needed | No limit |

**Rule:** A section that exists only as a placeholder ("This section will be written later") must be removed. Empty sections with meaningful content in progress must be marked `Draft` at the section level.

---

### 4.5 Numbers and Measurements

- Always include units: `3 seconds`, `200 ms`, `NPR 30,000`, `1,000 users`
- Use ISO 8601 for all dates: `2026-07-02`
- Use 24-hour time with timezone: `08:00 NPT (02:15 UTC)`
- Do not write `~3s` in Acceptance Criteria — write `less than 3 seconds`

---

# Part 5 — Naming Standards

---

### 5.1 SES Document File Names

```
SES-NNN_TITLE_IN_SNAKE_CASE.md

Examples:
  SES-000_MASTER_ROADMAP.md
  SES-000A_DOCUMENT_STANDARD.md
  SES-001_ARCHITECTURE.md
  SES-002_AGENT_SYSTEM.md
```

Rules:
- Three-digit zero-padded number: `000`, `001`, `020`
- Sub-documents use a letter suffix: `000A`, `000B`
- Title in SCREAMING_SNAKE_CASE
- No spaces in file names

---

### 5.2 ADR File Names

```
ADR-NNNN_SHORT_TITLE.md

Examples:
  ADR-0001_PLATFORM_FIRST_ARCHITECTURE.md
  ADR-0002_KNOWLEDGE_GRAPH_NEO4J.md
  ADR-0003_VOICE_OS_PIPECAT.md
```

---

### 5.3 Appendix File Names

```
SES-APP-X_TITLE.md

Examples:
  SES-APP-A_REPOSITORY_INDEX.md
  SES-APP-B_DATABASE_SCHEMA.md
  SES-APP-C_API_REFERENCE.md
```

---

### 5.4 Section Numbering

Sections within a document use hierarchical decimal numbering:

```
Part 1         — Major Part heading (no number in the heading itself)
  1.           — Top-level section
  1.1          — Subsection
  1.1.1        — Sub-subsection (use sparingly — maximum 3 levels)
```

Acceptance Criteria items: `AC-001`, `AC-002`
Implementation Checklist items: not numbered — use checkboxes
Risk items: `R-001`, `R-002`
Open Question items: `OQ-001`, `OQ-002`
Future Improvement items: `FI-001`, `FI-002`

---

# Part 6 — Diagram Conventions

---

### 6.1 Rule: ASCII First

Every architecture diagram, flow diagram, and data flow diagram must be provided in ASCII art. Visual diagrams (PNG, SVG, Mermaid) are optional additions. ASCII is mandatory.

**Reason:** ASCII diagrams are readable in raw text editors, Git diffs, terminal output, and by AI coding agents without rendering. Visual diagrams may not be accessible in all contexts.

---

### 6.2 Architecture Diagrams

Use box-and-line notation:

```
┌─────────────────┐         ┌─────────────────┐
│  Component A    │────────►│  Component B    │
│                 │         │                 │
│  - Attribute 1  │         │  - Attribute 1  │
│  - Attribute 2  │         │  - Attribute 2  │
└─────────────────┘         └─────────────────┘
                                     │
                                     ▼
                            ┌─────────────────┐
                            │  Component C    │
                            └─────────────────┘
```

**Characters:**
- `─` horizontal line
- `│` vertical line
- `┌ ┐ └ ┘` corners
- `├ ┤ ┬ ┴ ┼` junctions
- `►` directional arrow (right)
- `▼` directional arrow (down)
- `▲` directional arrow (up)
- `◄` directional arrow (left)

---

### 6.3 Flow Diagrams

Use indented tree notation for process flows:

```
[Trigger]
    │
    ▼
[Step 1: Description]
    │
    ├── [Condition A] ──► [Action A]
    │
    └── [Condition B] ──► [Action B]
                              │
                              ▼
                         [Final Step]
```

---

### 6.4 Reading Order Diagrams

Use the vertical arrow format:

```
SES-000 Master Roadmap
        │
        ▼
SES-001 Architecture
        │
        ▼
SES-002 Agent System
```

---

### 6.5 Layered Architecture Diagrams

Use horizontal layer notation with full-width separators:

```
┌──────────────────────────────────────────────────────┐
│                   [Layer Name]                       │
│                                                      │
│  [Component A]    [Component B]    [Component C]     │
└──────────────────────────────────────────────────────┘
         │ uses
┌────────▼─────────────────────────────────────────────┐
│                   [Layer Name]                       │
└──────────────────────────────────────────────────────┘
```

---

# Part 7 — Platform-First Design Principle

This is the single most important engineering principle in the SaathiAI platform. Every contributor — human or AI agent — must understand and apply it before writing a single line of code.

---

### 7.1 The Principle

> **Before implementing any capability for an individual product, ask: does this capability belong in the shared SaathiAI platform?**
>
> If the answer is yes, implement it once in the platform. Every product then inherits it.

---

### 7.2 The Test

Apply this test to every feature request:

```
Can this capability serve more than one product?
        │
        ├── YES ──► Implement in the SaathiAI platform layer.
        │           Document it in the relevant SES volume.
        │           Expose it through the standard API or tool registry.
        │
        └── NO ───► Implement in the product-specific layer.
                    Document why it is product-specific.
                    Write an Open Question if unsure.
```

---

### 7.3 Examples

| Product Request | Product-Level Thinking (Wrong) | Platform-First Thinking (Correct) |
|----------------|-------------------------------|-----------------------------------|
| pielts needs voice feedback | Add voice to the pielts codebase | Build Voice OS (SES-004). pielts calls it. |
| HCG POS needs analytics | Add analytics to HCGMS | Build Analytics Engine. HCG POS calls it. |
| HCG Live Signal needs push alerts | Add Telegram notifications to Live Signal | The Notification Service already exists. Wire it. |
| Travel Platform needs payment processing | Build payment into the travel module | Build Payment Service. Travel Platform calls it. |
| AI Studio needs media storage | Add storage to the AI Studio module | Build Asset Manager. All products use it. |

---

### 7.4 When to Deviate

Deviations from Platform-First Design are permitted when:

1. The capability is irreducibly product-specific (for example, IELTS rubric evaluation logic has no value to HCG POS)
2. The platform does not yet have the relevant subsystem and time constraints prevent building it first

**In both cases:** document the deviation in an ADR. The ADR must state what the platform-level solution would eventually look like and set a target date for migrating the product-specific implementation to the platform.

---

# Part 8 — Engineering Values

These values govern every contribution to SaathiAI. They are not aspirational. They are constraints.

---

| # | Value | What It Means | What Violates It |
|---|-------|--------------|-----------------|
| EV-01 | **Build once, reuse everywhere** | Every capability implemented for one product must be available to all products through the platform | Duplicating logic across product modules |
| EV-02 | **Prefer modular services over monolithic implementations** | Each subsystem has one clear responsibility and communicates through defined interfaces | A function that does five unrelated things |
| EV-03 | **Keep providers replaceable through abstraction layers** | No external API, LLM provider, database, or cloud service is directly referenced in business logic | Calling `groq.chat.completions.create()` directly in a tool module |
| EV-04 | **Design for observability from the beginning** | Every significant operation produces a measurable trace, log, or metric | A job that runs silently with no output |
| EV-05 | **Favor automation while preserving governance** | Routine tasks must be automated. Irreversible or high-impact actions require documented approval rules | Asking a human to approve a routine content generation job every day |
| EV-06 | **Every subsystem must be independently testable** | A subsystem can be tested in isolation without starting the entire platform | A test that requires a running FastAPI server to test a memory function |
| EV-07 | **Record major architectural decisions using ADRs** | Any decision involving a technology choice, a provider selection, or a design pattern must have an ADR | Choosing Neo4j over ArangoDB without any documented rationale |
| EV-08 | **Optimize for long-term maintainability over short-term convenience** | A solution that is easy to write today but hard to understand in six months is the wrong solution | Magic numbers, undocumented assumptions, one-letter variable names in shared modules |
| EV-09 | **Documentation is part of the product** | An undocumented feature does not exist from the platform's perspective. Every capability must be described in an SES document before it is considered complete | Shipping a new tool module without updating `SES-APP-E_AGENT_CAPABILITIES.md` |
| EV-10 | **Every capability developed for one product must strengthen every other product** | Features generalize upward to the platform. They do not stay isolated in product code unless architecturally impossible | Building a research pipeline inside the pielts codebase that the AI Studio cannot use |

---

# Part 9 — Repository Integration Standard

Every external repository evaluated for integration into SaathiAI must be documented using this standard template. The master table is maintained in `SES-019 GitHub Research`.

---

### 9.1 Integration Levels

| Level | Meaning |
|-------|---------|
| **Core** | Required for the platform to function. Must be integrated in Phase 1 or 2. |
| **Optional** | Enhances the platform but is not required. Integrated when value justifies cost. |
| **Research** | Under evaluation. No integration decision made. |
| **Rejected** | Evaluated and decided against. Reason must be documented. |

---

### 9.2 Repository Record Template

```markdown
## [Repository Name]

| Field | Value |
|-------|-------|
| Repository | [GitHub URL] |
| Purpose | [One sentence: what it does] |
| Integration Level | Core / Optional / Research / Rejected |
| Subsystem | [SES document that owns this integration] |
| Reason for Selection | [Why this over alternatives] |
| Alternatives Considered | [Names of alternatives] |
| Why Alternatives Were Rejected | [Specific reasons] |
| Dependencies Introduced | [New external dependencies this brings] |
| Migration Complexity | Low / Medium / High |
| Owner | [Engineer responsible for integration] |
| Status | Planned / In Progress / Integrated / Deprecated |
| ADR Reference | [ADR-XXXX if a decision record exists] |
| Notes | [Anything not captured above] |
```

---

### 9.3 Repository Integration Matrix

The master Repository Integration Matrix is maintained in `SES-019_GITHUB_RESEARCH.md`. It contains one row per repository and references this standard for detail records.

Format:

| Repository | Category | Level | Subsystem | Status | ADR |
|------------|----------|-------|-----------|--------|-----|
| HyperFrames | Video | Core | SES-006 | Integrated | ADR-0010 |
| Pipecat | Voice | Core | SES-004 | Planned | ADR-0003 |
| Crawl4AI | Research | Core | SES-005 | Partial | — |

---

# Part 10 — Architecture Decision Records (ADR)

---

### 10.1 When to Write an ADR

An ADR is required whenever:

- A specific technology, library, or provider is chosen over alternatives
- A design pattern is adopted that will constrain future implementation
- A Platform-First deviation is approved (see Part 7.4)
- A previously approved decision is reversed or modified
- A significant trade-off is accepted (for example: choosing SQLite over Postgres for operational simplicity at the cost of future migration effort)

**An ADR is not required for:**
- Implementation details that do not affect other subsystems
- Bug fixes
- Minor configuration changes

---

### 10.2 ADR Lifecycle

```
Proposed
    │
    ▼
Under Review  ──► Rejected (archived, never deleted)
    │
    ▼
Accepted
    │
    ▼
Superseded (by a newer ADR — original is kept and marked Superseded)
```

---

### 10.3 ADR File Format

Every ADR follows this exact structure:

````markdown
```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : [Decision Title]
Document ID         : ADR-NNNN
Version             : 1.0.0
Status              : Proposed | Under Review | Accepted | Rejected | Superseded
Classification      : Internal
Owner               : [Engineer Name]
Created             : YYYY-MM-DD
Last Updated        : YYYY-MM-DD
================================================================================
```

## Context

[The situation or problem that required a decision.
What forces were at play? What constraints existed?
Do not describe the decision here — only the context.]

## Decision

[The decision that was made. State it in one clear sentence.
Then provide supporting detail.]

**We will use [X] for [purpose].**

## Rationale

[Why this decision was made. Reference specific evaluation criteria.
Include measurements or benchmarks if available.]

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| [Option A] | [Specific reason] |
| [Option B] | [Specific reason] |

## Consequences

**Positive:**
- [Benefit 1]
- [Benefit 2]

**Negative / Trade-offs:**
- [Cost 1]
- [Cost 2]

## Implementation Notes

[Any specific implementation guidance that follows from this decision.]

## Related Documents

| Document | Relationship |
|----------|-------------|
| SES-XXX | This decision governs section X of this document |

## Superseded By / Supersedes

[Link to newer ADR if this one is Superseded. Link to older ADR if this one supersedes it.]
````

---

### 10.4 Numbering

ADRs are numbered sequentially from `ADR-0001`. Numbers are never reused, even if an ADR is rejected. The number is assigned when the ADR is first created as a Proposed record.

---

# Part 11 — Versioning Strategy

---

### 11.1 SES Version vs. Codebase Version

The SES version and the codebase version are independent.

- The SES version tracks the evolution of the engineering specification
- The codebase version tracks released software
- A single SES version may correspond to multiple codebase releases

---

### 11.2 Volume Versioning

```
docs/
└── SES/
    ├── v1.0/          ← Current approved specification
    │   ├── SES-000_MASTER_ROADMAP.md
    │   ├── SES-001_ARCHITECTURE.md
    │   └── ...
    ├── v1.1/          ← In progress or next revision
    │   └── [modified documents only]
    └── v2.0/          ← Major architectural revision (future)
```

When a document is revised, only the changed document is placed in the new version folder. Unchanged documents are referenced from the previous version and not duplicated.

---

### 11.3 Volume vs. Individual Document Versioning

Each document has its own version number (tracked in its header). The volume version (v1.0, v1.1) represents a snapshot of the entire specification at a point in time, analogous to a Git tag on the documentation set.

---

# Part 12 — SES-000 Document Hierarchy

The SES-000 series serves as the **constitutional layer** of the specification. Every document in SES-001 through SES-020 references one or more SES-000 series documents as its governing authority.

```
SES-000  Master Roadmap
         │
         ├── SES-000A  Document Standard        (this document)
         ├── SES-000B  Glossary
         ├── SES-000C  Architecture Principles
         ├── SES-000D  Coding Standard
         ├── SES-000E  Repository Index
         └── SES-000F  Capability Registry
```

### 12.0.1 Responsibilities of Each Foundation Document

| Document | Answers |
|----------|---------|
| SES-000 | Why does SaathiAI exist? What products? What long-term goals? What capabilities define the platform? |
| SES-000A | How must every SES document be structured, written, and governed? |
| SES-000B | What does every term used across the specification mean? |
| SES-000C | What architectural constraints govern every system built on SaathiAI? |
| SES-000D | What coding conventions govern every line of code written for SaathiAI? |
| SES-000E | Which external repositories are integrated and at what level? |
| SES-000F | What capabilities exist on the platform, which products use them, and what is their status? |

### 12.0.2 Separation of Concerns

**Engineering Standards** (SES-000A, SES-000C, SES-000D) define *how* things are built.

**Product Vision** (SES-000) defines *why* and *what* is being built.

These must not be merged into a single document. SES-000 must remain readable by a non-technical stakeholder. SES-000C must be precise enough for an AI coding agent to enforce architectural constraints.

---

# Part 13 — Document Maturity Model

Every SES document carries a maturity level in addition to its version and status. The status tracks governance (Draft → Approved). The maturity level tracks implementation readiness.

---

### 13.1 Maturity Levels

| Level | Name | Meaning | Who Can Implement Against It |
|-------|------|---------|------------------------------|
| **L1** | Draft | Being written. Content is incomplete or unreviewed. | No one — not ready for implementation |
| **L2** | Reviewed | Complete draft that has received at least one structured review. Findings may still be open. | Author only, for exploratory prototyping |
| **L3** | Architecture Approved | Architecture Team has approved the design decisions. No major open questions remain. | Engineering teams may begin implementation |
| **L4** | Implementation Ready | All acceptance criteria are defined, all checklist steps are specific, all interfaces are typed. AI coding agents may implement directly. | AI coding agents and engineers |
| **L5** | Production Validated | Implementation is complete. Acceptance criteria have been verified against a running system. | Reference only — no further implementation changes without a new version |

---

### 13.2 Maturity Level in Document Headers

The maturity level is added to the header block after `Status`:

```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : [Full Title]
Document ID         : SES-[NNN]
Version             : [MAJOR].[MINOR].[PATCH]
Status              : Draft | Under Review | Approved | Deprecated
Maturity            : L1 | L2 | L3 | L4 | L5
...
================================================================================
```

---

### 13.3 Maturity Transition Rules

| Transition | Requirement |
|------------|-------------|
| L1 → L2 | Author self-review complete. All sections present. No `TBD` in required fields. |
| L2 → L3 | Architecture Team review complete. All Design Decisions have ADR references or documented rationale. Open Questions have owners and dates. |
| L3 → L4 | All Acceptance Criteria are measurable. All Implementation Checklist steps are specific enough for an AI coding agent to execute without additional context. All Interfaces sections have typed signatures — no `TBD`. |
| L4 → L5 | All Acceptance Criteria verified against a running production system. Post-implementation review complete. |

---

### 13.4 Maturity Dashboard

The master maturity dashboard is maintained in `SES-000_MASTER_ROADMAP.md` as a table showing the current maturity level of every SES document. It is updated whenever any document advances a level.

---

# Part 15 — Review and Approval Workflow

---

### 12.1 Document Lifecycle

```
Author creates Draft (version 0.1.0)
        │
        ▼
Author marks "Under Review" — requests review
        │
        ▼
Review period (minimum 48 hours for architectural documents)
        │
        ├── Changes required ──► Author revises ──► Back to Under Review
        │
        └── No changes required
                │
                ▼
        Approved (version 1.0.0)
                │
                ▼
        Implemented against
                │
                ▼
        Revised as needed (version 1.1.0, 1.2.0, etc.)
                │
                ▼
        Deprecated when superseded
```

---

### 12.2 Review Criteria

A document may not be marked `Approved` if any of the following are true:

- [ ] The header contains `TBD` in any required field
- [ ] Any Acceptance Criterion is not measurable
- [ ] Any Implementation Checklist step references something undefined elsewhere in the specification
- [ ] Any section contains prohibited language (see Part 4.3)
- [ ] A major design decision was made without a corresponding ADR
- [ ] The document references an external repository without a corresponding entry in `SES-019`
- [ ] Open Questions exist without an owner and target date

---

### 12.3 AI Coding Agent Review

Before an AI coding agent uses a document for implementation, it must verify:

1. The document Status is `Approved`
2. The version in the header matches the version in the repository
3. All referenced ADRs are `Accepted`
4. No Open Questions are marked as blockers for implementation

If any of these conditions are not met, the agent must stop and report the issue rather than proceeding with implementation.

---

# Acceptance Criteria

| # | Criterion | Verification Method | Priority |
|---|-----------|---------------------|----------|
| AC-001 | Every SES document created after this standard is approved includes the mandatory header block | Manual review of header block in each document | Must Have |
| AC-002 | Every SES document includes all mandatory governance sections (Revision History, Purpose, Audience, Reading Order, Document Structure) | Automated check for section headers | Must Have |
| AC-003 | Every SES document closes with the nine mandatory sections in the correct order | Automated check for section headers | Must Have |
| AC-004 | No approved SES document contains any prohibited term from Part 4.3 | Text search across all approved documents | Must Have |
| AC-005 | Every external repository integrated into SaathiAI has a record in SES-019 following the Part 9.2 template | Cross-reference between code imports and SES-019 | Must Have |
| AC-006 | Every significant technology selection has a corresponding ADR in `docs/decisions/` | Cross-reference between architecture sections and ADR list | Should Have |
| AC-007 | AI coding agents can parse any approved SES document and extract: version, status, acceptance criteria, and implementation checklist without additional context | Test with Claude Code, Codex, and Cursor against three sample documents | Should Have |

---

# Implementation Checklist

**Phase 1 — Standard Definition**
- [x] Write SES-000A Document Standard
- [x] Define mandatory header format
- [x] Define document governance sections
- [x] Define chapter template
- [x] Define writing conventions
- [x] Define naming standards
- [x] Define diagram conventions
- [x] Define Platform-First Design Principle
- [x] Define Engineering Values
- [x] Define Repository Integration Standard
- [x] Define ADR format and lifecycle
- [x] Define versioning strategy
- [x] Define review and approval workflow

**Phase 2 — Application**
- [ ] Apply this standard to `SES-000 Master Roadmap` (first document written under this standard)
- [ ] Create ADR template file at `docs/decisions/ADR-TEMPLATE.md`
- [ ] Create `docs/decisions/ADR-0001_PLATFORM_FIRST_ARCHITECTURE.md`
- [ ] Update `docs/CHANGELOG.md` to record adoption of SES-000A

**Phase 3 — Validation**
- [ ] Review SES-000 Master Roadmap against AC-001 through AC-007
- [ ] Confirm AI coding agent can parse SES-000A without additional context

---

# Risks

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R-001 | Documents become too long to be practical for AI agents | Medium | High | Enforce length guidelines from Part 4.4. Split documents that exceed 10,000 words. |
| R-002 | The standard becomes a bureaucratic burden that slows development | Low | High | The standard applies to architectural documents, not to code comments or internal notes. Fast-path: any document can start as a Draft and be used by the author immediately. |
| R-003 | Future engineers ignore the standard | Medium | Medium | The standard is enforced through the review checklist in Part 12.2. No document reaches Approved without passing the review. |

---

# Dependencies

**Internal:** None. This document is the root of the specification. No SES document depends on any other document more than this one.

**External:** None. This document has no external technology dependencies.

---

# Decision References

| ADR | Title | Decision Summary | Status |
|-----|-------|-----------------|--------|
| — | — | No ADRs govern this document. SES-000A is itself a governing document. | — |

---

# Open Questions

| # | Question | Owner | Target Date | Status |
|---|----------|-------|-------------|--------|
| OQ-001 | Should "Classification" include a "Public" tier when SaathiAI open-sources its core? | Ajay Chaulagain | 2026-10-02 | Open |
| OQ-002 | Should AI coding agents be required to write ADRs autonomously when they make implementation decisions? | Ajay Chaulagain | 2026-09-01 | Open |

---

# Future Improvements

| # | Improvement | Target Phase | Notes |
|---|-------------|-------------|-------|
| FI-001 | Automated linter that checks every SES document against this standard on git commit | Phase 3 | Run as a GitHub Actions pre-commit hook |
| FI-002 | Machine-readable schema (JSON Schema or OpenAPI) version of this standard for AI agents to validate documents programmatically | Phase 4 | Enables agents to self-validate before submitting changes |
| FI-003 | Visual diagram standard (Mermaid or Excalidraw) as a companion to ASCII | Phase 3 | ASCII remains mandatory; visual is additive |

---

# Related Documents

| Document ID | Title | Relationship |
|-------------|-------|-------------|
| SES-000 | Master Roadmap | First document written under this standard |
| SES-019 | GitHub Research | Governs the Repository Integration Matrix |
| SES-APP-G | Glossary | Contains definitions for all terms used in this standard |
| All ADRs | — | All ADRs must follow the format defined in Part 10.3 |

---

# References

| # | Title | Source | Notes |
|---|-------|--------|-------|
| REF-001 | RFC 2119 — Key words for use in RFCs to Indicate Requirement Levels | IETF | Defines MUST, SHOULD, MAY — adapted for use in this standard |
| REF-002 | Michael Nygard — Architecture Decision Records | cognitect.com/blog | Original ADR format this standard is based on |
| REF-003 | arc42 — Architecture Documentation Template | arc42.org | Structural inspiration for chapter template |

---

*End of SES-000A Document Standard — Version 1.0.0*

*Status: Approved*

*Next: [`SES-000_MASTER_ROADMAP.md`](SES-000_MASTER_ROADMAP.md)*
