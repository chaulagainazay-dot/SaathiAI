# M61 — Draft Persistence

`workflow_drafts` table — one per (user, workspace, kind: onboarding|mission|plan|
approval), expiring (default 7 days), versioned. `PUT/GET/DELETE /workflow/drafts`.
`_reject_secrets` guards persisted bodies. Drafts never become live automatically.
Was: local-only → now SERVER_PERSISTED (API + tests; UI adoption incremental).
