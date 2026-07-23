# M47.2 — Shell & Information Architecture Implementation Plan

**Date:** 2026-07-22  
**Branch:** `milestone/saathios-ui-ux`  
**Baseline HEAD:** `dc177c8f3925cd6d5da34babdd5c31ce54fc3fb1`  
**PR:** #2 (draft) → `master`  
**Starting inline styles:** 1611

---

## 1. Files to modify

| File | Change |
|---|---|
| `saathi-os/lib/departments.js` | Fix duplicate `CONTROL`; keep DEPARTMENTS as accent metadata; deprecate DOCK |
| `saathi-os/components/Shell.jsx` | Wire sidebar, new TopBar, status bar, Copilot; prefs; keyboard |
| `saathi-os/components/TopBar.jsx` | Rebuild operator chrome (or replace via shell/TopBar) |
| `saathi-os/components/Dock.jsx` | Demote to unused/compat stub (desktop uses Sidebar) |
| `saathi-os/components/CommandPalette.jsx` | Canonical nav + safe commands only |
| `saathi-os/components/mobile/MobileTabBar.jsx` | Home · Approvals · Ask Saathi · Business · Me |
| `saathi-os/app/layout.jsx` | Suppress hydration warning on theme attrs if needed |
| `saathi-os/app/globals.css` | Shell layout tokens (sidebar widths, status bar, main offset) |
| `saathi-os/package.json` | Add `test` script (node:test) |

## 2. Files to create

| File | Purpose |
|---|---|
| `saathi-os/lib/navigation.js` | Canonical NAV_GROUPS, globals, aliases, match helpers |
| `saathi-os/lib/preferences.js` | Theme/density/experience persistence + apply |
| `saathi-os/components/shell/Sidebar.jsx` | Grouped left rail |
| `saathi-os/components/shell/StatusBar.jsx` | Passive status strip |
| `saathi-os/components/shell/CopilotPanel.jsx` | Ask Saathi scaffold |
| `saathi-os/components/shell/ShellChromeContext.jsx` | Shared shell UI state |
| `saathi-os/app/command/page.jsx` | Command Center surface |
| `saathi-os/app/agents/page.jsx` | Agents registry scaffold |
| `saathi-os/app/business/page.jsx` | Business OS compose/scaffold |
| `saathi-os/app/trading/page.jsx` | Trading Guardian advisory-only |
| `saathi-os/app/monitoring/page.jsx` | Observability compose |
| `saathi-os/app/approvals/page.jsx` | Approval inbox shell |
| `saathi-os/app/settings/page.jsx` | Theme/density/experience prefs |
| `saathi-os/lib/navigation.test.js` | Nav integrity + safety unit tests |
| `docs/ui-ux/M47_2_ROUTE_COMPATIBILITY_MATRIX.md` | Legacy→canonical matrix |
| `docs/ui-ux/M47_2_SHELL_IA_IMPLEMENTATION_REPORT.md` | Final report |
| `docs/ui-ux/M47_2_VALIDATION_REPORT.md` | Validation evidence |

## 3. Routes to alias / create

| Route | Strategy |
|---|---|
| `/command` | New surface composing control overview + honest action gates |
| `/agents` | Scaffold; real directors data if API available without fabrication |
| `/business` | Compose finance links + honest partial-backend note |
| `/trading` | Advisory-only BlockedState; no execution |
| `/monitoring` | Compose infra health + link to control (observe only) |
| `/approvals` | Aggregate `platformPendingApprovals` when available; else unavailable |
| `/settings` | Local prefs only |

## 4. Routes left untouched (compatibility)

`/`, `/missions/*`, `/studio/*`, `/automation/*`, `/projects`, `/knowledge/*`, `/security`, `/evidence`, `/control`, `/control/computer`, `/infrastructure`, `/finance`, `/ceo`, `/os`, `/mission`, `/chat`, `/workspace`, `/saathi`, `/voice`, `/me`, `/studio-os`, `/[dept]`, `/project/create/[token]`, auth unlock/reset pages.

## 5. Data sources to reuse

- `platformPendingApprovals` — approvals count (honest unavailable on failure)
- `controlAttention` / `controlOverview` — command/monitoring
- `fetchInfraHealth` — monitoring / status bar
- `useLive()` — SSE connection for status bar
- `API_BASE` / `NEXT_PUBLIC_SAATHI_API` — environment badge
- M1 primitives in `components/ui.jsx`
- Tokens in `globals.css`

## 6. Placeholders / blocked states

- **Trading Guardian:** always advisory / not-exercised / no execution UI
- **Agents:** registry pending aggregation if no safe API payload
- **Approvals:** per-source connected/unavailable/not-integrated
- **Business:** partial; no claim of unified backend
- **Copilot panel:** scaffold; no fabricated history

## 7. Regression risks

- Layout padding (`app-main` 130px bottom for old dock) must shift to sidebar offset
- Mobile must not inherit desktop sidebar
- Bare `/project/create/*` must remain shell-free
- LiveProvider/SSE must stay wrapped
- Existing pages importing DEPARTMENTS/color must keep working
- Hydration: theme attrs applied client-side carefully

## 8. Validation commands

```bash
cd ~/SaathiAI/saathi-os
npm test
npm run build
# lint may be unconfigured (pre-existing)
cd ~/SaathiAI && git diff --check
```

Browser: desktop routes + mobile tabs + theme/density + trading boundary.
