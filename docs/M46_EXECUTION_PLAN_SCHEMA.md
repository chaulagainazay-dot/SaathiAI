# M46 — Execution Plan Schema

`ExecutionPlan` is deterministic and tamper-evident (`plan_integrity_fingerprint`).

Fields include: execution_id, approval/m44/m45/m43 fingerprints, provider,
expected identity, endpoint, exact read-only action, call/time budgets,
rollout_percentage ≤1, error_budget=0, cleanup + external-revocation
requirements, rollback triggers, and no-write/deploy/production/TG assertions.

Created via `create_plan` / `m46-create-plan`.
