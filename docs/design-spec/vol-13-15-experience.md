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
