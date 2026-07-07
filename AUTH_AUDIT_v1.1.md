# Authentication v1.1 — Final Production Audit Report

**Project:** SaathiAI / Baadar AI  
**Date:** 2026-01-13  
**Auditor:** AI-assisted code review (comprehensive 11-area audit)  
**Branch:** `milestone/m5.1-infrastructure`  
**Scope:** Backend auth (`saathi/server.py`, `saathi/authsec.py`, `saathi/sessions.py`, `saathi/passkey.py`) + Frontend auth UI (`saathi-os/app/unlock/page.jsx`, `saathi-os/app/security/page.jsx`, `saathi-os/lib/api.js`, `saathi-os/lib/passkey.js`)  
**Constraint:** No new features added. Evaluate, document, fix critical issues only.

---

## Executive Summary

| Area | Rating | Status |
|------|--------|--------|
| 1. Password Storage & Hashing | ⚠️ **PARTIAL** | PBKDF2 used for verification, but `change_password` writes bare SHA256 to `.env` |
| 2. Session Token Security | ✅ **PASS** | Cryptographically random, SHA256-hashed storage, idle expiry, hard cap |
| 3. Session Expiry & Rotation | ⚠️ **PARTIAL** | 30-day cookie always set; "Remember Me" checkbox non-functional; rotation endpoint exists |
| 4. Password Reset (Forgot) | ✅ **PASS** | Time-limited tokens, SHA256-hashed, single-use, secure comparison, email sent |
| 5. Rate Limiting | ⚠️ **PARTIAL** | Login/reset covered, but passkey login endpoints **uncovered**; in-memory only |
| 6. Input Validation & Sanitization | ✅ **PASS** | Pydantic models, length limits, regex, password strength checker |
| 7. Secure Communication | ⚠️ **PARTIAL** | HTTPS in production, `secure=True` cookies, but `allow_origin_regex=".*"` CORS |
| 8. Error Handling & Information Disclosure | ✅ **PASS** | Generic errors, no enumeration, no stack traces to client |
| 9. Audit Logging & Monitoring | ⚠️ **PARTIAL** | Events logged, but no retention/rotation; no real-time alerting |
| 10. Frontend Auth Flow Security | ⚠️ **PARTIAL** | XSS-safe storage, passkey support, but "Remember Me" broken, dashboard placeholders |
| 11. Test Coverage & Regression | ⚠️ **PARTIAL** | No dedicated local auth tests found; only JWT test exists |

**Overall Verdict: CONDITIONAL PASS — 2 Critical Fixes Required Before Production**

---

## 1. Password Storage & Hashing

### ✅ What Works
- `authsec.py` uses **PBKDF2-SHA256 with 600,000 iterations** (`hash_password`) — industry standard
- `verify_password` correctly checks both legacy bare SHA256 and new PBKDF2 formats
- `password_strength()` enforces 8+ chars, mixed case, digit, and symbol requirements
- Frontend displays real-time password strength meter with visual feedback

### ⚠️ Critical Finding: Password Change Writes Bare SHA256 to `.env`

**Location:** `saathi/server.py` — `change_password` endpoint

```python
# Line ~1919 in server.py
env_path = Path(".env")
new_line = f'BAADAR_PASSWORD="{hashlib.sha256(body.new_password.encode()).hexdigest()}"\n'
```

**Problem:** The `change_password` endpoint stores the **bare SHA256** of the new password in the `.env` file, not the PBKDF2 hash. This means:
1. The PBKDF2 hash in `authsec.py` is only used for **comparison**, not for **storage**
2. The actual stored password is a fast-computable SHA256 hash, vulnerable to rainbow tables and GPU cracking
3. The `.env` file is the source of truth for login, so every new password set via the UI is weakly hashed

**Impact:** HIGH — An attacker who gains read access to `.env` can crack passwords orders of magnitude faster than if PBKDF2 were used.

**Fix:** Change the `change_password` endpoint to call `authsec.hash_password()` and store the PBKDF2 hash instead of bare SHA256. Update `verify_password` to handle the new format (already does). Remove legacy SHA256 support from storage (keep for verification of old passwords only).

