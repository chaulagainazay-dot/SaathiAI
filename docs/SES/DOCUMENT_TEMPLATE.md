---
Document ID:       SES-XXX
Title:             [Full Title]
Volume:            Volume-1
Version:           1.0
Status:            Draft
Classification:    Internal
Owner:             SaathiAI Architecture Team
Last Updated:      YYYY-MM-DD
Next Review:       YYYY-MM-DD
Depends On:        [SES-000, SES-001, ...]
Referenced By:     [SES-002, SES-003, ...]
---

# [Document Title]

## Revision History

| Version | Date | Author | Summary of Changes |
|---------|------|--------|--------------------|
| 0.1 | YYYY-MM-DD | Ajay Chaulagain | Initial draft |
| 1.0 | YYYY-MM-DD | Ajay Chaulagain | Approved |

---

## Purpose

*Why this document exists. One to three paragraphs. Answer: what decision does this document govern? What would be unknown without it?*

---

## Audience

| Role | Read Sections |
|------|--------------|
| Software Engineers | All |
| AI Engineers | All |
| DevOps / Infrastructure | Sections X, Y |
| AI Coding Agents | All — treat every section as a constraint |
| Product Architects | All |
| Future Contributors | Start with Purpose, then Architecture |

---

## Reading Order

Documents that must be read before this one:

```
SES-000 Master Roadmap (always first)
    ↓
SES-001 Architecture
    ↓
[This Document]
```

---

## Document Structure

| Section | Title | Summary |
|---------|-------|---------|
| 1 | [Section 1 Title] | Brief description |
| 2 | [Section 2 Title] | Brief description |
| ... | ... | ... |

---

# Part 1 — [Part Name]

---

## 1. [Section Title]

### 1.1 [Subsection]

*Content.*

### 1.2 [Subsection]

*Content.*

---

# Part 2 — [Part Name]

---

## 2. [Section Title]

*Content.*

---

# Part N — [Part Name]

---

# Acceptance Criteria

*This section defines when this subsystem is considered complete for the purposes of v1.0.*

*Written as testable, measurable statements. Not aspirational. If it cannot be verified, it does not belong here.*

| # | Criterion | Verification Method | Priority |
|---|-----------|---------------------|----------|
| AC-001 | [Statement] | [How to verify] | Must Have |
| AC-002 | [Statement] | [How to verify] | Should Have |
| AC-003 | [Statement] | [How to verify] | Nice to Have |

---

# Implementation Checklist

*A sequence of verifiable steps. A coding agent should be able to execute these in order.*

**Phase 1 — Foundation**
- [ ] Step 1
- [ ] Step 2
- [ ] Step 3

**Phase 2 — Integration**
- [ ] Step 4
- [ ] Step 5

**Phase 3 — Validation**
- [ ] Step 6
- [ ] Step 7

---

# Risks

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R-001 | [Description] | Low / Medium / High | Low / Medium / High | [Action] |
| R-002 | [Description] | Low / Medium / High | Low / Medium / High | [Action] |

---

# Dependencies

**Internal Dependencies (other SaathiAI subsystems this depends on):**

| Subsystem | Document | Dependency Type |
|-----------|----------|-----------------|
| [Name] | SES-XXX | Hard / Soft |

**External Dependencies (third-party libraries, APIs, services):**

| Dependency | Version | Purpose | Fallback |
|------------|---------|---------|---------|
| [Name] | [Version] | [Purpose] | [Fallback or None] |

---

# Decision References

*ADRs that govern this document's design decisions.*

| ADR | Title | Decision |
|-----|-------|----------|
| ADR-0001 | [Title] | [One-line summary of decision] |
| ADR-0002 | [Title] | [One-line summary of decision] |

---

# Open Questions

*Questions that remain unanswered and must be resolved before or during implementation.*

| # | Question | Owner | Target Date | Status |
|---|----------|-------|-------------|--------|
| OQ-001 | [Question] | [Name] | YYYY-MM-DD | Open |

---

# Future Improvements

*Capabilities planned for phases beyond v1.0. Not in scope now but must not be architecturally prevented.*

| # | Improvement | Target Phase | Notes |
|---|-------------|-------------|-------|
| FI-001 | [Description] | Phase 3 | [Notes] |
| FI-002 | [Description] | Phase 4 | [Notes] |

---

*End of [Document Title] — Version 1.0*

*Next: [Link to next document in reading order]*
