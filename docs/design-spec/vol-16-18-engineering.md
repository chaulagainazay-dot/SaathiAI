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
