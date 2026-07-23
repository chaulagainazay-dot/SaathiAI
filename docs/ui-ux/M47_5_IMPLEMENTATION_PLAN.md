# M47.5 — Implementation Plan

**Date:** 2026-07-23  
**Baseline:** `69750da74c8660dd9642cee52652947cfce5878c`  
**PR:** #2 draft

## Goal

1. Promote only evidence-backed routes to **READY_TO_REDIRECT**
2. Implement **soft** redirects (308/temporary preferred) with query preservation
3. Never force-redirect chat/control/voice/ceo/os/finance without parity
4. PR production-readiness **assessment** (remain draft unless gates fully green)

## Redirects to implement (after content absorb)

| Legacy | Target | Work required |
|---|---|---|
| `/infrastructure` | `/monitoring` | Absorb infra health workspace into Monitoring |
| `/me` | `/settings` | Absorb profile (MobileMe) into Settings |

## Explicitly NOT redirecting

`/ceo`, `/os`, `/control`, `/chat`, `/workspace`, `/voice`, `/finance`, `/studio-os`, `/mission` — still below readiness.

## Files

- Create `components/infra/InfraHealthWorkspace.jsx`
- Update `app/monitoring/page.jsx`, `app/settings/page.jsx`
- Replace `app/infrastructure/page.jsx`, `app/me/page.jsx` with redirect helpers
- `next.config.mjs` redirects (query preserved)
- `lib/redirects.js` + tests
- Docs: readiness, validation, PR production report

## Safety

No Trading Guardian changes · no force-push · no merge · no mark-ready without verdict  
