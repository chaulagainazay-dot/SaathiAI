# M48.3 — Recovery Contract

`classify_recovery` / `recover_run` / `recover_all`:

RESUME_SAFE | RETRY_SAFE | CANCEL_REQUIRED | TIMEOUT_REQUIRED |
RECONCILE_REQUIRED | MANUAL_REVIEW_REQUIRED | TERMINAL_NO_ACTION

No automatic success. Unsafe mid-task → MANUAL_REVIEW / BLOCKED.
CLI: `recover <id>`, `recover-all`.