### ✅ Legacy Compatibility Note
The system accepts both old deterministic `_session_token()` and new random tokens for backward compatibility. This is acceptable because the old tokens are time-bound and the system is single-owner.

---

## 2. Session Token Security

### ✅ What Works
- **Cryptographic randomness:** `secrets.token_urlsafe(32)` — ~256 bits entropy
- **Storage hashing:** Only SHA256 hashes stored, never plaintext tokens (`sessions.py` line 16: `th = _hash(token)`)
- **Hard cap:** Maximum 100 sessions (`_HARD_CAP = 100`)
- **Idle expiry:** `_prune()` removes sessions older than 30 days of inactivity
- **Session metadata:** Tracks UA, IP, browser, OS, kind, label for audit

### ✅ Token Transmission
- Frontend uses dual auth: `httponly` cookie **+** `x-baadar-session` header from `localStorage`
- This works around Safari ITP and cross-origin cookie restrictions
- `samesite="none"` with `secure=True` is correct for cross-origin deployments

---

## 3. Session Expiry & Rotation

### ⚠️ Critical Finding: "Remember Me" Checkbox Is Non-Functional

**Location:** `saathi-os/app/unlock/page.jsx` (lines ~190-210) + `saathi/server.py` login endpoint

**What the frontend does:**
```jsx
// unlock/page.jsx
if (!rememberMe) {
  try { localStorage.setItem("saathi_session_short", "1"); } catch {}
}
```

**What the server does:**
```python
# server.py login endpoint
r.set_cookie("baadar_session", token, httponly=True, samesite="none", secure=True, max_age=30*24*3600)
```

**Problem:** The server **never reads** `saathi_session_short` from localStorage. The cookie `max_age` is **always** `30*24*3600` (30 days) regardless of the checkbox state. The `localStorage` flag is set but never consumed by the server or any other code.

**Impact:** MEDIUM — Users expecting short sessions (e.g., on shared computers) get 30-day sessions instead, increasing exposure if the device is compromised.

**Fix Options:**
1. **Server-side:** Add `remember_me` boolean to login request body; if false, set `max_age=24*3600` (24 hours) or use session cookie (no `max_age`)
2. **Client-side:** After login, if `saathi_session_short` is set, call a new endpoint to set a short-lived session, or simply delete the flag after reading

**Recommended fix:**
```python
# In login endpoint
max_age = 30*24*3600 if body.remember_me else 24*3600
r.set_cookie("baadar_session", token, ..., max_age=max_age)
```

### ✅ What Works
- `rotateSession()` API endpoint exists and returns new token
- `revokeAllSessions()` API endpoint exists
- `_prune()` removes idle sessions on every operation

---

## 4. Password Reset (Forgot Password)

### ✅ What Works
- Time-limited tokens: 15-minute expiry (`reset_ttl = 15*60`)
- Tokens stored as SHA256 hashes only (`_hash(reset_token)`)
- Single-use: `_used_reset.add(th)` prevents replay
- Secure comparison: `secrets.compare_digest` for constant-time token verification
- Email enumeration prevention: accepts **any** email address, returns same message regardless
- Plain text email sent via SMTP (no HTML, no branding — see Area 9)
- Reset token is a `secrets.token_urlsafe(24)` — ~192 bits entropy

### ✅ Security Flow
```
POST /api/v1/auth/forgot  →  generates token, stores hash, emails link
POST /api/v1/auth/reset   →  compares digest, verifies expiry, updates password, revokes sessions
```

### ⚠️ Minor Issue: No Rate Limit Per-Email
The forgot-password endpoint uses IP-based rate limiting, but an attacker could rotate IPs and target the same email. Consider adding per-email rate limiting as well (with care to prevent enumeration).

---

## 5. Rate Limiting

