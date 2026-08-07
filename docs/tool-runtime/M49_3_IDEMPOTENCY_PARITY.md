# M49.3 Idempotency Parity

Durable SQLite idempotency from M49.2 is preserved.

- Mutation connector tools require idempotency keys
- Fingerprint includes tool_id/version/arguments/authority/run_id/caller
- Same key + different payload → conflict
- Replay returns prior result
- Dry-run results are durable-keyed (no live mutation)
- Multi-host idempotency remains deferred (accepted limitation)
