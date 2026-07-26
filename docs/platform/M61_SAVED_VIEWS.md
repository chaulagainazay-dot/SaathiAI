# M61 — Saved Workspace Views

`saved_views` table (versioned, user+workspace scoped). CRUD via
`/workflow/saved-views`. Persists route + config (filters/sort/grouping) only;
`_reject_secrets` fails closed on any token/credential/secret/authority/permission
key (400). Was: LOCAL_ONLY → now SERVER_PERSISTED. The M60 saved-views page now
round-trips to the server; survives a fresh browser with no localStorage.
