# THE DHAAGO SPECIFICATION
## SaathiOS Master Product Design Bible · v1.0 · July 2026

**Dhaago** (धागो, "thread") — the single thread that ties every SaathiOS application into one family. This document is the permanent source of truth for every designer, developer, AI agent, and future contributor. Nothing ships that contradicts it; anything it doesn't cover gets added to it through Governance (Volume 18), never invented ad-hoc.

**Applications governed:** HCG OS (hospital cafeteria) · IELTSAlert · SaathiOS Console · future Travel, Trading, CRM, ERP, AI Business apps.

**Reconciliation note (binding):** two design languages predate this bible — SOVEREIGN_ORBIT (SaathiOS Console: navy, dark-first, saathi-blue) and Chulo (HCG OS 2.0: emerald, light-first). Dhaago does not replace them; it **promotes their shared DNA to the platform layer** and demotes their differences to the App Accent Layer (Vol 7). Both remain valid expressions of one system.

---

# VOLUME 1 — PLATFORM VISION

## 1.1 Purpose
Define why SaathiOS exists and the non-negotiable philosophy every product decision inherits.

## 1.2 Mission
> **Give one person the operating leverage of an organization.**
Every SaathiOS app turns a messy real-world operation — a canteen, an exam prep journey, a trading book, a travel business — into something one owner can see, decide, and act on in minutes a day, with AI carrying the routine.

