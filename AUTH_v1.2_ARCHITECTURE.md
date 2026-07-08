# SaathiOS Authentication v1.2 — Security Platform Architecture

**Status:** Design Document  
**Date:** 2025-06-26  
**Branch:** `milestone/m5.2-auth-hardening` → `milestone/m6-security-platform`  
**Scope:** Move Authentication from application feature to reusable Security Platform

---

## Executive Summary

Auth v1.2 transforms Authentication from a collection of endpoints in `server.py` into a **dedicated Security subsystem** with its own Store, Registry, Router, and Timeline. The design supports single-owner operation today while leaving clear extension points for enterprise multi-user, multi-organization, and RBAC futures.

**Core principle:** Every authentication object lives in the Security Store (SQLite). `.env` contains configuration only. Runtime state never touches `.env`.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SaathiOS Security Platform                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Security   │  │   Identity   │  │    Token     │  │    Risk      │    │
│  │    Store     │  │   Provider   │  │   Registry   │  │   Engine     │    │
│  │  (SQLite)    │  │   Router     │  │              │  │              │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│         │                 │                 │                 │            │
│         └─────────────────┴─────────────────┴─────────────────┘            │
│                                   │                                        │
│                           ┌───────▼────────┐                              │
│                           │  Auth Service  │                              │
│                           │  (server.py)   │                              │
│                           └───────┬────────┘                              │
│                                   │                                        │
│         ┌─────────────────────────┼─────────────────────────┐              │
│         │                         │                         │              │
│  ┌──────▼──────┐         ┌────────▼────────┐      ┌────────▼────────┐     │
│  │  Sessions   │         │ Security        │      │  Audit /        │     │
│  │  (SQLite)   │         │ Timeline        │      │  Event Log      │     │
│  └─────────────┘         └─────────────────┘      └─────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                        ┌────────────▼────────────┐
                        │    SaathiOS Frontend    │
                        │  (Next.js / SaathiOS)   │
                        └─────────────────────────┘
```

---

## 2. New Folder Structure

```
saathi/
├── __init__.py
├── server.py                      # ← Auth endpoints now thin wrappers
├── authsec.py                     # ← Password hashing, rate limiting (enhanced)
├── sessions.py                    # ← API unchanged; backend now SQLite via Security Store
├── passkey.py                     # ← API unchanged; backend now SQLite via Security Store
│
└── security/                      # ← NEW: Security Platform package
    ├── __init__.py
    ├── store.py                   # Security Store — SQLite schema + CRUD
    ├── registry.py                # Token Registry — named, permissioned API tokens
    ├── risk.py                    # Risk Engine — session risk scoring
    ├── identity.py                # Identity Provider abstraction + adapters
    ├── timeline.py                # Security Timeline — append-only event log
    ├── health.py                  # Password Health — strength, age, rotation
    └── diagnostics.py             # Passkey / OAuth diagnostic messages

saathi-os/
├── lib/
│   ├── api.js                     # ← Add token registry endpoints
│   └── passkey.js                 # ← Add diagnostic error mapping
└── app/
    └── security/
        └── page.jsx               # ← Add Password Health, Security Timeline
