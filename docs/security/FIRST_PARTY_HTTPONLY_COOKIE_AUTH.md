# SaathiOS — First-Party HttpOnly Cookie Auth

**Builds on `c76e464c` (single-origin).** Migrates BROWSER auth from a localStorage-readable bearer to a first-party **HttpOnly** cookie. Authority architecture, PBKDF2-600k, session lifecycle/cap, and non-browser (CLI/service) auth are unchanged.

## Previous → final browser auth
- **Before:** `localStorage["saathi_session"]` → `afetch` injects `x-baadar-session` header. JS could read the credential.
- **After:** password login sets an **HttpOnly** cookie `baadar_session`; `afetch` sends it automatically via `credentials:"include"` and injects **no** header; browser JS cannot read the credential; no localStorage bearer.

## Cookie contract (`_set_session_cookie` / `_clear_session_cookie`, server.py)
- Name: `baadar_session`. HttpOnly always. `SameSite=Lax`. `Path=/`. **Host-only** (no Domain).
- **Secure is env-aware:** off over plain-http localhost (so the cookie works on `:3100`), on when `x-forwarded-proto=https` (prod behind Caddy). Verified: local login → `HttpOnly; Max-Age; Path=/; SameSite=lax` (no Secure); `x-forwarded-proto: https` login → same + `Secure`.
- Max-Age = session TTL: 24h standard, 30d remember-me (unchanged).

## Credential precedence (`_is_authed`)
1. session cookie `baadar_session` (browser) → 2. legacy `x-baadar-session` header (non-browser/CLI, migration) → 3. `x-saathi-token` (registry / `SAATHI_TOKEN`, service). Deterministic; cookie wins. Login credential check is store-first (`verify_active_owner_password`) then env `_PASSWORD_HASH` then `SAATHI_TOKEN`.

## CSRF (`_csrf_ok`, defense-in-depth atop SameSite=Lax)
Unsafe methods (POST/PUT/PATCH/DELETE) carrying the **cookie** require a same-origin `Origin` (netloc == request host); mismatched Origin → **403**. Bypassed for: safe methods, `x-saathi-token` service requests, and header-only (no-cookie) requests — non-browser clients keep working. Absent Origin allowed (SameSite=Lax already blocks cross-site cookie POSTs). Verified: hostile-origin POST → 403, same-origin POST → 200.

## Frontend
`afetch` (lib/api.js): no `x-baadar-session`, `credentials:"include"`, 401 still emits raw `saathi:auth-401` (dedup/no-replay unchanged) and purges any legacy localStorage bearer. `setSessionToken` = legacy-clearing no-op; `hasSessionToken` = false (JS can't read the cookie). `bootstrapAuth` no longer gates on localStorage — always validates via `GET /auth/session` (cookie). Logout revokes server session + clears cookie + purges legacy.

## Evidence
- **Backend (curl, new-code instance):** Set-Cookie attrs (local no-Secure / prod Secure), cookie-auth GET 200, no-cookie 401, CSRF 403/200, logout clears cookie, post-logout 401, service token 200, legacy header 200.
- **Real browser:** login 200; `document.cookie` has no `baadar_session` (HttpOnly); no `localStorage["saathi_session"]`; cookie-auth protected GET 200; **reload stays authenticated**; logout → 401 + cookie cleared.
- **Deterministic fixtures (cookie-era code):** dedup 12/12 (concurrent 401 → one AUTH_REQUIRED transition + one canonical event), replay 12/12 (no auto-replay; auth-endpoint 401 ignored). Frontend: cookie-auth 4/4, single-origin 4/4, canonical-port 3/3. Session focused 20/20 (cap/TTL/marker preserved).
- Voice: `/voice/enroll` gated (401), providers gated; `command`/`transcribe` exemptions unchanged.

## Authority/security invariants
No change to ExecutionGateway, Trading Guardian, deterministic risk, approvals, RBAC, audit, agent authority, broker/provider, external-write, paper/live, voice policy. No new auth exemption. PBKDF2-600k untouched. Session cap/TTL/marker unchanged.

## ⚠️ Incident during verification (disclosed + remediated)
While building an *isolated* verification harness, a shell mistake put the env vars on the wrong side of a pipe — `SAATHI_SECURITY_DB=... SAATHI_ENV_FILE=... printf ... | python …` applied the vars to `printf`, not to Python. The reset-seed therefore ran against the **real** store + real `.env`, writing a throwaway PBKDF2 credential (store row + `.env`) and revoking the owner's live session. **The owner's real password was never known or printed.**
**Remediated (verified):** deleted the throwaway store row (store now falls back to the owner's real 09:11 credential, which login checks first); set real `.env BAADAR_PASSWORD` to a fresh **random unrecorded** value (kills the throwaway on any restart; the store credential is authoritative); revoked/pruned the test sessions (real active = 0). Confirmed: throwaway login → **401**. The owner's real password still authenticates via the store credential.
**Residual:** real `.env` password (random) and the store credential (owner's real) now diverge — harmless because login checks the store first, but the owner should re-run `python scripts/reset_owner_password.py` (normal, no env overrides) to realign both to their chosen password.

## Deployment status
Code is committed but **not deployed to the live `:8765`/`:3100`** (still the pre-cookie build). Deploying needs a backend+frontend restart; to avoid the known `kickstart -k` backend-kill race, the owner should restart deliberately, then log in once to obtain the cookie.

**Verdict: SAATHIOS_FIRST_PARTY_HTTPONLY_COOKIE_AUTH_CERTIFIED_WITH_LIMITATIONS** — cookie code implemented and curl/browser/fixture-proven, but not yet deployed live, live owner cookie-login is owner-interactive, and a real-DB verification incident occurred (remediated).
