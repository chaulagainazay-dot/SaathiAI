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
