# M47.7 — PR #2 Owner Readiness

**Date:** 2026-07-23  
**PR:** https://github.com/chaulagainazay-dot/SaathiAI/pull/2  
**Branch:** `milestone/saathios-ui-ux`  
**GitHub state at decision:** OPEN · **DRAFT** · UNMERGED (unchanged by this milestone)

## Decision

```text
PR2_READY_FOR_OWNER_REVIEW
```

This is a **readiness recommendation**. M47.7 does **not** mark the GitHub PR ready and does **not** merge.

## Why ready for owner review

Post-M47.6 browser re-certification completed with managed BFF + UI lifecycle:

| Area | Status |
|---|---|
| Managed Playwright lifecycle | pass |
| Canonical routes (13) | pass |
| Compatibility routes retained | pass |
| Soft redirects (2) + query | pass |
| CORS runtime (allow/deny/preflight/credentials) | pass |
| Chat full workspace | pass (honest errors without auth) |
| Copilot compact + shared transport | pass |
| Control retained | pass |
| Approvals honesty | pass |
| Business / Finance safety | pass |
| Studio distinct surfaces | pass |
| Trading Guardian advisory-only | pass |
| Keyboard / theme / density / experience / responsive | pass |
| Fatal console / unexplained page errors | none |
| Unit / lint / build / CORS unit / secret scan | pass |

## Accepted compatibility surfaces

Owner should review these as **intentional KEEP_COMPATIBILITY**, not as incomplete bugs:

| Surface | Why keep |
|---|---|
| `/chat` | Full workspace (team/voice/timeline) beyond compact panel |
| `/control` | Search, release gate, full cell grid not fully rehomed |
| `/finance` | No unified metrics API; honest thin shell |
| `/studio-os` | StudioWorkspace ≠ production queue `/studio` |
| `/ceo`, `/os`, `/voice`, `/mission`, … | Documented legacy / specialized |

## Remaining limitations (non-blocking for owner review)

1. Live chat streaming + Stop cancel not exercised without credentials/model.
2. Backend API calls without session produce expected network failures (filtered).
3. No full WCAG certification.
4. Control not fully rehomed to Command (by design KEEP).
5. Finance API still unwired.
6. Studio dual entry points remain (KEEP_BOTH_DISTINCT).

## Blocking defects

```text
Critical: none
High: none
```

## Non-blocking defects

- Harness initially used `networkidle` (fixed test-only).
- Trading advisory copy briefly false-positive matched `Withdraw` substring (fixed test-only).

## Owner decisions required

1. **Accept** documented KEEP_COMPATIBILITY surfaces for foundation merge, **or** request follow-up rehome epics before merge.
2. **Authorize** marking PR #2 ready on GitHub (human only).
3. **Authorize** merge to `master` only after your review of soft redirects and Trading Guardian posture.
4. Confirm production `SAATHI_CORS_ORIGINS` before any production deploy (fail-closed without it).

## What this PR is safe to review as

- Shell IA + design tokens + attention Home + Approvals honesty  
- Soft redirects: `/infrastructure` → `/monitoring`, `/me` → `/settings`  
- Bounded BFF CORS contract  
- Shared Chat/Copilot transport (compact + full)  
- Trading Guardian advisory boundary  

**Not** a claim that every legacy surface is retired.

## Milestone state

```text
M47_7_COMPLETE_PR2_OWNER_REVIEW_READY
```

## Next recommended action

Owner reviews PR #2 draft on GitHub; if accepted, **owner** marks ready for review and merges. No agent auto-ready or auto-merge.
