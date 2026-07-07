# SaathiOS Authentication v1.0 — Audit Report

**Date:** 2026-07-04
**Auditor:** Kimi Work (continuing from Claude)
**Branch:** `milestone/m5-investment-intelligence` (uncommitted: `authsec.py`, `mailer.py`, `sessions.py`)
**Commit:** `2bca433` — feat(auth): cookie-independent cross-device auth

---

## 1. Executive Summary

The authentication system has **solid foundations** but a **critical integration gap**: `sessions.py` (the new random-token session store with device metadata) was built but **never wired into the actual auth flow**. The server still relies on the old deterministic `_session_token()` hash, which means:

- ❌ **No real session management** — device lists, per-session revocation, logout-everywhere are impossible with the deterministic token
- ❌ **Session store is orphaned** — `sessions.py` functions exist but are never called by `server.py`
- ❌ **Passkey login issues the wrong token** — it mints the deterministic hash, not a random session
- ❌ **Password change doesn't invalidate existing sessions** — old sessions remain valid
- ❌ **No session rotation on sensitive actions** — stolen tokens stay valid forever

**Fix priority: CRITICAL** — wire `sessions.py` into `_is_authed()` before adding any new features.

---

## 2. Current Implementation — What's Real

### Backend (Python)

| Module | Status | Notes |
|--------|--------|-------|
| `authsec.py` | ✅ Built | PBKDF2 password hashing, rate limiting, audit log, password strength |
| `mailer.py` | ✅ Built | SMTP-pluggable, inert until configured, outbox.log fallback |
| `sessions.py` | ⚠️ **Orphaned** | Random tokens, device metadata, listing, revoke, rotate — **not wired** |
| `passkey.py` | ✅ Built | WebAuthn registration + login, per-host credentials |
| `auth_logto.py` | ✅ Built | JWT verification, RBAC, org tokens — additive, inert until env set |
| `server.py` auth endpoints | ⚠️ Partial | Login, change-password, logout, passkey status/register/login — **uses old deterministic token** |

### Frontend (Next.js)

| Component | Status | Notes |
|-----------|--------|-------|
| `unlock/page.jsx` | ✅ Built | Responsive, password manager support, safe-area, passkey UI, friendly errors |
| `me/page.jsx` | ⚠️ Minimal | Just a mobile dashboard — no security settings, no session management |
| `lib/api.js` | ✅ Built | `afetch()` with `x-baadar-session` header, `setSessionToken()`, `clearSessionToken()` |
| `lib/passkey.js` | ✅ Built | WebAuthn client, base64url helpers, register/unlock |

### Tests

| Test File | Status | Coverage |
|-----------|--------|----------|
| `test_auth_logto.py` | ✅ 8 tests pass | JWT header parsing, valid/expired/wrong issuer/wrong audience/tampered signature, RBAC scopes, org claim |
| `test_auth_hardening.py` | ✅ 4 tests pass | Loopback detection, proxied loopback rejection, `_is_authed` without password |
| `test_sessions.py` | ❌ **Missing** | No tests for the orphaned session store |
| `test_passkey.py` | ❌ **Missing** | No tests for WebAuthn module |
| `test_password_reset.py` | ❌ **Missing** | No tests for forgot-password flow |

---

## 3. Critical Gap — The Orphaned Session Store

### The Problem

`sessions.py` implements a proper random-token session store:
- `create()` → mints `secrets.token_urlsafe(32)`, stores SHA256 hash + device metadata
- `validate()` → checks hash against store, prunes expired, refreshes `last_seen`
- `listing()` → returns device list (browser, OS, IP, last seen) — **never leaks token**
- `revoke()` → removes one session by public ID
- `revoke_all()` → logout everywhere
- `rotate()` → invalidate old + mint new (same device)
- `rename()` → label a session (e.g., "Work Mac")

But `server.py` still uses:
```python
def _session_token() -> str:
    seed = _PASSWORD_HASH or ACCESS_TOKEN or ""
    return _hashlib.sha256((seed + ":baadar-session").encode()).hexdigest()
```

