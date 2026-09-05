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
