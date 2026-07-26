# M59 — Unified Context Drawer (Workstream 6)

`components/spatial/SpatialContextDrawer.jsx`, used across all four workspaces for
quick inspection; complete workflows live on the standalone detail routes.

## Behaviour

- Right-side glass sheet on desktop; full-screen bottom sheet on ≤820px.
- `role="dialog" aria-modal="true"` with an accessible label.
- **Focus trapped** while open (Tab / Shift+Tab cycle within the drawer); focus is
  restored to the previously-focused element on close.
- Escape closes; scrim click closes.
- Reduced-motion safe (entrance animation disabled under `prefers-reduced-motion`).
- Renders only truthful field values — callers pass explicit `Unavailable` /
  `Unknown` sentinels; the shared `Field` primitive shows `—` for empty values.

Each workspace mounts the drawer with a domain summary (mission / agent / approval /
attention) and an "Open full …" button that deep-links to the standalone route,
preserving route state. No domain logic is duplicated inside the drawer and no fake
data is shown.