This is **deterministic** — every device gets the same token. It never expires, never rotates, and there's no way to invalidate one device without invalidating all.

### The Impact

| Feature | Expected | Actual | Because |
|---------|----------|--------|---------|
| Logout this device | Cookie deleted | Cookie deleted | Works by accident |
| Logout everywhere | All sessions invalidated | Only this cookie deleted | No server-side revocation |
| Per-device session list | 3 devices shown | Not possible | Deterministic token = 1 token |
| Revoke stolen device | 1 device gone | All devices gone | Same token everywhere |
| Session rotation | New token after password change | Same token | Deterministic from password |
| Session expiration | 30-day idle timeout | Never expires | No timestamp tracking |
| Audit "which device" | Browser/OS/IP logged | "unknown" | No metadata attached to token |

---

## 4. Phase-by-Phase Gap Analysis

### Phase 1 — Forgot Password ❌ NOT IMPLEMENTED

| Requirement | Status | Notes |
|-------------|--------|-------|
| Forgot password endpoint | ❌ Missing | No `/api/v1/auth/forgot` or `/api/v1/auth/reset` |
| Email verification | ❌ Missing | `mailer.py` exists but no forgot-password flow calls it |
| One-time secure reset token | ❌ Missing | No token generation/validation for password reset |
| Reset password page | ❌ Missing | No frontend route `/reset-password` |
| Token expiration | ❌ Missing | No reset token TTL |
| Invalid/expired token handling | ❌ Missing | No endpoint to handle these |
| Rate limiting | ⚠️ Partial | `authsec.rate_check` exists but not used for password reset |
| Audit logging | ⚠️ Partial | `authsec.audit` exists but not called for password reset events |

**Blocker:** Email not configured. **Mitigation:** Build architecture now with `mailer.py` outbox fallback; SMTP enables later with zero code changes.

### Phase 2 — Face ID / Touch ID / Fingerprint ⚠️ PARTIAL

| Requirement | Status | Notes |
|-------------|--------|-------|
| Face ID | ⚠️ Partial | `passkey.py` uses `webauthn` library, but registration fails on some devices due to missing `rp_id` handling and no user-facing setup instructions |
| Touch ID | ⚠️ Partial | Same as above |
| Windows Hello | ⚠️ Partial | Should work via WebAuthn but untested |
| Android Fingerprint | ⚠️ Partial | Should work via WebAuthn but untested |
| Security Keys | ⚠️ Partial | `authenticator_selection` doesn't explicitly allow security keys; `resident_key=preferred` may exclude roaming authenticators |
| Platform Authenticators | ✅ Supported | `resident_key=preferred, user_verification=preferred` targets platform authenticators |
| Register credential | ✅ Built | `/api/v1/auth/passkey/register/options` + `/verify` |
| Manage credentials | ❌ Missing | No list/rename/delete passkey endpoints |
| Rename credential | ❌ Missing | Not implemented |
| Delete credential | ❌ Missing | Not implemented |
| Multiple devices | ⚠️ Partial | Can register multiple, but no UI to manage them |
| Multiple passkeys | ⚠️ Partial | Same — no management UI |
| Fallback to password | ✅ Built | Unlock page always shows password field |
| Clear setup instructions | ❌ Missing | No "How to set up" guidance in UI |
| Unsupported browser message | ❌ Missing | `passkeySupported()` returns false silently; no explanatory message shown |

**Critical Bug:** Passkey login issues the **old deterministic token** (`_session_token()`), not a random session from `sessions.py`. This means passkey login doesn't create a trackable session.

### Phase 3 — Account Security ❌ NOT IMPLEMENTED

