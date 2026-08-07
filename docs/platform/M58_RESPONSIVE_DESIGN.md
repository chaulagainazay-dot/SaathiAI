# M58 — Responsive Design

## Breakpoint
`useMediaQuery("(max-width: 900px)")` switches between ring and compact modes
(SSR-safe: initial state matches server, so no hydration divergence).

## Desktop (>900px)
- Full spatial ring: SaathiCore centred, 12 nodes on the ellipse, animated SVG
  connection layer behind, in-page glass panels below.
- Ops: full constellation (central Runtime Operations + 10 nodes on curves) with a
  right-side contextual glass drawer on selection.

## Compact (≤900px)
- Home: core simplified to 200px; module ring becomes an accessible
  `auto-fill minmax(150px,1fr)` grid of full-width node capsules; connections hidden
  (not meaningful at this size); glass panels stack.
- Ops: central label + `minmax(220px,1fr)` grid of node cards; drawer stacks inline.
- Not merely a shrunk desktop canvas — layout genuinely reflows; touch targets ≥44px.

## Verified
M58 cert `responsive_mobile` gate: at 390×844 the home renders **12 node capsules** as
a grid with the core present (`platform_mobile.png`). Desktop verified at 1280×900
(`platform_spatial_desktop.png`, `ops_constellation_desktop.png`).

## Tablet
Falls into desktop mode above 900px (compressed ring) or compact below; the contextual
drawer stacks. Body never scrolls horizontally (`overflow-x: hidden` on the canvas).
