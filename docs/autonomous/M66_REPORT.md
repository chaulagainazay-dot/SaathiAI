# M66 — Authenticated IELTSAlert Workflows

- Objective: expose the bounded IELTS domain through the authenticated platform API
  and prove a minimum learner journey.
- Baseline SHA: `97b2ad6092dd6882f2246cd0e5a915198b9d4123`.
- Implementation: authenticated dashboard/health/record/profile/goal/practice/alert/
  payment/evidence/search routes; API validation and safe error mapping; four-skill
  practice records; writing and speaking local feedback; fixture alert evaluation;
  manual payment submission and review service; notification, evidence, and audit
  integration.
- Non-goals: external provider calls, live availability, payment settlement, external
  sends, frontend activation, or production changes.
- Tests: M65+M66 and platform API/module regression slice: 21 passed, 7 pre-existing
  deprecation warnings.
- Evidence: unauthenticated routes return 401; logout revokes access; invalid input
  returns bounded 400; unknown records return safe 404; learner HTTP journey covers
  goal, writing feedback, alert, payment, dashboard, search, and evidence.
- Completion verdict: complete.
- Rollback: revert the M66 commit; M65 schema remains inert and compatible.
- Next decision: proceed automatically to M67 frontend and truthful module activation.