| Requirement | Status | Notes |
|-------------|--------|-------|
| Device list | ❌ Missing | `sessions.listing()` exists but no API endpoint |
| Current sessions | ❌ Missing | Same — no `/api/v1/auth/sessions` endpoint |
| Recent login history | ❌ Missing | `authsec.recent_audit()` exists but no endpoint; no login history per session |
| Browser / OS display | ❌ Missing | `sessions.describe()` parses UA but never exposed via API |
| Approximate location | ❌ Missing | IP stored but not geocoded |
| Last activity | ❌ Missing | `last_seen` tracked but not exposed |
| Logout current device | ✅ Built | `/api/v1/auth/logout` deletes cookie |
| Logout selected device | ❌ Missing | `sessions.revoke()` exists but no endpoint |
| Logout all devices | ❌ Missing | `sessions.revoke_all()` exists but no endpoint |
| Rotate session token | ❌ Missing | `sessions.rotate()` exists but no endpoint |
| Revoke passkeys | ❌ Missing | No `passkey.delete()` or endpoint |
| Revoke refresh tokens | ❌ Missing | No refresh token system exists (only single session token) |

### Phase 4 — User Profile ❌ NOT IMPLEMENTED

| Requirement | Status | Notes |
|-------------|--------|-------|
| Security page | ❌ Missing | `me/page.jsx` shows departments only; no security settings |
| Change password | ✅ Built | `/api/v1/auth/change-password` exists, UI on unlock page |
| Update email | ❌ Missing | No email field in any user model |
| Update display name | ❌ Missing | Hardcoded "Ajay Chaulagain" in `MobileMe.jsx` |
| Manage passkeys | ❌ Missing | No passkey management UI |
| Manage sessions | ❌ Missing | No session management UI |
| Enable/disable biometric login | ❌ Missing | No toggle; passkey always enabled if registered |
| Two-factor authentication (future-ready) | ❌ Missing | No TOTP architecture |
| Recovery email | ❌ Missing | No recovery email field |

### Phase 5 — OAuth Architecture ⚠️ MINIMAL

| Requirement | Status | Notes |
|-------------|--------|-------|
| Google | ❌ Missing | No OAuth endpoint |
| Apple | ❌ Missing | No OAuth endpoint |
| GitHub | ❌ Missing | No OAuth endpoint |
| Microsoft | ❌ Missing | No OAuth endpoint |
| Facebook | ❌ Missing | No OAuth endpoint |
| Telegram | ❌ Missing | No OAuth endpoint |
| Pluggable architecture | ⚠️ Partial | Logto integration exists (JWT RBAC) which can act as an OAuth proxy; but no native OAuth2/OIDC client code |

**Mitigation:** Logto can federate all these providers. If Logto is configured, SaathiOS gets SSO for free. But native OAuth client architecture for direct provider integration is not built.

### Phase 6 — Mobile Experience ⚠️ PARTIAL

| Requirement | Status | Notes |
|-------------|--------|-------|
| iPhone Safari | ✅ Tested | Responsive UI, safe-area, 16px font prevents zoom |
| iPhone Chrome | ⚠️ Likely | Same WebKit engine, should work |
| Android Chrome | ⚠️ Likely | Chrome should work; needs testing |
| Android Firefox | ⚠️ Unknown | Firefox WebAuthn support varies |
| iPad Safari | ⚠️ Likely | Same as iPhone Safari |
| iPad Chrome | ⚠️ Likely | Same WebKit |
| Mac Safari | ✅ Tested | Touch ID works |
| Mac Chrome | ⚠️ Likely | Should work |
| Windows Chrome | ⚠️ Unknown | Needs testing |
| Windows Edge | ⚠️ Unknown | Windows Hello should work |
| Keyboard overlap | ⚠️ Unknown | Not explicitly tested |
| Screen rotation | ⚠️ Unknown | `dvh` units used, should adapt |
| Password autofill | ✅ Built | `autoComplete="current-password"` / `"new-password"` set |
| Face ID prompt | ⚠️ Partial | Prompts appear but error handling is basic |
| Fingerprint prompt | ⚠️ Partial | Same as above |
| Passkey prompt | ⚠️ Partial | Same as above |
| Session restore | ⚠️ Partial | `localStorage` token persists, but no automatic re-auth on page load |
| Deep links | ❌ Missing | No deep link handling |
| Browser refresh | ⚠️ Partial | Token in `localStorage` survives, but user must re-login manually |
| Offline recovery | ❌ Missing | No offline mode for auth |

### Phase 7 — Security Audit

