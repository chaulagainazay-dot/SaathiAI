# M47.8 — Compatibility Route Acceptance

**Authorization:** owner accepts compatibility for draft exit **if** M47.7 evidence remains consistent.  
**Evidence:** M47.7 browser cert + parity matrices + local revalidation gates.

## `/chat`

| Criterion | Evidence | Classification |
|---|---|---|
| Full workspace remains | `data-chat-mode="full"`; team/search chrome | **OWNER_ACCEPTED_COMPATIBILITY** |
| Copilot compact | panel `compact` + shared transport badge | accepted |
| Shared safe transport | both use `/api/v1/chat/*` + afetch | accepted |
| No false total session parity claim | dual presentation documented | accepted |
| No redirect required | KEEP_COMPATIBILITY | accepted |

## `/control`

| Criterion | Evidence | Classification |
|---|---|---|
| Search / release / timeline retained | M47.6 matrix + M47.7 control load + search | **OWNER_ACCEPTED_COMPATIBILITY** |
| Canonical absorbs only mapped workflows | Command partial; Control KEEP | accepted |
| No authority loss | no frontend auto-approve | accepted |
| No redirect required | retained path | accepted |

## `/finance`

| Criterion | Evidence | Classification |
|---|---|---|
| Legacy/read available | route loads retained | **OWNER_ACCEPTED_COMPATIBILITY** |
| Business does not fabricate finance data | honest/not-wired posture | accepted |
| No payment/transaction authority | no pay/transfer controls | accepted |
| No redirect required | KEEP_FINANCE | accepted |

## `/studio-os`

| Criterion | Evidence | Classification |
|---|---|---|
| Distinct from `/studio` and control-room | three paths retained in cert | **OWNER_ACCEPTED_COMPATIBILITY** |
| Responsibilities documented | M47.6 studio boundary | accepted |
| No accidental workflow loss | no redirect | accepted |

## Other legacy

`/ceo`, `/os`, `/workspace`, `/saathi`, `/voice`, `/mission`, `/trading` remain per M47.6/M47.7 — **OWNER_ACCEPTED_COMPATIBILITY** or NO_REDIRECT_REQUIRED where applicable.

## Summary

```text
/chat      = OWNER_ACCEPTED_COMPATIBILITY
/control   = OWNER_ACCEPTED_COMPATIBILITY
/finance   = OWNER_ACCEPTED_COMPATIBILITY
/studio-os = OWNER_ACCEPTED_COMPATIBILITY
```
