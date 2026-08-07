# M58 — Glass Frame Design System

## Intent
Dark, luminous, technical, spatial — an AI operating system, not frosted-white glass.
The scene reads as a living topology: one intelligence core, modules orbiting it,
luminous connections encoding real relationships.

## Colour language (semantic, not decorative)
- **Cyan** (`--signal-active`) — healthy / operational data flow.
- **Amber/gold** (`--signal-attention`) — attention, approvals, authority.
- **Red** (`--signal-danger`) — blocked / unsafe / failed.
- **Blue-grey** (`--signal-idle`) — idle / inactive / offline.
- **Green** (`--signal-success`) — completed verification only, used sparingly.
- **Dashed grey** (`--signal-unknown`) — data genuinely unavailable.

## Glass surfaces
`.glass-frame` — translucent dark-blue (`rgba(10,17,32,.55)`), 1px luminous edge
(`--glass-frame-border`, low-opacity cyan), `backdrop-filter: blur(22px)`, layered
shadow + inner highlight. Modifiers: `--strong` (denser), `--active` (cyan edge+glow),
`--authority` (amber edge+glow), `--danger` (red edge+glow). Rounded 14–20px, never
pill.

## Background / depth
`.spatial-canvas` uses `--canvas-bg`: radial navy glow at the core, a faint cyan wash
low-right, and a vertical navy→midnight gradient. `.spatial-particles` is a bounded,
drifting star field (disabled under reduced motion). The scene keeps its dark canvas
even in light theme via `.spatial-scope` overrides so glow and contrast still read.

## Tokens
All values live as CSS custom properties (see M58_FINAL_REPORT §6). Components never
hard-code hex; they reference `--signal-*`, `--glass-frame-*`, `--connection-*`,
`--glow-*`. Signals map to the existing primitive ramp (cyan/amber/red/green/slate)
and use 600-weights in light theme for contrast.

## Typography
Geometric sans (`--font-ui`) for UI, monospace (`--font-mono`) for runtime ids, state
codes, counts, and timestamps; uppercase mono micro-labels; large `--font-display`
headings on the core. Minimal paragraph text on the spatial home.

## Iconography
One outline icon family (`SpatialIcon`, 24×24, 1.6 stroke, `currentColor`) covering
modules and ops nodes. Luminous only when the parent signal is active; no emoji in the
operational interface.
