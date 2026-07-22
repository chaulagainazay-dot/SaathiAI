# SaathiOS — Current UI/UX Audit (Phase 1)

**Date:** 2026-07-19
**Branch:** `milestone/m7-security-engine`
**Scope:** Repository inspection before any redesign. No implementation changes made in this phase.
**Author:** Principal product designer / design-systems engineer (audit pass)

> This document is the gate for all later phases. It records **what exists today**, grounded in the repository — not what should exist. Recommendations are marked as such and are deferred to the IA / design-system / implementation docs.

---

## 0. Executive snapshot

SaathiOS already ships a **large, real, working frontend** — not a greenfield. There is a Next.js 15 / React 19 application (`saathi-os/`) with ~30 routes, a persistent shell (TopBar, Dock, CommandPalette, CEO Mode, mobile companion), and a **718-line typed API client** wired to a **real FastAPI backend** exposing **~448 endpoints across 83 router modules**. Real-time updates arrive over SSE (`LiveProvider`).

The problem is **not** missing capability. It is **coherence and consolidation**:

1. **Design language is applied by hand, not by system** — 1,595 inline `style={{…}}` sites vs. a 168-line token file that defines only ~12 tokens. The design system exists as a *philosophy PDF*, not as enforced code.
2. **Route + concept duplication** — several capabilities have 2–3 competing entry points (`studio` vs `studio-os`, `ceo` vs `ceo-os` vs `/`, `chat` vs `workspace`, `control` vs `control-center`, `os` vs `mission`). The `DEPARTMENTS` map even defines the `CONTROL` key twice.
3. **35 departments, 20 in the dock** — the navigation is a flat wall of destinations with no grouping, hierarchy, or beginner/expert distinction.
4. **Accessibility is largely absent** — ~50 `aria-*`/`role` attributes across the entire app; dark-mode-only (`color-scheme: dark`, zero `prefers-color-scheme` handling); focus states rely on browser defaults.
5. **Authority/risk is not a first-class visual concept** — approvals, leases, kill switches, simulated-vs-live, and evidence exist in the backend and in scattered pages, but there is no consistent, reusable status/risk/authority vocabulary in the UI.

**Verdict:** Consolidate and systematize the existing app. Do **not** rebuild. The redesign is a *design-system + information-architecture + state-coverage* program layered onto real, working routes and APIs.

---

## 1. Current frontend stack

| Layer | Technology | Evidence |
|---|---|---|
| Framework | **Next.js 15.1.6** (App Router) | `saathi-os/package.json`, `app/` dir |
| UI runtime | **React 19.0.0** | `package.json` |
| Styling | **Tailwind CSS v4** (`@tailwindcss/postcss`) + `@theme` tokens | `postcss.config.mjs`, `app/globals.css` |
| Animation | **framer-motion 11** | `package.json` |
| Fonts | `next/font` — Jura (display), Outfit (UI), Geist Mono (mono) | `layout.jsx`, `globals.css` |
| Data | Typed fetch client → FastAPI BFF (`:8765`) | `lib/api.js` (718 lines, 90 exported fns) |
| Real-time | SSE via `LiveProvider` | `components/live/LiveProvider.jsx` |
| PWA | manifest + service worker | `app/manifest.js`, `components/PWA.jsx`, `client/sw.js` |
| Session | localStorage token + `x-baadar-session` header (cookie-independent) | `lib/api.js` |

**Second, legacy frontend:** `client/` contains a standalone static `dashboard.html` + `index.html` + service worker — an older PWA surface, separate from `saathi-os`. This is a **duplicate frontend** and a consolidation candidate (see §12).

**Backend served UI:** `static/ielts/` holds a separate product surface (IELTSAlert), not part of the SaathiOS shell.

---

## 2. Existing routes (App Router)

Top-level (each is `app/<route>/page.jsx`):

