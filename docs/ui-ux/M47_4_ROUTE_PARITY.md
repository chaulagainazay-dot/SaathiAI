# M47.4 — Route Parity Audit

**Date:** 2026-07-23  
**Policy:** Classify only. **No redirects.**

Source: static capability comparison + browser HTTP load of legacy routes + M47.2/M47.3 implementation reports.  
Parity % is an engineering coverage estimate, not a fabricated user-study score.

## Classification legend

| Class | Meaning |
|---|---|
| READY_TO_REDIRECT | Full functional parity; deep-links safe — **none in M47.4** |
| KEEP_COMPATIBILITY | Both live; redirect later after more work |
| BLOCKED_MISSING_UI | Canonical lacks critical UI surface |
| BLOCKED_BACKEND | Needs backend work |
| BLOCKED_DEEP_LINK | Deep-link / bookmark risk high |
| BLOCKED_WORKFLOW | Multi-step operator workflow incomplete on canonical |

## Matrix

| Legacy | Canonical | Parity % | Browser load | Classification | Notes |
|---|---|---|---:|---|---|
| `/ceo` | `/` | 55 | loads | KEEP_COMPATIBILITY | Attention Home ≠ CEO briefing twin |
| `/os` | `/` | 50 | loads | KEEP_COMPATIBILITY | Distinct OS payload/UI |
| `/control` | `/monitoring` + `/command` | 65 | loads | BLOCKED_WORKFLOW | Control search/facets not fully rehomed |
| `/chat` | Ask Saathi panel | 35 | loads | BLOCKED_MISSING_UI | Panel scaffold; no ambient history |
| `/workspace` | Ask Saathi panel | 35 | loads | BLOCKED_MISSING_UI | Workspace features absent |
| `/voice` | Command / Copilot | 25 | loads | BLOCKED_WORKFLOW | Enroll/local STT not in panel |
| `/me` | `/settings` | 60 | loads | KEEP_COMPATIBILITY | Settings is prefs; /me still profile |
| `/finance` | `/business` | 45 | loads | BLOCKED_MISSING_UI | Business is compose links only |
| `/infrastructure` | `/monitoring` | 70 | loads | KEEP_COMPATIBILITY | Shared health API; legacy richer chrome |
| `/studio-os` | `/studio` | 75 | loads | KEEP_COMPATIBILITY | Canonical studio exists; layout may differ |

## Canonical routes (verified load)

All ten canonical routes certified in browser harness (see `M47_4_BROWSER_CERTIFICATION.md`).

## Summary counts

| Classification | Count |
|---|---:|
| READY_TO_REDIRECT | **0** |
| KEEP_COMPATIBILITY | 5 |
| BLOCKED_MISSING_UI | 3 |
| BLOCKED_WORKFLOW | 2 |
| BLOCKED_BACKEND | 0 |
| BLOCKED_DEEP_LINK | 0 (risk noted, not sole class) |

**No route is ready for automatic redirect in this milestone.**