### ✅ What Works
- Login endpoint: `5 per 60s` per IP (`sliding_window`, `authsec.py` line ~90)
- Password reset: `3 per 60s` per IP
- Account creation: `5 per 60s` per IP
- Generic check: `30 per 60s` per IP for all endpoints
- Returns `429` with `Retry-After` header

### ⚠️ Critical Finding: Passkey Login Endpoints Have NO Rate Limiting

**Location:** `sahti/server.py` — `/api/v1/auth/passkey/login/options` and `/api/v1/auth/passkey/login/verify`

**Problem:** Neither of the passkey login endpoints has any rate limiting. An attacker could:
1. Request `/passkey/login/options` indefinitely to generate challenges
2. Submit `/passkey/login/verify` with crafted credentials to probe for valid passkeys

**Impact:** MEDIUM — While WebAuthn itself is resistant to brute force, the server-side challenge generation and verification could be abused for DoS or resource exhaustion.

**Fix:** Add `@sliding_window` decorator to both passkey login endpoints, same as `/auth/login`.

### ⚠️ Finding: In-Memory Rate Limit Store Lost on Restart
**Impact:** LOW — Rate limit counters reset on server restart. For a single-owner system, acceptable. For multi-user, should use Redis or persistent store.

---

## 6. Input Validation & Sanitization

### ✅ What Works
- All auth endpoints use Pydantic models (`LoginIn`, `ChangePasswordIn`, `ResetIn`, `RenameIn`, etc.)
- Password length enforced (max 128 characters)
- Email regex validation in `forgot` endpoint
- `password_strength()` checks length, case, digits, symbols
- `strip()` applied to strings where appropriate
- No raw SQL — all data stored in JSON files

### ✅ Frontend Validation
- Real-time password strength meter before submission
- Minimum 8 characters enforced client-side
- Visual feedback (red/yellow/green) with checkmarks

---

## 7. Secure Communication

### ✅ What Works
- Cookies: `httponly=True`, `secure=True`, `samesite="none"` (required for cross-origin)
- Token header: `x-baadar-session` sent with `credentials: "include"`
- HTTPS expected in production (relies on Caddy/reverse proxy)
- No token in URL parameters

### ⚠️ Finding: Overly Permissive CORS

**Location:** `saathi/server.py` — CORS configuration

```python
allow_origin_regex=".*"
allow_credentials=True
```

**Problem:** The `allow_origin_regex=".*"` allows **any origin** to make credentialed requests. This is dangerous because:
1. Any malicious website can make authenticated requests on behalf of a logged-in user
2. CSRF protection is weakened because the origin check is bypassed

**Impact:** HIGH for multi-user scenarios; MEDIUM for single-owner (attacker needs to know the specific API endpoints and session token)

**Fix:** Restrict to known origins:
```python
allow_origin_regex=r"https://(saathi\.ai|localhost|.*\.saathi\.ai)"
```
Or use explicit `allow_origins` list from environment variable.

**Note:** The `samesite="none"` is required for the cross-origin mobile/web setup, but this makes the CORS restriction even more important.

---

## 8. Error Handling & Information Disclosure

### ✅ What Works
- Login failure: returns `{"ok": false, "error": "Invalid password"}` — no enumeration
- Forgot password: returns same message for any email — no enumeration
- Session invalid: returns `401` with generic message
- No stack traces leaked to client
- No internal paths or system details in error messages
- Password reset token expiry: generic "Invalid or expired token"

### ✅ Information Disclosure Audit
- ❌ No username enumeration (single owner, no username)
- ❌ No email enumeration (forgot password accepts any email)
- ❌ No timing attack on password verification (constant-time `compare_digest`)
- ❌ No account existence leaks
- ✅ `Platform-OS` header reveals `sys.platform` — low risk for single owner

---

## 9. Audit Logging & Monitoring

### ✅ What Works
- `auth_audit.log` in `~/.saathi/` records all auth events as JSON lines
- Events include: `login`, `logout`, `password_change`, `forgot_password`, `reset_password`, `session_revoke`, `passkey_register`, `passkey_login`, `session_rotate`
- Each event includes: timestamp, action, IP, user agent, session ID, result
- `audit_log` function in `server.py` ensures consistent logging
- Frontend Security Dashboard displays last 40 events with icons

