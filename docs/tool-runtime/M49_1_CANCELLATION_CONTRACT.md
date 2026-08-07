# M49.1 Cancellation Contract

Unified with M48 CancellationToken via cancel_check callback.

Support classes: HARD_CANCEL_SUPPORTED, COOPERATIVE_CANCEL_SUPPORTED, TIMEOUT_ONLY, NOT_CANCELLABLE, UNKNOWN(not registerable).

Checkpoints: before invoke, between stages, before success.
Cancel ≠ success. Timeout ≠ cancel.
Migrated builtins: cooperative + pre-start cancel.
