# M60 — First-Run Onboarding

Route: `/platform/onboarding`. Behavior: DERIVED read of real state + LOCAL-only progress.

Nine steps (`ONBOARDING_STEPS`): Welcome → Safety boundaries → Workspace → Project →
Available agents → Approval model → Execution model → Notification preferences → Ready.

- **Reads real state** via `onboardingFacts()`: platform health, production
  authorization, connector mode, financial/trading state, org/workspace/role,
  project + binding counts, gateway. Never fabricated.
- **Safety steps gate**: `safety`, `approvals`, `execution` are safety steps and
  must be explicitly acknowledged; `onboardingProgress()` reports
  `safetyAcknowledged` only when all are complete. Educational steps can be skipped.
- **Progress** stored local-only (`saathi_m60_onboarding_progress`). Resume,
  restart, and skip (non-safety) are supported. No authority is stored in the browser.
- No unsupported backend mutation: org/workspace/project creation is delegated to
  bootstrap / mission creation, with links rather than invented mutations.
