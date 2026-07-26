# M59 — Spatial Command Palette (Workstream 5)

`components/spatial/SpatialCommandPalette.jsx`, hosted by `SpatialWorkspaceShell`.

## Behaviour

- Opens with **⌘K** (macOS) / **Ctrl+K** (others); mobile ⌘K FAB.
- Closes with Escape (dialog handler + document-level safety net).
- Full keyboard navigation: ↑/↓ move the active option, Enter runs it, Escape closes.
- `role="dialog" aria-modal="true"`; a flat `role="listbox"` with `role="option"`
  children (axe-clean `aria-required-parent`); group headers are presentational.
- Search + grouped results via pure `filterCommands()` / `groupCommands()`.

## Commands (pure `buildCommands()`)

Always present: Go to Home / Missions / Agents / Approvals / Attention / Operations,
Open command help, Toggle reduced motion. Per-object "open" commands (missions,
agents, approvals, attention) come **only** from the caller's already-fetched
authorized records — never a browser-side unauthorized index. Records are capped at
20 per type with truthful labels; no secret or internal identifier leakage.

**No mutation or decision command is ever synthesized** (asserted by unit test):
approve / reject / decide / cancel / revoke never appear as palette commands — those
live only on their server-authorized detail routes.

## De-confliction

On workspace routes the spatial palette wins ⌘K over the pre-existing global
app-shell palette via a capture-phase handler with `stopImmediatePropagation()`, so
only the axe-clean spatial palette opens.
