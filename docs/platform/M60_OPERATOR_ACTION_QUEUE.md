# M60 — Operator Action Queue

Route: `/platform/actions`. `aggregateOperatorActions()` derives ONLY real,
supported actions from authorized records: pending approvals (decide), blocked
missions (inspect), failed executions (inspect), runtime attention (inspect),
incomplete onboarding (revisit). Categories: Urgent / Needs decision / Needs review
/ Needs configuration / Waiting / Informational, ranked. Each item links to the real
supported next step. No invented acknowledge / resolve / rerun / approve action
(unit-tested).
