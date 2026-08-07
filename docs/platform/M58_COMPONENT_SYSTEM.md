# M58 — Component System

All in `saathi-os/components/spatial/` + `lib/spatial.js`. Token-driven, no hard-coded
visual values, no new dependencies.

## Semantics — `lib/spatial.js` (pure, unit-tested)
- `SIGNAL`, `SIGNAL_TOKENS`, `CONNECTION` — the colour/state vocabulary.
- `MODULES` — the 12-module registry (id, label, route, icon, flow, group).
- `coreSignal({health,metrics,diagnostics})` — core state; danger only on explicit
  failure words (never on healthy `TOOL_GATEWAY_ENFORCED`).
- `coreMetrics(...)`, `moduleState(id,data)` — live-or-null derivations.
- `ringLayout`, `curvePath`, `connectionSignal` — geometry + edge semantics.
- `round2`, `pct`, `pathD` — hydration-stable coordinate emission.

## Visual primitives — `frame.jsx`
`GlassFrame` (signal edge variants), `GlassPanel`, `StatusPulse` (non-colour-only),
`SafetyBoundaryBadge`, `LiveMetric` (value or explicit "—"), `SystemStatusStrip`,
`ContextDrawer`, `useReducedMotion`, `ReducedMotionProvider`.

## Composed
- `SaathiCore.jsx` — central orb: SAATHI + state text + subtitle + metric chips.
- `SpatialMap.jsx` — `SpatialModuleNode`, `ConnectionLayer`, `SpatialMap` (ring/grid).
- `icons.jsx` — `SpatialIcon` outline family + `ICON_NAMES`.

## Reuse
Existing `components/ui.jsx` primitives (`Button`, `Text`, `Heading`, `StatusBadge`,
`AuthorityBadge`, `LoadingState`, `ErrorState`) are reused inside panels. No giant page
component — `page.jsx` files compose primitives + a local `ModulePanel`/`NodeCard`.

## Testing
`lib/spatial.test.js` — 25 tests: registry integrity, signal priority (danger/attention/
active/idle/unknown), enforced-gateway-not-blocked, live-or-null derivations, ring
determinism, connection semantics, and hydration-stable rounding.
