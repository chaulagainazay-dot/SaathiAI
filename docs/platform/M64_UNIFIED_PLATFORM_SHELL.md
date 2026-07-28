# M64 — Unified Platform Shell

## Navigation (backend-driven Applications group)

`shell.js::getShellNavigationFromBackend(discovery.navigation)`:

- **Platform** — existing `NAV_GROUPS` (unchanged, still locked by `navigation.test.js`)
- **Applications** — built from the authoritative backend navigation payload
  (`applicationsGroupFromBackend`): icons pass through the safe allowlist; only
  backend-`actionable` (state `available`) modules get a live `href`; placeholders
  and restricted modules render non-actionable with a truthful badge
  (`soon` / `locked` / `off` / `degraded`)
- **Administration** — platform-owned (`ADMIN_GROUP`)

Rule enforced by test: the mirror cannot produce a live link the backend did not
mark actionable.

The production `components/shell/Sidebar.jsx` now calls
`applicationsGroupFromBackend`; Applications entries are withheld until discovery
is ready. Browser evidence proves Trading enabled and all four placeholders disabled.

## Applications dashboard (`/apps`)

`app/apps/page.jsx` consumes `useModuleDiscovery`:

- while loading → non-operational skeleton from the mirror (dimmed, `state=unknown`)
- ready → backend cards with truthful `StateChip` (Available / Degraded /
  Unavailable / Disabled / Coming soon / Restricted)
- only `available` cards link to their `primary_route`; everything else is
  `aria-disabled`
- distinct banners for `AUTH_REQUIRED`, `SESSION_EXPIRED`, `PERMISSION_RESTRICTED`,
  `OFFLINE` (with Retry), `ERROR` (with Retry), `DEGRADED`
- module health is **never computed in the browser** — the chip renders backend state

Trading → operational card linking to `/trading`. IELTSAlert, HCG POS, Travel,
Finance → "Coming soon", no route, no fabricated metrics.

## Route guard (`guard.js`)

`evaluateModuleRoute(shell, moduleId)` → `allow` / `auth_required` / `not_found` /
`not_implemented` / `disabled` / `permission_restricted` / `degraded` /
`unavailable`, read from the authoritative `state`. **UX only** — backend routes
enforce the real permission. Errors are not blanket-redirected to the dashboard;
the cause is surfaced.

`components/modules/ModuleRouteBoundary.jsx` is the production caller. During
bootstrap, the fallback route skeleton may withhold a known application path but
can never grant it. Once ready, backend module state is the only route-presentation
input. Direct `/finance` browser evidence shows the truthful not-implemented state.

## Command palette

Existing platform commands remain. Production `components/CommandPalette.jsx` adds
`applicationCommandsFromBackend(discovery.navigation)`; only actionable backend
modules yield an Application command. Browser evidence shows `Open Trading` and no
placeholder command. Search-provider interfaces are **not** treated as a global
index in this milestone.

## Bootstrap states

See `M64_AUTHENTICATED_MODULE_DISCOVERY.md`. The shell never flashes unauthorized
navigation during hydration: modules render only in `READY`/`DEGRADED`, and any
failure clears the set.

## Accessibility

- status chips carry `role="status"` + `aria-label` (not color-only)
- the applications grid sets `aria-busy` during load
- actionable cards are real `<Link>`s; non-actionable are `aria-disabled` divs
- icons are `aria-hidden` decorative glyphs

Production browser certificate covers desktop/tablet/mobile, keyboard focus,
semantic controls, textual statuses, and no horizontal overflow.