`/` (CEO Home) · `/ceo` · `/os` · `/mission` · `/missions` (+ `/missions/new`, `/missions/[id]` and sub-routes: `website`, `intake`, `proposal`, `voice`, `reference`) · `/chat` · `/workspace` · `/studio` (+ `/studio/control-room`) · `/studio-os` · `/finance` · `/knowledge` (+ `/knowledge/library`) · `/learning` · `/projects` · `/project/create/[token]` (public client-facing) · `/evidence` · `/security` · `/connectors` · `/lab` · `/skills` · `/automation` (+ `/automation/production`) · `/control` (+ `/control/computer`) · `/infrastructure` · `/maturity` · `/voice` · `/me` · `/saathi` · `/unlock` · `/reset-password` · `/[dept]` (dynamic catch-all department page)

**Observations**
- ~30 concrete routes + 1 dynamic `[dept]` catch-all + nested mission/knowledge/automation/control/studio sub-routes.
- **Duplication clusters** (same job, multiple doors):
  - Executive: `/`, `/ceo`, `/os`, `/mission` all present executive/mission-control-style content.
  - Studio: `/studio`, `/studio-os`, `/studio/control-room`.
  - Conversation: `/chat`, `/workspace`, `/saathi`, `/voice`.
  - Control: `/control`, `/control/computer`, plus `control-center` referenced in CSS comments.
- `/project/create/[token]` correctly renders **bare** (no dock/nav) for external clients — good pattern, keep.

---

## 3. Existing components

**Shell chrome:** `Shell.jsx` (orchestrator), `TopBar.jsx`, `Dock.jsx`, `CommandPalette.jsx`, `CeoMode.jsx` (spacebar overlay), `Stars.jsx` + `Universe.jsx` (decorative background), `MissionNav.jsx`, `PWA.jsx`, `MobileMic.jsx`.

**Mobile companion:** `mobile/` — `MobileTopBar`, `MobileTabBar`, `MobileHome`, `MobileMe`, `MobileFinance`, `MobileSaathi`, `QuickSheet`.

**Feature workspaces:** `studio/StudioWorkspace`, `chat/ChatWorkspace` + `VoiceControl` + `AgentRunPanel`, `ceo/CeoWorkspace`.

**Live:** `live/LiveProvider` (SSE context), `live/LiveToasts` (actionable toasts).

**Primitives:** `components/ui.jsx` — the *only* shared primitive file. This is thin relative to a 30-route app; most UI is built ad-hoc inline (see §12).

**Hooks (`lib/`):** `useCeoHome`, `useVoice`, `useInfraHealth`, `useAutomation`, `passkey`, `data` (mock), `departments`, `api`.

---

## 4. Existing dashboards / layouts

- **Desktop = "Control Center":** TopBar + main + Dock. Full-width, dark, glass panels.
- **Mobile (<700px) = "CEO Companion":** separate `MobileTopBar` + `MobileTabBar` + bottom `QuickSheet` + floating mic. Genuinely adaptive, not just responsive reflow.
- **Tablet (700–1200px):** CSS forces desktop dashboard, collapses multi-column grids to single column.
- **CEO Mode:** full-screen spacebar-triggered overlay (`CeoMode.jsx`).
- Layout is driven by hand-authored inline grids per page rather than a shared layout primitive.

---

## 5. Existing design tokens

Defined in `app/globals.css` `@theme` block — **~12 tokens total**:

- Colors: `--color-ink` `#05070f`, `--color-bg` `#0a1120`, `--color-panel` (translucent white), ink ramp `ink-100…ink-500`, `--color-line`.
- Radius: `--radius-glass: 20px`.
- Fonts: `--font-display/ui/mono`.
- Utility classes: `.glass`, `.glass-soft`, `.eyebrow`, `.mono`, `.display`, `.aurora` (with `data-mood="amber|critical"`), `.stars`, `.pulse`, `.flow`.

**Department color system** lives separately in `lib/departments.js` — 35 department→hue mappings (the "immutable color system").

**Gaps vs. a real design system:** no spacing scale, no typographic scale, no elevation/shadow tokens beyond the baked-in glass shadow, no semantic status colors (success/warning/critical/blocked/simulated/live), no risk/authority colors, no light theme, no motion tokens, no density modes. The **design language is documented as a PDF** (`design/SAATHIAI_UI.pdf`, `design/SOVEREIGN_ORBIT.pdf`, `design/SOVEREIGN_ORBIT_philosophy.md`) — i.e. as *intent*, not as *enforced code*.

---

## 6. Existing API integrations

