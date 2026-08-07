# M59 — Shared Spatial Workspace Shell

`SpatialWorkspaceShell` (`components/spatial/SpatialWorkspaceShell.jsx`) is the single
reusable route shell for every Glass Frame platform screen. It is not duplicated
across pages; each workspace composes its content as children.

## Responsibilities

| Concern | Implementation |
|---|---|
| Deep spatial canvas | `.spatial-scope` / `.spatial-canvas` + optional particle field (reduced-motion drops particles) |
| System-status strip | `SystemStatusStrip` — identity/RBAC/gateway health + always-visible safety badges |
| Floating navigation | `NavDock` (left rail desktop → bottom bar mobile), current-route aware, keyboard reachable |
| Breadcrumb | Deep routes pass an ordered `breadcrumb` array; renders an accessible `<nav><ol>` |
| Route title + compact state | `<h1>` + signal pulse + loading indicator |
| Command palette | Hosts `SpatialCommandPalette`, owns ⌘K/Ctrl+K (capture phase) |
| Context drawer | Pages mount `SpatialContextDrawer` for quick inspection |
| Private-alpha safety | Persistent `SafetyBoundaryBadge`s: Private Alpha · Non-production · Trading disabled |
| Reduced motion | `useReducedMotion()` gates particle rendering; CSS disables all animation |
| Route-level error boundary | `WorkspaceErrorBoundary` class — catches client render errors, shows safe retry, never leaks a stack trace |
| Loading / unavailable | `loading` prop → status text; unavailable data → explicit sentinels, never blanks |

## Navigation model

`WORKSPACE_NAV`: Home · Missions · Agents · Approvals · Attention · Operations ·
Evidence · Settings. The user can always return to `/platform`. The dock never
becomes an oversized permanent sidebar; on ≤820px it collapses to a bottom bar
and a ⌘K FAB appears.

## De-confliction with the global app shell

The pre-existing global `Shell` (`components/Shell.jsx`) wraps all routes and has
its own ⌘K palette. To avoid a double-palette conflict on workspace routes, the
spatial shell registers its ⌘K handler in the **capture phase** with
`stopImmediatePropagation()`, so the spatial (workspace-aware, axe-clean) palette
wins and the global palette does not also open.

## Authority boundary

The shell renders presentation only. It holds no execution authority, performs no
mutations, and fabricates no data. All server calls flow through the shared
`usePlatformData` hook against `/api/v1/platform/*`.
