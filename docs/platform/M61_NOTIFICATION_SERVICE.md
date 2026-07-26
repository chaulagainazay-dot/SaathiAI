# M61 — Notification Service

`notifications` table. Durable records with type/title/summary/severity/actor/
related object/read/archived/dedupe_key. Sources: approvals, executions, attention,
runtime health (derived events synced into durable, deduped records by the
Notification Center for operator+). Read/archive flags persist and are audited.
Informational only — changes no server authority; no browser push. Was:
DERIVED_NOTIFICATION_VIEW → now SERVER_PERSISTED + SERVER_AUDITED.