### ⚠️ Finding: No Log Rotation or Retention Policy
**Location:** `saathi/server.py` — `auth_audit.log`

**Problem:** The audit log is append-only with no rotation. On a busy system, this file could grow indefinitely. There is no retention policy, compression, or archival.

**Impact:** MEDIUM — Disk space exhaustion; difficulty in incident response with large files.

**Fix:** Implement log rotation (e.g., daily or 10MB max) with gzip compression for old logs. Retain 90 days.

### ⚠️ Finding: No Real-Time Alerting
- No failed login alerting
- No suspicious IP alerting
- No anomaly detection
- No integration with external SIEM

**Impact:** LOW for single-owner system, but would be MEDIUM for multi-user.

---

## 10. Frontend Auth Flow Security

### ✅ What Works
- **XSS-safe storage:** Token in `localStorage` (not `sessionStorage` which is XSS-vulnerable in a different way, but `localStorage` is the standard for SPAs). The dual cookie+header approach mitigates XSS risks for the cookie.
- **Passkey support:** Touch ID / Face ID unlock with `navigator.credentials.create/get`
- **Password strength meter:** Real-time visual feedback with 4 checks
- **Secure logout:** Clears `localStorage` token + calls server logout + cookie clear
- **Session management:** Users can view, rename, revoke individual sessions or all sessions
- **CSRF protection:** Cookie is `httponly`, and `x-baadar-session` header is required — effectively CSRF-safe for state-changing endpoints

### ⚠️ Finding: "Remember Me" Checkbox Broken (Duplicate of Area 3)
See Area 3 for full details. The checkbox is UI-only with no backend effect.

### ⚠️ Finding: Security Dashboard Shows Placeholders for 2FA and Recovery Email

**Location:** `saathi-os/app/security/page.jsx` — lines ~370-400

```jsx
<div style={{ fontSize: 13, opacity: 0.5, lineHeight: 1.5 }}>
  2FA is not yet enabled. This will be available in a future update (TOTP-based).
</div>
```

**Problem:** The Security Dashboard displays hardcoded placeholder text for 2FA and Recovery Email with no real computed state. This is misleading because:
1. Users see "2FA not enabled" but there's no way to enable it
2. The "Security Score" section is commented out / not implemented
3. No actual security posture calculation

**Impact:** LOW — UI/UX issue, not a security vulnerability. But it reduces user trust.

**Fix:** Either hide the sections until implemented, or compute a real security score based on: password age, passkey presence, number of active sessions, last password change, etc.

