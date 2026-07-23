# M47.7 — Browser Re-Certification Plan

**Date:** 2026-07-23  
**Branch:** `milestone/saathios-ui-ux`  
**Starting HEAD:** `01a0296057cf10b77b3844ee3dde370aaf8eac0b`  
**PR:** #2 (OPEN · DRAFT · base `master`)  
**Prior milestone:** `M47_6_COMPLETE_WITH_LIMITATIONS_PR2_DRAFT`  
**Harness:** `saathi-os/scripts/m47_7_browser_cert.mjs`  
**Evidence dir:** `docs/ui-ux/m47_7_evidence/`

## Purpose

Complete post-M47.6 browser and runtime re-certification of PR #2. Validation-first. No major features. Decide:

```text
PR2_READY_FOR_OWNER_REVIEW
```

or

```text
PR2_KEEP_DRAFT
```

Do **not** mark the PR ready or merge.

## Files changed since last full browser cert (M47.4 → M47.6)

| File | Area | M47.7 validation mapping |
|---|---|---|
| `saathi/cors_policy.py` | CORS | Phase 8 runtime + unit tests |
| `saathi/server.py` | CORS middleware wiring | Phase 8 preflight / credentials |
| `tests/test_m47_6_cors_policy.py` | CORS unit | Phase 4 baseline |
| `saathi-os/components/chat/ChatWorkspace.jsx` | Chat + stop/stream | Phases 9–11 |
| `saathi-os/components/shell/CopilotPanel.jsx` | Compact chat | Phases 10–11 |
| `saathi-os/app/business/page.jsx` | Business honesty | Phase 14 |
| `saathi-os/app/command/page.jsx` | Command handoff | Phase 12 |
| `saathi-os/lib/navigation.js` | Nav labels | Phases 5–6 |
| M47.5 redirects (`redirects.js`, `next.config.mjs`, pages) | Soft redirects | Phase 7 |

## Managed lifecycle

```text
clean check free ports
start managed BFF (uvicorn, free port, SAATHI_ENV=development)
start managed frontend (next start|dev, free cert port in CORS allowlist)
wait health (UI / + BFF open endpoint)
run Playwright suites
capture console / network / screenshots
terminate frontend + BFF
verify no orphan cert children
non-zero exit on hard gate failure
```

Ports (preference order):

| Service | Prefer | Fallbacks |
|---|---|---|
| Frontend | 3110 | 3112 (both in M47.6 dev CORS allowlist) |
| BFF | 8766 | 18765, 18766 (avoid colliding with always-on :8765) |

Do **not** kill unrelated always-on processes on :8765. Cert must own its children only.

## Certification matrix

| test area | routes | browser actions | expected result | network | console | authority | evidence | failure class |
|---|---|---|---|---|---|---|---|---|
| Managed lifecycle | n/a | start/stop children | both healthy; clean exit | health 2xx-class | lifecycle logs | n/a | `lifecycle` in JSON | BLOCKING |
| Canonical routes | `/` `/command` `/missions` `/projects` `/approvals` `/monitoring` `/business` `/agents` `/trading` `/settings` `/chat` `/studio` `/studio/control-room` | goto, shell checks | HTTP success, shell, non-blank, no error boundary | page load | no fatal | trading advisory | pages + screenshots | BLOCKING |
| Compatibility | `/ceo` `/os` `/control` `/chat` `/workspace` `/saathi` `/voice` `/finance` `/studio-os` `/mission` `/trading` | load, no unexpected redirect | retained routes load; no accidental soft redirect | HTTP | non-fatal | no new authority | legacy map | BLOCKING if lost |
| Soft redirects | `/infrastructure` `/me` + query | follow redirect | temporary → monitoring/settings; query preserved | 307/308 soft | clean | n/a | redirects | BLOCKING |
| CORS runtime | BFF endpoints | OPTIONS + GET with Origin | allow exact origin; deny unknown; never `*`; bounded methods/headers | preflight headers | no fabricated pass | credentials explicit | cors JSON | BLOCKING |
| Chat workspace | `/chat` | open, composer, send safe, stop UI, full chrome | full workspace; honest errors if transport unavailable | `/api/v1/chat/*` | expected offline/auth noise | no privileged auto-exec | chat evidence | BLOCKING if crash/false success |
| Copilot panel | `/` + key pages | `]` open, Esc close, compact workspace | shared transport badge; compact only | same chat APIs | expected noise | advisory badge | copilot evidence | BLOCKING if crash |
| Shared transport | `/` + `/chat` | open both surfaces | one transport, two presentations | chat endpoints | n/a | no dual false session claim | coherence | BLOCKING if false claim |
| Control | `/control` | search UI, links | search present; no frontend authority | control APIs | offline ok | server auth | control | KEEP_COMPAT; block if missing |
| Approvals | `/approvals` | inbox load, dialog labels | unavailable ≠ zero; confirm dialogs | approvals APIs | offline ok | SERVER_AUTH | approvals | BLOCKING if false zero |
| Business/Finance | `/business` `/finance` | load text | not wired honest; no payment | optional | offline ok | no payment | biz/fin | KEEP_COMPAT |
| Studio | `/studio` `/studio-os` `/studio/control-room` | load | distinct boundaries; no redirect | studio APIs | offline ok | no extra authority | studio | KEEP_BOTH |
| Trading Guardian | `/trading` | scan body | advisory-only; no buy/sell/execute | n/a | clean | ADVISORY_ONLY | trading | BLOCKING if live action |
| Keyboard | `/` | ⌘K Esc ] g-h/c/p/m/a | once each; Esc topmost | n/a | clean | n/a | keyboard | BLOCKING core fail |
| Theme | settings + routes | dark/light/system | readable | n/a | clean | n/a | themes | BLOCKING blank |
| Density / experience | settings | compact/standard/comfortable; beginner/expert | no H-overflow; warnings remain | n/a | clean | protections stay | density | BLOCKING overflow |
| Responsive | phone→wide | layout chrome | phone tabs; desktop sidebar | n/a | clean | n/a | responsive | BLOCKING layout |
| A11y basics | high-traffic | headings, labels, focus | PASS_WITH_LIMITATIONS ok | n/a | clean | n/a | a11y doc | non-full WCAG |
| Console/hydration | all | collect | zero unexplained fatal | failed req classified | filtered noise | n/a | runtime | BLOCKING unexplained |

## Explicit M47.6 surface coverage

| Surface | Tests |
|---|---|
| CORS policy | Unit + managed BFF OPTIONS/GET allow/deny/credentials |
| ChatWorkspace | Full `/chat` load, chrome, send/error, Stop control present, stream abort path |
| CopilotPanel | Open/close, compact ChatWorkspace, shared transport label, Full chat link |
| Command | Canonical load; control handoff links |
| Business | Honest not-wired / no trade-payment language |
| Navigation | Active nav on canonical; studio labels not misleading |

## Failure classification legend

| Class | Meaning |
|---|---|
| BLOCKING_RUNTIME_FAILURE | Blocks `PR2_READY_FOR_OWNER_REVIEW` |
| NON_BLOCKING_KNOWN_LIMITATION | Documented; may keep draft if High/Critical residual |
| EXPECTED_TEST_CONDITION | Offline/auth/mock assertion |

## Owner-readiness logic (summary)

Ready only if hard gates pass, no Critical/High residual blockers, security/authority intact, and compatibility surfaces either certified or accepted KEEP_COMPATIBILITY with honest UI.

Otherwise:

```text
PR2_KEEP_DRAFT
```
