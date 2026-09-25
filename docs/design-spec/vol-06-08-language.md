# VOLUME 6 — TYPOGRAPHY SYSTEM

## 6.1 Purpose
Type does 80% of the interface. One scale, two faces, zero improvisation.

## 6.2 Faces
- **Inter** — the platform face. All UI, body, tables, forms. Chosen for x-height, hinting at small sizes, true tabular figures, and complete Latin coverage.
- **Poppins** — display only (page titles, hero numbers, brand moments). It is the family's "voice"; overuse dilutes it. Max 2 Poppins elements per screen.
- **Noto Sans Devanagari** — Nepali (ne) text, paired to match Inter's optical size; falls back automatically via `font-family` stack. Never render Nepali in Poppins (incomplete conjuncts).
- Monospace (`ui-monospace` stack) — IDs, code, evidence hashes (console).
- Self-host all faces (`next/font`), `font-display: swap`, subsets: latin + devanagari.

## 6.3 Scale (platform tokens — no other sizes exist)
| Token | px/lh | Face/weight | Use |
|---|---|---|---|
| `display-xl` | 36/40 | Poppins 700 | Hero numbers, empty-state heroes |
| `display` | 28/34 | Poppins 600 | Page titles |
| `title` | 20/28 | Inter 600 | Card/dialog titles |
| `body-lg` | 17/26 | Inter 500 | Primary rows, POS items |
| `body` | 15/22 | Inter 400 | Default text |
| `label` | 13/18 | Inter 500 | Buttons, form labels, tabs |
| `caption` | 12/16 | Inter 400 | Meta, timestamps — **absolute floor** |
**KDS scale:** ×1.6 multiplier tokens (`kds-item` 32/40 600, `kds-id` 48 Poppins 700, `kds-timer` 24 tabular). **Consumer apps (IELTS/Travel):** body upgrades to 16/24.

## 6.4 Rules
- Letter-spacing: 0 for body; +0.02em on ALL-CAPS labels; ALL-CAPS only for `caption`-size eyebrows/group headers.
- Numbers: `tabular-nums` wherever digits align (tables, money, timers, stats). Money format: `Rs 12,450` — currency prefix, thin space, en-style grouping; negative = `−Rs 500` red, never parentheses.
- Truncation: single-line ellipsis + full text in tooltip/Sheet; never truncate money or names in money contexts.
- Line length: running text ≤65ch. Headings `text-wrap: balance`.
- User font-scale respected: everything in rem; layouts must survive 130% (Vol 14 gate).
- Dark mode: same scale; body weight may NOT be dropped (thin-on-dark halation); increase `--text-2` contrast instead.

## 6.5 Localization
All strings in locale files (`en`, `ne`) from day one — no literals in JSX (lint). Nepali runs ~15% longer: buttons and tabs must tolerate +20% width. Dates: localized short forms ("Thu, Jul 24" / "बिही, साउन ८"), relative times under 24h ("2h ago"). Nepal timezone (UTC+5:45) via platform `dates.ts` only.

## 6.6 Anti-patterns
✗ `text-[10px]`/`text-[11px]` (banned, lint). ✗ Poppins body text. ✗ Font-weight as hierarchy on the same size everywhere (use scale steps). ✗ ALL-CAPS sentences. ✗ Placeholder-as-label.

## 6.7 Developer notes
`--font-inter`, `--font-poppins`, `--font-devanagari` via next/font. Tailwind: `text-display-xl…text-caption` classes map to tokens; raw `text-{n}px` classes removed from theme.

---

# VOLUME 7 — COLOR SYSTEM

## 7.1 Purpose
One neutral spine + one semantic law + per-app accents = family resemblance with app identity.

## 7.2 Architecture (3 layers, binding — from SOVEREIGN_ORBIT, now platform law)
```
Primitive (raw ramps) → Semantic (roles, theme-mapped) → Component (rare)
```
Components touch **semantic only**. Hex in a component file = lint error.

