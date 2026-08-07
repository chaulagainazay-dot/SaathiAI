# M61 — Mission Plan Persistence

`workflow_plans` + `workflow_plan_revisions`. States: draft / published / archived.
Autosave/explicit save via `PUT /workflow/plans` (upsert, version bump, revision
appended). Publish is explicit (`POST /workflow/plans/publish`) — never automatic.
Optimistic concurrency: pass `expected_version`; mismatch → 409 STALE_STATE. The
M60 plan page now loads the persisted plan and offers Save / Publish with server
reconciliation. Was: MISSION_PLAN_DRAFT_ONLY → now SERVER_PERSISTED.
