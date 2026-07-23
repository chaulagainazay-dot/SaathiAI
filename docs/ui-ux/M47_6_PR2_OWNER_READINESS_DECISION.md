# M47.6 — PR #2 Owner Readiness Decision

**Date:** 2026-07-23  
**HEAD at decision:** (see final commit on branch)

## Decision

```text
PR2_KEEP_DRAFT
```

## Rationale

Critical CORS blocker is **closed** with a fail-closed production contract and unit tests.

High Chat/Copilot blocker is **partially closed**: shared transport + compact panel + stop stream. Full workspace remains required → `/chat` not redirected (by design).

High Control blocker is **classified non-blocking for merge of foundation UI** only if Control remains available — it does (**KEEP_COMPATIBILITY**). Not fully rehomed.

Medium Business/Finance and Studio blockers are **classified** with KEEP_COMPATIBILITY / KEEP_BOTH_DISTINCT — no false redirects.

Therefore PR #2 is **not** declared ready for owner “merge” review as a complete product replacement of all legacy surfaces. It **is** a coherent UI/UX foundation suitable for continued draft review of:

- Shell IA + tokens  
- Attention Home + Approvals  
- Soft redirects (2)  
- Compact Copilot chat  
- CORS contract  

Owner should review as **foundation stack**, not as “all legacy routes retired.”

## When to flip to READY_FOR_OWNER_REVIEW

1. Owner accepts KEEP_COMPATIBILITY for control/chat/finance/studio as intentional, **or**  
2. Remaining high workflows rehomed with evidence  

Then mark ready **only with owner authorization** (this milestone does not mark ready on GitHub).

## Milestone state

```text
M47_6_COMPLETE_WITH_LIMITATIONS_PR2_DRAFT
```