| Check | Status | Severity | Notes |
|-------|--------|----------|-------|
| CSRF | ⚠️ Partial | MEDIUM | `samesite="none"` on cookie + CORS `allow_origin_regex=".*"` = no CSRF protection. Mitigation: `x-baadar-session` header is custom, but could be forged. **Fix:** `SameSite=Lax` or `Strict` for non-API routes; require `Origin` header validation. |
| XSS | ⚠️ Partial | MEDIUM | No Content-Security-Policy header. Login errors are rendered client-side; server doesn't echo user input in HTML. **Fix:** Add CSP header. |
| Cookie flags | ⚠️ Partial | MEDIUM | `httponly=True, secure=True, samesite="none"` — `samesite="none"` weakens protection. **Fix:** `samesite="lax"` for same-origin, `"none"` only for cross-origin with explicit origin check. |
| JWT | ✅ Secure | LOW | Logto JWT uses RS256, proper issuer/audience validation, expiry checking. |
| Refresh tokens | ❌ Missing | HIGH | No refresh token system. Session cookie lasts 30 days. **Fix:** Implement short-lived access + long-lived refresh tokens. |
| Rate limiting | ⚠️ Partial | MEDIUM | `authsec.rate_check` exists but only used for chat, not login/passkey/change-password. **Fix:** Apply rate limiting to all auth endpoints. |
| Brute-force protection | ⚠️ Partial | MEDIUM | `rate_check` with 5 attempts / 5 min window exists but not wired to login. **Fix:** Wire it. |
| Password hashing | ✅ Secure | LOW | PBKDF2-SHA256, 600k iterations, transparent legacy upgrade. |
| Session fixation | ⚠️ Partial | MEDIUM | Login issues same deterministic token. **Fix:** Issue random token on login (wire `sessions.py`). |
| Replay attacks | ⚠️ Partial | MEDIUM | No nonce or request signing. WebAuthn prevents replay for passkeys. Password login vulnerable to replay if token intercepted. **Fix:** HTTPS + short-lived tokens. |
| Input validation | ⚠️ Partial | MEDIUM | Pydantic models for login/change-password. Password min 4 chars (too weak for production). **Fix:** Enforce 8+ with complexity. |
| Security headers | ❌ Missing | HIGH | No HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy. **Fix:** Add middleware. |

### Phase 8 — UX Improvements

| Requirement | Status | Notes |
|-------------|--------|-------|
| Forgot Password button | ❌ Missing | Not in unlock UI |
| Show/Hide password | ❌ Missing | No toggle on password inputs |
| Caps Lock warning | ❌ Missing | Not implemented |
| Password strength meter | ⚠️ Partial | Server has `password_strength()`, client doesn't show it |
| Password requirements | ❌ Missing | No "8+ chars, upper, lower, number, symbol" guidance |
| Remember me | ❌ Missing | No "keep me signed in" checkbox; all sessions are 30 days |
| Keep me signed in | ❌ Missing | Same as above |
| Loading indicators | ✅ Built | `busy` state disables buttons, shows opacity change |
| Offline warning | ❌ Missing | No network status detection |
| Clear success messages | ✅ Built | `✓ Signed in.` etc. |
| Clear failure messages | ✅ Built | `friendly()` function converts errors to human sentences |
| Never display raw server errors | ✅ Built | `friendly()` sanitizes all errors |

### Phase 9 — Testing

| Test Target | Status | Notes |
|-------------|--------|-------|
| Desktop | ⚠️ Partial | Mac tested, Windows unknown |
| Tablet | ⚠️ Unknown | iPad assumed working, not tested |
| Mobile | ⚠️ Partial | iPhone tested, Android unknown |
| Portrait | ✅ Tested | Responsive design handles this |
| Landscape | ⚠️ Unknown | Not explicitly tested |
| Passkey registration | ⚠️ Partial | Mac Touch ID works, other devices unknown |
| Passkey login | ⚠️ Partial | Same as above |
| Password login | ✅ Tested | Works across devices |
| Password reset | ❌ Missing | No flow to test |
| Logout | ✅ Tested | Cookie deletion works |
| Logout everywhere | ❌ Missing | No endpoint to test |
| Session recovery | ⚠️ Partial | `localStorage` token survives, but no auto-restore |
| OAuth preparation | ❌ Missing | No architecture to test |

