# SaathiOS — Information Architecture (Phase 2)

**Date:** 2026-07-19
**Depends on:** `SAATHIOS_CURRENT_UI_AUDIT.md`
**Status:** Design proposal — no implementation. Evaluated against repository evidence (35 departments, ~30 routes, ~448 backend endpoints).

> Goal: collapse a flat wall of 35 destinations into a hierarchy an operator can understand in under a minute, without hiding authority, risk, or operational state. Supports **Beginner** and **Expert** modes on the same structure.

---

## 1. Design principles

1. **Attention-first.** The system's spine is "what needs me now," not "here are all the tools." The data already exists (`/api/v1/control/attention`, approvals, events).
2. **One door per job.** Every capability has exactly one canonical route. Duplicates from the audit (§17) are consolidated or demoted to sub-views.
3. **Group by intent, not by module.** ~12 product areas, each a coherent operator goal — not 35 backend services.
4. **Progressive disclosure.** Beginner sees plain language + important actions; Expert reveals run IDs, evidence, policies, budgets, providers, logs. Same IA, denser payload.
5. **Authority is visible, never bypassable.** Approvals, leases, kill switches, simulated-vs-live are represented consistently and cannot be actioned around via UI.
6. **Never fabricate.** Missing data/endpoints render explicit "not exercised / design dependency" states, not fake numbers.

---

## 2. Top-level product areas (primary navigation)

12 areas. Evaluated against the brief's proposed 14 and trimmed to avoid overload (audit §14). Each maps to real routes/APIs; new areas are flagged.

| # | Area | Canonical route | Consolidates (audit §17) | Backing API | Status |
|---|---|---|---|---|---|
| 1 | **Home** | `/` | `/ceo`, `/os` | `/api/executive/briefing`, `/control/attention` | exists (merge) |
| 2 | **Command Center** | `/command` | `/mission`, parts of `/control` | `/control/*`, `/agent/chat`, missions | exists (rehome) |
| 3 | **Work** (Missions) | `/missions` | `/mission` deep-work parts | `/api/v1/missions/*` | exists |
| 4 | **Agents** | `/agents` | — (**new**) | `/api/v1/directors` + aggregation | **design dependency** |
| 5 | **Automations** | `/automation` | `/automation/production` (sub) | `/automation/*`, `/human/*` | exists |
| 6 | **Projects** | `/projects` | `/[dept]` scaffolds | `/api/v1/intake/*` | exists |
| 7 | **Business** | `/business` | `/finance`, `/[dept]` ventures | partial (**gap**) | partial |
| 8 | **Studio** | `/studio` | `/studio-os`, `/studio/control-room` (sub) | `/api/v1/studio/*` | exists (merge) |
| 9 | **Trading Guardian** | `/trading` | — (**new**) | none today | **design dependency** |
| 10 | **Monitoring** | `/monitoring` | `/infrastructure`, `/control` ops | `/infrastructure/health`, `/control/*`, `/events` | exists (merge) |
| 11 | **Knowledge** | `/knowledge` | `/knowledge/library` (sub), `/learning` | `/knowledge/*`, `/learning/*` | exists |
| 12 | **Security** | `/security` | — | `/api/v1/security/*`, `/auth/*` | exists |

**Global (not in the 12, always reachable via chrome):**
- **Approvals** — approval inbox, surfaced in the top bar as a badge + a dedicated `/approvals` view (aggregates `connectors/approvals/pending` + mission decisions). *Elevated to chrome because it is cross-area and time-sensitive.*
- **Ask Saathi (Copilot)** — right-side context panel, not a page (replaces `/chat` + `/workspace` + `/saathi` as *pages*; conversation becomes ambient).
- **Settings** — `/settings` (consolidates `/me`, connectors config, automation settings, theme/density/mode).
- **Evidence** — reachable contextually from any run/decision; also `/evidence` as a browsable store.

**Retired:** `/ceo`, `/os`, `/mission`, `/studio-os`, `/chat`, `/workspace`, `/saathi` as standalone pages → redirect to their consolidated home. `client/` static frontend and `lib/data.js` mock → deleted.

---

## 3. Navigation layers

- **Primary** — left sidebar, the 12 areas, grouped (see §4). Collapsible to icon rail.
- **Secondary** — within an area, tabs/sub-nav (e.g. Studio → Queue · Control Room · Calendar · Assets).
- **Contextual** — right Copilot panel + per-object actions (mission → intake/proposal/voice/website already exist as sub-routes).
- **Global search / Command palette** — ⌘K (exists), extended to jump to any object (mission, agent, run, project, doc) and to run commands.
- **Recent / Favorites / Pinned** — top of sidebar; pinned workspaces + recent projects (mobile companion already has a recents notion).
- **Environment indicator** — persistent (local / VM / production), from `NEXT_PUBLIC_SAATHI_API` context.
- **System status + notifications + approval inbox + operator identity/authority** — top bar cluster.

