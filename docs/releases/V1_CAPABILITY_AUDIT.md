# SaathiOS v1.0 — Capability Audit (Phase 1)

**Captured:** 2026-07-10 · **Branch:** `milestone/m7-security-engine` @ `d1736ed`
**Scale:** 291 API endpoints · 35 frontend routes · 116 backend test files · ~100 backend modules
Machine-readable: `docs/releases/v1_capability_registry.json`

Classification legend: **READY** (works UI+real data+states+auth) · **DEGRADED** (works but missing states/auth/mobile/tests) · **MOCK** (renders on fake/sample data) · **BROKEN** (errors) · **UNUSED** (no route wiring) · **EXPERIMENTAL** (behind-flag candidate).

> Honesty note: classifications below are from static inspection + startup smoke + prior runtime smoke of 10 routes. Full READY certification requires the Phase 9–11 per-flow UI + responsive + test verification, which has **not** been run for most surfaces. Where UI data-state/auth/mobile/test evidence is absent, the surface is capped at **DEGRADED** regardless of how polished the code looks.

---

## A. v1 target navigation vs. reality

| v1 surface (Phase 2 target) | Frontend route | Backend | Status | Gap to v1 |
|---|---|---|---|---|
| 1. Home / CEO OS | `/os`, `/` | `/api/v1/ceo` (3), `/api/v1/dashboard` (3), BFF | **DEGRADED** | 2 BFF contract tests fail (`payload contract`, `dream_pct`) → risk of NaN/fabricated metrics |
| 2. Saathi Chat | `/saathi` | `/api/v1/agent/chat`, `/agent/chat_with_file` | **DEGRADED→partial** | **No 6-mode (Ask/Research/Plan/Code/Execute/Cowork). No conversation persistence API. No streaming/stop/regenerate/edit contract. No cited-research path wired.** Phase 3 largely unbuilt. |
| 3. Missions | `/missions*` (8 routes) | `/api/v1/missions` (27), `/mission` (2), `/intake` (8) | **DEGRADED** | Richest surface; needs per-flow UI verification (intake→knowledge→timeline→proposal→evidence). |
| 4. Tasks / Cowork | `/workspace`, `/projects` | `/api/v1/tasks` (3), `/workspace` (2) | **BROKEN/absent for Cowork** | Tasks = flat done/clear only. **No durable Work Session, no states (PLANNING…FAILED), no resume-after-restart.** Phase 6 unbuilt. |
| 5. Code Workspace | `/workspace` | `/github/actions` (GET), `/code-memory/status` (GET) | **MOCK/absent** | **No repo open, tree, file read/write/delete, patch/diff, run tests, git branch/commit, rollback.** Phase 5 unbuilt — only read-only status stubs exist. |
| 6. Automation / Execution | `/automation*` | `/automation` (5), `/directors` (3), `/factory` (6) | **DEGRADED** | Runs exist; **not routed through a Secure Execution Layer** (see §C). |
| 7. Files / Knowledge | `/knowledge*`, files | `/knowledge` (7), `/files/upload`, `/evidence` (3) | **DEGRADED** | Upload + knowledge exist; retrieval-into-chat (Phase 3/4) not wired. |
| 8. Connected Accounts | `/connectors` | `/connectors` (6), `/connections` (2) | **DEGRADED** | Needs Account-Center consolidation: expiry/health/last-error/quota per Phase 8; must show `Not configured`/`Reauth required` truthfully. |
| 9. Security | `/security`, `/unlock` | `/auth` (24), `/security` (5) | **DEGRADED (strongest)** | Auth v1.2 platform, 24 endpoints, passing auth tests. Needs full Phase 9 auth-flow UI verification + secret-exposure fix. |
| 10. Settings | `/me`, `/settings`-ish | `/system` (2), `/platform` | **DEGRADED** | Present; unverified. |

## B. Full endpoint groups (291 total)

