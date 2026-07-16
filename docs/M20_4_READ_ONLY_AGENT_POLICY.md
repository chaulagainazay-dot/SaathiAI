# M20.4 — Read-Only Agent Policy

## Allowed

List/read repository files within root; Git metadata; diffs; discover tests; architecture inspection; proposed change plan; validation recommendations; handoff report.

## Forbidden (code-enforced)

File create/modify/delete/rename; chmod; stage/commit/push/merge/rebase/reset/checkout; apply patch; package install; deploy; DB/secret mutation; trading.

Enforcement:

1. Prompt mode prefix (instructional)
2. `forbid_readonly_operation()` denylist
3. Pre/post/during integrity snapshots → **quarantine** on mutation (no auto-rollback)
4. Writes/commits/pushes env flags remain default-off
5. Real Claude adapter requires bound approval; dry_run if `claude` binary absent

## Claude Code profile

Fixed argv, sanitized env (no inherited secrets), loopback cwd, timeout, output tail bounds, process-group stop. No user-supplied arbitrary flags.