```

---

## 3. Security Store Design

### Database: `~/.saathi/security.db`

### Schema

```sql
-- Users table — single owner today, multi-user tomorrow
CREATE TABLE users (
    id          TEXT PRIMARY KEY,           -- UUID
    email       TEXT UNIQUE,
    name        TEXT,
    avatar_url  TEXT,
    status      TEXT DEFAULT 'active',      -- active | suspended | deleted
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

-- Password history — tracks changes for health metrics
CREATE TABLE passwords (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    hash        TEXT NOT NULL,              -- PBKDF2 or legacy
    strength_score INTEGER DEFAULT 0,
    created_at  REAL NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Sessions — replaces ~/.saathi/sessions.json
CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,       -- public handle (hash prefix)
    token_hash      TEXT NOT NULL UNIQUE,   -- sha256(token) for validation
    user_id         TEXT NOT NULL,
    browser         TEXT DEFAULT 'Unknown',
    os              TEXT DEFAULT 'Unknown',
    platform        TEXT DEFAULT 'Unknown', -- desktop | mobile | tablet
    device_name     TEXT DEFAULT 'Unknown',
    user_agent      TEXT,
    ip_address      TEXT,
    country         TEXT,                   -- future: geoip
    timezone        TEXT,                   -- future: client-reported
    language        TEXT,                   -- future: Accept-Language
    login_method    TEXT DEFAULT 'password',-- password | passkey | oauth | token
    first_seen      REAL NOT NULL,
    last_seen       REAL NOT NULL,
    revoked         INTEGER DEFAULT 0,      -- soft delete
    expires_at      REAL NOT NULL,
    remember_me     INTEGER DEFAULT 1,
    risk_score      INTEGER DEFAULT 0,      -- 0-100
    label           TEXT DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Passkeys — replaces ~/.saathi/passkeys.json
CREATE TABLE passkeys (
    id              TEXT PRIMARY KEY,       -- credential ID (base64url)
    user_id         TEXT NOT NULL,
    public_key      TEXT NOT NULL,          -- base64url
    sign_count      INTEGER DEFAULT 0,
    rp_id           TEXT NOT NULL,
    device_name     TEXT DEFAULT 'Unknown',
    browser         TEXT DEFAULT 'Unknown',
    platform        TEXT DEFAULT 'Unknown',
    created_at      REAL NOT NULL,
    last_used_at    REAL DEFAULT 0,
    label           TEXT DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Reset tokens — replaces ~/.saathi/reset_tokens.json
CREATE TABLE reset_tokens (
    token       TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    email       TEXT,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    used        INTEGER DEFAULT 0,
    ip_address  TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- API Tokens — replaces SAATHI_TOKEN global
CREATE TABLE api_tokens (
    id              TEXT PRIMARY KEY,       -- UUID
    user_id         TEXT NOT NULL,
    name            TEXT NOT NULL,          -- "Studio", "Mission Bot", etc.
    purpose         TEXT,
    token_hash      TEXT NOT NULL UNIQUE,   -- sha256(raw_token)
    permissions     TEXT DEFAULT '[]',      -- JSON array of endpoint patterns
    created_at      REAL NOT NULL,
    expires_at      REAL,
    last_used_at    REAL DEFAULT 0,
    revoked         INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- OAuth identities — federated login accounts
CREATE TABLE oauth_identities (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    provider        TEXT NOT NULL,          -- google | apple | github | ...
    provider_user_id TEXT NOT NULL,
    email           TEXT,
    name            TEXT,
    access_token    TEXT,                   -- encrypted at rest (future)
    refresh_token   TEXT,                   -- encrypted at rest (future)
    expires_at      REAL,
    created_at      REAL NOT NULL,
    last_used_at    REAL DEFAULT 0,
    UNIQUE (provider, provider_user_id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Security Timeline — append-only event log
CREATE TABLE security_events (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    timestamp   REAL NOT NULL,
    kind        TEXT NOT NULL,              -- password_changed | passkey_added | ...
    title       TEXT NOT NULL,
    detail      TEXT,
    meta        TEXT DEFAULT '{}',          -- JSON
    ip_address  TEXT,
    user_agent  TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Audit log — replaces ~/.saathi/auth_audit.log
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   REAL NOT NULL,
    event       TEXT NOT NULL,
    ok          INTEGER DEFAULT 1,
    user_id     TEXT,
    ip_address  TEXT,
    user_agent  TEXT,
    detail      TEXT,
    session_id  TEXT
);

-- Multi-user foundation (stubs — not wired yet, but schema-ready)
CREATE TABLE organizations (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    owner_id    TEXT NOT NULL,
    created_at  REAL NOT NULL,
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE teams (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    created_at  REAL NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

CREATE TABLE team_members (
    team_id     TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    role        TEXT DEFAULT 'member',      -- admin | member | viewer
    joined_at   REAL NOT NULL,
    PRIMARY KEY (team_id, user_id),
    FOREIGN KEY (team_id) REFERENCES teams(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE roles (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    permissions TEXT NOT NULL DEFAULT '[]', -- JSON array of permission strings
    created_at  REAL NOT NULL
);

CREATE TABLE user_roles (
    user_id     TEXT NOT NULL,
    role_id     TEXT NOT NULL,
    org_id      TEXT,                       -- NULL = platform-wide role
    assigned_at REAL NOT NULL,
    PRIMARY KEY (user_id, role_id, org_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (role_id) REFERENCES roles(id),
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);
```

### Indexes

```sql
CREATE INDEX idx_sessions_user ON sessions(user_id, last_seen DESC);
CREATE INDEX idx_sessions_token ON sessions(token_hash);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);
CREATE INDEX idx_passkeys_user ON passkeys(user_id);
CREATE INDEX idx_api_tokens_hash ON api_tokens(token_hash);
CREATE INDEX idx_api_tokens_user ON api_tokens(user_id, last_used_at DESC);
CREATE INDEX idx_oauth_provider ON oauth_identities(provider, provider_user_id);
CREATE INDEX idx_security_events_user ON security_events(user_id, timestamp DESC);
CREATE INDEX idx_security_events_kind ON security_events(kind, timestamp DESC);
CREATE INDEX idx_audit_event ON audit_log(event, timestamp DESC);
CREATE INDEX idx_audit_user ON audit_log(user_id, timestamp DESC);
```

---

## 4. Session Model (v1.2)

### Enhanced Session Fields

| Field | Source | Example |
|-------|--------|---------|
| `browser` | UA parsing | "Chrome", "Safari" |
| `os` | UA parsing | "macOS", "iOS" |
| `platform` | UA + screen | "desktop", "mobile", "tablet" |
| `device_name` | UA parsing | "Mac", "iPhone", "iPad" |
| `country` | Future: GeoIP | "NP", "US" |
| `timezone` | Client-reported | "Asia/Kathmandu" |
| `language` | Accept-Language | "en-US,ne" |
| `login_method` | Endpoint | "password", "passkey", "oauth_google" |
| `risk_score` | Risk Engine | 15 (low) |
| `first_seen` | Session creation | 1750963200.0 |
| `last_seen` | validate() touch | 1750966800.0 |

### Risk Score Computation

```
Base: 0

Same browser as last session:     -10
Same IP as last session:          -10
Known device (seen before):       -20
New browser:                      +15
New country:                      +30
VPN / proxy detected:             +20
Multiple failed attempts (≥3):    +25
New device:                       +15
Off-hours login:                  +10

Range: 0-100
Interpretation:
  0-20   → Low risk (green)
  21-50  → Medium risk (yellow)
  51-75  → High risk (orange)
  76-100 → Critical risk (red)
```

**Rule:** Risk score is computed at login and stored. It is **never** used to block logins. It is reported to the client for display and audit logging only.

---

## 5. Token Registry Design

### Concept

Replace the single `SAATHI_TOKEN` with a registry of named, permissioned tokens. Each service gets its own token with scoped permissions.

### Token Lifecycle

```
Create → Use → Refresh (optional) → Revoke
   ↓       ↓           ↓              ↓
Stored  Checked   Extended        Soft-delete
```

### Default Tokens (auto-created on first run)

| Name | Purpose | Permissions |
|------|---------|-------------|
| `legacy-admin` | Backward compat for SAATHI_TOKEN | `["*"]` |
| `studio` | Video production pipeline | `["/api/v1/studio/*", "/api/v1/render/*"]` |
| `mission-bot` | Automated mission execution | `["/api/v1/missions/*", "/api/v1/agent/*"]` |
| `cli` | Command-line access | `["*"]` |

### API

```python
class TokenRegistry:
    def create(self, user_id: str, name: str, purpose: str = "",
               permissions: list[str] | None = None,
               expires_in_days: int | None = None) -> tuple[str, str]:
        """Returns (token_id, raw_token). Raw token is shown ONCE."""

    def verify(self, raw_token: str) -> dict | None:
        """Validate token and update last_used. Returns token record or None."""

    def revoke(self, token_id: str) -> bool:
        """Soft-delete a token."""

    def list(self, user_id: str) -> list[dict]:
        """All tokens for a user (no secrets)."""

    def check_permission(self, token_id: str, path: str, method: str) -> bool:
        """Does this token have permission for endpoint + method?"""
```

### Migration Path

1. On first Security Store initialization, read `SAATHI_TOKEN` from env
2. Create a `legacy-admin` token with hash of `SAATHI_TOKEN`
3. All existing `x-saathi-token` checks now route through Token Registry
4. New tokens can be created via API/CLI
5. `SAATHI_TOKEN` remains in `.env` for backward compat but is no longer the source of truth

---

## 6. Identity Provider Abstraction

### Architecture

```
IdentityProvider (abstract base)
    ├── name() → str
    ├── authorize_url(redirect_uri, state) → str
    ├── exchange_code(code, redirect_uri) → OAuthToken
    ├── refresh_token(token) → OAuthToken
    ├── get_user_info(token) → UserInfo
    └── diagnostic(error) → str          ← NEW: human-readable error messages

Adapters:
    ├── GoogleIdentityProvider
    ├── AppleIdentityProvider
    ├── GitHubIdentityProvider
    ├── MicrosoftIdentityProvider
    └── TelegramIdentityProvider

Registry:
    IdentityProviderRouter
        ├── register(provider)
        ├── get(name) → IdentityProvider
        ├── list() → list[IdentityProvider]
        └── available() → list[str]       -- providers with configured credentials
```

### Adapter Contract

```python
@dataclass
class OAuthToken:
    access_token: str
    refresh_token: str | None
    expires_at: float | None
    token_type: str = "Bearer"

@dataclass
class UserInfo:
    provider_user_id: str
    email: str | None
    name: str | None
    avatar_url: str | None
    raw: dict          # provider-specific extra fields

class IdentityProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def authorize_url(self, redirect_uri: str, state: str) -> str: ...

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthToken: ...

    @abstractmethod
    async def get_user_info(self, token: OAuthToken) -> UserInfo: ...

    def diagnostic(self, error: Exception) -> str:
        """Convert provider error to human-readable message. Override per provider."""
        return f"{self.name} authentication failed: {error}"
```

### Adding a New Provider

1. Create `saathi/security/adapters/<provider>.py`
2. Subclass `IdentityProvider`
3. Implement 4 abstract methods
4. Register in `IdentityProviderRouter`

No changes to `server.py` OAuth endpoints needed.

---

## 7. Security Timeline Integration

### Design Philosophy

Following the Mission Timeline pattern (`saathi/missions/timeline.py`):
- Append-only, never mutated
- Kinds define the vocabulary of security history
- Metadata stores provider-specific details as JSON

### Event Kinds

```python
SECURITY_EVENT_KINDS = (
    "password_changed",
    "password_reset",
    "passkey_added",
    "passkey_removed",
    "passkey_renamed",
    "session_created",
    "session_revoked",
    "session_rotated",
    "login_success",
    "login_failed",
    "logout",
    "logout_everywhere",
    "token_created",
    "token_revoked",
    "token_used",
    "oauth_connected",
    "oauth_disconnected",
    "security_setting_changed",
    "risk_alert",
    "mfa_enabled",        # future
    "mfa_disabled",       # future
)
```

### Integration with Existing Timeline

The Security Timeline is a **separate store** (`security_events` table) but follows the same API:

```python
security_timeline.record(user_id, "password_changed",
    title="Password changed",
    detail="From Chrome on macOS",
    meta={"browser": "Chrome", "os": "macOS", "ip": "1.2.3.4"})
```

The Security Dashboard queries both:
- Security Timeline for structured security events
- Audit Log for low-level auth attempts

---

## 8. Passkey Diagnostics

### Problem

Current: `Passkey Failed` — no actionable information.

### Solution

Map WebAuthn / browser errors to human-readable diagnostics:

| Error Pattern | Diagnostic Message | Action |
|--------------|-------------------|--------|
| `NotAllowedError` + user cancelled | "You cancelled the biometric prompt." | "Try again when ready." |
| `NotAllowedError` + timeout | "Biometric prompt timed out." | "Try again within 30 seconds." |
| `NotSupportedError` | "Your browser does not support passkeys." | "Use Chrome, Safari, or Edge." |
| `SecurityError` + HTTPS | "Passkeys require a secure HTTPS connection." | "Ensure you're on https://..." |
| `InvalidStateError` | "No passkey found for this device." | "Register a passkey first." |
| `ConstraintError` | "RP ID mismatch." | "Check domain settings." |
| `NotSupportedError` + platform | "Face ID / Touch ID not available." | "Set up biometrics in system settings." |
| WebAuthn `verify_*` exception | "Passkey verification failed." | "Remove and re-register this passkey." |

### Frontend Integration

```javascript
// In passkey.js
const DIAGNOSTICS = {
  "NotAllowedError": {
    userCancelled: "You cancelled the biometric prompt. Try again when ready.",
    timeout: "The biometric prompt timed out. Try again within 30 seconds.",
    default: "Biometric authentication was not allowed. Check your browser settings."
  },
  "NotSupportedError": "Your browser doesn't support passkeys. Use Chrome, Safari, or Edge.",
  "SecurityError": "Passkeys require HTTPS. Ensure you're on a secure connection.",
  "InvalidStateError": "No passkey found. Register one first.",
};
```

---

## 9. Multi-user Architecture (Future-Ready Stubs)

### Current State (v1.2)

- Single user: `users` table has exactly one row (the owner)
- No login page for user selection
- All auth endpoints assume owner context

### Future State (v2.0+)

- Multiple users in `users` table
- Organization-scoped data via `org_id` foreign keys
- RBAC via `roles` + `user_roles` tables
- Team-based access via `teams` + `team_members`

### v1.2 Design Decisions for Future Compatibility

1. **Every table has `user_id`** — even though there's only one user now
2. **Soft deletes everywhere** (`revoked`, `status`) — never hard-delete user data
3. **UUID primary keys** — no auto-increment integers that would collide across instances
4. **JSON metadata fields** — extensible without schema migrations
5. **Organization table exists but is empty** — ready for `org_id` foreign keys
6. **Role table seeded with default roles** — `owner`, `admin`, `member`, `viewer`

### Default Roles (seeded)

```sql
INSERT INTO roles (id, name, permissions, created_at) VALUES
('role-owner',  'Owner',  '["*"]', 1750963200),
('role-admin',  'Admin',  '["read", "write", "delete", "invite"]', 1750963200),
('role-member', 'Member', '["read", "write"]', 1750963200),
('role-viewer', 'Viewer', '["read"]', 1750963200);
```

---

## 10. Migration Plan

### Phase A: Security Store (Backend)

1. Create `saathi/security/` package
2. Implement `SecurityStore` with full schema
3. Migrate existing JSON files on first init:
   - `~/.saathi/sessions.json` → `sessions` table
   - `~/.saathi/passkeys.json` → `passkeys` table
   - `~/.saathi/reset_tokens.json` → `reset_tokens` table
   - `~/.saathi/auth_audit.log` → `audit_log` table
4. Create default user (owner) from env
5. Create `legacy-admin` API token from `SAATHI_TOKEN`

### Phase B: Enhanced Sessions + Risk Engine

1. Update `sessions.py` to use Security Store
2. Add risk scoring to login endpoints
3. Add session intelligence fields

### Phase C: Token Registry

1. Implement `TokenRegistry`
2. Update `server.py` auth middleware to check Token Registry
3. Add token management endpoints
4. Migrate `SAATHI_TOKEN`

### Phase D: Identity Provider Layer

1. Create `IdentityProvider` ABC
2. Implement OAuth skeleton adapters (no credentials yet)
3. Wire into existing OAuth endpoints

### Phase E: Security Timeline

1. Create `SecurityTimeline` store
2. Add `record_security_event()` calls throughout auth endpoints
3. Add `/api/v1/security/timeline` endpoint

### Phase F: Frontend Updates

1. Password Health panel on Security page
2. Security Timeline view
3. Passkey diagnostic messages
4. Token management UI

### Phase G: Tests + Documentation

1. Comprehensive test suite for Security Store
2. Tests for Token Registry, Risk Engine, Identity Provider
3. Migration verification tests
4. Update `AUTH_HARDENING.md` → `AUTH_v1.2.md`

---

## 11. Files to Modify

### Backend

| File | Changes |
|------|---------|
| `saathi/sessions.py` | Backend migrated to Security Store; API unchanged |
| `saathi/passkey.py` | Backend migrated to Security Store; API unchanged |
| `saathi/authsec.py` | Add password health functions; keep hashing/rate limiting |
| `saathi/server.py` | Wire Token Registry into auth middleware; add new endpoints; record security events |
| `saathi/config.py` | Add Security Store path config |

### New Backend Files

| File | Purpose |
|------|---------|
| `saathi/security/__init__.py` | Package init, exports |
| `saathi/security/store.py` | Security Store — SQLite schema + CRUD |
| `saathi/security/registry.py` | Token Registry |
| `saathi/security/risk.py` | Risk Engine |
| `saathi/security/identity.py` | Identity Provider ABC + router |
| `saathi/security/timeline.py` | Security Timeline |
| `saathi/security/health.py` | Password Health calculator |
| `saathi/security/diagnostics.py` | Passkey / auth diagnostic messages |

### Frontend

| File | Changes |
|------|---------|
| `saathi-os/lib/api.js` | Add token registry, security timeline endpoints |
| `saathi-os/lib/passkey.js` | Add diagnostic error mapping |
| `saathi-os/app/security/page.jsx` | Add Password Health, Security Timeline, Token list |

---

## 12. Tests to Add

### Security Store Tests

- `test_store_init_creates_schema`
- `test_store_migrate_sessions_json`
- `test_store_migrate_passkeys_json`
- `test_store_user_crud`
- `test_store_session_crud`
- `test_store_passkey_crud`
- `test_store_api_token_crud`
- `test_store_oauth_identity_crud`
- `test_store_audit_log_append`
- `test_store_security_events_append`

### Token Registry Tests

- `test_registry_create_token`
- `test_registry_verify_token`
- `test_registry_revoke_token`
- `test_registry_list_tokens`
- `test_registry_check_permission_wildcard`
- `test_registry_check_permission_specific`
- `test_registry_reject_expired_token`
- `test_registry_reject_revoked_token`

### Risk Engine Tests

- `test_risk_same_browser_lowers`
- `test_risk_new_country_raises`
- `test_risk_failed_attempts_raise`
- `test_risk_known_device_lowers`
- `test_risk_combined_score`

### Identity Provider Tests

- `test_router_register_provider`
- `test_router_get_provider`
- `test_router_list_available`
- `test_adapter_google_authorize_url`

### Integration Tests

- `test_login_creates_security_event`
- `test_passkey_login_creates_security_event`
- `test_token_auth_via_registry`
- `test_legacy_token_backward_compat`
- `test_password_health_metrics`

---

## 13. Security Checklist

- [ ] Security Store encrypts sensitive fields at rest (future: SQLCipher)
- [ ] Token hashes use same PBKDF2 as passwords (or at least SHA256)
- [ ] Session tokens remain opaque random values
- [ ] All revoked data is soft-deleted (audit trail preserved)
- [ ] Rate limiting covers ALL auth endpoints
- [ ] CORS whitelist remains strict
- [ ] Security headers middleware stays active
- [ ] No secrets logged in audit trail
- [ ] `.env` never written to at runtime (only read)
- [ ] Migration preserves all existing data
- [ ] Backward compat for all existing API clients

---

## 14. Deprecations

### Immediately Deprecated (still works, no longer source of truth)

| Component | Replacement | Migration |
|-----------|-------------|-----------|
| `~/.saathi/sessions.json` | `security.sessions` table | Auto-migrated on first init |
| `~/.saathi/passkeys.json` | `security.passkeys` table | Auto-migrated on first init |
| `~/.saathi/reset_tokens.json` | `security.reset_tokens` table | Auto-migrated on first init |
| `~/.saathi/auth_audit.log` | `security.audit_log` table | Auto-migrated on first init |
| `SAATHI_TOKEN` (global) | `TokenRegistry` | Auto-migrated to `legacy-admin` token |
| `BAADAR_PASSWORD_HASH` in `.env` | `security.passwords` table | Kept in `.env` for bootstrapping; also stored in DB |

### Future Deprecations (v2.0+)

- `BAADAR_PASSWORD` in `.env` → move to Security Store (requires bootstrapping solution)
- Single `_is_authed()` check → per-endpoint permission checks via Token Registry
- `x-saathi-token` header → `Authorization: Bearer <token>` standard

---

## 15. Implementation Order

**Recommended parallel groups:**

**Group A (Backend Core):**
1. `saathi/security/store.py` — Security Store
2. `saathi/security/registry.py` — Token Registry
3. `saathi/security/risk.py` — Risk Engine
4. `saathi/security/timeline.py` — Security Timeline
5. `saathi/security/health.py` — Password Health
6. `saathi/security/identity.py` — Identity Provider skeleton
7. `saathi/security/diagnostics.py` — Diagnostic messages

**Group B (Backend Integration):**
8. Update `saathi/sessions.py` to use Security Store
9. Update `saathi/passkey.py` to use Security Store
10. Update `saathi/authsec.py` with health functions
11. Update `saathi/server.py` with new endpoints and wiring

**Group C (Frontend):**
12. Update `saathi-os/lib/api.js`
13. Update `saathi-os/lib/passkey.js`
14. Update `saathi-os/app/security/page.jsx`

**Group D (Tests & Docs):**
15. Write comprehensive test suite
16. Write `AUTH_v1.2.md` documentation
17. Verify migration and backward compatibility

---

*Architecture designed for SaathiOS Security Platform v1.2*  
*Single-owner today. Enterprise-ready tomorrow. No rewrites.*