`lib/api.js`: **90 exported async functions**, all through one `afetch()` wrapper (adds session header, `credentials: include`). Backend base is env-driven (`NEXT_PUBLIC_SAATHI_API`), with a separate `LOCAL_BASE` for Mac-only capabilities (voice/STT, code-memory). Backend exposes **~448 endpoints across 83 router modules** in `saathi/`.

Representative endpoint families the UI already consumes:
`/api/executive/briefing` · `/api/v1/infrastructure/health` · `/api/v1/control/{overview,attention,timeline,security,search,release,computer}` · `/api/v1/connectors/*` (accounts, approvals, execute, executions, capabilities, health, metrics) · `/api/v1/missions/*` (incl. brand, document, proposal/decide, tasks, voice, workflows, twin) · `/api/v1/evidence` (+ stats) · `/api/v1/events` (+ stats) · `/api/v1/learning/{analyze,decide,recommendations}` · `/api/v1/lab/prompts` · `/api/v1/studio/{queue,plan,produce,script,control-room}` · `/api/v1/security/{health,timeline,tokens}` · `/api/v1/knowledge/{library,queue}` · `/api/v1/automation/{plan,settings,credits}` · `/api/v1/auth/*` (login, sessions, passkeys, oauth, audit) · `/api/v1/voice/{command,enroll}` · `/api/v1/intake/*` · `/api/v1/platform/maturity` · `/api/v1/human/*`.

**Implication:** the data foundation for a centralized OS **already exists**. Approvals, evidence, executions, security, timeline, and attention are all real API surfaces — the redesign should *surface and unify* them, not invent them.

---

## 7. Real-time event sources

- **SSE** via `components/live/LiveProvider.jsx` → drives `LiveToasts` (actionable notifications).
- Backend `/api/v1/events` (+ `/events/stats`) and control `/timeline`.
- No WebSocket usage detected in the frontend; realtime is SSE + polling (`cache: "no-store"` fetches, hook-driven).

---

## 8. Roles / permissions / authority concepts

Present in the **backend and data**, weak in the **UI vocabulary**:

- Auth surface is mature: sessions, passkeys, OAuth providers, audit log, session rotation/revocation (`/api/v1/auth/*`).
- Security surface: `/api/v1/security/{health,timeline,tokens}`, `security/` dir in repo, `SecretHandle` referenced in project docs.
- Approvals: `/api/v1/connectors/approvals/pending` + `/decide`; `home.approvals` in mock data; `control/attention` aggregates.
- **Missing in UI:** a consistent, reusable representation of *operator authority state*, *agent authority level* (advisor vs executor), *approval-required*, *simulated vs live*, *blocked-by-policy*. These appear as ad-hoc labels per page, not as a shared component vocabulary.

---

## 9. Agent / mission / workflow / studio / business / security / trading surfaces

| Surface | Route(s) | Backend | Notes |
|---|---|---|---|
| Executive / CEO | `/`, `/ceo`, `/os` | `/api/executive/briefing`, `/api/v1/ceo/os` | 3 overlapping doors |
| Missions / workflows | `/missions`, `/mission`, `/missions/[id]/*` | `/api/v1/missions/*`, `/mission` | rich sub-flows (intake→proposal→voice→website) |
| Agents | *(no dedicated route)* | `/api/v1/directors`, agent modules in `saathi/agents` | **No first-class Agents workforce screen** |
| Automations | `/automation`, `/automation/production` | `/api/v1/automation/*`, `/human/automation` | present |
| Studio | `/studio`, `/studio-os`, `/studio/control-room` | `/api/v1/studio/*` | 3 doors |
| Monitoring / infra | `/infrastructure`, `/control` | `/api/v1/infrastructure/health`, `/control/*` | present |
| Security | `/security` | `/api/v1/security/*` | present |
| Evidence | `/evidence` | `/api/v1/evidence` | present |
| Knowledge / memory | `/knowledge`, `/knowledge/library` | `/api/v1/knowledge/*` | present |
| Learning | `/learning` | `/api/v1/learning/*` | present |
| Connectors | `/connectors` | `/api/v1/connectors/*` | present |
| Business | `/finance`, `/[dept]` (cafeteria/travel/etc.) | partial | **No unified Business OS; per-dept scaffolds** |
| **Trading Guardian** | *(none)* | `crypto` dept color only | **Does not exist as a UI surface** — highest-risk gap |
| Approvals (central) | *(none — scattered)* | `/connectors/approvals/*`, `/control/attention` | **No central Approval Inbox screen** |

