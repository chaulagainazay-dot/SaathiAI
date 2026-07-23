# SaathiOS — Design System (Phase 15, brought forward)

**Date:** 2026-07-19
**Depends on:** audit + IA. **Implementation target:** `saathi-os/app/globals.css` (`@theme`) + `components/ui.jsx`.
**Status:** Specification. This is the source of truth Milestone 1 implements.

> Evolves the existing **SOVEREIGN_ORBIT** dark language (deep navy, restrained, clinical mono labels) into an enforced, tokenized, dual-theme system. Directly attacks the audit's #1 problem — **1,595 inline styles** — by giving every value a token. Per the brief: premium, calm, legible; **not** neon, not casino, not glass-everywhere. Glass is demoted from default surface to an occasional accent.

---

## 1. Token architecture (3 layers)

```
Primitive  →  Semantic  →  Component
(raw values)  (roles)       (specific)
--navy-900    --surface     --card-bg
#05070f       (theme-mapped) (= --surface-raised)
```

- **Primitive:** raw scales, theme-agnostic. Never used directly in components.
- **Semantic:** role tokens (`--surface`, `--text`, `--border`, `--accent`, status/risk/authority). Theme-mapped (light/dark). **This is what components use.**
- **Component:** only when a component needs a value the semantic layer doesn't express.

Rule after Milestone 1: **components reference semantic tokens, never hex, never primitives.** Lint target: drive the 1,595 inline styles toward tokened utility classes.

---

## 2. Color — primitives

```css
/* Neutrals (cool navy-ink ramp — extends current ink-100..500) */
--navy-950:#04060d; --navy-900:#05070f; --navy-850:#070c17; --navy-800:#0a1120;
--navy-700:#111a2e; --navy-600:#1b2a4a; --navy-500:#2a3a5c;
--ink-050:#f7f9fd; --ink-100:#eef3fc; --ink-200:#d3dcec; --ink-300:#aebad4;
--ink-400:#8b98b4; --ink-500:#6c7a96; --ink-600:#4b5876; --ink-700:#323d57;

/* Brand accent (Saathi) */
--saathi-400:#8fb4ff; --saathi-500:#5f8fff; --saathi-600:#3e6bff;

/* Functional hues (each has 400/500/600 + a low-alpha tint for fills) */
--green-500:#35c47a;  --amber-500:#e8b84b;  --orange-500:#ff8a3d;
--red-500:#f0555a;    --cyan-500:#35e0d0;   --violet-500:#9b6bff;
--blue-500:#3e7bff;   --slate-500:#6c7a96;
```

Department hues (from `lib/departments.js`) are retained as **accents only** (applied to Area/Project headers, not as status).

---

## 3. Color — semantic (dual theme)

Mapped via `:root` (dark default) + `:root[data-theme="light"]`. Ship dark first (current), add light in the theme milestone.

```css
:root {                      /* DARK (default, keeps current look) */
  --bg:            var(--navy-900);
  --surface:       #0c1424;          /* solid, replaces default glass */
  --surface-raised:#111a2e;
  --surface-sunken:#080e1a;
  --text:          var(--ink-100);
  --text-muted:    var(--ink-400);
  --text-faint:    var(--ink-500);
  --border:        rgba(255,255,255,.09);
  --border-strong: rgba(255,255,255,.16);
  --accent:        var(--saathi-500);
  --focus-ring:    var(--saathi-400);
}
:root[data-theme="light"] {
  --bg:#f5f7fc; --surface:#ffffff; --surface-raised:#ffffff; --surface-sunken:#eef1f8;
  --text:#0c1424; --text-muted:#4b5876; --text-faint:#6c7a96;
  --border:rgba(12,20,36,.10); --border-strong:rgba(12,20,36,.20);
  --accent:var(--saathi-600); --focus-ring:var(--saathi-600);
}
```

**Note:** default surface becomes **solid** (`--surface`), not translucent glass. `.glass` remains a token'd opt-in accent (`--surface-glass`) for hero/overlay moments only — killing the "glass everywhere" smell.

---

## 4. Status semantics (color + shape + label — never color alone)

Each status = a token + an icon shape + a text label. Satisfies the brief's "color is never the only indicator" rule.

| Status | Token | Hue | Icon shape | Example label |
|---|---|---|---|---|
| neutral | `--st-neutral` | slate | dot ○ | — |
| informational | `--st-info` | blue | i | "Info" |
| success | `--st-success` | green | ✓ | "Completed" |
| attention | `--st-attention` | amber | ● | "Needs review" |
| warning | `--st-warning` | orange | △ | "Warning" |
| critical | `--st-critical` | red | ✕ / ▲ | "Failed" |
| blocked | `--st-blocked` | red-outline | ⊘ | "Blocked by policy" |
| paused | `--st-paused` | slate | ❙❙ | "Paused" |
| simulated | `--st-simulated` | violet-dashed | ◇ dashed | "Simulated" |
| not-exercised | `--st-inactive` | ink-500 dashed | ◌ | "Not exercised" |
| approval-required | `--st-approval` | amber-bold | ! | "Approval required" |
| live | `--st-live` | green-solid | ● live | "Live" |
| canary | `--st-canary` | cyan | ◐ | "Canary" |
| production | `--st-prod` | orange-bold | ⬤ | "Production" |

