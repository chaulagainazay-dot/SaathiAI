# M61 — API Contracts

All under `/api/v1/platform/workflow/*`. Auth via `X-Platform-Token`. Permission-
gated, audited, tenant-scoped. Errors: 401 (auth), 403 (permission), 404 (not
found), 409 (STALE_STATE optimistic-concurrency conflict), 400 (validation/unsafe).

## Plans
- `GET /workflow/plans/{mission_id}` → `{plan|null}` — WORKFLOW_READ
- `PUT /workflow/plans` `{mission_id, body, state?, expected_version?}` → `{plan}` — WORKFLOW_WRITE; upsert; version bump; revision recorded
- `POST /workflow/plans/publish` `{mission_id, expected_version}` → `{plan}` (never auto-published)
- `GET /workflow/plans/{mission_id}/revisions` → `{revisions}`

## Notifications
- `GET /workflow/notifications?include_archived=` → `{notifications}` — NOTIFICATION_READ
- `POST /workflow/notifications` `{type,title,summary?,severity?,related_object?,related_type?,evidence?,dedupe_key?}` → `{notification}` — NOTIFICATION_WRITE; deduped
- `PATCH /workflow/notifications/{id}` `{read?,archived?}` → `{notification}`

## Saved views
- `GET/POST /workflow/saved-views`; `PATCH/DELETE /workflow/saved-views/{id}` — WORKFLOW_READ/WRITE; versioned; forbidden fields rejected (400)

## Templates
- `GET/POST /workflow/templates`; `PATCH /workflow/templates/{id}` — versioned

## Drafts
- `GET /workflow/drafts/{kind}`; `PUT /workflow/drafts` `{kind,body}`; `DELETE /workflow/drafts/{kind}` — expiring, one per (user,workspace,kind)

## Attention mutations
- `GET /workflow/attention/{execution_id}/state` → `{attention}`
- `POST /workflow/attention/{execution_id}/action` `{action: acknowledge|resolve|reopen, note?, expected_version?}` — ATTENTION_WRITE; audited

## Server search
- `GET /workflow/search?q=&type=&limit=` → `{scope:"SERVER_AUTHORIZED", results, count}` — tenant-scoped
