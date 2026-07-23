# M47.2 — Route Compatibility Matrix

**Date:** 2026-07-22  
**Milestone:** Shell & Information Architecture Migration  
**Policy this milestone:** prefer aliases/wrappers; **do not force redirects** for high-risk deep links.

| Legacy route | Canonical destination | Current status | Redirect safe? | Deep-link risk | Planned retirement |
|---|---|---|---|---|---|
| `/` | Home `/` | canonical | n/a | low | keep |
| `/ceo` | Home `/` | live compat | **no** (deferred) | bookmarks / PWA | later after Home parity proof |
| `/os` | Home `/` | live compat | **no** | bookmarks | later |
| `/mission` | Command `/command` (alias in nav) | live compat | **no** | operators use mission control habit | later |
| `/control` | Monitoring `/monitoring` (alias) + Command for acts | live compat | **no** | control deep links | later |
| `/control/computer` | Monitoring related | live | no | computer agent ops | keep as sub-surface |
| `/infrastructure` | Monitoring `/monitoring` (alias) | live | no | infra dashboards | later merge |
| `/studio-os` | Studio `/studio` | live compat | **no** | studio users | later |
| `/studio/control-room` | Studio sub-view | live | n/a | production | keep sub-route |
| `/chat` | Ask Saathi panel (ambient) | live full page | **no** | conversations | later |
| `/workspace` | Ask Saathi panel | live | **no** | chat workspace | later |
| `/saathi` | Ask Saathi panel | live | **no** | mobile habit | later |
| `/voice` | Command / Copilot related | live | **no** | voice enroll | later |
| `/me` | Settings `/settings` | live | **no** | profile | later soft redirect |
| `/finance` | Business `/business` (alias) | live | no | finance ops | Business compose |
| `/learning` | Knowledge (alias) | live | no | learning flows | Knowledge tabs |
| `/knowledge/library` | Knowledge sub | live | n/a | library | keep sub-route |
| `/automation/production` | Automation sub | live | n/a | production | keep sub-route |
| `/[dept]` | Projects / Business scaffolds | live | no | dept URLs | demote when Business OS real |
| `/project/create/[token]` | public bare | live **bare shell** | never redirect into shell | client intake | keep bare |
| `/unlock`, `/reset-password` | auth | live | n/a | auth | keep |
| `/connectors` | Settings/Security adjacency | live | no | connector mgmt | later Settings cluster |
| `/evidence` | Global Evidence | canonical global | n/a | evidence | keep |
| `/security` | Security | canonical | n/a | security | keep |
| `/missions/*` | Work / Missions | canonical | n/a | mission deep work | keep |
| `/lab`, `/skills`, `/maturity` | System adjacencies | live | no | expert tools | expert overflow later |

## New canonical routes (M47.2)

| Route | Status |
|---|---|
| `/command` | shipped — composes control overview/attention |
| `/agents` | shipped — directors API or honest empty |
| `/business` | shipped — compose links + partial note |
| `/trading` | shipped — **advisory-only blocked** |
| `/monitoring` | shipped — infra health observe |
| `/approvals` | shipped — connector source + coverage map |
| `/settings` | shipped — theme/density/experience |

## Redirects implemented this milestone

**None.** Intentionally deferred per stop conditions and Phase 10.

## Notes

- Nav **aliases** allow active-state highlighting when visiting legacy paths that map to a canonical area (e.g. `/control` → Monitoring active).
- Command palette lists legacy routes under a **Legacy** group for discoverability without auto-redirect.
