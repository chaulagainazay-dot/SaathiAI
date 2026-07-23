# M47.7 — Compatibility Route Validation

**Date:** 2026-07-23

## Retained (must not soft-redirect)

| Route | Load | Final path retained | Notes |
|---|---|---|---|
| `/chat` | ✅ | ✅ | Full workspace; KEEP_COMPATIBILITY |
| `/control` | ✅ | ✅ | Search + control workflows retained |
| `/finance` | ✅ | ✅ | No payment authority; KEEP_FINANCE |
| `/studio-os` | ✅ | ✅ | Distinct from `/studio` |

## Other compatibility loads

| Route | OK |
|---|---|
| `/ceo` | ✅ |
| `/os` | ✅ |
| `/workspace` | ✅ |
| `/saathi` | ✅ |
| `/voice` | ✅ |
| `/mission` | ✅ |
| `/trading` | ✅ (advisory) |

## Soft redirects (only these)

| Source | Destination | Soft | Query |
|---|---|---|---|
| `/infrastructure` | `/monitoring` | yes | preserved |
| `/me` | `/settings` | yes | preserved |

No new redirects in M47.7. No accidental redirects of chat/control/finance/studio-os.

## Studio boundaries

| Route | Responsibility | Redirected? |
|---|---|---|
| `/studio` | production queue | no |
| `/studio-os` | StudioWorkspace | no |
| `/studio/control-room` | operational control room | no |

## Control

Search remains on `/control`. No frontend-authoritative approve. Links toward approvals/monitoring present.

## Classification

```text
COMPATIBILITY = PASS_KEEP_DOCUMENTED
```
