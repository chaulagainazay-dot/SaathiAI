# M47.4 — Redirect Readiness Matrix

**Date:** 2026-07-23  
**Redirects implemented:** **none** (explicit milestone rule)

## Per-route readiness

| Legacy route | Canonical destination | Parity % | Deep-link risk | Backend dependency | Redirect ready? | Notes |
|---|---|---:|---|---|---|---|
| `/ceo` | `/` | 55 | medium | executive briefing optional | **No** | Different product surface |
| `/os` | `/` | 50 | medium | ceo/os APIs | **No** | Different product surface |
| `/control` | `/monitoring` (+ `/command` for acts) | 65 | **high** | control/* aggregation | **No** | Workflow incomplete |
| `/chat` | Ask Saathi panel | 35 | **high** | chat runtime | **No** | Panel scaffold only |
| `/workspace` | Ask Saathi panel | 35 | **high** | workspace chat | **No** | Missing features |
| `/voice` | Command / Copilot | 25 | **high** | voice/LOCAL_BASE | **No** | Enrollment workflow |
| `/me` | `/settings` | 60 | low | profile optional | **No** | Soft redirect candidate later |
| `/finance` | `/business` | 45 | medium | finance APIs | **No** | Business partial |
| `/infrastructure` | `/monitoring` | 70 | medium | infra health | **No** | Closest; still keep both |
| `/studio-os` | `/studio` | 75 | medium | studio APIs | **No** | Closest; still keep both |

## Closest candidates for a future redirect milestone

1. `/infrastructure` → `/monitoring` (after Monitoring UI absorbs remaining widgets)  
2. `/studio-os` → `/studio` (after layout parity check with studio operators)  
3. `/me` → `/settings` (soft redirect if profile content moves into Settings)

## Hard blockers for redirects now

- Chat/workspace/voice ambient experience incomplete  
- Control Center workflow not fully split between Monitoring and Command  
- Business OS not a full Finance replacement  

## Policy for next milestone (suggested M47.5)

- Implement redirects **only** for rows that reach READY_TO_REDIRECT with browser re-cert  
- Preserve query strings  
- Avoid loops  
- Keep public bare `/project/create/*` never forced into shell  
