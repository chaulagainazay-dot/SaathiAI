# SaathiOS — Session Hygiene & Bounded Concurrency

**Builds on frozen auth SHA `c449c1d2`** (auth architecture unchanged). Scope: bounded active-session concurrency, automatic expiry hygiene, and retiring the split-brain local `:3000` frontend in favour of the canonical `:3100`. No cookie/KDF/authority changes.

## Canonical local frontend = http://localhost:3100
- **Root cause of split-brain:** a stale `next start` production server (PID from Sep 8) launched by `scripts/start_local.sh` via launchd `com.saathi.local`, serving an old build on `:3000` (`next start` does not hot-swap a running build). Same `saathi-os` repo — not a second checkout.
- **Fix:** `package.json` `dev` → `-p 3100`; `start` is now PORT-driven (no hard-coded `-p`) so the Oracle VM keeps `PORT=3000` while the Mac runs one canonical UI on `:3100`. `start_local.sh` exports `PORT=3100` (+ `SAATHI_OS_URL`, `SAATHI_SELF_BASE` → 3100) and gates on `:3100`.
- **KEEP (prod VM, unchanged):** `deploy/oracle/saathi-ui.service` (`PORT=3000`), `deploy/oracle/Caddyfile` (`:3000`), `saathi/server.py` `SAATHI_OS_URL` default (local overridden via env). **UNRELATED (unchanged):** numeric `3000` constants + test-fixture origins.
- **Guard:** `saathi-os/lib/canonical-port.test.js` asserts dev=3100, start is PORT-driven, launcher pins 3100 — prevents regression to 3000.

## Session lifecycle analysis (why 583 accumulated)
583 active, 0 expired, 0 revoked; **all remember-me (30d), all password login, all device/browser metadata `Unknown`** (created by repeated programmatic/curl logins during dev + certification). first_seen span Sep 2–11; **none exceed TTL, every `expires_at` within the 30d rule** → TTL logic is correct. The count is pure unbounded creation (no cap, no live-row pruning), not a TTL defect. Device identity is not reliably available → per-device caps/fingerprinting rejected.

## Bounded concurrency policy
Small **global cap** with **LRU eviction**, sized for a private single-owner install.
- `SAATHI_MAX_ACTIVE_SESSIONS` (default **10**, env-overridable). Covers the owner's real surfaces (dashboard browser, phone, Telegram, Mac voice) with headroom; prevents hundreds.
- On each login (password + passkey): opportunistic prune (expired+revoked), then `enforce_cap` keeps the newest `cap` active sessions by `last_seen` and **soft-revokes the rest — never the just-minted current session** (no owner lockout). Evictions are audited (`session_cap_evict`) and hard-pruned on subsequent logins.
- CLI/API clients authenticate with header tokens (`x-saathi-token` / registry / `SAATHI_TOKEN`) which **do not create sessions**, so they are never conflated with the browser session cap.
- Decisions: single-session REJECT; small global max **IMPLEMENT**; per-device max/replacement REJECT (no device identity); LRU/oldest eviction **ADAPT** (LRU by last_seen); approval-on-cap REJECT (lockout/friction risk).

## Automatic cleanup
**KEEP opportunistic-on-login prune** (expired + revoked). A daemon/scheduler is rejected — overkill for a handful of rows on an 8 GB box; the cap plus login-time prune bound growth. Live valid sessions are never deleted.

## Security invariants (unchanged)
No change to ExecutionGateway, Trading Guardian, deterministic risk, approvals, RBAC, audit, agent authority, broker/provider, external-write containment, paper/live, or **voice auth policy** (`/voice/enroll` gated — verified 401; `command`/`transcribe` still the only exemptions; no new whitelist entries). Auth architecture (exact-once recovery, no replay, 24h/30d TTL) untouched. No raw tokens in diagnostics/logs (fingerprint = `sha256(token)[:12]`).

## Historical 583 collapse — OWNER APPROVAL REQUIRED
Not executed. On the owner's **next real login the cap will keep the newest 10 and revoke 573** (deterministic). Alternatively:
- `POST /api/v1/auth/sessions/revoke-all` → revokes 582, keeps current.
- `POST /api/v1/auth/sessions/revoke-all-including-current` → revokes all 583 (then re-login).
All 583 carry `Unknown` device metadata (programmatic/cert artifacts), so few/no real browser devices should need to sign in again. The owner decides. `OWNER_APPROVAL_REQUIRED_FOR_HISTORICAL_SESSION_COLLAPSE`.

---

## Closure (three bounded issues, 2026-09-12)

