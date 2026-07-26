# M58 — Spatial Navigation Model

## Model
Hybrid, not a permanent admin sidebar-only model. On `/platform` and `/platform/ops`
the primary navigation is the **spatial map**: the SaathiCore at centre with a floating
module ring. The existing app shell (left rail, top strip, command palette ⌘K) remains
around the spatial scope.

## Ring geometry
`ringLayout(n, {cx,cy,rx,ry,startDeg})` places nodes deterministically on an ellipse,
starting at top (−90°) and stepping clockwise — no randomness (SSR-safe). Coordinates
are rounded via `pct()`/`pathD()` to 2 decimals so server render, browser
reserialization, and client hydration agree (see M58_VISUAL_QA).

## Connections
`ConnectionLayer` draws one cubic-ish curve per module from centre to node.
`connectionSignal(module, state)` colours it: authority modules → amber; danger
state → red; idle/unknown → grey-blue inactive; success → green; else cyan. Selected
path brightens and thickens; unselected dim to 0.28. A flow-dash overlay pulses on
active/authority/blocked paths (reduced-motion disables it). Every edge maps to a real
navigation/authority relationship.

## Interaction
- **In-page modules** (Runtime, Approvals, Attention, Bindings, Projects, Missions,
  Operations-readiness): click → `aria-current` + smooth-scroll to the module's glass
  panel + lit connection.
- **Routed modules** (Agents, Evidence, Memory, Automation, Settings, Operations→ops):
  click → `router.push(route)`.
- Keyboard: nodes are real `<button>`s, focusable, Enter/Space activate; visible focus
  ring; drawer close is a labelled button.

## Compact
≤900px: ring degrades to an accessible grid of the same nodes (connections hidden),
core simplified to 200px. Touch targets ≥44px.

## Desktop chrome
Top status strip (identity/RBAC/gateway + safety badges), spatial hero, in-page glass
panels, and the shared shell rail/palette. Right-side contextual drawer is used on the
ops constellation for node detail.