## 1.3 Product philosophy
1. **Operator software, not office software.** Users are standing, rushing, mid-task. Software must respect the posture of work (Vol 2). Benchmark: Square in a restaurant, not Excel in a cubicle.
2. **Attention is the spine.** The system's first job is triage: *what needs me now?* Every app's home answers this before showing anything else. (Inherited from SaathiOS IA principle #1; generalized platform-wide.)
3. **Trust through evidence.** Numbers link to their sources. AI answers cite tables. Money movements leave audit trails. Never fabricate; render "not measured" honestly.
4. **One door per job.** Every capability has exactly one canonical place. Duplicated entry points are IA bugs.
5. **The domain is the moat.** Nepali payroll advances, ward-level credit, ZKTeco punches, IELTS band math — deep domain fit beats generic polish. Design amplifies domain features; never sands them off to look like a template.

## 1.4 Design philosophy
- **Calm, premium, legible.** Not neon, not casino, not glass-everywhere (SOVEREIGN_ORBIT brief, now platform law). Excitement comes from *speed and correctness*, not decoration.
- **Form encodes state.** Status is shape + label + color, never color alone. A screen's visual weight maps to operational urgency.
- **Density is a dial, not a fork.** Beginner and Expert see the same structure at different densities (progressive disclosure), never different apps.
- **Delight budget: three moments per app.** Signature micro-interactions are chosen deliberately (e.g., HCG's flying cart dot, payment check-draw, inbox all-clear). Everything else is utility motion.

## 1.5 Core principles (the Ten Threads)
Every screen review (Vol 18) scores against these:
1. One primary action per screen.
2. Everything important within one tap/keystroke of the surface home.
3. Exception-based UI — quiet when nothing needs you; "All clear" is a valid, designed state.
4. Readable at the working distance of its surface (30cm phone / 40cm till / 2m kitchen).
5. Zero training required for staff roles; power depth for operators (palette, shortcuts, bulk).
6. Undo over confirm; preview over apology.
7. Offline-tolerant where money or food moves.
8. Every number traceable to source.
9. Authority visible, never bypassable (approvals, risk, simulated-vs-live).
10. Same gesture means the same thing everywhere (Vol 9 grammar).

## 1.6 Brand identity
- **Platform mark:** "Saathi" wordmark, saathi-blue `--saathi-500 #5f8fff` on navy or white. Apps carry their own accent (Vol 7 App Accent Layer) plus the platform badge in About/Settings — "A SaathiOS product."
- **Voice:** a competent friend (साथी). Plain sentences, active verbs, no exclamation inflation, bilingual-ready. Says "Rs 4,500 overdue from Ward B" not "Uh oh! Some payments look late!"
- **Naming rule:** features get human job names (Inbox, Cash Book, Count Mode), never system names (NotificationCenterV2, LedgerModule).

## 1.7 Product values → design consequences
| Value | Consequence |
|---|---|
| Speed | Interaction→paint <100ms on operator surfaces; optimistic UI default (Vol 15) |
| Clarity | 12px text floor; one primary per screen; labels on all icons |
| Scalability | 3-layer tokens; capability-based nav config; app = accent + IA instance |
| Accessibility | WCAG 2.2 AA is a release gate, not a backlog item (Vol 14) |
| Consistency | 16-component library is the only UI vocabulary (Vol 8) |
| Maintainability | Lint-enforced: no hex in components, no inline styles, no native dialogs (Vol 16) |
| AI integration | AI is ambient presence with three modes (Vol 13), never a page |

## 1.8 Anti-patterns (Volume 1)
- ✗ "Dashboard as brochure" — stacking every widget at equal weight.
- ✗ Aesthetic dark mode that inverts colors without redesigning contrast.
- ✗ Feature pages named after backend modules.
- ✗ Per-app reinvention of buttons, dialogs, toasts "because our app is different." Your app is an accent, an IA, and workflows — never new primitives.

## 1.9 Developer notes
- This bible lives at `docs/design-spec/` in the SaathiAI repo; apps vendor a copy or link it in their CLAUDE.md. AI coding agents: load Volumes 5–10 before generating any UI; load Volume 16 before generating any component file.
- Precedence: user's explicit instruction > this bible > app-local docs > model defaults.

---

# VOLUME 2 — USER RESEARCH & CONTEXTS

## 2.1 Purpose
Ground every rule in real humans and real rooms. Personas here are drawn from live operations (HCG staff roster, SaathiOS operator, IELTS learner) — not invented archetypes.

## 2.2 The five platform personas
**P1 — The Operator (Ajay).** Owner of everything. Phone in pocket 14h/day, desktop at night. Checks in 5-minute bursts. Wants: is today okay, what needs me, one-tap approve. Fears: silent failures, money leaks. Expert-mode user; lives in ⌘K and Inbox.

**P2 — The Counter (Sajana).** Standing at till 8h/day. Two-finger typist. Speed is identity — a slow POS embarrasses her in front of a queue. Wants: 4-touch sale, instant credit lookup. Never opens settings.

**P3 — The Maker (Yabesh, kitchen).** Wet/greasy hands, 2m from screen, ambient noise, heat. Reads glances, not paragraphs. Wants: what to cook next, batch quantities, one-motion bump. Any typing is design failure.

**P4 — The Crew (Aryan, helper).** Minimal smartphone literacy, budget Android, 2 minutes/day of app use. Wants: am I clocked in, what are my duties, submit report, see salary. Trust matters: attendance and pay must be visible and fair.

**P5 — The Learner/Client (IELTS student; future travel customer).** Consumer expectations (Instagram-grade polish), self-serve, mobile-only, notification-driven. Wants progress made visible and next action obvious.

## 2.3 Journey maps (canonical three)
**Operator's day:** 07:00 phone glance (Home pulse + overnight Whispers) → 10:00 Inbox sweep (approve 3, reject 1) → lunchtime watch live orders → 20:00 close-day ritual (wizard) → 21:00 digest arrives in Telegram. *Design target: total screen time <20 min.*
**Counter's rush:** queue of 8 → repeat-customer chip → charge → drawer → next. *Target: <15s/sale, zero navigation events during rush.*
**Crew's day:** punch machine → phone shows "In ✓ 9:02" → duty list ticks → 15:00 break timer → 20:00 report nag → submit → done. *Target: <3 min total.*

## 2.4 Pain points (from audit evidence, permanent regression list)
Illegible 10px text · native browser prompts mid-workflow · nav duplication · spinner-only loading · raw server errors shown to staff · hover-only affordances on touch devices · UTC dates in a UTC+5:45 country. These seven are **banned regressions** — any reappearance fails design review (Vol 18).

## 2.5 Environment standards
| Environment | Facts | Binding rules |
|---|---|---|
| **Hospital canteen** | Glare, steam, noise, gloves, power cuts, flaky wifi, Moto-G-class devices | KDS dark-first ×1.6 type scale; 72px bump targets; offline queues; one chime max; battery-frugal polling |
| **Counter/till** | Standing, queue pressure, cash drawer | Fullscreen surface, no chrome; 56px primaries; keyboard path complete; offline sale queue |
| **Office/desk** | Desktop or phone, quiet, analytical | Density toggle; tables with keyboard nav; export everywhere; multi-column ≥1280px |
| **On-the-move** | Phone, one thumb, sunlight | Bottom-reachable primaries; pull-refresh; system font scale respected |
| **Consumer (IELTS/Travel)** | Personal phone, evening use | Larger type default, softer density, notification etiquette (Vol 13 caps) |

## 2.6 Device matrix (test floor)
Budget Android (Moto G / Redmi, 360×800, 4G) = the floor; iPhone SE→Pro; 10" Android tablet (KDS/till); 1366×768 laptop; 1440p desktop. Every release certifies on the floor device first (Vol 18 checklist).

## 2.7 Anti-patterns (Volume 2)
- ✗ Designing on a 27" monitor and "checking" mobile.
- ✗ Personas as posters — if a rule can't cite a persona+environment, it's taste, not design.
- ✗ Treating the Crew as "basic users" — they are expert *at their job*; the UI must be expert at fitting it.

## 2.8 Developer notes
Playwright viewport suite must include 360×800 and 1024×768-landscape (tablet). Type-scale and contrast checks run against the environment table above, not generic breakpoints.
# VOLUME 3 — INFORMATION ARCHITECTURE

## 3.1 Purpose
One structural grammar for every current and future app, so a user who learns one SaathiOS product already knows the next.

## 3.2 The platform IA stack
```
PLATFORM  →  APP  →  SURFACE  →  AREA  →  SCREEN  →  OBJECT
SaathiOS     HCG OS   Till/Office  Money    Customers   Bimala's account
             IELTSAlert  Learner    Practice  Mock test   Attempt #12
             Console    Operator    Monitoring Incidents  Run #4711
```
- **App** = accent + domain IA + workflows on shared foundation.
- **Surface** = a posture-specific shell (Vol 2 environments). Apps declare 1–4 surfaces. HCG: Till/Kitchen/Office/My Day. Console: Operator shell. IELTSAlert: Learner + Coach.
- **Area** = intent group inside a surface (max 12 per surface — Console proved 12 is the ceiling; HCG Office uses 5).
- **Object** = the nouns (sale, KOT, mission, attempt, account). Objects get canonical URLs, palette entries, and AI addressability.

## 3.3 Standards
- **Area count:** 3–12 per surface. >12 = split a surface or merge areas.
- **Depth:** max 3 levels below surface home (Area → Screen → Object detail). Deeper = restructure.
- **Canonical routes:** kebab-case, object IDs last: `/office/money/customers/[id]`. Old routes 301 forever.
- **Global chrome citizens** (never buried in areas): Approvals/Inbox, AI Copilot, Search/Palette, Settings, Environment indicator (console) / Sync state (operator apps).
- **Duplication rule:** a capability may have shortcuts (palette, FAB, dashboard card) but exactly one canonical screen.

## 3.4 Role & permission system
- Capabilities, not role names, gate UI: `nav.filter(item => user.can(item.capability))`. Role → capability map lives in DB (HCG: category-derived; Console: authority levels advisor/planner/executor).
- **Same IA for all roles** — items the user can't access are absent, not disabled (except: approval-gated actions render disabled+reason, because visibility of authority is a platform value).
- Hardcoded person-names in logic = banned (HCG audit finding; lint rule).

## 3.5 Search & command palette (platform contract)
- `⌘K` everywhere. One index per app: screens, actions, objects (customers, items, staff, missions), recency-weighted fuzzy.
- Rows: icon + name + type chip + right-hint (shortcut or context). Actions verb-first: "Record payment…", "86 an item…".
- Palette actions = the same action registry the AI "Do" mode uses (Vol 13). Build once.
- Mobile: search icon in top bar opens same index full-screen.

## 3.6 Future expansion rules
New module checklist: (1) which persona + surface; (2) which existing area it joins — creating a new area needs Governance sign-off; (3) its objects, URLs, palette entries; (4) its Inbox event types; (5) its AI tools (read + act). A module that can't answer all five isn't ready to build.
New app checklist: accent hue + neutral bias (Vol 7), surfaces declared, IA sketch ≤12 areas/surface, reuses the 16 components, ships Settings/Inbox/Palette from platform kit.

## 3.7 Anti-patterns
✗ "More" pages (retired in HCG 2.0 — permanent). ✗ Backend-module nav ("Automations/Production"→ user intent names). ✗ Two notification systems in one app. ✗ Role-forked IA.

## 3.8 Developer notes
`lib/nav.ts` single config: `{surface, area, href, icon, label, capability, palette: {keywords, verbs}}`. Sidebar, tabs, palette, breadcrumbs, and AI navigation tools all derive from this one object. Drift is structurally impossible.

---

# VOLUME 4 — NAVIGATION STANDARDS

## 4.1 Purpose
Fixed navigation furniture so muscle memory transfers across apps.

## 4.2 The shell grammar (all apps, all surfaces)
```
Operator/desktop surface:            Fullscreen surfaces (Till/KDS):
┌─────────────────────────────┐      ┌─────────────────────────────┐
│ TopBar                      │      │ [surface content only]      │
├──────┬───────────────┬──────┤      │  minimal top strip:          │
│ Side │  Workspace    │ AI   │      │  identity · sync · exit      │
│ bar  │               │ panel│      └─────────────────────────────┘
├──────┴───────────────┴──────┤      Phone surfaces (My Day/Learner):
│ StatusBar (console only)    │      content + bottom tabs (3–5)
└─────────────────────────────┘
```

## 4.3 Standards per element
- **Sidebar** (desktop office/console): grouped areas; expanded 240px ↔ icon rail 64px, persisted; order = Pins → Recents → Groups; badges only for time-sensitive counts (Inbox, incidents). Hover AND focus-visible styles in CSS classes (never JS handlers).
- **TopBar** (all non-fullscreen): left = surface switcher (avatar) + breadcrumb/title; right cluster max 4 items = Search · Create(+) · Inbox bell · AI. Console adds environment pill left of cluster.
- **Bottom tabs** (phone): 3–5 items, ≥56px tall, active = accent icon + label + dot; center slot may be an action (Sell) not a page.
- **Breadcrumbs:** desktop only, ≥3 levels deep only, last item = title (not a link).
- **Tabs (in-page):** SegmentedControl for 2–4 mutually-exclusive views of the same data; Tabs for 2–6 sub-sections; never both on one screen.
- **Context menus:** long-press (touch) / right-click (desktop) on any object row → Sheet (mobile) or menu (desktop) with the object's verb list. Same verbs as palette. Max 7 verbs; overflow into "More…".
- **FAB:** phone only, one per surface max, always a create verb, 56px, bottom-right above tabs. Never on Till/KDS.
- **Keyboard shortcuts:** global `⌘K` palette, `⌘J` AI, `g` then letter go-tos, `?` shortcut overlay. Surface-local shortcuts documented in that surface's spec (POS: Vol 11). Every shortcut discoverable via palette row hint.

## 4.4 Rules
1. Navigation chrome never scrolls away (sticky) except on fullscreen surfaces.
2. Nothing important lives *only* behind a gesture or shortcut — always a visible path.
3. Back always works: browser back = app back; sheets close on Esc/swipe-down and return focus (Vol 14).
4. Surface switching is explicit (avatar sheet), never automatic mid-session.

## 4.5 Anti-patterns
✗ Hamburger menus on desktop. ✗ Icon-only nav without labels (rail shows tooltips + aria-labels). ✗ >5 bottom tabs. ✗ Nav items that are really actions (looking at you, "Logout" as a nav row — it's a Settings/account verb).

## 4.6 Developer notes
One `<Shell>` per surface type in the platform kit (`@saathi/ui`): `<OperatorShell>`, `<FullscreenShell>`, `<PhoneShell>`. Apps pass nav config + accent; shells own responsive behavior, skip-links, focus management, safe-areas.

---

# VOLUME 5 — LAYOUT SYSTEM

## 5.1 Purpose
Space is the first thing users feel. One spatial system = instant family resemblance.

## 5.2 Grid & containers
- Base unit **4px**; working rhythm **8pt**: `4 8 12 16 24 32 48 64`.
- Containers: phone = fluid, 16px gutters · tablet = fluid, 24px · desktop content max-width **1200px**, 32px gutters, 12-col grid (24px gutter) · consoles/dense tables may go 1440px with Governance sign-off.
- Fullscreen surfaces define their own fixed panes (POS: menu-flex + cart 360px; KDS: N swimlanes ≥320px each, horizontal scroll beyond 4).
- Safe areas: `env(safe-area-inset-*)` on all fixed bars; bottom tabs add inset padding (exists in HCG — keep).

## 5.3 Page anatomy (operator screens)
```
PageHeader: title (display) · context line · ≤2 header actions (1 primary)
NextStrip:  0–1 exception suggestion ("2 approvals waiting") or "All clear"
Content:    StatRow? → attention sections (conditional) → primary content
```
Vertical rhythm: sections gap-24; cards internal padding-16; related list rows gap-0 with dividers, unrelated cards gap-12.

## 5.4 Component-class layout rules
- **Cards:** radius-card(16), border 1px, elevation-0 resting; interactive cards elevation-1 + hover elevation-2 + focus ring. A card = one object or one question, never a dumping ground.
- **Lists vs tables:** phone default = card-list; desktop ≥3 comparable columns = Table. Tables: sticky header, row height 44 (comfortable) / 36 (dense toggle), first column identity, last column right-aligned numbers, tap row → detail Sheet, no horizontal scroll of the page (table gets own scroll container).
- **Forms:** single column, max-width 480px; labels above; groups separated by 24; one primary submit bottom-right (desktop) / full-width bottom (mobile); destructive never adjacent to primary. Multi-step > long form when >8 fields — steps with progress ("2 of 3"), each step ≤5 fields.
- **Dialog vs Sheet vs Drawer decision table:**

| Need | Use | Size |
|---|---|---|
| Confirm irreversible / tiny decision | Dialog | ≤400px, 1 primary + cancel |
| Any form, object detail, filters | Sheet (bottom on phone, right 480px on desktop) | up to 90vh |
| Persistent secondary context (AI, evidence) | Panel/Drawer (docked, collapsible) | 360–420px |
| Full task with own nav (count mode, close-day) | Fullscreen takeover with explicit exit | 100% |

Modals never stack >2 (Dialog atop Sheet max). Third layer = you designed the flow wrong.

## 5.5 Responsive rules
Breakpoints: `sm 640 · md 768 · lg 1024 · xl 1280`. Phone-first CSS. Rules of transformation (not per-page improvisation): table→card-list below md · sidebar→bottom-tabs below md · right-Sheet→bottom-Sheet below md · StatRow 4-up→2-up grid below sm · header actions collapse to ⋯ menu below sm (primary stays visible).

## 5.6 Examples
HCG Customers desktop: 1200px, StatRow (3 stats), table 44px rows, right-Sheet detail. Same screen phone: 2-up stats, card-list with balance bars, bottom-Sheet detail. Identical hierarchy, transformed containers.

## 5.7 Anti-patterns
✗ Margins on children instead of `gap` on parents (collapse bugs — platform lint). ✗ px-perfect absolute layouts. ✗ Center-aligned body text. ✗ Full-width buttons on desktop forms. ✗ Two primaries side by side.

## 5.8 Developer notes
Tailwind theme maps spacing scale 1:1 (`p-4` = 16). Only `gap-*` for sibling spacing in flex/grid. `tabular-nums` utility mandatory on numeric columns. Layout primitives in kit: `<Page>`, `<PageHeader>`, `<StatRow>`, `<Section>`, `<FormGrid>` — hand-rolled page scaffolds fail review.
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
# VOLUME 9 — INTERACTION DESIGN

## 9.1 Purpose
Same gesture, same meaning, every app. Interaction grammar is platform law; apps choose *which* interactions to expose, never what they mean.

## 9.2 The gesture grammar (binding)
| Input | Meaning | Notes |
|---|---|---|
| Tap / click | Primary: open or execute the row's main verb | Whole row/card is the target, not just text |
| Swipe right | Positive advance (approve, bump, pay, complete) | Reveals green action ≥50% then commits; haptic tick |
| Swipe left | Negative (reject, remove, trouble) | Always lands on reason-chips or undo, never silent delete |
| Long-press / right-click | Context menu (object verbs) | Same verb list as palette; 400ms, haptic |
| Drag | Reorder / move between lanes | Edit-modes and boards only; FLIP animation; drop targets highlight |
| Pull-down | Refresh | Lists only; spinner in the pull zone, not page |
| Hover | Preview/affordance only | Nothing *functional* is hover-only (touch parity law) |
| Double-tap | Reserved — unused | Too error-prone near money |

## 9.3 Undo/redo doctrine
- Reversible actions execute immediately + undo toast (6s, countdown ring, `⌘Z`). Server pattern: soft-state with `undo_until` or compensating action (HCG soft-cancel is the reference implementation).
- Irreversible (post-window cancel, deactivate staff, send money, live-mode trading actions): Dialog with typed consequence line ("Rs 120 returns to Bimala's balance") — and for `--risk-high`+ actions, hold-to-confirm (800ms fill).
- Forms: drafts autosave to localStorage every 5s; abandoning warns only if >30s of input would be lost.

## 9.4 Selection & bulk
Long-press (touch) / checkbox column (desktop) enters selection mode → sticky bottom bulk bar: count + ≤4 verbs + cancel. `⌘A` selects filtered set (with count confirmation >50). Bulk operations report per-item results ("14 approved · 2 failed — view").

## 9.5 Inline editing
Numbers and short text edit in place (tap → input with keypad, ✓/Esc). Tables: Enter edits focused cell where editable, Tab advances. Anything multi-field opens a Sheet — inline is for one value.

## 9.6 Keyboard (desktop operator contract)
Global: `⌘K` palette · `⌘J` AI · `g h/o/i/m…` go-tos · `?` overlay · `Esc` closes topmost layer · `⌘Enter` submits focused form. Lists: `↑↓` move, `Enter` open, `x` select, `e` edit, `.` context menu (Linear grammar). Every screen fully operable by keyboard = release gate (Vol 14).

## 9.7 Scanning & hardware
QR/barcode via `BarcodeDetector` + manual fallback input always visible. Platform events for hardware: cash drawer kick, printer, punch device — abstracted in `@saathi/devices` so UI code never talks to hardware.

## 9.8 Anti-patterns
✗ Hover-revealed action buttons (touch orphans). ✗ Swipe with hidden meanings that differ per screen. ✗ `confirm()` culture — undo is the default posture. ✗ Selection modes without visible exit.

## 9.9 Developer notes
`useSwipeAction`, `useLongPress`, `useUndoable(action, compensate)`, `useSelection` in `@saathi/ui/hooks`. All gesture thresholds tokenized (`--swipe-commit: 50%`, `--longpress: 400ms`) — no magic numbers in app code.

---

# VOLUME 10 — ANIMATION SYSTEM

## 10.1 Purpose
Motion explains state change; it never entertains during work.

## 10.2 Tokens & curves
`--t-fast 120ms` (state flips: hover, active, toggle) · `--t-med 200ms` (enter/exit: menus, toasts, rows) · `--t-slow 300ms` (sheets, palette, page transitions). Curve: `cubic-bezier(.2,.8,.2,1)` standard; spring (stiffness ~300, damping ~30) only for sheets and drag-release.

## 10.3 Choreography rules
- One property family per element (transform+opacity); never animate layout properties (width/height/top) — use transforms/FLIP.
- Enter = translateY(8→0)+fade; exit = fade only, 60% duration of enter (exits feel faster).
- Lists: stagger ≤40ms/item, cap 6 items, first paint only (not on every filter).
- Skeleton→content: crossfade 200ms, zero layout shift (skeleton is shape-accurate, Vol 8).
- Success: check-draw 240ms. Error: field shake 2×4px 160ms + focus jump. Celebration: reserved for rare human milestones (inbox-zero "all clear" fade, IELTS band goal) — subtle fade+scale, **no confetti** on money surfaces, ever.
- KDS/alarm contexts: single pulse on arrival (300ms), never looping animation (alarm fatigue, Vol 2).

## 10.4 Reduced motion
`prefers-reduced-motion`: all transforms→opacity crossfades; staggers→0; springs→ease; countdown rings→numeric timers. This is a token-level switch (`--motion-scale: 0`), not per-component effort.

## 10.5 Anti-patterns
✗ Spinners as transitions. ✗ Parallax/scroll-jacking anywhere. ✗ Animating during drag (follow finger 1:1). ✗ >300ms anything on operator surfaces.

## 10.6 Developer notes
CSS-first; JS animation only for FLIP/drag (`@saathi/ui/motion` wraps). Motion tokens in Tailwind (`duration-fast`, `ease-saathi`). Every keyframe added to an app = review question: "which state change does this explain?"

---

# VOLUME 11 — SCREEN STANDARDS

## 11.1 Purpose
Canonical anatomy for the recurring screen archetypes. Any future screen of a given archetype follows its standard; deviations need Governance sign-off. (HCG OS 2.0 Blueprint Part IV is the reference implementation of these archetypes; Console IA docs the operator variants.)

## 11.2 Archetype: Dashboard/Home ("the 5-second answer")
Pulse StatRow (≤4) → NextStrip exception → conditional attention sections → trends → team/social. Router screen: no primary action; every element drills somewhere. Never >2 screens of scroll on phone. Anti: chart walls; widgets without drill.

## 11.3 Archetype: POS/Transactional
Fullscreen surface. Grid of sellable tiles (favorites row auto-computed) + persistent order panel (desktop/tablet) or summary-bar→sheet (phone). Charge = takeover screen with ≥72px tender buttons, quick-tender denominations, change display huge. Complete keyboard path. Offline queue pill. Reference: HCG Till (Blueprint 4.1).

## 11.4 Archetype: Kitchen/Live board
Dark-first, ×1.6 scale, swimlanes by state, aging via border→bg escalation, bump = whole-button + swipe parity, aggregate "All-Day" toggle, one arrival chime. Reference: HCG KDS (4.2).

## 11.5 Archetype: Ledger (Inventory/Finance/Cash Book/Payroll)
StatRow → filter chips → Table/card-list → row Sheet detail → FAB/+ entry (amount-first keypad). System rows lock-marked. Every ledger exports (CSV min). Count/reconcile flows = fullscreen takeover wizards (Count Mode, Close Day, Run Month).

## 11.6 Archetype: Directory (Customers/Staff/Contacts/Agents)
Search-always-visible → cards/rows with identity + 1 key metric + status → detail Sheet with tabs (overview/activity/actions) → create via ≤3-step Sheet. Balance/score visualized (limit bar, score ring) not just numbered.

## 11.7 Archetype: Report/Analytics
Period segmented + date pager → KPI StatRow → one hero chart → breakdown tabs → export. Read-only; every number drills to its transaction list. Print stylesheet mandatory.

## 11.8 Archetype: Inbox/Queue (approvals, complaints, alerts)
One list, type chips, card = who/what/when + the one decisive number + inline verbs; swipe grammar; batch by type; empty = designed "all clear". Reference: HCG Inbox (4.13); Console Approvals inherits with authority/risk pills.

## 11.9 Archetype: Settings
Single page, grouped sections, rows = label + value + chevron→Sheet; search within settings ≥15 rows; danger zone last, visually separated. Business rules (thresholds, windows, targets) live here — never hardcoded (audit law).

## 11.10 Archetype: AI Assistant
Never a page (Vol 13). Panel/sheet + whisper slots per Vol 8.5 kit.

## 11.11 Archetype: Attendance/Presence
Exceptions first (late/absent buckets), then present; per-person month heat-strip; device/hardware status visible; manual corrections always audited (who/when/why).

## 11.12 Developer notes
Each archetype = a composed template in `@saathi/ui/templates` (`<LedgerScreen>`, `<DirectoryScreen>`, `<InboxScreen>`…). New screens start from a template import — blank-page screens fail review.

---

# VOLUME 12 — WORKFLOW STANDARDS

## 12.1 Purpose
Workflows are where consistency pays or breaks. Each standard below defines: trigger → steps → feedback → failure path → audit.

## 12.2 Money workflows
- **Checkout:** ≤4 touches happy path; tender screen totals huge; change computed; receipt share optional post-state. Split = remainder-driven. Credit = picker with limit visualization; over-limit = warn + authority escalation (PIN/approval), never silent block or silent allow.
- **Refund/Cancel:** reason (chips + optional note) → consequence preview line → execute → undo window → audit stamp (who/when/why kept forever). Time-window rules displayed as countdown chips and enforced server-side (HCG 12h pattern = platform reference).
- **Payment collection (credit/receivables):** record → balance updates instantly → customer notified → statement reflects. Reminders are batched, capped (Vol 13 etiquette), and logged.

## 12.3 Operations workflows
- **Order lifecycle:** placed → (approval gate if untrusted channel) → queued → making → ready → served/delivered; every state visible to every party in their surface's idiom (customer progress view, maker board, operator list). State changes are optimistic + reconciled.
- **Opening ritual:** surface a morning card (yesterday's close ✓, today's prep/forecast, exceptions). Dismissible, auto-expires.
- **Closing ritual:** guided wizard — unresolved items → count/reconcile (variance highlighted + note if over threshold) → auto-summary → lock + distribute (Telegram/email). Un-closed prior day = persistent amber pill.
- **Inventory:** adjustments always reasoned (chips); spoilage feeds waste ledger; low-stock → draft order → external share (WhatsApp/text) → receive bumps stock + vendor balance.

## 12.4 People workflows
- **Attendance:** hardware-automatic; UI handles exceptions only; corrections audited; staff always sees own state (trust rule).
- **Approvals (leave/OT/advance/duty/any):** request from requester's surface (≤3 fields) → Inbox card → inline decide (swipe/buttons, reason on reject) → requester notified + state visible in their history. One queue per app; never scattered.
- **Payroll:** auto-assemble (base + approved OT − advances) → review grid → execute (creates ledger rows) → payslips distributed to staff surface. No manual arithmetic anywhere.
- **Complaint:** capture (photo-first where physical) → triage/assign → responsible party sees it in their surface → resolve with note → reporter notified → aggregate digest to team. Reference: HCG complaints.

## 12.5 Reporting & notification workflows
- Reports pull, never push raw tables: period → KPIs → drill. Scheduled digests are AI-composed summaries (Vol 13), not attachments.
- **Notification etiquette (platform caps):** per user per app per day: ≤3 proactive AI whispers, ≤2 reminder pushes; time-sensitive operational events (new order, approval needed) exempt but batched within 60s windows. Every notification deep-links to its object. Quiet hours honored (default 21:00–07:00 except operational surfaces on duty).

## 12.6 AI workflows
Ask/Do/Whisper contracts in Vol 13; every "Do" passes through `AIActionPreview`; automations (cron/agent-initiated) log to the same audit trail as humans, actor = agent identity with authority level (Console `--auth-*` pattern platform-wide).

## 12.7 Anti-patterns
✗ Confirmation-dialog chains instead of preview+undo. ✗ Workflows that dead-end off-app ("then go tell the manager"). ✗ State visible to operator but hidden from the person it's about (attendance, complaints, payroll — visibility builds trust). ✗ Any approval flow bypassing the Inbox.

## 12.8 Developer notes
Workflow = state machine documented in the feature's ADR (`docs/adr/`); UI states map 1:1 to machine states; no UI-only states that the server can't reproduce (offline queues excepted, flagged as `pending-sync`).
# VOLUME 13 — AI EXPERIENCE ("Sathi")

## 13.1 Purpose
One AI personality across the platform, three interaction modes, hard trust rules. AI is the platform's second user interface — it must be as governed as the first.

## 13.2 Personality & tone
- **Sathi is a competent colleague, not a mascot.** Speaks like the platform voice (Vol 1.6): plain, specific, bilingual, numerate. No emoji in analytical answers; at most one in celebrations.
- Confidence is worded, not faked: "Tea sales are down 40% vs your usual Thursday" (measured) vs "This might be because OPD was closed" (hypothesis — always marked "might/possibly").
- Never scolds users or staff. Frames people-insights neutrally: "Aryan has 3 late arrivals this week" + suggested action, not judgment.
- Every AI surface carries the `--ai` violet marker (Vol 8.5) — machine-generated is always visually distinct from system fact.

## 13.3 The three modes (platform contract)
1. **Ask** — conversational panel (`⌘J` / orb; never on Till/KDS mid-service). Context-aware: opened from a customer sheet, "this customer" resolves. Answers use `AIAnswer`: result first (StatCards/bullets, not essays), "based on:" source line, links to canonical screens. Tool-use over app DB: read-only SQL/query tools + typed action tools.
2. **Do** — verbs with previews. Same action registry as command palette (Vol 3.5 — built once). Flow: intent → `AIActionPreview` (exact effect, diff-style) → confirm → execute → undo where the action supports it. **AI never writes money/people rows without preview+confirm.** Risk-tiered: `--risk-high`+ actions additionally require the human hold-to-confirm (Vol 9.3).
3. **Whisper** — proactive cards in exactly two slots (Home attention area + scheduled digest). Caps: ≤3/day/user, dismiss = suppressed 7 days for that insight type, thumbs-down feeds review log. Whisper anatomy: insight sentence + evidence line + ≤2 verbs + dismiss.

## 13.4 Capabilities by grounding (what Sathi may claim)
| Grounding | May do | May NOT do |
|---|---|---|
| Ledger tables (sales, attendance, inventory…) | Aggregate, compare, trend, rank | Invent missing periods; extrapolate silently |
| Recipes/BOM links | Forecast consumption, purchase suggestions | Assume yields not in data |
| Events/complaints | Summarize, categorize, route | Attribute blame |
| External (weather, calendar) | Correlate as hypothesis | State as cause |
Unmeasured = say so: "I don't have waste data yet — start the waste log to unlock this."

## 13.5 Memory & personalization
Sathi remembers per-user: preferred answer formats, dismissed whisper types, recurring questions (offers to pin as dashboard card / scheduled digest). Memory is inspectable & erasable in Settings → AI. No cross-app memory without explicit opt-in ("Let Sathi share business context between HCG and Travel?").

## 13.6 Voice
Voice input = mic slot in `AIInput` (deferred until Ask is proven). Live human voice (walkie-talkie) is comms, not AI — separate affordance, never merged. Voice output only for hands-busy surfaces on request.

## 13.7 Agent collaboration (Console inheritance, platform rule)
Non-human actors (crons, agents, automations) act under visible authority levels (`--auth-advisor/planner/executor`), log to the same audit trail as humans, and their pending intents appear in the same Inbox. An agent's suggestion card = Whisper; an agent's action request = Inbox approval item. No third pattern.

## 13.8 Anti-patterns
✗ AI as a destination page. ✗ Unsourced numbers. ✗ Chatty filler ("Great question!"). ✗ Proactive interruptions during transactions. ✗ Autonomous money movement at any authority level without a standing, user-visible, revocable rule.

## 13.9 Developer notes
`@saathi/ai`: action registry (shared with palette), tool schemas (read/act split), `AIAnswer`/`WhisperCard`/`AIActionPreview` components, per-app grounding manifest (`ai.manifest.ts`: tables, tools, caps). Every tool call logged with inputs/outputs to evidence store. Prompt templates versioned in repo; eval set per app (20 golden Q→A pairs minimum) run in CI.

---

# VOLUME 14 — ACCESSIBILITY

## 14.1 Purpose
WCAG 2.2 AA as release gate. In a hospital canteen, accessibility is also just ergonomics: gloves, glare, haste, age.

## 14.2 Standards (the gates)
- **Contrast:** text ≥4.5:1, large ≥3:1, UI components ≥3:1 — both themes, CI-verified at token level (Vol 7.6).
- **Touch:** ≥44px all targets; ≥56px till primaries; ≥72px KDS bump; ≥8px between adjacent destructive/positive targets.
- **Type:** 12px floor (24px KDS); rem-based; survives 130% user scale without loss (test in CI viewport pass).
- **Keyboard:** every screen fully operable; visible focus ring (2px, 2px offset) on every interactive element; logical tab order = visual order; skip-link to content in every Shell; no focus traps outside modals; modals trap + restore.
- **Screen reader:** landmarks per Shell region; every icon button labeled; images meaningfully alt'd ("Complaint photo from Bimala — burnt samosa") or `alt=""` if decorative; live regions: cart total, new-KDS-order, toasts (`polite`; errors `assertive`); tables with proper headers/scope.
- **Color independence:** status = shape+label+hue (Vol 7 law); charts add pattern/position cues; delta arrows accompany red/green.
- **Motion:** `prefers-reduced-motion` global switch (Vol 10.4).
- **Cognition:** one primary per screen, plain-language errors (what happened + what to do), no timeout-losing-work (drafts autosave), reading level ≈ grade 6 for staff/consumer surfaces.

## 14.3 Voice control
All interactive elements have accessible names matching their visible labels (voice-control users speak what they see — label mismatch = broken).

## 14.4 Testing protocol
Per release: axe-core CI (zero criticals) → keyboard-only pass on the money flows → VoiceOver/TalkBack pass on the 4 core journeys per app → 130% font + 360px width sweep. Findings triage like functional bugs (blockers block).

## 14.5 Anti-patterns
✗ `outline: none` without replacement. ✗ aria-label contradicting visible text. ✗ Disabled buttons as the only explanation of gating (pair with reason). ✗ Contrast-passing-but-vibrating hue pairs (red text on green tint).

## 14.6 Developer notes
`@saathi/ui` primitives ship the a11y behavior — apps mostly inherit compliance. eslint-plugin-jsx-a11y strict; axe in Playwright suite; contrast script on token PRs. A11y checklist lives in the PR template (Vol 18).

---

# VOLUME 15 — PERFORMANCE

## 15.1 Purpose
Speed is the brand (Vol 1.7). Budgets are contracts, not aspirations.

## 15.2 Budgets (the floor device is a Moto-G-class Android on 4G)
| Metric | Operator surfaces (Till/KDS) | Office/консumer |
|---|---|---|
| Interaction→paint | <100ms | <200ms |
| LCP (cold) | <1.5s | <2.5s |
| Route JS (gz) | <150KB | <250KB |
| Realtime lag (visible) | <2s | <5s |
CI fails the build on budget breach (bundle analyzer + Lighthouse CI on floor-device profile).

## 15.3 Loading doctrine
Server components for reads; parallel queries (HCG dashboard pattern = reference); skeletons shape-accurate at page level; spinners only in buttons; stale-while-revalidate on focus; prefetch likely-next routes (POS→Charge, list→detail).

## 15.4 Optimistic UI & realtime
Money/state actions on operator surfaces: apply locally, reconcile on server echo, conflict = toast + refetch (never silent divergence). Realtime channels only where seconds matter (orders, approvals, incidents); everything else poll-on-focus. Every realtime feature has a poll fallback.

## 15.5 Offline
Tiered: **Till** = full sale queue (IndexedDB, sync pill, conflict-safe idempotency keys) · **KDS** = read cache + queued bumps · **Office/consumer** = read cache + "offline" banner, writes disabled except drafts. PWA precache per surface; offline page styled per app.

## 15.6 Data & rendering discipline
Select only used columns (HCG audit lesson — codified); paginate >100 rows (cursor); virtualize >200 DOM rows; images client-resized ≤1280px before upload, lazy, blur-up; charts render ≤120 points (aggregate beyond).

## 15.7 Error recovery
Every fetch path: retry (3×, backoff) → human message + Retry verb → error code (caption) for support. Global error boundary per Shell region (sidebar crash ≠ workspace crash). Failed mutations from queues surface in a "Pending issues" sheet, never vanish.

## 15.8 Battery & resource
Polling ≥30s intervals when tab hidden; KDS wake-lock only while lanes non-empty; animations pause off-screen; no永-looping animations (Vol 10).

## 15.9 Anti-patterns
✗ Waiting on wifi to show success at a counter. ✗ Chart libraries on transactional bundles. ✗ `select('*')`. ✗ Realtime-everything. ✗ Infinite spinners without error state.

## 15.10 Developer notes
Perf budgets in `saathi.config.ts` per route group; `@saathi/data` wraps fetching (SWR policy, retries, idempotency keys, offline queues) so policy is code, not convention.
# VOLUME 16 — DEVELOPER STANDARDS

## 16.1 Purpose
Make the right thing the only easy thing. Every rule here is lint-enforced or template-enforced; culture is not a mechanism.

## 16.2 Repository & folder structure (per app)
```
app/
  (till)/ (kitchen)/ (office)/ (myday)/   ← surfaces as route groups
  api/                                    ← route handlers (thin: auth → validate → service)
components/
  domain/            ← app composites (KOTCard, BandRing) built from @saathi/ui
lib/
  nav.ts             ← THE nav config (Vol 3.8)
  dates.ts           ← timezone-correct helpers (todayLocal(), never raw toISOString dates)
  capabilities.ts    ← role→capability map
  services/          ← business logic, callable from routes AND AI tools
locales/en.json ne.json
docs/adr/            ← decisions (workflow state machines live here)
```
Platform packages: `@saathi/tokens` `@saathi/ui` `@saathi/ai` `@saathi/data` `@saathi/devices`.

## 16.3 Naming
Components PascalCase by role (`CustomerSheet`, not `Modal2`); hooks `useX`; route folders kebab-case; DB snake_case; events `object.verb` (`sale.cancelled`); design tokens as specified (Vols 6–10) — no synonyms.

## 16.4 Component rules (lint-backed)
Banned in app code: raw hex colors · `style={{}}` (except dynamic transforms) · `window.alert/confirm/prompt` · `text-[Npx]` arbitrary sizes · native `<button>` outside `@saathi/ui` · string literals for user-visible text (must come from locales) · `new Date().toISOString().split` date math (use `lib/dates`). Each ban = an ESLint rule with autofix or codemod where possible.

## 16.5 State management
Server state: `@saathi/data` (SWR + optimistic + queues). UI state: local component state; cross-component per-surface state = one store max (Zustand), documented. No global god-store. URL is state for anything shareable (filters, periods, tabs → search params).

## 16.6 API rules
Route handlers thin; services own logic (shared with AI tools — one implementation of "cancel sale"). Zod-validate all inputs. Authority checks server-side always (UI gating is UX, not security). Money mutations idempotent (client idempotency keys). Every mutation writes audit fields (actor, actor_type human|agent|cron, reason where applicable) — the platform audit contract.

## 16.7 Errors, logging, analytics
Error taxonomy: `VALIDATION | AUTH | CONFLICT | UPSTREAM | UNKNOWN` → mapped to human copy per Vol 15.7. Client logs errors w/ context to Sentry-class sink; PII scrubbed. Product analytics: screen views + the named workflow funnels only (checkout, close-day, approval) — no keystroke surveillance of staff (trust value).

## 16.8 Feature flags & rollout
Flags per surface (`flags.till.newCharge`); strangler migrations (old+new parallel, cohort toggle, kill date written at flag creation). Dead flags removed within 2 releases (lint counts them).

## 16.9 Testing & review
Per feature: unit (services) + Playwright happy-path on floor viewport + axe pass. Money workflows additionally: failure-path tests (offline, double-tap, stale window). Visual regression = `/dev/kit` gallery snapshots. PR template embeds Vol 18 checklists; CI blocks on budgets (Vol 15.2), a11y criticals, lint bans.

## 16.10 Documentation
Every feature PR updates: the app's CLAUDE.md (if operational knowledge changed) + ADR if a decision was made. AI agents (Claude Code, Codex, Cursor) read: this bible → app CLAUDE.md → ADRs, in that order (stated in each CLAUDE.md header).

## 16.11 Anti-patterns
✗ Copy-pasting a component to change its color. ✗ Business logic in route handlers or components. ✗ "Temporary" inline styles. ✗ Untested money paths. ✗ Docs describing intent that code contradicts (docs follow code within the same PR).

---

# VOLUME 17 — FUTURE EXPANSION

## 17.1 Purpose
Rules that let the platform grow for 10 years without redesign.

## 17.2 New apps
Follow Vol 3.6 new-app checklist. The accent registry (Vol 7.3) is centrally owned; two apps may not claim the same hue. Each app ships the platform kit (Inbox, Settings, Palette, AI panel) before any domain feature — the family resemblance is the first deliverable.

## 17.3 Multi-business & multi-tenant
- Data: tenant_id on every table from day one for new apps; HCG retrofits when second canteen signs.
- UX: business switcher in the surface-switcher sheet (same avatar affordance — no new chrome); active business name always visible in TopBar when user has >1; cross-business dashboards are an Operator-surface feature ("All businesses" pseudo-tenant), never silent data mixing.
- Roles are per-tenant; capability map identical in shape.

## 17.4 White label & themes
White label = accent + logo + name swap ONLY (token layer makes this a config file). Semantic tokens, components, IA are non-negotiable — a white-label that wants different UX is a fork, and forks are declined. Theme marketplace (user-facing): limited to accent variants + light/dark/auto; arbitrary user CSS never.

## 17.5 Plugin/extension system (when it comes)
Plugins integrate at defined seams only: (1) Inbox event types, (2) dashboard cards (StatCard/WhisperCard contracts), (3) palette actions, (4) AI tools with manifest + authority level, (5) Settings sections. Plugins never inject arbitrary UI into surfaces. Each seam has a JSON-schema contract; plugin review = Governance checklist.

## 17.6 Marketplace & enterprise
Marketplace listings render from the same component kit (dogfooding). Enterprise adds: SSO, audit export, retention policies, org-level capability policies — all Settings-surface features, no new paradigms.

## 17.7 Internationalization
Locale files from day one (Vol 6.5); RTL not targeted (Nepali/English) but layout uses logical properties (`padding-inline`) so the door stays open; currency/units per tenant config; date/number formatting via `Intl` with tenant locale.

## 17.8 Anti-patterns
✗ Tenant-specific if-branches in components (config, not code). ✗ Plugins as iframes with free CSS. ✗ "We'll add tenant_id later."

---

# VOLUME 18 — DESIGN GOVERNANCE

## 18.1 Purpose
The mechanism that makes this bible permanent instead of aspirational.

## 18.2 Change management
- The bible is versioned (semver). Volumes carry a changelog footer. Changes via PR labeled `design-spec`, reviewed by the design owner (today: Ajay + AI design lead session; later: named humans).
- **Breaking token/component changes:** major version + codemod shipped in the same PR + migration note in every app's CLAUDE.md.
- Apps declare their bible version (`saathi.config.ts: specVersion`); CI warns when >1 minor behind, fails when >1 major behind.

## 18.3 Component approval process
New primitive request → issue with: job it does, why the Sixteen can't compose it, 2+ apps that need it, spec draft (states/a11y/tokens). Approved = built in `@saathi/ui` with gallery page; rejected = composite pattern documented instead. Domain composites need no approval (they compose primitives).

## 18.4 The four checklists (embedded in PR template)

**Design review** — ☐ archetype template used ☐ one primary action ☐ Ten Threads pass (Vol 1.5) ☐ both themes screenshot ☐ empty/loading/error states shown ☐ copy follows voice (Vol 1.6) ☐ no banned regressions (Vol 2.4 seven).

**UX review** — ☐ ≤3 levels deep ☐ palette entries added ☐ gesture grammar respected ☐ undo-over-confirm applied ☐ workflow state machine in ADR ☐ notification etiquette respected.

**Accessibility** — ☐ axe zero criticals ☐ keyboard-only walkthrough recorded ☐ contrast pass both themes ☐ touch targets measured ☐ labels/live-regions verified ☐ 130%/360px sweep.

**Performance/release** — ☐ budgets green on floor profile ☐ offline behavior defined ☐ failure paths tested (money flows) ☐ flags + kill date set ☐ docs/ADR/CLAUDE.md updated ☐ locale files complete (en+ne).

## 18.5 Design debt register
`docs/design-debt.md` per app: every accepted deviation logged with owner + expiry. Expired debt = blocking ticket. (This replaces "we'll fix it later" with a dated contract.)

## 18.6 The prime directive
When this document and reality disagree, one of them must change **in the same week** — either fix the product or amend the spec via 18.2. A spec that drifts from reality is dead; this one stays alive by being enforced (lint, CI, templates) rather than remembered.

---

## APPENDIX A — Adoption map (July 2026)
| App | State | First milestone under Dhaago |
|---|---|---|
| SaathiOS Console | SOVEREIGN_ORBIT tokens ≈ Dhaago-compliant | Rename/alias semantic tokens; adopt kit gallery |
| HCG OS | v2.0 Blueprint = reference implementation | Phase 0 foundation (tokens, dates, Dialog/Toast) |
| IELTSAlert | Pre-Dhaago | Rebuild shell on PhoneShell + indigo accent |
| Travel / Trading / CRM / ERP | Future | Born on platform kit |

## APPENDIX B — Document map
Vol 1–2 Foundation → Vol 3–5 Structure → Vol 6–8 Language → Vol 9–12 Behavior → Vol 13–15 Experience → Vol 16–18 Engineering & Law. Reference implementations: `docs/HCG_V2_DESIGN_BLUEPRINT.md` (HCGMS repo), `docs/ui-ux/SAATHIOS_*.md` (this repo).

*Dhaago v1.0 — compiled July 24, 2026. Source of truth: `docs/design-spec/` in SaathiAI repo.*