### Issue 1 — owner password recovery (no secret exposed)
Password sources: `.env BAADAR_PASSWORD` → `_PASSWORD_HASH` (env-derived) + the security-store owner credential (PBKDF2-600k) checked live by `verify_active_owner_password`. Owner couldn't log in = unknown `.env` value (recoverable but deliberately not read/printed). New local CLI **`scripts/reset_owner_password.py`** (LOCAL OPERATOR ONLY, no network/listener): prompts interactively (getpass) with confirmation + strength check, writes the new credential to BOTH the store (immediate) and `.env` (persistence), revokes all sessions, marks migration, audits (`owner_password_reset`, no secret). PBKDF2 unchanged; no Argon2; no default/backdoor password; no unauthenticated reset endpoint. Verified end-to-end in an isolated temp DB/.env (throwaway password, never printed). **Old env-derived password only leaves memory on backend restart** — the CLI prints the restart step.

### Issue 2 — historical collapse is now truly consent-gated
The cap (10) is the permanent FUTURE policy, but login-time enforcement is gated on a one-time marker (`app_kv.session_cap_migrated`): `enforce_cap_if_migrated()` is a **no-op until the owner explicitly migrates**. So an ordinary login (or inspection, or password-recovery investigation) never silently revokes the historical 583. Explicit collapse happens via `sessions.migrate_sessions()` (or the password reset, which revokes all + sets the marker). After migration every login enforces the cap normally, with no repeated prompt.

### Issue 3 — :3000 can no longer become a local default
`package.json` `start` is now `next start -H 127.0.0.1 -p ${PORT:-3100}` — bare `npm start` binds **3100** (proven: EADDRINUSE on 3100 when launchd holds it), while an explicit `PORT` still overrides (proven: `PORT=3399` bound 3399). Production keeps `:3000` through its **explicit** `deploy/oracle/saathi-ui.service` `Environment=PORT=3000` — a deployment override, not the package default. `dev`=3100, `start_local.sh`=3100, launchd `com.saathi.local`=3100. Guard test updated.

### Real owner reset — OWNER-INTERACTIVE, NOT PERFORMED HERE
The real reset requires the owner to choose their password interactively; an automated session must not set or know it. So it was NOT executed against the real DB — real live sessions remain **583** until the owner runs:
```
python scripts/reset_owner_password.py        # interactive; revokes all 583, sets new password
launchctl kickstart -k gui/$(id -u)/com.saathi.local   # reload backend
```
This reset is the approved historical collapse (explicit, owner-invoked, service/API tokens untouched, auditable, ends within cap). After it: active→0 then 1 on first login; cap governs thereafter.

---

## Certification closure — owner reset executed & independently verified (2026-09-12)

Owner ran `scripts/reset_owner_password.py` (typed RESET), then `launchctl kickstart -k gui/$(id -u)/com.saathi.local`, then logged in at http://localhost:3100. Independently verified from **non-secret** runtime state (no password read/printed, no code changed this run):

- **Real session DB:** active **1**, expired 0, revoked 0 (was 583) — historical collapse complete. The 1 active session was created 09:18 (after the 09:11 reset + 09:13 backend restart), method=password, **Chrome/Mac** (real UA), remember-me 30d, `expires 2026-10-12`. active ≤ cap(10). ✓
- **Migration marker** `app_kv.session_cap_migrated = 1` → post-migration enforcement active; future logins enforce the cap. ✓
- **Password reset (non-secret):** canonical credential exists, KDF prefix `pbkdf2` (value not shown), `_PBKDF2_ITERS` still 600_000 (policy unchanged). `owner_password_reset` audited ok. Service/API creds separate (`api_tokens` table + `SAATHI_TOKEN` env; sessions untouched). Backend restarted (PID new, 09:13). Old 583 sessions no longer live. ✓
- **Topology:** `:8765` backend + `:3100` frontend under `com.saathi.local`; **`:3000` no listener**. `:3100` serves current build (`<title>SaathiOS — Sovereign Orbit</title>`, 200). ✓
- **Authorization proofs:** `/api/v1/control/attention` no-auth → **401**, authenticated → **200**; `/api/v1/voice/providers` no-auth → 401, authenticated → 200; **`/api/v1/voice/enroll` no-auth → 401** (still protected). command/transcribe exemptions unchanged; no new exemptions.
- **Auth-recovery regressions:** concurrent-401 dedup 12/12 (two concurrent 401s → one AUTH_REQUIRED transition + one canonical event), replay/no-replay 12/12, canonical-port guard 3/3, focused session/cap tests 20/20.
- **Security invariants:** `git diff c449c1d2 -- saathi/server.py` shows no authority/middleware/voice-policy change; ExecutionGateway, Trading Guardian, deterministic risk, approvals, RBAC, audit, agent authority, broker/provider, external-write, paper/live untouched. No secret committed (owner `.env`/DB mutations remain local, uncommitted).

**Verdict upgraded → SAATHIOS_SESSION_HYGIENE_AND_BOUNDED_CONCURRENCY_CERTIFIED. Milestone frozen.**