---

## 5. Architecture Diagram — Current vs. Target

### Current (Broken Integration)

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────┐
│  Client UI  │────→│  /api/v1/auth/  │────→│ _session_token│  ← deterministic
│  unlock.jsx │     │  login/logout   │     │ (old hash)     │     (same on all devices)
└─────────────┘     └─────────────────┘     └──────────────┘
                                                   ↑
┌─────────────┐     ┌─────────────────┐          │
│  passkey.js │────→│ passkey_register│──────────┘
│  (WebAuthn) │     │ /login_verify   │  ← also issues deterministic token
└─────────────┘     └─────────────────┘

┌─────────────┐
│ sessions.py │  ← ORPHANED — built but never called
│  create()   │
│  validate() │
│  listing()  │
│  revoke()   │
└─────────────┘
```

### Target (After Integration)

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│  Client UI  │────→│  Auth API       │────→│ sessions.py  │────→│  ~/.saathi/ │
│  unlock.jsx │     │  (server.py)    │     │  create()    │     │  sessions.json
└─────────────┘     └─────────────────┘     │  validate()  │     └─────────────┘
                                            │  revoke()    │
┌─────────────┐     ┌─────────────────┐     │  rotate()    │
│  passkey.js │────→│ passkey_*.py    │────→│  listing()   │
│  (WebAuthn) │     │  (WebAuthn lib) │     └──────────────┘
└─────────────┘     └─────────────────┘

┌─────────────┐     ┌─────────────────┐     ┌──────────────┐
│  Security   │────→│  /api/v1/auth/  │────→│  authsec.py  │
│  /me        │     │  sessions/*     │     │  audit()     │
│  /reset     │     │  reset/*        │     │  rate_check()│
└─────────────┘     └─────────────────┘     └──────────────┘
```

---

## 6. Recommendations — Implementation Order

### Must Fix First (Blocking Everything Else)

1. **Wire `sessions.py` into `server.py`** — Replace `_session_token()` with `sessions.create()` on login, `sessions.validate()` on auth check, `sessions.revoke_all()` on logout
2. **Add session auth to `_is_authed()`** — Check `sessions.validate(token)` alongside the legacy deterministic token for backward compatibility
3. **Update passkey login** — Issue `sessions.create()` instead of `_session_token()`
4. **Invalidate sessions on password change** — Call `revoke_all()` then issue new session

### Then Build Missing Features

5. **Phase 3 API** — `/api/v1/auth/sessions` (GET/DELETE), `/api/v1/auth/sessions/revoke-all`, `/api/v1/auth/session/rotate`
6. **Phase 1 API** — `/api/v1/auth/forgot`, `/api/v1/auth/reset` with secure reset tokens
7. **Phase 2 API** — `/api/v1/auth/passkeys` (GET/DELETE/PATCH for rename), passkey unsupported browser message
8. **Phase 4 UI** — Security page with sessions, passkeys, password change, 2FA placeholder
9. **Phase 5 Architecture** — OAuth provider registry (pluggable, no providers enabled yet)
10. **Phase 7 Hardening** — Security headers middleware, rate limit auth endpoints, CSRF tokens, CSP
11. **Phase 8 UX** — Show/hide password, strength meter, caps lock, remember me, offline warning
12. **Phase 9 Tests** — Full test suite for all new auth endpoints

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing login | Medium | High | Keep legacy deterministic token as fallback; dual-validation for 1 release cycle |
| Passkey users locked out | Low | Medium | Passkey login falls back to password; password always works |
| Session file corruption | Low | Medium | JSON file with backup; SQLite migration path documented |
| Rate limit DoS | Low | Medium | In-memory only; persistent store can be added later |
| Email not configured = forgot password fails | High | Low | Outbox.log fallback + clear UI message; SMTP = one env change |

---

*End of Audit Report*