### ✅ What Works: Passkey Flow
- Registration requires existing session (can't register without being logged in)
- `passkeySupported()` feature detection before showing buttons
- Proper base64url encoding/decoding of WebAuthn binary data
- Challenge verification server-side before session creation

---

## 11. Test Coverage & Regression

### ⚠️ Critical Finding: No Dedicated Local Auth Tests Found

**Claimed:** "38 auth tests passing" (from previous context)  
**Found:** Only `test_auth_logto.py` — tests JWT/Logto integration, NOT local password auth

**Location searched:** `~/SaathiAI/` and subdirectories

**What was found:**
- `test_auth_logto.py` — JWT token verification tests (for Logto provider)
- No `test_auth.py`, `test_sessions.py`, `test_passkey.py`, or similar
- No tests for: login, logout, password change, session rotation, forgot password, reset password, rate limiting, passkey registration/verification

**Impact:** HIGH — Without automated tests, regressions in auth code are not caught. This is the highest-risk area for a production system.

**Required Tests:**
1. **Password hashing:** Verify PBKDF2 hash format, verify legacy SHA256 compatibility, verify strength checker
2. **Login flow:** Correct password → 200 + token; wrong password → 401; empty password → 400; rate limit → 429
3. **Session management:** Create → verify → rotate → revoke → verify revoked; session cap (100); idle expiry
4. **Password reset:** Generate token → verify token → use token → verify used → verify expiry; wrong token → 400
5. **Passkey:** Register options → verify → login options → verify → session created; wrong signature → 400
6. **Rate limiting:** 5 failed logins → 6th blocked; 3 forgot requests → 4th blocked
7. **Audit log:** Verify each action creates correct log entry

**Fix:** Create `test_auth.py` with the above test cases. Use `pytest` with FastAPI `TestClient`.

---

## Additional Findings

### OAuth Not Implemented (Out of Scope)
The OAuth callback endpoint (`/api/v1/auth/oauth/{provider}/callback`) returns:
```json
{"status": "not_implemented", "message": "Token exchange not yet implemented"}
```
This is acceptable as OAuth is a planned feature, not a bug. The architecture is in place (6 providers registered).

### Single-Owner System Design
The entire auth system is designed for a single owner (Ajay). This is intentional and documented:
- No user database; only one password in `.env`
- Email in forgot-password accepts any input (no user lookup)
- Passkey user ID is hardcoded as `b"ajay-owner"`
- Session management is per-device, not per-user

This is acceptable for the current use case but should be documented as a limitation.

### Email Templates
Password reset emails are plain text only (`You requested a password reset...`). No HTML, no branding, no Nepali/English localization. Acceptable for v1.1 but noted for future improvement.

---

## Critical Fixes Required (Before Production)

### 🔴 CRITICAL-1: Fix Password Change to Use PBKDF2 (Not Bare SHA256)
**File:** `saathi/server.py` — `change_password` endpoint (~line 1919)  
**Action:** Replace `hashlib.sha256(body.new_password.encode()).hexdigest()` with `authsec.hash_password(body.new_password)` and store PBKDF2 hash in `.env`.

### 🔴 CRITICAL-2: Implement "Remember Me" Backend Support
**File:** `saathi/server.py` — `login` endpoint + `saathi-os/app/unlock/page.jsx`  
**Action:** Add `remember_me: bool` to `LoginIn` model; if false, set cookie `max_age=24*3600` instead of 30 days.

### 🟡 HIGH-3: Add Rate Limiting to Passkey Login Endpoints
**File:** `saathi/server.py` — `/passkey/login/options` and `/passkey/login/verify`  
**Action:** Add `@sliding_window(5, 60)` decorator to both endpoints.

### 🟡 HIGH-4: Create Comprehensive Auth Test Suite
**File:** New `tests/test_auth.py`  
**Action:** Write tests for all auth flows: login, logout, password change, session rotation, forgot/reset password, passkey, rate limiting, audit logging.

### 🟡 HIGH-5: Restrict CORS Origins
**File:** `saathi/server.py` — CORS configuration  
**Action:** Replace `allow_origin_regex=".*"` with a whitelist of known origins from environment variable.

### 🟡 MEDIUM-6: Implement Audit Log Rotation
**File:** `sahti/server.py` — `audit_log` function  
**Action:** Add daily rotation with gzip compression for `auth_audit.log`.

### 🟡 MEDIUM-7: Fix Security Dashboard Placeholders
**File:** `saathi-os/app/security/page.jsx`  
**Action:** Either hide 2FA/Recovery Email sections until implemented, or compute a real security score.

### 🟢 LOW-8: Add Per-Email Rate Limiting for Forgot Password
**File:** `saathi/server.py` — `/forgot` endpoint  
**Action:** Add `sliding_window` keyed by email hash (not raw email) to prevent IP rotation attacks.

---

## Final Verdict

**Status: CONDITIONAL PASS — Production deployment is acceptable after fixing CRITICAL-1 and CRITICAL-2.**

The SaathiAI auth system is well-architected for a single-owner personal assistant. The core security primitives (PBKDF2, cryptographically random tokens, SHA256 storage hashing, WebAuthn passkeys) are industry-standard. However, two critical issues must be fixed:

1. **Password change writes bare SHA256** — This undermines the entire password security model.
2. **"Remember Me" is non-functional** — Users get 30-day sessions regardless of preference, which is a security/privacy issue on shared devices.

The remaining issues (passkey rate limiting, CORS restriction, test coverage, log rotation) are important but do not block production. They should be addressed in the next sprint (v1.2).

### Risk Summary

| Risk | Severity | Likelihood | Mitigation (Current) | Status |
|------|----------|------------|----------------------|--------|
| `.env` password cracked if file leaked | HIGH | LOW | File is in home directory, not repo | 🔴 Fix required |
| Session too long on shared devices | MEDIUM | MEDIUM | Token is random, not guessable | 🔴 Fix required |
| Passkey endpoint DoS | MEDIUM | LOW | Single-owner system, limited exposure | 🟡 Fix in v1.2 |
| CORS credential theft | MEDIUM | LOW | Single-owner, needs specific token | 🟡 Fix in v1.2 |
| No auth tests | HIGH | N/A | Manual testing only | 🟡 Fix in v1.2 |
| Log disk exhaustion | LOW | LOW | Single-owner, low volume | 🟡 Fix in v1.2 |
| Dashboard placeholders | LOW | N/A | UI-only, no security impact | 🟢 Cosmetic |

---

## Appendix A: File Locations

| Component | File Path | Lines |
|-----------|-----------|-------|
| Session Storage | `saathi/sessions.py` | 1–90 |
| Security Primitives | `saathi/authsec.py` | 1–90 |
| Auth Endpoints | `saathi/server.py` | 1668–2200+ |
| Passkey Logic | `sahti/passkey.py` | 1–120 |
| Login UI | `saathi-os/app/unlock/page.jsx` | 1–250 |
| Security Dashboard | `saathi-os/app/security/page.jsx` | 1–470 |
| Auth API Client | `saathi-os/lib/api.js` | 539–629 |
| Passkey Client | `saathi-os/lib/passkey.js` | 1–71 |

## Appendix B: Auth Endpoint Inventory

| Endpoint | Method | Auth Required | Rate Limit | Notes |
|----------|--------|---------------|------------|-------|
| `/api/v1/auth/login` | POST | No | 5/60s | Password login |
| `/api/v1/auth/logout` | POST | Yes | 30/60s | Cookie + header clear |
| `/api/v1/auth/change-password` | POST | Yes | 30/60s | Changes `.env` password |
| `/api/v1/auth/forgot` | POST | No | 3/60s | Email reset link |
| `/api/v1/auth/reset` | POST | No | 3/60s | Token verification |
| `/api/v1/auth/sessions` | GET | Yes | 30/60s | List active sessions |
| `/api/v1/auth/sessions/{sid}` | DELETE | Yes | 30/60s | Revoke one session |
| `/api/v1/auth/sessions/revoke-all` | POST | Yes | 30/60s | Revoke all sessions |
| `/api/v1/auth/session/rotate` | POST | Yes | 30/60s | Issue new token |
| `/api/v1/auth/sessions/{sid}/rename` | POST | Yes | 30/60s | Rename session |
| `/api/v1/auth/passkeys` | GET | Yes | 30/60s | List passkeys |
| `/api/v1/auth/passkeys/{pid}` | DELETE | Yes | 30/60s | Delete passkey |
| `/api/v1/auth/passkeys/{pid}` | PATCH | Yes | 30/60s | Rename passkey |
| `/api/v1/auth/passkey/register/options` | POST | Yes | 30/60s | WebAuthn registration |
| `/api/v1/auth/passkey/register/verify` | POST | Yes | 30/60s | Verify registration |
| `/api/v1/auth/passkey/login/options` | POST | No | **NONE** | 🔴 Missing rate limit |
| `/api/v1/auth/passkey/login/verify` | POST | No | **NONE** | 🔴 Missing rate limit |
| `/api/v1/auth/audit` | GET | Yes | 30/60s | Audit log events |
| `/api/v1/auth/oauth/providers` | GET | No | 30/60s | List OAuth providers |
| `/api/v1/auth/oauth/{provider}/callback` | GET | No | 30/60s | Not implemented |

---

*End of Audit Report*
