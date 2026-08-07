# M59 — Approval Authority Center (Workstream 3)

Routes: `/platform/approvals` (list) · `/platform/approvals/[approvalId]` (detail).

## Server-owned authority

Decisions route through the existing server-authorized APIs:

- `POST /api/v1/platform/approvals/{id}/decide` — body `{ approve: bool, reason: string }`
- `POST /api/v1/platform/approvals/{id}/revoke`

The browser holds **no** authority. After any decision the detail route refetches
from the server (`GET /approvals?status=`) and renders the authoritative record.
Decidability is re-derived from server state via `isApprovalDecidable()` — it is
**never** optimistically flipped. Stale / expired / consumed / insufficient-authority
responses are surfaced verbatim (secrets stripped) and trigger a resync.

## Lifecycle truth

`ApprovalStatus`: pending · approved · rejected · expired · revoked · consumed.
`approvalLifecycle()` honours the server status but also surfaces derived terminal
facts the raw status may not encode: `consumed` when `consumed_at > 0`, `expired`
when a pending record's `expires_at < now`. Risk is classified from
`side_effect_class` / `authority` keywords (high / medium / low / unknown).

## List

Summary tiles (pending, high-risk, consumed, rejected, expired). Fetches **all**
lifecycle states (`status=`) and filters client-side by lifecycle and risk; search
by tool/id/action. Cards show tool, risk, lifecycle chip, single-use consumed
state, action, authority, expiry.

## Detail

Request summary · authority & scope (org/workspace/project/mission/run) · lifecycle
& consumption · operator decision. The decision panel shows exact scope and expiry,
requires a `window.confirm` restating tool/authority/scope/expiry, disables during
in-flight requests (prevents duplicate action), and only appears when the record is
genuinely decidable. Consequential actions use restrained styling — no celebration
animation.
