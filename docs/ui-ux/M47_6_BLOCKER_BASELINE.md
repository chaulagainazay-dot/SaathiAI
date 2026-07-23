# M47.6 — Blocker Baseline (pre-fix evidence)

**Date:** 2026-07-23  
**Method:** Code inspection + prior M47.4 browser cert evidence

## CORS baseline

| Item | Evidence |
|---|---|
| Frontend origin (dev) | `http://localhost:3000` or Next alternate ports |
| Frontend origin (cert) | `http://127.0.0.1:3110` etc. |
| Backend origin | `http://localhost:8765` (`NEXT_PUBLIC_SAATHI_API`) |
| Config | `SAATHI_CORS_ORIGINS` env; default if empty |
| Default origins | `localhost:3000`, `127.0.0.1:3000`, `localhost:8765` |
| Credentials | `allow_credentials=True` |
| Methods/headers | `allow_methods=["*"]`, `allow_headers=["*"]` (too broad) |
| Failing cert | CORS blocked from `127.0.0.1:3110` → BFF (M47.4 evidence) |
| Production | Must set `SAATHI_CORS_ORIGINS` explicitly |

## Chat baseline (`ChatWorkspace`)

| Capability | Present |
|---|---|
| Conversation create/list/search | yes |
| History load | yes |
| Streaming messages | yes |
| Cancel/stop stream | partial (reader loop; no AbortController UI) |
| Agent selector | yes |
| Project context | yes |
| Team mode / agent runs | yes |
| Citations / AgentRunPanel | yes |
| Voice control | yes (optional) |
| Attachments | limited |
| Auth via afetch session | yes |
| Error / unreachable | yes |

## Copilot baseline

| Capability | Present |
|---|---|
| Open/close panel | yes |
| Full chat transport | **no** (scaffold) |
| History | **no** |
| Streaming | **no** |
| Links to /chat, /command, /approvals | yes |
| Authority badge advisory | yes |

## Control baseline

| Capability | Route |
|---|---|
| Overview cells | `/control` |
| Search | `/control` |
| Attention | also `/command`, Home |
| Approvals aggregation | `/approvals` |
| Infra health | `/monitoring` |
| Computer agent | `/control/computer` |

## Business / Finance

| | Finance | Business |
|---|---|---|
| Lines | ~23 | ~79 |
| Content | Thin finance shell | Compose links + partial badge |
| Authority actions | none observed | none |

## Studio

| Surface | Component | Role |
|---|---|---|
| `/studio` | AIStudio | Production queue / plan / produce |
| `/studio-os` | StudioWorkspace | OS-style studio workspace |
| `/studio/control-room` | control-room page | Operational control room |

## Soft redirects already live (M47.5)

`/infrastructure`→`/monitoring`, `/me`→`/settings`
