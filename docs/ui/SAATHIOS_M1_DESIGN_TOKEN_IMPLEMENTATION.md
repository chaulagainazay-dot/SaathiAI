# SaathiOS — Milestone 1: Design Token Foundation — Implementation Report

**Date:** 2026-07-19
**Branch:** `milestone/m7-security-engine`
**Baseline commit:** `379b617`
**Scope:** Two files only — `saathi-os/app/globals.css`, `saathi-os/components/ui.jsx`. Additive, backward-compatible. No routes, APIs, or backend calls changed.

---

## 1. Files changed

| File | Change | Lines |
|---|---|---|
| `saathi-os/app/globals.css` | Added 3-layer token system (primitive/semantic/component), light-theme scaffold, density modes, focus system, reduced-motion, surface utilities, spinner/skeleton keyframes | ~168 → ~545 |
| `saathi-os/components/ui.jsx` | Added 22 reusable primitives + `cx` helper. All 7 pre-existing exports preserved unchanged | ~112 → ~526 |
| `docs/ui/SAATHIOS_M1_*.md` | New documentation (this set) | new |

**Deliberately NOT changed:** every existing route, every existing component consumer (39 files import `components/ui.jsx` — none edited), `lib/api.js`, backend, `lib/data.js` (dead mock left in place per "do not delete compatibility during M1"), the `SOVEREIGN_ORBIT` dark look.

## 2. Existing system reused

- **Tailwind v4 `@theme`** — extended the existing block; all pre-existing tokens (`--color-ink-*`, `--color-panel`, `--color-line`, `--radius-glass`) kept verbatim as compatibility tokens.
- **Fonts** (`next/font`: Jura/Outfit/Geist Mono) — unchanged; typography tokens reference existing `--font-*`.
- **`.glass` / `.glass-soft`** — kept working; a new tokenized `.surface-glass` added as the opt-in accent, and solid `.surface*` utilities added as the new default.
- **Component export style** (named function exports, `className`/`style` props) — matched exactly.
- **No new dependencies.** No icon library existed; primitives use inline unicode/SVG glyphs. No `cn`/`clsx` existed; added a local 3-line `cx()`.

## 3. Token layering implemented

```
PRIMITIVE (@theme, theme-agnostic)        SEMANTIC (:root, theme-mapped)     COMPONENT (:root)
  --color-navy/ink/saathi/…       →         --surface --text-primary    →     --card-bg --btn-* --input-*
  --fs-* --space-* --rad-*        →         --status-* --risk-* …        →     --panel-* --dialog-* …
```

Rule going forward: components reference **semantic/component** tokens, never primitives or hex.

**Critical correctness fix during implementation:** the size/spacing/radius scales were initially placed in Tailwind's reserved utility namespaces (`--text-*`, `--spacing-*`, `--radius-*`), which would have silently redefined Tailwind's built-in `text-lg`, `p-8`, `rounded-lg` utilities. Renamed to non-colliding namespaces (`--fs-*`, `--space-*`, `--rad-*`). Colors intentionally remain `--color-*` (additive — generates new utilities, overrides nothing). Verified no `@theme` collisions remain.

## 4. Compatibility strategy

- **Purely additive.** No existing token removed or redefined. Verified: `--color-ink-100` still resolves to `#eef3fc` at runtime; body background still `rgb(5,7,15)`; `color-scheme` still `dark`.
- Existing components render **identically** (visually confirmed — see verification report).
- Light theme + density are **opt-in via attributes** (`data-theme`, `data-density`) — default behavior unchanged; no switch UI shipped.

## 5. Primitives added (22)

`cx`, `Surface`, `Stack`, `Divider`, `Text`, `Heading`, `Badge`, `StatusBadge`, `AuthorityBadge`, `RiskBadge`, `EnvironmentBadge`, `EvidenceBadge`, `Button`, `IconButton`, `Input`, `Card`, `Spinner`, `Skeleton`, `LoadingState`, `EmptyState`, `ErrorState`, `BlockedState`.

Design guarantees:
- **No color-only status.** Every `Badge`/`StatusBadge`/`AuthorityBadge`/`RiskBadge` renders a glyph + text label + border in addition to color, and carries an `aria-label`.
- **Authority safety.** `AuthorityBadge` defaults to `advisory`; `not-exercised`/`inactive` render dashed + explicit label. Nothing implies autonomy by default (Trading Guardian rule).
- **Solid by default.** `Surface`/`Card` are solid; glass is the explicit `accent-glass`/`glass` variant only.
- **Accessible.** `IconButton` requires a `label`; `Divider` uses `role="separator"`; state components use `role="status"`/`role="alert"` + `aria-live`; focus ring is global via `:focus-visible`.
- **Reduced-motion aware.** `Spinner`/`Skeleton` honor `prefers-reduced-motion`.

## 6. Known limitations

- **Light theme is scaffold-only** — structurally complete and verified to switch, but not contrast-audited across every real screen and not user-toggleable in M1.
- **Density** affects the new tokens only; existing inline-styled pages won't reflect it until migrated.
- **1,595 inline styles remain** — migration is intentionally deferred (M2+). This milestone only *enables* migration.
- **Lint** is not configured in the repo (`next lint` prompts interactively) — unchanged by this milestone; build/type-check is the effective gate.

## 7. What this unblocks

Shell restructuring, Home/Command Center/Approvals screens, and per-area inline-style migration can now all build on one enforced token layer with accessible, authority/risk-aware primitives.
