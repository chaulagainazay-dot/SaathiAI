# SaathiOS — Navigation Model (Phase 2b)

**Date:** 2026-07-19
**Depends on:** `SAATHIOS_INFORMATION_ARCHITECTURE.md`
**Status:** Design proposal. Extends the existing `Shell.jsx` / `TopBar.jsx` / `Dock.jsx` / `CommandPalette.jsx` — does not replace the shell model (audit §16 keeps it).

---

## 1. Shell regions

```
┌───────────────────────────────────────────────────────────────────────┐
│  TOP BAR: [env] [breadcrumb/title]      ⌘K search   + create   ● status │
│                                     approvals▪  alerts▪  Ask Saathi  [A] │
├───────────┬─────────────────────────────────────────────┬─────────────┤
│  SIDEBAR  │  MAIN WORKSPACE                              │  COPILOT     │
│  (rail /  │  page header · context · actions · tabs     │  (collapsible│
│  expanded)│  filters · content · timeline · evidence    │   Ask Saathi)│
│           │                                             │              │
├───────────┴─────────────────────────────────────────────┴─────────────┤
│  STATUS BAR: active runs · queued · providers · local models · sync ·   │
│              environment · security state · resource pressure           │
└───────────────────────────────────────────────────────────────────────┘
```

Maps onto existing components: TopBar (extend), Dock→**Sidebar** (restructure), CommandPalette (extend), CeoMode (keep as overlay), LiveProvider/LiveToasts (feed status bar + alerts), Copilot (new right panel).

---

## 2. Left sidebar

- **Two modes:** compact (icon rail, ~64px) and expanded (~240px). Persist choice. Existing `Dock` becomes the compact rail's ancestor.
- **Order:** Favorites/Pinned → Recent projects → the 4 groups (OPERATE / WORK / RUN THE BUSINESS / SYSTEM) with the 12 areas (IA §4).
- **Active workspace** highlighted with its accent hue (department color demoted to accent).
- **Collapsible groups**; group state persists.
- **Risk marker** persistently on Trading Guardian.
- **Badges:** Approvals count, Monitoring incident count — driven by live SSE.

## 3. Top command bar

Left → right:
- **Environment indicator** — `local · VM · production` (from `NEXT_PUBLIC_SAATHI_API`). Production = distinct, unmistakable color.
- **Breadcrumb / title** — replaces `TopBar.deriveTitle` half-derived/half-hardcoded logic (audit §10) with area→sub→object breadcrumb.
- **⌘K global search** (exists — extend to objects + commands).
- **+ Create** — new mission / project / automation / studio brief.
- **Ask Saathi** — toggles Copilot panel.
- **System health** dot → Monitoring.
- **Approvals** badge → Approval Inbox.
- **Alerts** badge → notification center.
- **Operator identity + authority state** — avatar (exists), with authority chip (e.g. "Owner · full").

## 4. Command palette (⌘K) — extended

Existing palette is the seed. Add:
- **Navigate:** jump to any area, project, mission, agent, run, doc.
- **Act:** run a command → routes into Command Center flow (intent → plan → approval → execute; see Command Center UX, later phase). Never executes sensitive actions directly from the palette.
- **Recent + suggestions** surfaced when empty.

## 5. Right Copilot panel ("Ask Saathi")

- Collapsible, context-aware to the current page/object.
- Shows: page-aware suggestions, recommended next actions, explanations, warnings, evidence, related projects, current run status, approval requirements, safe-action previews.
- **Hard rule:** never renders "done / executed" language without linked execution evidence. Suggested actions are *previews* until approved.
- Replaces `/chat`, `/workspace`, `/saathi` as pages — conversation is ambient, available everywhere.

## 6. Bottom status bar

Live (SSE-fed): active runs · queued jobs · provider status · local model status · sync state · environment · security state · resource pressure. Click any segment → the relevant Monitoring view. Hidden on phone (companion has its own chrome).

## 7. Mobile navigation (keep the companion)

- Phone (<700px) keeps the existing **CEO Companion**: `MobileTopBar` + `MobileTabBar` + `QuickSheet` + floating mic.
- Mobile tab bar = **5 items max**: Home · Approvals · Ask Saathi · Business · Me. (Approvals promoted to mobile — approving on the go is a core journey.)
- Expert controls are **not** forced onto mobile (brief rule). Mobile = monitoring + approvals + ask, not authoring.

## 8. Keyboard model (extend existing)

Existing global keys in `Shell.jsx`: ⌘K palette, Space = CEO Mode, Esc = close. Add:
- `g` then letter → go to area (`g h` Home, `g c` Command Center, `g a` Approvals…).
- `[` / `]` → collapse/expand sidebar / Copilot.
- Full tab-order + visible focus rings (a11y doc, later phase). Fix current default-focus reliance.

## 9. Redirects (backward compatibility)

All retired routes 301/replace to their consolidated target so existing links/bookmarks/PWA shortcuts keep working:
`/ceo`,`/os` → `/` · `/mission` → `/command` · `/studio-os` → `/studio` · `/chat`,`/workspace`,`/saathi` → open Copilot on `/` · `/me` → `/settings`. `/[dept]` catch-all → `/business` or the mapped area.

## 10. Fixes folded into nav work

- Deduplicate `DEPARTMENTS.CONTROL` (defined twice, audit §10).
- Replace `Dock` flat 20-item list with grouped sidebar.
- Replace `TopBar.deriveTitle` guesswork with breadcrumb from the route→area map.

---

## M58 — Spatial navigation (2026-07-26)

`/platform` and `/platform/ops` adopt a spatial command model on top of the existing
shell. Full detail in `docs/platform/M58_SPATIAL_NAVIGATION.md`.

- **Central SaathiCore** communicates system state (READY/ATTENTION/BLOCKED/IDLE/
  UNKNOWN) with colour + text.
- **Floating module ring** (12 modules) placed by deterministic `ringLayout`; each node
  is a real focusable `<button>` with icon, label, status pulse, live count.
- **Connections** are semantic (cyan data / amber authority / red blocked / grey
  inactive / green verified); selected path illuminates; every edge maps to a real
  navigation or authority relationship.
- **Interaction:** in-page modules scroll to their glass panel + set `aria-current`;
  routed modules `router.push`. Ops nodes open a right-side contextual glass drawer.
- **Responsive:** ≤900px the ring degrades to an accessible node grid (connections
  hidden); touch targets ≥44px. The shell rail + ⌘K palette remain around the scope.
