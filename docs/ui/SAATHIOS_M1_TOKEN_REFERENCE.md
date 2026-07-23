# SaathiOS — Milestone 1: Token Reference

**Source of truth:** `saathi-os/app/globals.css`. This document mirrors it. All values verified resolving at runtime.

---

## Primitive tokens (`@theme` — theme-agnostic, generate Tailwind color utilities)

### Neutrals
`--color-navy-950 #04060d` · `-900 #05070f` · `-850 #070c17` · `-800 #0a1120` · `-700 #111a2e` · `-600 #1b2a4a` · `-500 #2a3a5c`
`--color-ink-050 #f7f9fd` · `-100 #eef3fc` · `-200 #d3dcec` · `-300 #aebad4` · `-400 #8b98b4` · `-500 #6c7a96` · `-600 #4b5876` · `-700 #323d57`

### Brand
`--color-saathi-400 #8fb4ff` · `-500 #5f8fff` · `-600 #3e6bff`

### Functional hues (400/500/600 each)
green `#5fd39a/#35c47a/#2aa866` · amber `#f0c968/#e8b84b/#cc9f37` · orange `#ffa062/#ff8a3d/#e5701f` · red `#f47a7e/#f0555a/#d63b40` · cyan `#5fe8da/#35e0d0/#22bdb0` · violet `#b28cff/#9b6bff/#7f4ee5` · blue `#5f98ff/#3e7bff/#2a63e0` · slate `#6c7a96`

### Scales (non-Tailwind namespaces — consumed via `var()` only)
- Font size: `--fs-2xs 10` `--fs-xs 11` `--fs-sm 13` `--fs-base 14` `--fs-md 16` `--fs-lg 20` `--fs-xl 24` `--fs-2xl 30` `--fs-3xl 40` (px)
- Spacing (4px base): `--space-1 4` … `--space-8 64` (1,2,3,4,5,6,7,8 = 4,8,12,16,24,32,48,64)
- Radius: `--rad-xs 6` `--rad-sm 10` `--rad-md 14` `--rad-lg 20` `--rad-full 999`

### Preserved compatibility primitives (DO NOT REMOVE)
`--color-ink #05070f` · `--color-bg #0a1120` · `--color-panel rgba(255,255,255,.05)` · `--color-ink-100..500` · `--color-line rgba(255,255,255,.08)` · `--radius-glass 20px`

---

## Semantic tokens (`:root` = dark default / `:root[data-theme="light"]`)

| Token | Dark | Light |
|---|---|---|
| `--background` | navy-900 | `#f5f7fc` |
| `--foreground` | ink-100 | `#0c1424` |
| `--surface` | `#0c1424` | `#ffffff` |
| `--surface-raised` | `#111a2e` | `#ffffff` |
| `--surface-overlay` | `#0e1729` | `#ffffff` |
| `--surface-subtle` | `#0a1120` | `#eef1f8` |
| `--surface-sunken` | `#080e1a` | `#e7ecf6` |
| `--surface-interactive/hover/active` | white α .04/.07/.10 | ink α .03/.06/.10 |
| `--surface-glass` (opt-in) | white α .045 | white α .55 |
| `--border` / `-strong` / `-subtle` | white α .09/.16/.05 | ink α .10/.20/.06 |
| `--text-primary` | ink-100 | `#0c1424` |
| `--text-secondary` | ink-300 | `#323d57` |
| `--text-muted` | ink-400 | `#4b5876` |
| `--text-disabled` | ink-600 | `#aebad4` |
| `--accent` / `-foreground` / `-hover` | saathi-500 / #04060d / saathi-400 | saathi-600 / #fff / saathi-500 |
| `--focus-ring` | saathi-400 | saathi-600 |

### Status (each paired in components with glyph + label — never color-only)
`--status-success` green · `--status-warning` orange · `--status-danger` red · `--status-info` blue · `--status-neutral` slate · `--status-pending` amber · `--status-paused` slate · `--status-blocked` red. Light theme uses the `-600` primitives for contrast.

Glyphs: success ✓ · warning △ · danger ✕ · info i · pending ◔ · paused ❙❙ · blocked ⊘ · neutral ○.

### Authority (first-class)
`--authority-advisory` slate · `--authority-approval-required` amber · `--authority-limited-autonomous` orange · `--authority-denied` red · `--authority-inactive` ink-500 · `--authority-not-exercised` ink-500 (dashed).
Glyphs: advisory ◎ · approval-required ! · limited-autonomous ◑ · denied ⊘ · inactive/not-exercised ◌.
**Default = advisory. Never implies autonomy unless real backend state proves it.**

### Risk (first-class)
`--risk-low` green · `--risk-guarded` cyan · `--risk-elevated` amber · `--risk-high` orange · `--risk-critical` red · `--risk-unknown` ink-500 (dashed).
Glyphs (rising bars): ▁ ▃ ▅ ▆ ▇ · unknown ?.

### Motion / typography roles / elevation
`--motion-instant 90 · -fast 120 · -base 220 · -slow 400ms`; `--ease-standard cubic-bezier(.2,0,0,1)`; `--ease-emphasized cubic-bezier(.2,0,0,1.2)`.
`--leading-tight 1.2 · -normal 1.5 · --tracking-mono .14em · --weight-light/normal/medium/semibold 300/400/500/600`.
`--elev-0 none · -1/-2/-3` (dark: subtle black shadows; light: softer ink shadows).

---

## Density (`:root[data-density=...]`)

| Token | compact | standard (default) | comfortable |
|---|---|---|---|
| `--density-control-h` | 30px | 36px | 44px |
| `--density-row-h` | 34px | 44px | 56px |
| `--density-pad` | space-3 | space-4 | space-5 |
| `--density-pad-sm` | space-2 | space-3 | space-4 |
| `--density-gap` | space-2 | space-3 | space-4 |

Density changes spacing only — never IA, permissions, content meaning, or feature availability.

---

## Component tokens (`:root`, reference semantic)

- **Button:** `--btn-h --btn-radius --btn-primary-bg/-fg --btn-secondary-bg/-fg --btn-ghost-fg --btn-danger-bg/-fg`
- **Card/Panel:** `--card-bg/-border/-radius/-pad/-shadow` · `--panel-bg/-border/-radius`
- **Sidebar:** `--sidebar-bg --sidebar-item-fg/-active/-hover`
- **Top/Status bar:** `--topbar-bg/-border` · `--statusbar-bg/-fg`
- **Input:** `--input-bg/-border/-fg/-placeholder/-h/-radius/-invalid`
- **Command palette:** `--palette-bg/-border`
- **Badge/Banner:** `--badge-radius --banner-radius`
- **Table:** `--table-row-h/-border/-header-fg`
- **Dialog:** `--dialog-bg/-border/-radius/-scrim`
- **Tooltip:** `--tooltip-bg/-fg`
- **Drawer:** `--drawer-bg/-border`
- **Misc:** `--separator --nav-item-radius --focus-ring-width/-offset`

---

## Deprecated / compatibility aliases

None deprecated in M1. The pre-existing tokens (`--color-ink-*`, `--color-panel`, `--color-line`, `--radius-glass`) are retained as **compatibility tokens** — still used by existing components and by the new semantic layer (e.g. `--text-primary → var(--color-ink-100)`). Do not remove before the inline-style migration completes.

## Utility classes added

`.surface` (solid) · `.surface-raised` · `.surface-subtle` · `.surface-glass` (opt-in) · `.saathi-spin` · `.saathi-skeleton` · global `:focus-visible` ring · `prefers-reduced-motion` reset.
