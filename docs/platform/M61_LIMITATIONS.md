# M61 — Residual Limitations

## Delivered (M60 placeholder → M61 state)
| Capability | M60 | M61 |
|---|---|---|
| Mission plan | DRAFT_ONLY | SERVER_PERSISTED (versioned, revisions, publish) |
| Notifications | DERIVED | SERVER_PERSISTED + SERVER_AUDITED |
| Saved views | LOCAL_ONLY | SERVER_PERSISTED (versioned) |
| Templates | LOCAL_ONLY | SERVER_PERSISTED |
| Attention ack/resolve | BLOCKED | SERVER_AUTHORIZED + SERVER_AUDITED |
| Search | loaded-records | SERVER_AUTHORIZED |
| Drafts | local | SERVER_PERSISTED (API + tests) |
| Concurrency | none | OPTIMISTIC (version / 409) |

## Bounded limitations
- **Single-host SQLite.** Persistence is single-host (consistent with M52–M56); no
  distributed store, streaming, or multi-node coordination (that is M62).
- **UI adoption is incremental.** Saved views, notifications, search, attention
  triage, and plan persistence are wired to the server; mission/onboarding draft
  persistence exists as tested APIs but the M60 pages still autosave locally (server
  draft adoption deferred — no user-visible redesign required).
- **Notification synthesis** is client-triggered (operator+ syncs derived events into
  durable records); there is no server-side background event producer yet.
- **Search** covers missions/projects/approvals/templates/notifications; execution
  and evidence full-text search deferred.
- Production remains unauthorized; multi-host disabled; connectors dry-run; financial
  and trading execution disabled; approvals and execution authority unchanged.