---

## 4. Sidebar grouping (the 12 areas → 4 groups)

```
▸ OPERATE
   Home
   Command Center
   Approvals          (badge)
▸ WORK
   Work (Missions)
   Projects
   Automations
   Studio
▸ RUN THE BUSINESS
   Business
   Trading Guardian   (risk-flagged)
▸ SYSTEM
   Agents
   Monitoring
   Knowledge
   Security
   Settings
```

Rationale: groups map to operator mindset — *what needs me* → *what I'm building* → *what earns money* → *what keeps it safe*. Trading Guardian carries a persistent risk marker even in nav.

---

## 5. Beginner vs Expert mode

Single toggle in Settings + top bar; persists per operator. **Same IA, different payload density.**

| Dimension | Beginner | Expert |
|---|---|---|
| Terminology | plain ("Waiting for your OK") | precise ("approval-required, lease T-3h") |
| Surfaced actions | important + safe only | all, incl. advanced/destructive |
| IDs & evidence | hidden behind "Details" | run IDs, evidence, provenance inline |
| Policies/budgets/providers | summarized | raw, with controls |
| Logs | hidden (Details → last) | available, progressive |
| Retries/dependencies/config | hidden | inline |
| Trading Guardian | advisory view only by default | full risk controls (still gated) |

Mode never changes **authority** — it changes **verbosity**. Expert mode does not grant new permissions; it only reveals detail and advanced controls that remain policy-gated.

---

## 6. Cross-cutting surfaces

- **Attention Queue** (Home spine) — unifies failed runs, pending approvals, expiring credentials, delayed projects, business alerts, incidents, content approvals, trading warnings, missed tasks, degradation. Source: `/control/attention` + aggregation.
- **Approval Inbox** — global; every sensitive action funnels here (see `SAATHIOS_APPROVAL_UX.md`, later phase).
- **Copilot (Ask Saathi)** — page-aware; shows suggestions, next actions, explanations, warnings, evidence, related projects, run status, approval requirements, safe-action previews. **Never implies execution without evidence.**
- **Evidence** — any run/decision links to its evidence; browsable store at `/evidence`.

---

## 7. Object model (what the operator navigates between)

Clean separation (audit §14 problem was overlapping models):

- **Area** — one of 12 nav destinations (a *place*).
- **Project** — a venture/workstream (SaathiAI, IELTSAlert, HCG POS, crypto/NEPSE, travel, content).
- **Mission** — a bounded unit of work with lifecycle (intake→proposal→execution→evidence).
- **Agent** — an actor with an authority level (advisor/planner/executor/reviewer/monitor/approver/bounded-autonomous).
- **Run** — one execution instance (has status, evidence, cost, provider, retries).
- **Approval** — a gate on a sensitive action.
- **Evidence** — provenance for a run/decision.

"Department" (the current 35-hue system) is **demoted** from a navigation concept to a **visual accent** applied to Areas/Projects (see design-system doc). It stops being a route.

---

## 8. Mapping: current → target (consolidation table)

| Current route(s) | Target area | Action |
|---|---|---|
| `/`, `/ceo`, `/os` | Home | merge into one; redirect old |
| `/mission`, `/control` (ops) | Command Center + Monitoring | split by intent (act vs observe) |
| `/missions/*` | Work | keep, re-home under WORK group |
| *(none)* | Agents | **create** (design dependency) |
| `/automation`, `/automation/production` | Automations | keep; production = sub-tab |
| `/projects`, `/[dept]` | Projects | keep; retire `[dept]` scaffolds |
| `/finance`, `/[dept]` ventures | Business | consolidate into Business OS |
| `/studio`, `/studio-os`, `/studio/control-room` | Studio | merge; control-room = sub-tab |
| *(none)* | Trading Guardian | **create** (design dependency, isolated) |
| `/infrastructure`, `/control` | Monitoring | merge |
| `/knowledge`, `/knowledge/library`, `/learning` | Knowledge | merge; library + learning = sub-tabs |
| `/security` | Security | keep |
| `/chat`, `/workspace`, `/saathi`, `/voice` | Copilot panel + Command Center | demote pages to ambient panel |
| `/me`, connectors/automation settings | Settings | consolidate |
| `/evidence` | Evidence (contextual + store) | keep |
| `client/` static app | — | delete |
| `lib/data.js` | — | delete |

---

## 9. Open dependencies (carried to implementation)

1. **Approval Inbox aggregation endpoint** (or BFF composition) — unify pending approvals across connectors, missions, and future deploy/finance/trading.
2. **Agents aggregation** — per-agent authority/reliability/cost/workload on top of `/directors`.
3. **Trading Guardian backend** — must exist before the UI shows anything but "not exercised / simulated." Do not fabricate.
4. **Business venture metrics** — real per-venture endpoints (HCG cafeteria, IELTSAlert) before dashboards.

These are the only genuine backend gaps; everything else in the IA maps to existing APIs.
