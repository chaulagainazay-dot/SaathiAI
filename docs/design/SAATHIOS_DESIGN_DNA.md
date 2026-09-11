# SAATHIOS_DESIGN_DNA

**Authority:** This document is the SaathiOS design source of truth (UI-NEXT-2).

## Product personality

Calm · intelligent · alive · trustworthy · high-information-density · professional · premium.

Not: crypto casino, cyberpunk demo, generic admin, Dribbble fake data, animation showcase.

## Visual principles

1. Graphite command environment (dark-first for Command).
2. Controlled contrast; minimal glow.
3. Density for decisions; whitespace with purpose.
4. Status color is semantic, never decorative.
5. Numbers are first-class (tabular).
6. Motion serves state, not spectacle.
7. Voice presence is structural.
8. PAPER / LIVE OFF always honest.

## Information hierarchy

1. Authority & safety (TG, PAPER, health)
2. Attention (what needs you)
3. Saathi focus (context / voice)
4. Portfolio & risk truth
5. Mission/agent activity
6. Evidence

## Density tiers

`COMFORTABLE | STANDARD | DENSE` — Command desktop default STANDARD→DENSE.

## Tokens (semantic)

```text
background          #0E1116
surface-1           #151A21
surface-2           #1B222C
surface-raised      #232B36
text-primary        #E8EDF4
text-secondary      #A8B3C4
text-muted          #7A8699
border-default      #2A3340
border-active       #4A90D9

accent-saathi       #5B9FD4

status-healthy      #3D9B6E
status-warning      #C9A227
status-critical     #C45C5C
status-info         #5B9FD4

risk-safe           #3D9B6E
risk-warning        #C9A227
risk-breached       #C45C5C

voice-listening     #5B9FD4
voice-thinking      #8B7EC8
voice-speaking      #3D9B6E
```

## Typography

- Display / titles: system UI sans, medium weight
- Body: system UI sans
- Tabular numeric: `ui-monospace, SFMono-Regular, Menlo, monospace` with `font-variant-numeric: tabular-nums`
- Monospace: IDs, evidence, transcripts optional

## Spacing / radii

8px grid. Radii: 6 / 10 / 14. Borders 1px subtle.

## Surface hierarchy

background < surface-1 < surface-2 < surface-raised.

## Charts

Thin grids, muted axes, no neon fills, emphasize risk thresholds as lines not fireworks.

## Agent representation

Nodes with state color + label; edges only for real dependencies.

## Voice representation

Ring/pulse only on LISTENING/SPEAKING; reduced-motion = static badge.

## Risk representation

Budget bars used/remaining/limit/status; breaches as reason codes.

## Approval representation

Amber attention cards; never green until approved.

## Evidence representation

Timeline, mono IDs, causal arrows.

## Mobile

Saathi-first stack; no topology graph.

## Accessibility

WCAG contrast targets, focus visible, keyboard modes, reduced motion, no color-only status.

## Performance

No Three.js in production path; no permanent ambient GPU loops; respect 8 GB host.
