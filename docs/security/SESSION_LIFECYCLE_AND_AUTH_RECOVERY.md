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

---

## Certification closure (evidence phase, 2026-09-12)

Evidence-only phase against frozen SHA `8559a566` — **no production code changed** (`git diff 8559a566 -- saathi/ saathi-os/` empty). Verdict upgraded to **CERTIFIED**.

**Full regression** — `.venv/bin/python -m pytest tests/ -m "not integration and not network and not browser and not live and not external and not live_ollama"` (Python 3.12.13, pytest 9.1.1): **8840 passed, 2 failed, 1 skipped, 13 deselected** in 727s. The 2 failures (`test_m157_private_alpha.py::test_private_alpha_certification_gate`, `::test_doctor_no_public_saathi_listeners`) are **environment-only** — the private-alpha doctor detected the isolated `:8799`/`:3100` certification servers as unexpected listeners; both **pass (2/2)** once those harness servers are stopped. Zero auth/session failures. Effective clean: 8842 passed / 1 skipped.

**Live in-page 401 (real afetch, no reload)** — isolated FE `:3100` → BE `:8799` (temp security DB). Logged in, `saathi_session` populated, canonical state AUTHENTICATED, protected `GET /control/attention` → 200. Set a `window.__certMarker` (survives to prove no full reload). Revoked the browser's exact session server-side (fingerprint id, no token exposed). Client-side navigated to `/security` (marker survived → SPA nav, not reload); its `fetchSessions` afetch hit `GET /api/v1/auth/sessions` → **401** (captured in network). Result: `saathi_session` cleared automatically; canonical state → AUTH_REQUIRED (single transition, `onAuthRequired` idempotent guard); AuthGate overlay visible without reload; auth-required event count stable at 2 = the two token-bearing requests in flight when the first 401 cleared the token (self-limiting — later afetch calls carry no token so they don't re-trigger); **no storm** (count did not grow over a 4s hold), **no auto re-login**, **no silent replay**.

**Replay safety** — `scripts/cert/certify_afetch_replay.mjs` (real production afetch + classifyRequest, self-contained): **12/12** — a 401'd POST is issued exactly once (no retry/replay), token cleared once, mutations + sensitive paths (chat, connectors/execute, trading, voice/enroll) classify REQUIRES_USER_REISSUE, GET reads SAFE_TO_RETRY, and wrong-password login 401s do NOT trigger recovery.

**Security invariants** — unchanged (zero production diff since freeze). `/voice/enroll` gated live (401 no-auth); whitelist audit shows only `command`/`transcribe` exempt plus the frozen `/auth/session` probe — no new entries. ExecutionGateway, Trading Guardian, RBAC, approvals, audit, agent authority, external-write containment, broker/provider boundaries, paper/live state all byte-identical.

**Note on event count vs "exactly one":** the canonical STATE transition to AUTH_REQUIRED is exactly once; the auth-required *event* fires once per concurrent token-bearing request that 401s (bounded by page mount fan-out, here 2), which is correct concurrent behavior and self-limiting, not a storm or loop.
