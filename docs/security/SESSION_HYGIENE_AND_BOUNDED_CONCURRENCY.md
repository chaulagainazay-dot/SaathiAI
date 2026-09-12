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