```css
--st-success:var(--green-500);  --st-attention:var(--amber-500);
--st-warning:var(--orange-500); --st-critical:var(--red-500);
--st-info:var(--blue-500);      --st-neutral:var(--slate-500);
--st-blocked:var(--red-500);    --st-paused:var(--slate-500);
--st-simulated:var(--violet-500); --st-inactive:var(--ink-500);
--st-approval:var(--amber-500); --st-live:var(--green-500);
--st-canary:var(--cyan-500);    --st-prod:var(--orange-500);
```

## 5. Risk & authority palettes (first-class — audit §8 gap)

```css
/* Risk (used by approvals, trading, destructive actions) */
--risk-low:var(--green-500); --risk-medium:var(--amber-500);
--risk-high:var(--orange-500); --risk-critical:var(--red-500);

/* Authority (agent + operator) */
--auth-advisor:var(--slate-500);   /* can only recommend */
--auth-planner:var(--blue-500);
--auth-executor:var(--orange-500); /* can act — visually heavier */
--auth-reviewer:var(--violet-500);
--auth-monitor:var(--cyan-500);
--auth-approver:var(--amber-500);
--auth-autonomous:var(--red-500);  /* bounded-autonomous — highest visual weight */
```

**Rule:** an advisory agent must never be styled with executor/autonomous weight (brief rule). Authority weight increases border thickness + adds a lock/action glyph, not just color.

## 6. Typography

Fonts unchanged (Jura display, Outfit UI, Geist Mono). Add a scale:

```css
--text-2xs:10px; --text-xs:11px; --text-sm:13px; --text-base:14px;
--text-md:16px;  --text-lg:20px; --text-xl:24px; --text-2xl:30px; --text-3xl:40px;
--leading-tight:1.2; --leading-normal:1.5;
--tracking-mono:0.14em; /* clinical labels */
```
Roles: display = Jura 300 (headings), UI = Outfit (body/controls), mono = Geist Mono (labels, IDs, evidence, numbers). Eyebrow label pattern (`.eyebrow`) retained.

## 7. Spacing, radius, elevation, layout

```css
/* 4px base scale */
--space-1:4px; --2:8px; --3:12px; --4:16px; --5:24px; --6:32px; --7:48px; --8:64px;
/* radius */
--radius-xs:6px; --radius-sm:10px; --radius-md:14px; --radius-lg:20px; --radius-full:999px;
/* elevation (subtle — not glow) */
--elev-0:none;
--elev-1:0 1px 2px rgba(0,0,0,.25);
--elev-2:0 6px 20px rgba(0,0,0,.30);
--elev-3:0 20px 60px rgba(0,0,0,.35);
/* grid + breakpoints */
--container:1440px; --gutter:var(--space-5);
--bp-phone:699px; --bp-tablet:1200px;   /* match existing CSS */
```

## 8. Density modes

`data-density="comfortable|compact"` scales row height + padding via multiplier tokens. Expert mode defaults to compact (denser tables); Beginner to comfortable.

## 9. Motion

```css
--motion-fast:120ms; --motion-base:220ms; --motion-slow:400ms;
--ease-standard:cubic-bezier(.2,0,0,1);
--ease-emphasized:cubic-bezier(.2,0,0,1.2);
```
Subtle only (brief: "no fake AI animations"). `@media (prefers-reduced-motion:reduce)` disables non-essential motion, `.pulse`/`.flow`/star drift included.

## 10. Focus & accessibility tokens

```css
--focus-ring-width:2px; --focus-ring-offset:2px;
```
Every interactive element gets a visible `--focus-ring` outline (fixes audit §12 default-focus reliance). Minimum contrast: body text AA (4.5:1) on `--surface` in both themes — glass surfaces must not carry primary text. Touch targets ≥ 44px on mobile.

## 11. Icon rules

One icon set, line style, 1.5px stroke, 20px default. **Icons always paired with a label** in nav and actions (brief: "no confusing icons without labels"). Status glyphs (§4) are the exception — they carry the shape semantics and always sit beside text.

## 12. Visual direction (guardrails from the brief)

**Do:** restrained, spacious, layered, legible; excellent tables; strong command/status visibility; solid surfaces; subtle motion; dual theme.
**Don't:** excessive gradients, neon glow borders, glass everywhere, huge low-info cards, decorative 3D, inconsistent card styles. `Stars`/`Universe`/`aurora` are retained but toned to background-only accents, off under reduced-motion.

## 13. Migration note (inline styles → tokens)

Milestone 1 adds tokens + primitives **without** touching existing inline styles (backward compatible). Subsequent milestones migrate per-area: replace inline hex/px with `var(--token)` and shared classes. Track progress by counting remaining `style={{` sites (baseline: **1,595**).

---

## 14. Milestone 1 deliverable (design-system slice)

1. Extend `app/globals.css` `@theme` + `:root` with §2–§10 tokens (dark now, light scaffolded).
2. Add primitives to `components/ui.jsx`: `StatusBadge`, `RiskBadge`, `AuthorityBadge`, `EnvironmentBadge`, `EvidenceBadge`, `EmptyState`, `LoadingState`, `ErrorState`, `BlockedState`, `ConfirmDialog`, `DestructiveDialog`.
3. No route/API changes. Fully backward compatible. This is the safe first implementation milestone from the audit.