**Biggest capability gaps (design dependencies):** central **Approval Inbox**, first-class **Agents workforce**, and **Trading Guardian**. Data for approvals partially exists; Trading Guardian needs backend definition before UI (mark as design dependency — do not fabricate live trading data).

---

## 10. Broken / duplicated UI patterns

- **1,595 inline `style={{…}}` sites** — the dominant styling method. Design changes cannot be made centrally; every panel re-implements spacing, color, radius, shadow.
- **`DEPARTMENTS.CONTROL` defined twice** in `lib/departments.js` (Control Room vs Control Center) — the second silently wins.
- **Duplicate routes** for executive, studio, chat, control (see §2).
- **Two frontends** (`saathi-os/` and `client/`) and a third product surface (`static/ielts/`).
- **`lib/data.js` mock is now dead** — no file imports `@/lib/data` (real API took over), but the mock file and its `DREAM_TARGET`/`home` fixtures remain, risking accidental reuse and drift.
- Titles/eyebrows are half-derived, half-hardcoded (`TopBar.deriveTitle` + `TITLES` map) — inconsistent naming across routes.

---

## 11. Missing loading / empty / error / blocked / approval / permission states

- Only **26 of ~30 route files** reference any loading/error/empty handling keyword, and most are ad-hoc (a spinner or a thrown error). `lib/api.js` functions `throw new Error(...)` on non-OK — there is **no shared error/empty/blocked component**, so failures surface inconsistently (some as toasts, some as thrown errors, some silent).
- No standard **blocked-by-policy**, **approval-required**, **simulated/not-exercised**, **provider-unavailable**, **credential-missing**, or **permission-denied** UI states.
- Risk: raw error strings and unexplained spinners (the brief's explicit "no blank white pages / raw error dumps" rule is currently violable).

---

## 12. Accessibility issues

- **~50 `aria-*`/`role` attributes total** across the whole app — far below what a control surface of this size needs.
- **Dark-mode only:** `color-scheme: dark`, `0` `prefers-color-scheme` rules. No light theme.
- **Focus states** rely on browser defaults; heavy translucent glass backgrounds risk **insufficient contrast** (ink-400/500 on translucent panels).
- Status is often **color-only** (department hues, `data-mood`) — fails the brief's "color is never the only status indicator" rule.
- Keyboard: global `⌘K`, spacebar (CEO Mode), Escape are handled in `Shell`, but per-widget keyboard nav / tab order is not systematized.

---

## 13. Responsive-design issues

- Adaptive phone/tablet/desktop split is a **genuine strength** (phone companion vs desktop control center).
- But tablet handling is a blunt CSS override (`grid-template-columns: 1fr !important` on anything matching a selector) — fragile, `!important`-driven.
- Inline-styled grids per page mean responsive behavior is re-decided ad hoc; no shared breakpoint tokens.

---

## 14. Information-architecture problems

- **Flat, oversized navigation:** 35 departments, 20 pinned in the Dock, with no grouping into product areas (Work / Business / Studio / Monitoring / Security…).
- **No beginner/expert mode** — every operator sees the same expert-dense surface.
- **Overlapping mental models** — "department" vs "route" vs "dock item" vs "mission" are not cleanly separated; the same capability appears under several names.
- **No global concept of "what needs my attention"** unified across approvals, failures, expiring credentials, incidents — the data exists (`/control/attention`) but is not the spine of the Home screen.

---

## 15. Overloaded / underused screens

- **Overloaded:** `/` and `/control` try to be everything (executive brief + attention + timeline + security + search).
- **Underused / thin:** `/[dept]` catch-all department pages are scaffolds; several dock departments have no real backing screen.
- **Redundant:** `/ceo` + `/os` + `/mission` vs `/`; `/studio-os` vs `/studio`; `/workspace` vs `/chat`.

---

## 16. Components worth preserving

- **Shell orchestration model** (`Shell.jsx`) — clean separation of desktop/mobile chrome, keyboard handling, live provider wrapping. Keep and extend.
- **CommandPalette** (⌘K) — foundation for the Command Center.
- **LiveProvider + LiveToasts** (SSE) — the real-time backbone. Keep.
- **Mobile companion** set — genuinely good adaptive design; keep the phone-as-companion philosophy.
- **`lib/api.js`** typed client — the single source of truth for backend access. Keep; extend, don't replace.
- **Department color system** — good *idea* (one hue per area); needs to become tokens + be paired with non-color cues.
- **Public `/project/create/[token]` bare render** — correct pattern for external-facing pages.

---

## 17. Screens that should be consolidated

| Consolidate | Into | Rationale |
|---|---|---|
| `/`, `/ceo`, `/os` | **Home** (executive operating dashboard) | one executive door |
| `/mission` (control-style) | **Command Center** / Monitoring | mission-control belongs in ops |
| `/studio`, `/studio-os` | **Studio** | one production surface (`control-room` stays as a sub-view) |
| `/chat`, `/workspace`, `/saathi` | **Ask Saathi** (Copilot) + Command Center | conversation is a panel, not 3 pages |
| `/control`, `/control/computer` | **Monitoring** (+ Command Center for actions) | ops consolidation |
| `client/` static dashboard | retire in favor of `saathi-os` | remove duplicate frontend |
| `lib/data.js` mock | delete | dead code |

## 18. Screens that should remain separate

Security · Approvals (to be created, central) · Trading Guardian (to be created, isolated) · Evidence · Knowledge/Memory · Connectors · Projects · Missions (deep work surface) · Automations/Workflows · Settings · public `/project/create/[token]`.

---

## 19. Data & API dependency notes (for later phases)

- **Reusable now (real endpoints):** executive briefing, infra health, control overview/attention/timeline/security, connectors (+approvals), missions, evidence, events, learning, lab, studio, security, knowledge, automation, auth, voice, intake, maturity.
- **Design dependencies (UI needs backend definition or aggregation before building):**
  - **Central Approval Inbox** — aggregate `connectors/approvals/pending` + mission proposal decisions + any future deploy/finance/trading approvals into one feed (needs a unifying endpoint or BFF composition).
  - **Agents workforce** — `/api/v1/directors` exists; needs per-agent profile/authority/reliability/cost aggregation.
  - **Trading Guardian** — no backend surface today; **must not** be given fabricated live data. Design against explicit "not exercised / simulated" states until backend exists.
  - **Business OS** (HCG cafeteria, IELTSAlert metrics) — partial; per-venture metrics need real endpoints before dashboards are built.

---

## 20. Audit conclusion & recommended first milestone

**Conclusion:** SaathiOS is a capable but *hand-assembled* operating surface. The redesign is a **systematization + consolidation** effort, not a rebuild. Priorities, in order of leverage:

1. **Design tokens** — convert the PDF philosophy + inline styles into an enforced token layer (color/spacing/type/elevation/status/risk/authority, + light theme + non-color status cues). Highest leverage: unblocks everything and directly attacks the 1,595-inline-style problem.
2. **Shell + navigation IA** — group 35 destinations into ~12 product areas with beginner/expert modes; kill route duplication; fix the duplicate `CONTROL` key.
3. **Shared state components** — loading/empty/error/blocked/approval/permission/simulated, so no screen can show a raw spinner or error dump.
4. **Home (attention-first)** + **Command Center** + central **Approval Inbox** on real APIs.

**Recommended first implementation milestone (safest, highest leverage):**
> **Milestone 1 — Design Token Foundation.** Add a complete token layer to `app/globals.css`'s `@theme` (semantic color, spacing, type scale, elevation, status/risk/authority palettes, light+dark) plus a small documented set of primitive components in `components/ui.jsx` (StatusBadge, RiskBadge, AuthorityBadge, EnvironmentBadge, EmptyState, LoadingState, ErrorState, BlockedState). This changes **no routes and no APIs**, is fully backward-compatible (existing inline styles keep working), and every later milestone builds on it. Ship it behind no flag; migrate inline styles opportunistically.

No implementation has been performed in this phase. Proceed to Phase 2 (Information Architecture) and the design-system doc once this audit is accepted.
