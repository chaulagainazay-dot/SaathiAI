# claude-mem memory-save failure — diagnosis (no changes made)

Symptom: observer health `consecutiveFailures` ≥ 168 since 2026-09-15 15:32 local,
`NOT NULL constraint failed: session_summaries.memory_session_id`.

Findings (read-only inspection of `~/.claude-mem/`):
- `settings.json` only sets `CLAUDE_MEM_RUNTIME=worker`; no provider/key problem involved.
- Schema: `session_summaries.memory_session_id TEXT NOT NULL` → FK `sdk_sessions.memory_session_id`.
- 175 of ~187 logged "Generator failed" errors are `[session-24]`. `sdk_sessions` row 24 is a
  long-lived session (started 2026-07-19, prompt 52+) whose DB row HAS a `memory_session_id`
  (`ca680632-…`), so the NULL comes from the worker's in-memory session object, not the DB.
- The worker daemon (PID from 2026-09-07, uptime 11 days) logs "Worker PID file points to a live
  process, skipping duplicate spawn" on every hook, so the stale in-memory state is never rebuilt.
- Other sessions fail only sporadically (1–2 each).

Proposed fix (bounded, reversible, touches no data): restart the claude-mem worker daemon so
it reloads session state from the DB (stop the `worker-service.cjs --daemon` process; the next
hook respawns it). Do NOT reset or edit `claude-mem.db`. Not executed — awaiting owner approval.
Verify afterwards: `observer-health.json` `consecutiveFailures` returns to 0.
