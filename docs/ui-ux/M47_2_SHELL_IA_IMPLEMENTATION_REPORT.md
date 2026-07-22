# M47.2 — Shell & IA Implementation Report

**Date:** 2026-07-22  
**Branch:** `milestone/saathios-ui-ux`  
**PR:** #2 draft — `feat(saathios): establish centralized UI/UX foundation`  
**Starting commit:** `dc177c8f3925cd6d5da34babdd5c31ce54fc3fb1`  
**Program state:** `PR2_UI_UX_IMPLEMENTATION_IN_PROGRESS` → shell/IA slice complete with limitations

---

## Summary

Replaced the desktop bottom Dock with a grouped left sidebar, rebuilt the operator TopBar, added a passive status bar and Ask Saathi panel scaffold, introduced the canonical 12-area navigation model, fixed the duplicate CONTROL department key, shipped seven new canonical route surfaces, aligned mobile tabs, and migrated the command palette to safe navigation-only actions.

## Navigation data

- **New:** `saathi-os/lib/navigation.js` — `NAV_GROUPS` (4), 12 primary areas, `GLOBAL_NAV`, `MOBILE_TABS`, `GO_SHORTCUTS`, `matchNavItem`, `breadcrumbFor`, `validateNavigationModel`, `inferEnvironment`
- **Updated:** `saathi-os/lib/departments.js` — department hues retained as accents; `STUDIO_CONTROL` + `CONTROL_CENTER`; single `CONTROL` compat alias; `DOCK` deprecated short list
- **Preferences:** `saathi-os/lib/preferences.js` — theme / density / experience / sidebar / copilot persistence

### CONTROL resolution

Previously two `CONTROL` keys in one object (silent overwrite). Now:

- `STUDIO_CONTROL` → `/studio/control-room`
- `CONTROL_CENTER` → `/control`
- `CONTROL` → `/control` (compat for existing imports)

## Shell components

| Component | Role |
|---|---|
| `components/shell/Sidebar.jsx` | Grouped primary nav + globals; expand/collapse; `aria-current` |
| `components/TopBar.jsx` | Env, breadcrumb, ⌘K, Create→command, approvals, alerts, Ask Saathi, authority, settings |
| `components/shell/StatusBar.jsx` | Live connection, env, authority, approvals honesty, prefs |
| `components/shell/CopilotPanel.jsx` | Bounded Ask Saathi scaffold |
| `components/shell/ShellChromeContext.jsx` | Shared shell + prefs state |
| `components/Shell.jsx` | Orchestration, keyboard (`⌘K`, Esc, `]`, `g` then letter), bare public routes |
| `components/Dock.jsx` | No-op stub (deprecated) |
| `components/CommandPalette.jsx` | Canonical + safe actions + legacy group |
| `components/mobile/MobileTabBar.jsx` | Home · Approvals · Ask Saathi · Business · Me |

## Canonical routes

| Route | Implementation |
|---|---|
| `/command` | Control overview + attention; observe/plan/approval/execute gates labeled |
| `/agents` | `fetchDirectors` or honest empty/error |
| `/business` | Compose finance/projects links; partial backend badge |
| `/trading` | Advisory-only BlockedState; no execution UI |
| `/monitoring` | Infra health observe; links to legacy infra/control |
| `/approvals` | Connector pending + source coverage (connected/unavailable/not integrated) |
| `/settings` | Theme, density, experience, sidebar; link to Security |

## Redirects

**None added.** See `M47_2_ROUTE_COMPATIBILITY_MATRIX.md`.

Deferred: `/chat`, `/workspace`, `/saathi`, `/voice`, `/control`, `/ceo`, `/os`, etc.

## Theme / density / experience

- `data-theme` light via attribute; dark default; system via `prefers-color-scheme`
- `data-density` compact | standard | comfortable
- `data-experience-mode` beginner | expert — **verbosity only**
- LocalStorage keys under `saathi_pref_*`

## Primitive adoption (new code)

Uses M1: `Surface`, `Card`, `Button`, `StatusBadge`, `AuthorityBadge`, `RiskBadge`, `EnvironmentBadge`, `EvidenceBadge`, `LoadingState`, `EmptyState`, `ErrorState`, `BlockedState`, `IconButton`, `Heading`, `Text`.

Legacy pages **not** mass-migrated.

## Accessibility improvements

- Semantic `<nav>`, `<aside>`, `<header>`, `<footer role="status">`
- `aria-current="page"` on active nav
- IconButton labels; focus-visible (M1) retained
- Reduced-motion transitions on shell layout
- Mobile tab labels preserved

## Intentional deviations from IA docs

1. User brief groups (OPERATE includes Missions/Agents/Automation) followed over earlier IA doc §4 ordering where they conflicted.
2. Status taxonomy uses M1 token names (`status-pending` etc.), not every DS table glyph.
3. Copilot does not replace chat routes yet (explicit milestone rule).
4. Approvals aggregation is connector-first only; other sources marked not integrated.

## Known limitations

1. Inline style count 1611 → 1635 (+24)
2. Light theme not WCAG-certified per screen
3. Approval decide not exposed (by design); inbox is review shell
4. Agents aggregation still thin (directors list only)
5. Business OS not unified backend
6. Trading has no certified read-only market data
7. Legacy redirects deferred
8. `next lint` still unconfigured repo-wide
9. Double CSS offset for TopBar/main requires desktop viewport ≥700px (mobile companion unchanged)

## Next recommended milestone

**M47.3 — Primitive adoption + Approval Inbox depth + Home attention spine**  
Or **M47.4 — Safe legacy redirects** after Home/Command/Copilot parity validation.

## Final state

```text
M47_2_COMPLETE_WITH_LIMITATIONS_PR2_DRAFT
```
