# Auth Hardening M5.2 — Coordination Spec

## User Goal
Make SaathiAI authentication production-grade. Do NOT add new features (OAuth providers, 2FA). Fix critical issues, harden existing code, improve UX.

## Non-Goals
- Do NOT implement OAuth provider token exchange
- Do NOT implement 2FA/TOTP
- Do NOT add multi-user support (remains single-owner)

## Stack
- Backend: FastAPI, Python 3.12, stdlib + webauthn
- Frontend: Next.js (App Router), React, no external CSS framework
- Tests: pytest, FastAPI TestClient
- Storage: JSON files in ~/.saathi/ (sessions.json, passkeys.json, reset_tokens.json, auth_audit.log)

## Shared API Contract

### 1. Login Request Body
```python
class LoginIn(BaseModel):
    password: str
    remember_me: bool = True   # NEW
```

### 2. Session Store Fields (sessions.py)
Each session row must include:
- `id` (public handle, first 12 chars of token hash)
- `th` (full token hash)
- `created`, `last_seen`
- `browser`, `os`, `ua`, `ip`
- `kind` ("password" | "passkey" | "rotate")
- `label`
- `remember_me: bool`  # NEW
- `expires: float`     # NEW — epoch timestamp
- `revoked: bool`      # NEW — default False

### 3. Session Lifetime
- `remember_me=True`: expires = now + 30 days
- `remember_me=False`: expires = now + 24 hours
- Cookie max_age matches session expiry
- Server-side `validate()` checks `expires` and `revoked`

### 4. Password Hashing (CRITICAL — ONLY PBKDF2)
- `authsec.hash_password(pw)` → PBKDF2-SHA256, 600k iterations
- `authsec.verify_password(pw, stored)` → verifies PBKDF2 or legacy bare SHA256
- `authsec.needs_upgrade(stored)` → True if legacy SHA256
- ALL password storage must call `authsec.hash_password()`:
  - login initialization from env
  - change-password endpoint
  - reset-password endpoint
- The `.env` file stores PBKDF2 hashes, NOT bare SHA256
- Backward compat: `verify_password()` still accepts legacy SHA256 for existing logins

### 5. Rate Limits
- `/auth/login`: 5 per 60s per IP
- `/auth/forgot`: 3 per 900s per IP
- `/auth/reset`: 5 per 300s per IP
- `/auth/change-password`: 3 per 600s per IP
- `/auth/passkey/login/options`: 10 per 60s per IP  # NEW
- `/auth/passkey/login/verify`: 10 per 60s per IP    # NEW

### 6. CORS Origins (from env var)
```python
# Development (default when env not set):
allow_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8765"]
# Production (from SAATHI_CORS_ORIGINS env var, comma-separated):
allow_origins = os.getenv("SAATHI_CORS_ORIGINS", "").split(",")
```
NO wildcard. NO `allow_origin_regex=".*"`.

### 7. Security Headers (all documented with comments)
- `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
- `Content-Security-Policy` (keep existing, document each directive)
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `Cross-Origin-Opener-Policy: same-origin`
- `Cross-Origin-Embedder-Policy: require-corp`
- `Cross-Origin-Resource-Policy: same-origin`

### 8. Reset Token Storage
- Tokens stored as SHA256 hashes (not plaintext)
- Same 15-min TTL, single-use, hashed comparison

### 9. Passkey Metadata
- `created`: timestamp
- `last_used`: timestamp (updated on each successful auth)
- `device_name`: from UA parsing
- `browser`: from UA parsing

### 10. Frontend Login API Contract
```javascript
// api.js — login must pass remember_me
export async function login(password, rememberMe = true) {
  const r = await afetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password, remember_me: rememberMe }),
  });
  // ...
}
```

### 11. Audit Events (all must be logged)
- login_success, login_failure
- logout, logout_everywhere
- password_changed
- password_reset_requested, password_reset_success, password_reset_failed
- passkey_registered, passkey_login_success, passkey_login_failed, passkey_deleted
- session_revoked, session_revoked_all, session_rotated
- rate_limited (include endpoint name)
- oauth_linked, oauth_removed (when implemented)

## Worker Assignments

### Agent: backend-core
- **Worktree**: `/Users/macbookpro/.worktrees/backend-core`
- **Branch**: `agent/backend-core`
- **Files**: `saathi/server.py` (auth section ~L1546-2142), `saathi/sessions.py`, `saathi/authsec.py`, `saathi/passkey.py`, `saathi/mailer.py`
- **Tasks**:
  1. Fix password hashing to use PBKDF2 everywhere
  2. Add remember_me to LoginIn, sessions, login endpoint
  3. Improve session architecture (expires, revoked fields)
  4. Add rate limiting to passkey login endpoints
  5. Fix CORS to use origin whitelist
  6. Add/document all security headers
  7. Harden forgot password (hash tokens, better template)
  8. Add passkey metadata (created, last_used, device, browser)
  9. Ensure all audit events are logged
  10. Add `LinkedIn` to OAuth provider registry

### Agent: frontend-auth
- **Worktree**: `/Users/macbookpro/.worktrees/frontend-auth`
- **Branch**: `agent/frontend-auth`
- **Files**: `saathi-os/app/unlock/page.jsx`, `saathi-os/app/security/page.jsx`, `saathi-os/lib/api.js`, `saathi-os/lib/passkey.js`
- **Tasks**:
  1. Pass remember_me in login request body
  2. Remove orphaned localStorage flag for short sessions
  3. Improve passkey UX (detect platform authenticator, show unsupported message)
  4. Add caps lock detection, show password toggle, offline indicator
  5. Hide 2FA/recovery email placeholders in security page
  6. Add keyboard navigation, ARIA labels
  7. Improve responsive design (safe areas)
  8. Add loading states

## Validation
- Backend: `cd /Users/macbookpro/.worktrees/backend-core && python -m pytest tests/ -x -q` (if tests exist) or `python -c "from saathi import authsec; print(authsec.hash_password('test'))"`
- Frontend: Ensure JSX compiles (no syntax errors)

## Merge Order
1. Merge `agent/backend-core` into `milestone/m5.2-auth-hardening`
2. Merge `agent/frontend-auth` into `milestone/m5.2-auth-hardening`
3. Run integration tests
4. Write tests + docs
