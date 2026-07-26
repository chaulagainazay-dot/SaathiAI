# M60 — Notification Center

Route: `/platform/notifications`. Behavior: **DERIVED_NOTIFICATION_VIEW** — no
notification persistence API exists, so notifications are derived from authorized
platform events via `deriveNotifications()` (approval requested/consumed, execution
failed/completed, attention raised, runtime unhealthy), newest first.

Informational only — changes no server authority; no durable delivery implied
(labelled in-UI). Preferences (density, mute-informational) and read state are
local-only. Browser notification permission is never auto-requested.
