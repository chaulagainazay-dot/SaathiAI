# M61 — Optimistic Concurrency

Every mutable resource (plans, saved views, templates, drafts, attention states)
carries an integer `version`. Update endpoints accept `expected_version`; on
mismatch the store returns a `conflict` and the service raises `STALE_STATE` → HTTP
409. Nothing is silently overwritten. The client adapter (`lib/workflow-api.js`)
exposes `isConflict()`; UI pages show a `conflict` reconciliation state and reload
authoritative server state. Certified: a stale plan write returns 409.
