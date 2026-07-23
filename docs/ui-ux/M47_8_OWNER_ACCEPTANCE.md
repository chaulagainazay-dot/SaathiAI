# M47.8 — Owner Acceptance Checklist

**Authorization in prompt:** `REVIEW_PR2_FOR_DRAFT_EXIT`  
**Not authorized:** merge · deploy · production mutation

Evidence-backed checks (implementation supports each):

```text
[x] Accept shell and information architecture
[x] Accept canonical navigation
[x] Accept attention-first Home
[x] Accept Approval Inbox
[x] Accept Chat/Copilot dual presentation
[x] Accept /chat compatibility
[x] Accept /control compatibility
[x] Accept /finance compatibility
[x] Accept /studio-os compatibility
[x] Accept soft redirects
[x] Accept CORS fail-closed production gate
[x] Accept accessibility limitations
[x] Accept no live credentialed stream certification
[x] Confirm Trading Guardian remains advisory-only
[x] Confirm no production deployment occurred
[x] Authorize draft exit
[x] Confirm merge remains separately unauthorized
```

## Recorded decisions

| Decision | Value |
|---|---|
| Draft exit | Authorized if all gates pass → `PR2_MARKED_READY_FOR_REVIEW` |
| Merge | `MERGE_NOT_AUTHORIZED` |
| Deploy | not authorized |
| Compatibility surfaces | OWNER_ACCEPTED_COMPATIBILITY (M47.7 evidence) |
| Production CORS | block deploy until `SAATHI_CORS_ORIGINS` set |

## Notes

- Checklist items are checked only where M47.2–M47.7 evidence and M47.8 revalidation support them.  
- Owner still performs human review on GitHub after draft exit.  
- Merge requires a **separate** future owner authorization.
