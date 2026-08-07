# M49.1 Idempotency Contract

Fingerprint: tool_id, version, normalized args, authority, run_id, caller (no secrets).

Classes: NATURALLY_IDEMPOTENT, IDEMPOTENCY_KEY_REQUIRED, NON_IDEMPOTENT.

Same key+fp → replay. Same key different fp → conflict.
Store: process-local IdempotencyStore (not a second ledger).
