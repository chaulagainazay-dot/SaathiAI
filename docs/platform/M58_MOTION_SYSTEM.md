# M58 — Motion System

## Principles
Slow, controlled, meaningful, GPU-conscious (transform/opacity only), and fully
reduced-motion aware.

## Motions
- **Core breathing** — `coreBreathe` on the two rings (scale 1→1.04, opacity), 6–8s.
- **Rotating aura** — `coreRotate` conic gradient, 24s linear.
- **Status pulse halo** — `pulseHalo`, expanding ring on active/attention/danger dots.
- **Connection flow** — `flowDash` dashed overlay on active/authority/blocked edges.
- **Node hover elevation** — translateY(−3px) + brighter edge/glow (CSS transition).
- **Node entrance** — `spatialNodeEnter` staggered fade-up (pure CSS, per-index delay).
- **Particle drift** — `particleDrift`, 42s background field.
- **Panel/selection** — connection dim/brighten transitions on select.

## Determinism
Framer-motion was removed from `SpatialMap`; all motion is CSS so server and client
markup are identical (no hydration divergence). Entrance uses `animationDelay` computed
from the node index (rounded), not from time or random.

## Reduced motion
The global `@media (prefers-reduced-motion: reduce)` block neutralises all animations
(`animation: none`), and each spatial component additionally guards
(`.spatial-particles`, `.saathi-core__aura/__ring`, `.status-pulse__halo`,
`.connection-flow`, `.spatial-node-enter`). `useReducedMotion` also drops the JS-side
flow overlay and entrance class. **Verified:** M58 `reduced_motion` gate passes with
`reducedMotion: "reduce"` — core + 12 nodes still render, statically.

## Performance
No WebGL; bounded particles; CSS animations pause in background tabs by browser default.
Targets M2 / 8 GB.
