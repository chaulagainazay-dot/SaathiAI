# M47.5 — Redirect Matrix

**Date:** 2026-07-23  
**Implementation:** soft (`permanent: false`) via `next.config.mjs` + page-level `redirect()`

## Implemented soft redirects

| Legacy | Destination | Permanent | Query preserved | Content absorb | Browser verified |
|---|---|---|---|---|---|
| `/infrastructure` | `/monitoring` | no | yes (`?x=1` → `/monitoring?x=1`) | InfraHealthWorkspace on Monitoring | ✅ |
| `/me` | `/settings` | no | yes | MobileMe profile on Settings | ✅ |

## Explicitly not redirected

| Legacy | Reason |
|---|---|
| `/ceo`, `/os` | Different executive surfaces vs attention Home |
| `/control` | Workflow not fully rehomed |
| `/chat`, `/workspace`, `/saathi` | Copilot panel incomplete |
| `/voice` | Enrollment workflow |
| `/finance` | Business partial |
| `/studio-os` | Different StudioWorkspace UI vs `/studio` queue |
| `/mission` | Distinct Mission Control experience |
| `/trading` | Isolated advisory surface (never collapse away) |
| `/project/create/*` | Public bare form — never force shell |

## Loop safety

- No destination is also a source in `SAFE_REDIRECTS`
- Validated by `lib/redirects.test.js`
