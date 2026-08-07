# M51 Auth Abuse Controls

SQLite `rate_limits` table, single-host.

Surfaces: login, session_create, invite_accept, recovery, approval_action.

Fail-closed temporary lockout; owner can clear via rate-limit clear (service).
