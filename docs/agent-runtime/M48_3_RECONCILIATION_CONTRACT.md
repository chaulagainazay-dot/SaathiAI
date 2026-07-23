# M48.3 — Reconciliation Contract

`classify_stale` + `reconcile` / `reconcile_all`.

Stale classes: ACTIVE_HEALTHY, STALE_*, TERMINAL.
Actions: NO_ACTION, MARK_TIMEOUT, MARK_CANCELLED, BLOCK_FOR_REVIEW, RELEASE_STALE_LEASE.
CLI: `reconcile-all`.
