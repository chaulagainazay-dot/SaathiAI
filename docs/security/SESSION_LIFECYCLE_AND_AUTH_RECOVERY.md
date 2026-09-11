# SaathiOS — Session Lifecycle & Auth Recovery

**Status:** implemented, verified (isolated live server + browser).
**Branch:** `milestone/m312-m319-connectivity-governance`.
**Principle:** fix stale-session *recovery* and bounded *lifecycle* — never weaken authentication. No endpoint was exempted to silence a 401; the only middleware whitelist added is the read-only session-validity probe, which returns `{authenticated:false}` (never token material, never a 401).

---

## Root cause (confirmed, unchanged)
`BAADAR_PASSWORD` is set → localhost free-access is intentionally off → protected requests need a valid session. Browser 401s were caused by a **stale/absent `localStorage["saathi_session"]`** while the UI had no canonical auth state and no central 401 handling, so Chat/Voice looked functional and 401'd repeatedly. This milestone turns recovery into a deterministic product behavior and bounds the session table.

## Canonical frontend auth state (`saathi-os/lib/authState.js`)
`UNKNOWN → CHECKING → AUTHENTICATED | AUTH_REQUIRED | AUTH_ERROR`; `AUTH_REQUIRED → AUTHENTICATING → AUTHENTICATED | AUTH_ERROR`. Single pub/sub store; `AuthGate` (mounted once in `Shell.jsx`) is the only consumer that gates the UI.

- **Startup** (`bootstrapAuth`): no token → `AUTH_REQUIRED`; token → `CHECKING` → `GET /api/v1/auth/session`; valid → `AUTHENTICATED`; invalid/expired/revoked → **clear token** → `AUTH_REQUIRED`.
- A stale token can never leave Chat/Voice looking functional: it is validated on load and cleared.

## Central 401 recovery (`saathi-os/lib/api.js` `afetch`)
On a genuine `401` for a request that **carried** a token and is **not** an auth endpoint: clear `saathi_session`, dispatch `saathi:auth-required` once, return the response. **No retry loop. No auto-replay** of the original request. Auth endpoints (`/auth/login`, `/auth/session*`, `/auth/logout`, `/auth/reset`, `/auth/forgot`, `/auth/passkey`) are excluded so a wrong password never masquerades as a revoked session.

### Request replay policy (`classifyRequest`)
- `SAFE_TO_RETRY` — idempotent `GET`/`HEAD` reads; UI *may* re-fetch after re-login.
- `REQUIRES_USER_REISSUE` — every mutation, and anything whose path matches sensitive fragments (`/approv`, `/execute`, `/trading`, `/trade`, `/authority`, `/voice/enroll`, `/deploy`, `/publish`, `/revoke`, `/rotate`, `/change-password`, `/reset`, `/connectors/execute`, `/missions/`, `/automation/plan`, `/kill`). These are **never** auto-replayed; the operator must deliberately redo them.

## Session lifecycle (backend)
Schema already had `first_seen`/`last_seen`/`expires_at`/`revoked`/`remember_me` — no schema change.

- **TTL:** normal login **24h**; remember-me **30d** (both bounded). Set in `sessions.create` (`saathi/sessions.py`).
- **Why ~582 live:** `session_prune_expired` existed in the store but was **never wired**, and every login mints a new remember-me row. Fix: `SecurityStore.session_prune` (deletes expired **and** revoked, never live) + `sessions.prune()` wrapper, called **opportunistically on every login** so the table stays bounded without a background job. The 582 are all *live* (not dead) so prune does not delete them; they bound-decay via TTL, or the owner can collapse them with revoke-all-others.
- **Revocation:** current (`DELETE /auth/sessions/{sid}`), all-others (`POST /auth/sessions/revoke-all`), and **owner emergency** all-including-current (`POST /auth/sessions/revoke-all-including-current`, clears the caller cookie).

## Observability (`GET /api/v1/auth/sessions/diagnostics`, owner-only)
Returns `counts` (active / expired / revoked / total / oldest_active_age_seconds), `current` session metadata, and `last_prune`. **No raw tokens.** Session `id` is `sha256(token)[:12]` — a bounded, irreversible fingerprint. `POST /api/v1/auth/sessions/prune` triggers a manual prune and returns counts.

## New/changed endpoints
| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/auth/session` | whitelisted | validity probe; `{authenticated, session|null}`, never 401/token |
| GET | `/api/v1/auth/sessions/diagnostics` | authed | counts + current + last_prune (no secrets) |
| POST | `/api/v1/auth/sessions/prune` | authed | prune expired+revoked |
| POST | `/api/v1/auth/sessions/revoke-all-including-current` | authed | owner emergency revoke-all |

## Voice security (unchanged, verified)
`/voice/enroll` and the `voice_os` stateful router stay authenticated (`enroll` no-auth → 401 verified). `command`/`transcribe` remain the only ephemeral exemptions. Stale-session recovery covers Voice: `enrollVoice()` + `VoiceControl.jsx` use `afetch`, so a 401 there routes through the same central recovery. Biometric/authority voice actions are `REQUIRES_USER_REISSUE` — never silently replayed after re-auth.

## Security invariants (unchanged)
No change to ExecutionGateway/Trading Guardian authority, deterministic risk checks, approval requirements, RBAC, audit, external-write containment, broker/provider boundaries, or paper/live state. No auth bypass introduced. localStorage token storage is pre-existing (documented cross-origin fallback; httpOnly cookie also set) — not expanded by this milestone; see follow-ups.
