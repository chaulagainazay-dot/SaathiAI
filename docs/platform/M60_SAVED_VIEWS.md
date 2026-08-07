# M60 — Saved Workspace Views

Route: `/platform/saved-views`. Behavior: **SAVED_VIEWS_LOCAL_ONLY** (no persistence
API). `validateSavedView()` stores only allowed non-sensitive fields (name, route,
filters, sort, group, layout, columns, workspaceId) and rejects/strips any forbidden
field (token, credential, secret, authority, permission, password) — unit-tested.
Presets for high-risk approvals, blocked missions, critical attention, action queue.
