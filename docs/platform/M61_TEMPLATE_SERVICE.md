# M61 — Workflow Template Service

`workflow_templates` table (versioned, workspace-scoped). CRUD via
`/workflow/templates`. Starter catalog can be published to the server. Templates
grant no authority, hold no secrets, do not execute, and do not bypass approvals.
Was: LOCAL_TEMPLATE → now SERVER_PERSISTED.