## 7.3 The App Accent Layer (the reconciliation)
Every app declares exactly:
1. **Accent hue** (its identity): Console `--saathi-500 #5f8fff` · HCG `--emerald #10b981` · IELTSAlert `--indigo #6366f1` · Travel `--sky #0ea5e9` · Trading `--amber #f59e0b` (reserved) · CRM `--violet #8b5cf6` (reserved).
2. **Neutral bias**: neutrals are tinted ≤4% toward the accent (HCG's green-biased papers, Console's navy inks). Same ramp shape, different bias.
3. **Default theme**: environment-driven — Console/KDS dark-first; canteen/consumer light-first. Both themes always ship (Vol 7.6).
Everything else — semantic statuses, risk, spacing, type, components — is platform-fixed. **An app may never repurpose a semantic hue as its accent** (Trading's amber accent therefore renders warnings as orange `--warn-strong` per the status table).

## 7.4 Semantic tokens (identical names in every app)
```css
--bg  --surface  --surface-raised  --surface-sunken
--text  --text-2  --text-3          /* 3 text levels, no more */
--border  --border-strong  --focus-ring
--primary --primary-press --primary-tint     /* = app accent */
--ok --warn --danger --info --ai             /* + -tint versions */
```
Status/risk/authority extended tokens (console set: `--st-*`, `--risk-*`, `--auth-*`) are platform-available; operator apps adopt the subset they need with identical names. **Status = hue + icon shape + label, never hue alone** (platform law, inherited).

## 7.5 Charts
Categorical ramp (6, colorblind-checked): accent → cyan → violet → amber → slate → green; sequential = accent alpha ramp; diverging = red↔slate↔green (money deltas). Gridlines `--border` dashed; current point emphasized; no pies (stacked bars).

## 7.6 Themes
- Both themes are first-class; `data-theme` attribute overrides `prefers-color-scheme` both directions; token redefinition only — component CSS never branches on theme.
- Dark is a redesign, not inversion: accents lift one step (e.g. emerald 500→400) for contrast; elevation on dark = lighter surface + subtler shadow; tints go alpha-based.
- Contrast gates (CI-checked on token pairs): text ≥4.5:1, large text ≥3:1, UI borders/icons ≥3:1 — both themes.

## 7.7 Anti-patterns
✗ Hex in TSX. ✗ Semantic hue as decoration ("red looks bold here"). ✗ Same green for "success" and brand *meaning* in one view (HCG exception: emerald is both — therefore success states there always pair icon ✓ + label so meaning never rides on hue). ✗ The v1 dark-mode `!important` override layer — deleted pattern, never reintroduce.

## 7.8 Developer notes
`@saathi/tokens` package: `base.css` (primitives + semantics) + `app.css` per app (accent + bias + defaults). Tailwind preset maps semantic names (`bg-surface`, `text-2`, `border-strong`, `bg-primary`). Contrast test script runs in CI on every token PR.

---

# VOLUME 8 — COMPONENT LIBRARY (the Sixteen + AI kit)

## 8.1 Purpose
Sixteen primitives are the entire UI vocabulary. Every screen in every app is composed from these; new primitives require Governance approval (Vol 18).

## 8.2 The roster
Button · Input/Field · Select+Chips · Card · StatCard · StatusPill · Dialog · Sheet · Toast · Skeleton · EmptyState · Table/List · Tabs/Segmented · Avatar/Badge · CommandPalette · Timeline/Calendar. Plus the AI kit (8.5) and chart wrappers (Vol 7.5).

## 8.3 Universal contract (every component, no exceptions)
- Six states shipped and visible in the kit gallery: default / hover / **focus-visible** (2px `--focus-ring`, 2px offset) / active (scale .98, 120ms) / disabled (40% + `aria-disabled` + reason tooltip when gated by authority) / loading (skeleton or in-button spinner).
- Sizes off the 8pt grid; touch targets ≥44px (56 till, 72 KDS bump zone).
- Keyboard + screen-reader behavior specified below is part of the component, not app code.
- Semantic tokens only; both themes verified in gallery.

## 8.4 Per-component specification (condensed but binding)

**Button.** Variants: primary (accent, ≤1/screen), secondary (surface+border), destructive, ghost. Heights 36/44/56. Loading replaces label with spinner+label, width locked (no jump). Icon+label default; icon-only requires `aria-label` + tooltip and is banned as a row's only action on touch. Anti: two primaries; disabled-without-reason.

**Input/Field.** Label above, help below, error replaces help (icon+sentence, `aria-describedby`). Numeric: `inputmode`, right-aligned, tabular; money keypad-first on touch. Validate blur, re-validate change after first error. Anti: placeholder-as-label; silent max-length truncation.

**Select & Chips.** ≤5 options visible = chips/segmented; >5 = searchable Select (palette-style sheet on mobile). Multi-select shows count chip. Anti: native `<select>` styling drift — kit wraps it.

**Card / StatCard.** Card: one object/question, header (title + optional verb) + body + optional footer meta. StatCard: caption label, Poppins number, delta arrow + % (color+arrow, not color alone), optional sparkline slot, whole card = link when it drills. Anti: nested cards >2 levels; stat without comparison context.

**StatusPill.** Icon shape + label + tint bg (status table Vol 7.4). Sizes: caption/label. Anti: dot-only status anywhere decisions happen.

**Dialog.** ≤400px, title + one sentence + primary/cancel; destructive variant red primary. Focus-trapped, Esc closes, returns focus. Used ONLY for irreversible confirms & tiny decisions (Vol 5 table). Anti: forms in dialogs; stacking dialogs.

**Sheet.** The workhorse. Bottom (phone, drag handle, snap 50/90vh, swipe-down close) / right 480px (desktop). Header sticky: title + close; footer sticky when form: primary + secondary. Content scrolls. Anti: sheet-in-sheet beyond Dialog-confirm; unlabeled close.

**Toast.** Success 4s · error sticky-until-dismiss + retry verb when retryable · **undo variant 6s with countdown ring and `⌘Z` binding**. Bottom-center phone, bottom-right desktop, max 2 stacked then queue. `aria-live=polite` (assertive for errors). Anti: toast for validation errors (inline instead); success toasts for every trivial save (silent optimistic OK when instant).

**Skeleton.** Shape-accurate (matches real layout), shimmer 1.4s, page-level always skeleton never spinner; lists render 6 ghost rows. Anti: layout-shifting spinners; skeletons >3s without error state.

**EmptyState.** 40px icon `--text-3`, one sentence (what+why), one action. First-run variants may add one illustration-free tip. "All clear" is the celebratory sibling (distinct copy, subtle check). Anti: dead-end empties (no action); lorem-tone copy.

**Table/List.** Vol 5.4 rules + column sort (single), sticky first column on scroll, selection mode via long-press/checkbox column, bulk bar bottom-sticky. Card-list morph below md is the same component (`variant`). Anti: >7 columns without dense mode; horizontal page scroll.

**Tabs/Segmented.** Segmented = views of same data (≤4); Tabs = subsections (≤6, overflow scrolls with fade). Keyboard: arrows move, Enter activates; `aria-selected`. Anti: tabs as navigation between unrelated screens.

**Avatar/Badge.** Initials on accent-tint; photo when exists; sizes 24/32/40; presence dot bottom-right (status hues). Badge: count ≤99+, `--danger` only for needs-attention counts. Anti: red badges for neutral counts.

**CommandPalette.** Vol 3.5 contract; sections Recents/Actions/Objects/Screens; fuzzy; `↑↓ Enter Esc`; action rows show shortcut hints. Anti: palette-only features.

**Timeline/Calendar.** Timeline: activity/audit trails — icon per event type, actor + verb + object + relative time, day dividers. Calendar: month grid + agenda list toggle; events = accent chips; today emphasized. Anti: calendar as default when agenda answers "what's next" better.

## 8.5 AI components (Vol 13's visual kit)
`AIPanel` (docked right / bottom sheet; conversation + tool-result cards) · `WhisperCard` (proactive suggestion: insight sentence + evidence line + ≤2 verbs + dismiss; `--ai` accent stripe) · `AIAnswer` (answer + "based on:" source line + confidence wording, links to screens) · `AIActionPreview` (the confirm step: diff-style "will do X" + Confirm/Cancel) · `AIInput` (text + mic slot + suggestion chips). All AI surfaces carry the `--ai` violet marker so machine-suggested is never mistaken for human/system fact.

## 8.6 Developer notes
Package `@saathi/ui`; gallery route `/dev/kit` in every app (all components × states × themes — this page IS the visual regression baseline). Component PRs need: spec parity screenshot, keyboard demo, both themes, axe pass. Apps import — never fork — primitives; app-specific composites (e.g., `KOTCard`, `BandScoreRing`) compose primitives and live in `app/components/domain/`.