`auth 24 · missions 27 · studio 38 · human 10 · reddit 10 · intake 8 · pielts 8 · knowledge 7 · linkedin 7 · analytics 6 · connectors 6 · factory 6 · yeti 6 · automation 5 · lab 5 · mac 5 · security 5 · skills 5 · tiktok 5 · comments 4 · content 4 · project 4` + ~40 singletons (`dev`, `auto_develop`, `auto_improve`, `github`, `code-memory`, `n8n`, `telegram`, `hcgms`, `generate_image`, `hyperframes`, `trends`, `voice`, `workspace`, `tasks` …).

Observation: the surface is **content/marketing-engine heavy** (studio 38, reddit/linkedin/tiktok/yeti/factory ~35). The v1 "unified AI workspace" surfaces (chat modes, code, cowork) are the **thinnest** part of the API — the opposite of the release thesis.

## C. Universal Secure Execution Layer (Phase 7) — DEAD CODE

| Fact | Evidence |
|------|----------|
| `saathi/execution/` has `toolintent.py`, `gateway.py`, `state.py`, `results.py`, `errors.py`, `adapters/`, `orchestrators/`, `queue/`, `integration.py` | present |
| `saathi/execution/__init__.py` | **empty — exports nothing** |
| Server import of ExecutionGateway/ToolIntent | **none** (`grep` on server.py + all top-level modules: 0 hits) |
| Tests | `test_execution.py` **fails collection** (imports `ExecutionIntent`, no longer exists) |
| Queue methods async but gateway calls them sync | noted TODO in integration.py |

**Verdict: the execution layer is unwired, unexported, and untested at collection time. No Director/chat/workflow routes side-effects through it.** Phases 5–7 cannot be called complete. This is the single biggest release blocker.

## D. Test-visible BROKEN

| Area | Tests | Root cause |
|---|---|---|
| Infra event bus | `test_infra_events.py` ×4, `test_eventstream.py` ×1 | `saathi.events.bus` lost `subscribe()` → Phase 9 "Automation/Infrastructure health valid, no NaN" at risk |
| BFF/CEO OS contract | `test_bff.py` ×2 | payload shape + dream_pct metric drift → **fabricated/incorrect Home metrics** (violates "Unknown, never fabricated") |
| Studio tracking | `test_ai_lab.py`, `test_client_intake.py` | studio run tagging attribute drift |
| Execution import | 3 files | empty `__init__` / rename regression |

## E. Not audited to READY (require Phase 9–11 execution)

Per-route loading/empty/error-state proof, cross-Mission isolation tests, responsive (iPad/mobile/safe-area), ExecutionGateway tests, code-workspace safety tests, migration check, offline/reconnect. **None run yet.** Therefore **no surface qualifies as READY** under the non-negotiable definition — the ceiling today is DEGRADED.

## F. Classification roll-up

- READY: **0** (definition not yet satisfiable — no Phase 9–11 evidence)
- DEGRADED: Home, Missions, Automation, Knowledge/Files, Connectors, Security, Settings (~7 clusters, ~230 endpoints)
- Partial/absent for v1 thesis: **Saathi Chat (6-mode), Code Workspace, Cowork** — the three headline v1 features
- BROKEN: execution import (3 files), infra events (5 tests), BFF contract (2 tests)
- Secret exposure: HF token + firebase-admin.json (Security-critical)

---

## Gate decision for Phases 2–12

Cannot proceed to build Phases 3–7 on top of a red baseline. **Required-first repair set (release-critical slice):**
1. Fix `saathi/execution/__init__.py` exports + rename dependents → un-break 3 test files, then wire gateway into at least the connector execute path.
2. Restore `saathi.events.bus.subscribe` (or update 5 tests to current API) → infra/automation health valid.
3. Fix BFF contract + dream_pct → Home shows real/Unknown, never fabricated.
4. Rotate HF token, de-track firebase-admin.json.
5. Only then: build 6-mode chat, code workspace, cowork per Phases 3–6, each to the 8-point completion bar.

Estimated scope: multi-session engineering program, not a single pass.
