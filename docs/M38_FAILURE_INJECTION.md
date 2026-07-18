# M38 — Failure Injection

Offline injections: before_handle, before_sender, during_sender, after_response,
cleanup_exception, lease_revoke_failure, timeout, 429, provider 500.

Each proves: handle closed, no leak, deterministic terminal/cleaned state,
authority unchanged.
