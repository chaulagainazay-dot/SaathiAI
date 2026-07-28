# M68 IELTSAlert Browser Certification

Mode: checkout-local production build on `127.0.0.1:3000` with the authenticated
platform API on `127.0.0.1:8765`.

## Learner and reviewer journey

- PASS — authenticated Applications dashboard exposes IELTSAlert as Available while
  HCG POS, Travel, and Finance remain non-actionable placeholders.
- PASS — IELTSAlert opens through backend-driven navigation and its guarded `/ielts`
  route.
- PASS — exam goal creation persists and appears in the preparation dashboard.
- PASS — Writing submission produces a `practice estimate`, an explicit non-official
  disclaimer, evidence, and an in-app feedback-ready notification.
- PASS — the dedicated Writing and Speaking URLs initialize the matching skill;
  Speaking states that pronunciation is not assessed from a transcript.
- PASS — fixture-labelled Kathmandu availability alert creates, evaluates, records a
  non-live match, and emits evidence/notification state.
- PASS — learner manual-payment evidence submission enters `submitted`.
- PASS — an authorized owner reviews a different learner's payment; the result is
  `approved`, audited, and explicitly performs no settlement.
- PASS — an owner's own submitted payment exposes no self-review controls and remains
  awaiting another authorized reviewer.
- PASS — the IELTS evidence timeline and centralized Notification Center show the
  relevant workflow events.
- PASS — Security sign-out clears `saathi_platform_token`; reopening IELTSAlert
  requires sign-in and exposes no prior actionable module state.

## Shell regression

The retained M64 production browser harness was updated to the truthful two-module
state and run with evidence directed to an ephemeral directory:

- 21 hard gates — PASS
- 12 state/context/logout gates — PASS
- 6 responsive gates — PASS
- 3 accessibility gates — PASS
- unexpected console errors — 0
- page errors — 0
- framework overlays — 0

The harness observed six already-classified TopBar approvals CORS messages. This is
the pre-existing M64 global-shell limitation; no IELTS/module request produced an
unexpected console error.

## Responsive and accessibility sweep

- PASS — 390×844 IELTS dashboard and Writing workflow have no horizontal overflow.
- PASS — 820×900 Payments workflow has no horizontal overflow.
- PASS — 1440×900 Applications dashboard has no horizontal overflow.
- PASS — IELTS navigation has an accessible label; forms expose associated labels;
  save/error state is announced through a polite live region.
- Limitation — focused semantic, keyboard, status, label, and overflow checks were
  performed; this is not exhaustive assistive-technology certification.

No screenshots or browser authentication material are committed.
