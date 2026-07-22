# Authentication v1.3 — Security Platform Architecture

> **Status:** Design Complete  
> **Base:** v1.2 (production)  
> **Rule:** Evolve only. Never rewrite. Never duplicate. Never break compatibility.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Principles](#2-architecture-principles)
3. [System Map](#3-system-map)
4. [Phase 1 — Mission Security](#4-phase-1--mission-security)
5. [Phase 2 — Identity Registry](#5-phase-2--identity-registry)
6. [Phase 3 — Connector Permissions](#6-phase-3--connector-permissions)
7. [Phase 4 — Security Learning](#7-phase-4--security-learning)
8. [Phase 5 — Recovery Center](#8-phase-5--recovery-center)
9. [Phase 6 — Security Control Room](#9-phase-6--security-control-room)
10. [Phase 7 — Test Infrastructure](#10-phase-7--test-infrastructure)
11. [Phase 8 — CI/CD Pipeline](#11-phase-8--cicd-pipeline)
12. [Database Schema Changes](#12-database-schema-changes)
13. [API Endpoints](#13-api-endpoints)
14. [Frontend Changes](#14-frontend-changes)
15. [Migration Plan](#15-migration-plan)
16. [Files to Create / Modify](#16-files-to-create--modify)
17. [Production Checklist](#17-production-checklist)
18. [Risks & Mitigations](#18-risks--mitigations)
19. [Future Roadmap](#19-future-roadmap)

---

## 1. Executive Summary

Authentication v1.2 built a solid Security Platform on SQLite. v1.3's job is to make Security a **first-class engine** inside SaathiOS — integrated with every Mission, every Connector, every Learning loop, and every Evidence stream.

Security stops being a separate dashboard and becomes:
- A **dimension of Mission Health** (score: 0-1, contributes to overall health)
- A **registry of connected identities** (OAuth accounts, not duplicated from AccountStore)
- A **permission gate on Connectors** (what each account can do, per-mission)
- A **Learning Director** (security events → evidence → recommendations)
- A **Recovery subsystem** (recovery codes, trusted devices, emergency logout)
- A **unified Control Room** (live, no fake metrics)
- A **deterministic test suite** (100% isolated, CI-gated)

All v1.2 APIs remain unchanged. All existing data migrates automatically.

---

## 2. Architecture Principles

| Principle | Enforcement |
|-----------|-------------|
| **Store once, reference everywhere** | Security data lives in `SecurityStore`. Missions, Connectors, and Learning reference it — never duplicate. |
| **Adapter pattern for integration** | Every external system (Mission, Learning, Evidence, Connector) gets a lightweight adapter, not a rewrite. |
| **Registry pattern for discovery** | Identity Registry, Connector Permission Registry, Recovery Registry — all follow the existing `TokenRegistry` pattern. |
| **Event-driven observability** | Security events feed the Timeline, Audit Log, Evidence system, and Event Bus. |
| **CEO approval gate** | All recommendations are `pending` until approved. Nothing auto-executes. |
| **Backward compatibility** | All v1.2 endpoints, tables, and APIs remain functional. New columns have defaults. |

---

## 3. System Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SAATHIOS v1.3 — SECURITY ENGINE                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐ │
│  │ Mission      │◄──►│ Security     │◄──►│ Identity     │◄──►│ Connector │ │
│  │ Engine       │    │ Store        │    │ Registry     │    │ Registry  │ │
│  │ (9 dims)     │    │ (SQLite)     │    │ (oauth_id)   │    │ (perms)   │ │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘    └─────┬─────┘ │
│         │                   │                   │                  │       │
│         ▼                   ▼                   ▼                  ▼       │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐ │
│  │ Evidence     │◄──►│ Learning     │◄──►│ Recovery     │◄──►│ Control   │ │
│  │ Adapter      │    │ Director     │    │ Center       │    │ Room      │ │
│  │ (security)   │    │ (security)   │    │ (codes/devs) │    │ (UI)      │ │
│  └──────────────┘    └──────────────┘    └──────────────┘    └───────────┘ │
│         │                   │                   │                  │       │
│         └───────────────────┴───────────────────┴──────────────────┘       │
│                                    │                                        │
│                                    ▼                                        │
│                           ┌──────────────┐                                 │
│                           │  Event Bus   │                                 │
│                           │  (existing)  │                                 │
│                           └──────────────┘                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Phase 1 — Mission Security

### 4.1 Problem

Mission Health today has 8 dimensions: knowledge, marketing, finance, revenue_tracking, operations, automation, evidence, learning. Security is not one of them. A mission can have zero security practices and still show "healthy."

### 4.2 Design

Add **Security as the 9th dimension** of Mission Health. The score is computed by querying the Security Store — never by storing security state inside the mission.

```python
# saathi/missions/health.py — add to _dimensions()
def _security_score(mission_key: str) -> float:
    """Security health for a mission. Queries Security Store; no local state."""
    from saathi.security.store import get_store
    from saathi.security.health import PasswordHealth
    from saathi.security.registry import TokenRegistry
    from saathi.connectors.accounts import AccountStore
    
    store = get_store()
    owner = store.get_or_create_owner()
    
    scores = []
    
    # 1. Password health (0.0 - 1.0)
    ph = PasswordHealth(store=store)
    pm = ph.metrics(owner)
    if pm["has_password"]:
        scores.append(pm["strength"]["score"] / 4.0)  # normalize to 0-1
    else:
        scores.append(0.0)
    
    # 2. Passkey adoption (0.0 or 1.0)
    pk_count = len(store.passkey_list(owner))
    scores.append(1.0 if pk_count > 0 else 0.0)
    
    # 3. Session hygiene (0.0 - 1.0)
    sessions = store.session_list(owner)
    expired = sum(1 for s in sessions if s.get("expires_at", 0) < time.time())
    total = len(sessions)
    if total > 0:
        scores.append(1.0 - (expired / total))
    else:
        scores.append(0.5)  # neutral if no sessions
    
    # 4. Token hygiene (0.0 - 1.0)
    tokens = store.api_token_list(owner)
    active = sum(1 for t in tokens if not t.get("revoked"))
    total_t = len(tokens)
    if total_t > 0:
        scores.append(active / total_t)
    else:
        scores.append(0.5)  # neutral if no tokens
    
    # 5. Connector security (0.0 - 1.0)
    # Does this mission have accounts with 2FA/scoped permissions?
    accts = AccountStore().list_for_mission(mission_key)
    if accts:
        with_perms = sum(1 for a in accts if a.get("permissions"))
        scores.append(with_perms / len(accts))
    else:
        scores.append(0.5)  # neutral if no connectors
    
    # Average across all security sub-dimensions
    return sum(scores) / len(scores) if scores else 0.0
```

### 4.3 Integration Points

| System | Change |
|--------|--------|
| `saathi/missions/health.py` | Add `_security_score()` + include in `overall` average |
| `saathi/missions/knowledge.py` | Add `"security"` to `NODE_TYPES` (node type 29) |
| `saathi/missions/store.py` | Add `"security"` to default `directors` list in `_SEED` |
| `saathi/evidence/adapters.py` | Add `from_security_audit()` adapter |
| `saathi/ceo_os.py` | Add `_security()` snapshot field |
| `saathi/platform_maturity.py` | Add `security` layer score |

### 4.4 Mission Health Output (updated)

```json
{
  "mission": "mr_yeti",
  "overall": 0.72,
  "dimensions": {
    "knowledge": 0.85,
    "marketing": 0.60,
    "finance": 0.90,
    "operations": 0.75,
    "automation": 0.50,
    "evidence": 0.80,
    "learning": 0.65,
    "security": 0.70
  },
  "weakest": "automation"
}
```

---

## 5. Phase 2 — Identity Registry

### 5.1 Problem

OAuth identities are stored in `SecurityStore.oauth_identities` but:
- Missing fields: `avatar_url`, `verified`, `last_sync`, `connected_at`, `status`
- Not connected to the OAuth callback endpoint in `server.py`
- No unified registry class for querying/manipulating identities

### 5.2 Design Decision: Enhance, Don't Duplicate

The `oauth_identities` table already exists and has the right shape. Instead of creating a parallel table or registry, we:

1. **Add columns** to `oauth_identities` (with defaults for backward compat)
2. **Create `IdentityRegistry`** — a thin wrapper class (same pattern as `TokenRegistry`)
3. **Connect the OAuth callback** in `server.py` to `IdentityRegistry.connect()`

### 5.3 Schema Changes

```sql
-- Add to oauth_identities (all nullable/with defaults for migration)
ALTER TABLE oauth_identities ADD COLUMN avatar_url TEXT;
ALTER TABLE oauth_identities ADD COLUMN verified INTEGER DEFAULT 0;
ALTER TABLE oauth_identities ADD COLUMN last_sync REAL DEFAULT 0;
ALTER TABLE oauth_identities ADD COLUMN connected_at REAL DEFAULT 0;
ALTER TABLE oauth_identities ADD COLUMN status TEXT DEFAULT 'active';
ALTER TABLE oauth_identities ADD COLUMN metadata TEXT DEFAULT '{}';
```

### 5.4 Identity Registry API

```python
# saathi/security/identity_registry.py
class IdentityRegistry:
    def __init__(self, store=None):
        self.store = store or get_store()
    
    def connect(self, user_id, provider, provider_user_id, email, name,
                avatar_url=None, verified=False, access_token=None,
                refresh_token=None, expires_at=None, metadata=None) -> str:
        """Upsert an identity. Returns identity ID."""
    
    def list(self, user_id, status=None) -> list[dict]:
        """List connected identities for a user."""
    
    def get(self, identity_id) -> dict | None:
        """Get a single identity by ID."""
    
    def disconnect(self, identity_id) -> bool:
        """Soft-delete (set status='disconnected')."""
    
    def sync(self, identity_id, access_token=None, refresh_token=None,
             expires_at=None, metadata=None) -> bool:
        """Update tokens and metadata after refresh."""
    
    def diagnostic(self, provider, error_code) -> str:
        """Human-readable error for this provider."""
```

### 5.5 OAuth Callback Wiring

```python
# saathi/server.py — in oauth_callback endpoint
from saathi.security.identity_registry import IdentityRegistry

@router.get("/api/v1/auth/oauth/callback")
async def oauth_callback(request: Request):
    # ... validate state ...
    
    # Exchange code for tokens via IdentityProvider
    router = default_router()
    provider = router.get(state["provider"])
    token = await provider.exchange_code(code, state["redirect_uri"])
    user_info = await provider.get_user_info(token)
    
    # Store in Identity Registry
    reg = IdentityRegistry()
    identity_id = reg.connect(
        user_id=get_store().get_or_create_owner(),
        provider=state["provider"],
        provider_user_id=user_info.provider_user_id,
        email=user_info.email,
        name=user_info.name,
        avatar_url=user_info.avatar_url,
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        expires_at=token.expires_at,
        metadata=user_info.raw,
    )
    
    # Also upsert into AccountStore for connector use
    from saathi.connectors.accounts import AccountStore
    AccountStore().upsert_oauth_identity(identity_id, ...)
    
    return {"ok": True, "identity_id": identity_id}
```

---

## 6. Phase 3 — Connector Permissions

### 6.1 Problem

Connector accounts exist in `AccountStore` but:
- `scopes` column stores OAuth scopes (provider-defined) but is not validated
- No Saathi-native capability permissions exist
- No per-mission permission scoping
- `ConnectorManager.execute()` does not check permissions before running

### 6.2 Design Decision: Permissions in AccountStore, Not SecurityStore

`AccountStore` already couples `provider + scopes + missions + status + secret`. It is the natural home for permissions. `SecurityStore` handles user identity and OAuth tokens. We keep this boundary clean.

### 6.3 Permission Model

```json
// Stored in AccountStore.permissions (JSON column)
[
  "social.post",
  "social.schedule",
  "email.send",
  "mission:hcg video.upload",
  "mission:pielts analytics.read"
]
```

**Rules:**
- Plain capability = global grant (any mission can use)
- `mission:{key} capability` = scoped to that mission only
- `*` = all capabilities (admin)

### 6.4 Permission Check

```python
# saathi/connectors/permissions.py
from saathi.connectors.catalog import CAPABILITIES

def check_permission(account: dict, capability: str, mission: str = "") -> bool:
    perms = account.get("permissions", [])
    if "*" in perms:
        return True
    if capability in perms:
        return True
    if mission and f"mission:{mission} {capability}" in perms:
        return True
    # Also check legacy OAuth scopes
    scopes = account.get("scopes", [])
    required_scope = CAPABILITIES.get(capability, {}).get("required_scope")
    if required_scope and required_scope in scopes:
        return True
    return False
```

### 6.5 Enforcement Points

| Layer | Where | Action |
|-------|-------|--------|
| `ConnectorManager.execute()` | `saathi/connectors/manager.py:50-66` | Add `check_permission()` before dispatch |
| `ConnectorRegistry.execute()` | `saathi/infrastructure/connectors/registry.py` | Add permission check when `account_id` provided |
| Server endpoint | `POST /api/v1/connectors/execute` | Return 403 if permission denied |

### 6.6 API Endpoints

```
GET  /api/v1/connectors/accounts/{id}/permissions
POST /api/v1/connectors/accounts/{id}/permissions  {permissions: [...]}
GET  /api/v1/connectors/capabilities               # List all capabilities + required scopes
```

---

## 7. Phase 4 — Security Learning

### 7.1 Problem

Security events (failed logins, expired passwords, unused tokens, high-risk sessions) are recorded in the Timeline but never fed into the Learning Engine. There is no Security Learning Director.

### 7.2 Design

Follow the exact same pattern as the three existing Learning Directors (Technical, Educational, Business).

### 7.3 Security Learning Director

```python
# saathi/learning/directors.py — add SecurityLearningDirector
class SecurityLearningDirector:
    """Generates security recommendations from timeline events and evidence."""
    
    def analyze(self, since_days=7) -> list[Recommendation]:
        from saathi.security.store import get_store
        from saathi.security.health import PasswordHealth
        from saathi.security.timeline import SecurityTimeline
        
        store = get_store()
        owner = store.get_or_create_owner()
        
        recs = []
        
        # 1. Password age check
        ph = PasswordHealth(store=store)
        pm = ph.metrics(owner)
        if pm["status"] == "overdue":
            recs.append(Recommendation(
                category="security",
                priority="high",
                problem=f"Password is {pm['age_days']} days old",
                recommendation="Rotate your password. It's past the 90-day rotation window.",
                affected_director="security",
                requires_approval=True,
            ))
        
        # 2. Failed login pattern
        timeline = SecurityTimeline(store=store)
        events = timeline.list(owner, since=time.time() - since_days * 86400)
        failed_logins = [e for e in events if e["kind"] == "login_failed"]
        if len(failed_logins) >= 3:
            recs.append(Recommendation(
                category="security",
                priority="high",
                problem=f"{len(failed_logins)} failed login attempts in {since_days} days",
                recommendation="Enable passkeys for biometric login to prevent brute-force attacks.",
                affected_director="security",
                requires_approval=True,
            ))
        
        # 3. Unused API tokens
        tokens = store.api_token_list(owner)
        unused = [t for t in tokens if not t.get("revoked") and 
                  (not t.get("last_used_at") or t["last_used_at"] < time.time() - 30 * 86400)]
        if len(unused) >= 1:
            recs.append(Recommendation(
                category="security",
                priority="medium",
                problem=f"{len(unused)} API tokens unused for 30+ days",
                recommendation="Review and revoke unused API tokens to reduce attack surface.",
                affected_director="security",
                requires_approval=True,
            ))
        
        # 4. No passkey
        if not store.passkey_list(owner):
            recs.append(Recommendation(
                category="security",
                priority="medium",
                problem="No passkeys registered",
                recommendation="Set up Face ID / Touch ID for passwordless login.",
                affected_director="security",
                requires_approval=True,
            ))
        
        # 5. High-risk sessions
        risk_events = [e for e in events if e.get("meta", {}).get("risk_score", 0) > 70]
        if risk_events:
            recs.append(Recommendation(
                category="security",
                priority="high",
                problem=f"{len(risk_events)} high-risk login events detected",
                recommendation="Review recent sessions and revoke any unrecognized devices.",
                affected_director="security",
                requires_approval=True,
            ))
        
        return recs
```

### 7.4 Evidence Integration

```python
# saathi/evidence/adapters.py — add security adapter
def from_security_event(ev: dict) -> list[Evidence]:
    return [Evidence(
        department="security",
        project=ev.get("mission", "saathi"),
        episode=ev.get("event_id", ""),
        director="security",
        status="ready",
        metrics={
            "kind": ev.get("kind"),
            "risk_score": ev.get("risk_score", 0),
            "severity": "high" if ev.get("risk_score", 0) > 70 else "medium",
        },
        timestamp=ev.get("ts", time.time()),
    )]

ADAPTERS["security"] = from_security_event
```

### 7.5 Failure Classification

```python
# saathi/learning/failures.py — add SECURITY category
class FailureCategory(Enum):
    # ... existing categories ...
    SECURITY = "security"

SECURITY_PATTERNS = [
    (r"unauthorized|authentication|login failed|wrong password", FailureCategory.SECURITY),
    (r"csrf|xss|injection|breach|exploit|vulnerability", FailureCategory.SECURITY),
    (r"rate.?limit|too many attempts", FailureCategory.SECURITY),
    (r"token.*invalid|expired.*token|revoked", FailureCategory.SECURITY),
]
```

### 7.6 Learning Engine Routing

```python
# saathi/learning/engine.py — add to route_lesson()
def route_lesson(lesson: Lesson) -> list[LearningOutput]:
    outputs = [LearningOutput.IMPROVEMENT_PROPOSAL]
    
    if lesson.failure_category == FailureCategory.SECURITY:
        outputs.append(LearningOutput.ENGINEERING_TASK)
        if lesson.confidence >= 0.7:
            outputs.append(LearningOutput.ADR_CANDIDATE)
    
    # ... existing routing ...
    return outputs
```

---

## 8. Phase 5 — Recovery Center

### 8.1 Design

A Recovery subsystem with three pillars:
1. **Trusted Devices** — devices that can skip 2FA / passkey verification
2. **Recovery Codes** — single-use codes for account recovery
3. **Emergency Logout** — instant revocation of all sessions + tokens

### 8.2 Schema

```sql
-- Recovery codes
CREATE TABLE recovery_codes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    code_hash TEXT NOT NULL UNIQUE,  -- SHA256 of the raw code
    used INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    used_at REAL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX idx_recovery_codes_user ON recovery_codes(user_id, used);

-- Trusted devices
CREATE TABLE trusted_devices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,  -- browser+os+screen hash
    browser TEXT,
    os TEXT,
    ip_address TEXT,
    device_name TEXT,
    last_seen REAL,
    status TEXT DEFAULT 'active',  -- active | revoked
    created_at REAL NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE (user_id, fingerprint)
);
CREATE INDEX idx_trusted_devices_user ON trusted_devices(user_id, status);

-- Recovery timeline (uses security_events with kind="recovery_*")
```

### 8.3 Recovery Manager

```python
# saathi/security/recovery.py
class RecoveryManager:
    def __init__(self, store=None):
        self.store = store or get_store()
    
    def generate_codes(self, user_id, count=8) -> list[str]:
        """Generate recovery codes. Returns raw codes (shown once)."""
        import secrets, hashlib
        codes = []
        for _ in range(count):
            raw = secrets.token_hex(4)  # 8 chars, e.g., "a3f9b2c1"
            code_hash = hashlib.sha256(raw.encode()).hexdigest()
            self.store.recovery_code_create(user_id, code_hash)
            codes.append(raw)
        return codes
    
    def verify_code(self, user_id, code: str) -> bool:
        """Verify a recovery code. Consumes it (one-time use)."""
        import hashlib
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        return self.store.recovery_code_consume(user_id, code_hash)
    
    def trust_device(self, user_id, fingerprint, browser, os, ip, device_name) -> bool:
        """Mark a device as trusted."""
        return self.store.trusted_device_add(user_id, fingerprint, browser, os, ip, device_name)
    
    def is_trusted_device(self, user_id, fingerprint) -> bool:
        """Check if device is trusted."""
        return self.store.trusted_device_check(user_id, fingerprint)
    
    def emergency_logout(self, user_id) -> dict:
        """Revoke ALL sessions and tokens. Return counts."""
        sessions_revoked = self.store.session_revoke_all(user_id)
        tokens_revoked = self.store.api_token_revoke_all(user_id)
        return {"sessions_revoked": sessions_revoked, "tokens_revoked": tokens_revoked}
```

### 8.4 API Endpoints

```
POST /api/v1/security/recovery/codes        → generate recovery codes
POST /api/v1/security/recovery/verify       → verify a recovery code
POST /api/v1/security/devices/{fp}/trust    → trust a device
DELETE /api/v1/security/devices/{fp}/trust  → revoke trust
POST /api/v1/security/emergency-logout      → revoke everything
GET  /api/v1/security/recovery/status       → recovery codes remaining, trusted devices
```

---

## 9. Phase 6 — Security Control Room

### 9.1 Design

Merge all existing security views (Timeline, Health, Tokens, Sessions, Passkeys, Identity Providers) into a **unified Control Room** with:
- Overall Security Score (0-100)
- Mission Security (per-mission health contribution)
- Connected Accounts (with permission status)
- Live Sessions (with risk scores)
- Passkeys
- Risk Events (high-risk logins)
- Recent Timeline
- Security Recommendations (from Learning Director)
- API Tokens
- Password Health
- Recovery Status

### 9.2 Backend Endpoint

```python
@app.get("/api/v1/security/control-room")
def security_control_room(request: Request):
    """Unified security dashboard — all data in one call."""
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    
    from saathi.security.store import get_store
    from saathi.security.health import PasswordHealth
    from saathi.security.timeline import SecurityTimeline
    from saathi.security.registry import TokenRegistry
    from saathi.security.recovery import RecoveryManager
    from saathi.security.identity_registry import IdentityRegistry
    from saathi.connectors.accounts import AccountStore
    from saathi.learning.directors import SecurityLearningDirector
    
    store = get_store()
    owner = store.get_or_create_owner()
    
    # Compute overall security score
    ph = PasswordHealth(store=store)
    pm = ph.metrics(owner)
    sessions = store.session_list(owner)
    passkeys = store.passkey_list(owner)
    tokens = store.api_token_list(owner)
    
    score = 0
    if pm["has_password"]:
        score += 20 * (pm["strength"]["score"] / 4.0)
    if passkeys:
        score += 30
    if sessions:
        score += 10
    if tokens:
        score += 10
    if pm["status"] != "overdue":
        score += 20
    score = min(100, int(score))
    
    return {
        "overall_score": score,
        "status": "strong" if score >= 80 else "fair" if score >= 50 else "at_risk",
        "password_health": pm,
        "sessions": [{"id": s["id"], "browser": s["browser"], "os": s["os"],
                      "risk_score": s.get("risk_score", 0), "current": False,
                      "last_seen": s["last_seen"]} for s in sessions],
        "passkeys": [{"id": p["id"], "device_name": p["device_name"],
                      "browser": p["browser"]} for p in passkeys],
        "tokens": [{"id": t["id"], "name": t["name"],
                    "permissions": t.get("permissions", [])} for t in tokens],
        "identities": IdentityRegistry(store=store).list(owner),
        "accounts": AccountStore().list_all(),
        "timeline": SecurityTimeline(store=store).list(owner, limit=20),
        "recommendations": SecurityLearningDirector().analyze(since_days=7),
        "recovery": RecoveryManager(store=store).status(owner),
    }
```

### 9.3 Frontend

Replace the tabbed Security page with a **Control Room** layout:
- Top: Overall score + status badge
- Left column: Password Health, Recovery Status, API Tokens
- Center: Live Sessions (with risk colors), Passkeys, Connected Accounts
- Right column: Security Recommendations, Recent Timeline
- Bottom: Risk Events (filtered to score > 50)

---

## 10. Phase 7 — Test Infrastructure

### 10.1 Root Cause

`test_auth_v1.py` fails as a suite because:
1. `_clean_stores` does NOT delete `~/.saathi/security.db`
2. Does NOT call `close_store()` to reset the singleton
3. `TestClient(app)` shares the global app singleton across tests

### 10.2 Fix

```python
# tests/test_auth_v1.py — replace _clean_stores fixture
@pytest.fixture(autouse=True)
def _clean_stores(tmp_path, monkeypatch):
    from saathi import passkey, authsec
    from saathi.security import store as _store_mod
    from saathi import sessions
    
    # Close any existing singleton
    _store_mod.close_store()
    _store_mod._default_store = None
    
    # Create fresh temp store
    fresh = _store_mod.SecurityStore(db_path=tmp_path / "security.db")
    fresh.migrate_from_legacy()
    
    # Monkeypatch get_store to return the fresh instance
    monkeypatch.setattr(_store_mod, "get_store", lambda _dp=None: fresh)
    monkeypatch.setattr(sessions, "_store", lambda: fresh)
    
    # Clean legacy files
    for p in (Path.home() / ".saathi").glob("*.json"):
        p.unlink(missing_ok=True)
    (Path.home() / ".saathi" / "auth_audit.log").unlink(missing_ok=True)
    (Path.home() / ".saathi" / "security.db").unlink(missing_ok=True)
    (Path.home() / ".saathi" / "oauth_states.json").unlink(missing_ok=True)
    
    authsec._WINDOWS.clear()
    passkey._pending.clear()
    
    yield
    
    fresh.close()
    _store_mod.close_store()
    _store_mod._default_store = None
```

### 10.3 Add Missing Singleton Resets

```python
# saathi/security/registry.py — add
_registry_instance = None

def get_registry(store=None):
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = TokenRegistry(store)
    return _registry_instance

def close_registry():
    global _registry_instance
    _registry_instance = None

# saathi/security/timeline.py — add
_timeline_instance = None

def get_timeline(store=None):
    global _timeline_instance
    if _timeline_instance is None:
        _timeline_instance = SecurityTimeline(store)
    return _timeline_instance

def close_timeline():
    global _timeline_instance
    _timeline_instance = None
```

### 10.4 Test Coverage Target

| Suite | Tests | Target |
|-------|-------|--------|
| `test_auth_v12.py` | 40 | All pass (already ✅) |
| `test_auth_v1.py` | 28 | All pass after fix |
| New v1.3 tests | ~25 | All pass |
| **Total** | **~93** | **100% deterministic** |

---

## 11. Phase 8 — CI/CD Pipeline

### 11.1 GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [master, main]
  pull_request:
    branches: [master, main]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -e ".[voice,generation]" pytest pytest-cov ruff mypy
      - run: ruff check saathi/ tests/
      - run: mypy saathi/ --ignore-missing-imports --no-error-summary || true
      - run: pytest tests/test_auth_v12.py tests/test_auth_v1.py -v --cov=saathi --cov-report=xml --cov-report=term
      - uses: codecov/codecov-action@v4
        with: { files: ./coverage.xml, fail_ci_if_error: false }

  frontend-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd saathi-os && npm ci
      - run: cd saathi-os && npm run build
```

### 11.2 pyproject.toml Coverage Config

```toml
[tool.coverage.run]
source = ["saathi"]
omit = ["tests/*", "saathi-os/*", "scripts/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "pass",
]
fail_under = 60
```

---

## 12. Database Schema Changes

### 12.1 v1.2 → v1.3 Migration (auto-run in SecurityStore.__init__)

```sql
-- oauth_identities enhancements
ALTER TABLE oauth_identities ADD COLUMN avatar_url TEXT;
ALTER TABLE oauth_identities ADD COLUMN verified INTEGER DEFAULT 0;
ALTER TABLE oauth_identities ADD COLUMN last_sync REAL DEFAULT 0;
ALTER TABLE oauth_identities ADD COLUMN connected_at REAL DEFAULT 0;
ALTER TABLE oauth_identities ADD COLUMN status TEXT DEFAULT 'active';
ALTER TABLE oauth_identities ADD COLUMN metadata TEXT DEFAULT '{}';

-- recovery_codes (new table)
CREATE TABLE IF NOT EXISTS recovery_codes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    code_hash TEXT NOT NULL UNIQUE,
    used INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    used_at REAL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_recovery_codes_user ON recovery_codes(user_id, used);

-- trusted_devices (new table)
CREATE TABLE IF NOT EXISTS trusted_devices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    browser TEXT,
    os TEXT,
    ip_address TEXT,
    device_name TEXT,
    last_seen REAL,
    status TEXT DEFAULT 'active',
    created_at REAL NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE (user_id, fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_trusted_devices_user ON trusted_devices(user_id, status);

-- Add security event kinds (insert if not exists)
INSERT OR IGNORE INTO security_events (kind) VALUES
    ('recovery_code_generated'),
    ('recovery_code_used'),
    ('device_trusted'),
    ('device_revoked'),
    ('emergency_logout'),
    ('permission_denied'),
    ('identity_connected'),
    ('identity_disconnected');
```

### 12.2 AccountStore Migration

```sql
-- In ~/.saathi/accounts.db
ALTER TABLE accounts ADD COLUMN permissions TEXT DEFAULT '[]';
```

---

## 13. API Endpoints

### 13.1 New Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/security/control-room` | Session | Unified dashboard |
| POST | `/api/v1/security/recovery/codes` | Session | Generate recovery codes |
| POST | `/api/v1/security/recovery/verify` | Public | Verify recovery code |
| GET | `/api/v1/security/recovery/status` | Session | Recovery status |
| POST | `/api/v1/security/devices/{fp}/trust` | Session | Trust device |
| DELETE | `/api/v1/security/devices/{fp}/trust` | Session | Revoke trust |
| POST | `/api/v1/security/emergency-logout` | Session | Revoke all sessions |
| GET | `/api/v1/connectors/accounts/{id}/permissions` | Session | Get permissions |
| POST | `/api/v1/connectors/accounts/{id}/permissions` | Session | Set permissions |
| GET | `/api/v1/connectors/capabilities` | Session | List capabilities |
| GET | `/api/v1/missions/{key}/health` | Session | Mission health (now includes security) |

### 13.2 Modified Endpoints

| Method | Path | Change |
|--------|------|--------|
| GET | `/api/v1/auth/oauth/callback` | Now exchanges code, saves identity via IdentityRegistry |
| POST | `/api/v1/connectors/execute` | Now checks permissions before execution |

---

## 14. Frontend Changes

### 14.1 New API Functions (lib/api.js)

```javascript
export async function fetchControlRoom() {
  const r = await afetch(`${API_BASE}/api/v1/security/control-room`, { cache: "no-store" });
  if (!r.ok) throw new Error(`control-room ${r.status}`);
  return r.json();
}

export async function generateRecoveryCodes() {
  const r = await afetch(`${API_BASE}/api/v1/security/recovery/codes`, { method: "POST" });
  return r.json();
}

export async function verifyRecoveryCode(code) {
  const r = await afetch(`${API_BASE}/api/v1/security/recovery/verify`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  return r.json();
}

export async function trustDevice(fingerprint) {
  const r = await afetch(`${API_BASE}/api/v1/security/devices/${fingerprint}/trust`, { method: "POST" });
  return r.json();
}

export async function emergencyLogout() {
  const r = await afetch(`${API_BASE}/api/v1/security/emergency-logout`, { method: "POST" });
  return r.json();
}

export async function fetchConnectorPermissions(accountId) {
  const r = await afetch(`${API_BASE}/api/v1/connectors/accounts/${accountId}/permissions`, { cache: "no-store" });
  return r.json();
}

export async function setConnectorPermissions(accountId, permissions) {
  const r = await afetch(`${API_BASE}/api/v1/connectors/accounts/${accountId}/permissions`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ permissions }),
  });
  return r.json();
}
```

### 14.2 New Page: Security Control Room

Replace `app/security/page.jsx` with a unified Control Room:
- **Score Card**: Large number (0-100) with color-coded status
- **Recommendations Panel**: List from SecurityLearningDirector (click to approve/reject)
- **Sessions Panel**: Live sessions with risk indicators
- **Passkeys Panel**: Registered passkeys
- **Connected Accounts**: OAuth identities + connector accounts with permission badges
- **API Tokens**: Scoped tokens with revoke
- **Password Health**: Strength, age, rotation countdown
- **Recovery Status**: Codes remaining, trusted devices
- **Timeline**: Last 20 events

### 14.3 New Component: SecurityRecommendation

```jsx
function SecurityRecommendation({ rec, onApprove, onDismiss }) {
  const color = rec.priority === "high" ? RED : rec.priority === "medium" ? AMBER : TEAL;
  return (
    <div style={{ padding: 12, borderRadius: 10, background: "rgba(255,255,255,0.04)", borderLeft: `3px solid ${color}` }}>
      <div style={{ fontSize: 13, fontWeight: 600 }}>{rec.problem}</div>
      <div style={{ fontSize: 12, opacity: 0.6, marginTop: 4 }}>{rec.recommendation}</div>
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button onClick={onApprove} style={{ ...btn(TEAL), marginTop: 0, width: "auto", padding: "6px 12px", fontSize: 12 }}>Approve</button>
        <button onClick={onDismiss} style={{ ...btn("transparent"), marginTop: 0, width: "auto", padding: "6px 12px", fontSize: 12 }}>Dismiss</button>
      </div>
    </div>
  );
}
```

---

## 15. Migration Plan

| Step | Action | Risk |
|------|--------|------|
| 1 | Deploy v1.3 backend (no breaking changes) | Low — new columns have defaults |
| 2 | Auto-migrate SecurityStore schema on startup | Low — `IF NOT EXISTS` guards |
| 3 | Auto-migrate AccountStore schema on startup | Low — same |
| 4 | Verify v1.2 endpoints still work | Low — regression tests |
| 5 | Deploy frontend Control Room | Low — new page, old page can coexist briefly |
| 6 | Run Security Learning Director manually | Low — no auto-execution |
| 7 | Monitor migration logs | Low |
| 8 | Enable CI pipeline | Low |

---

## 16. Files to Create / Modify

### Files to Create (14)

| File | Purpose |
|------|---------|
| `saathi/security/identity_registry.py` | IdentityRegistry class (wraps oauth_identities) |
| `saathi/security/recovery.py` | RecoveryManager (codes, trusted devices, emergency logout) |
| `saathi/connectors/permissions.py` | Permission check logic |
| `saathi/learning/directors.py` | SecurityLearningDirector (add to existing file) |
| `saathi/evidence/adapters.py` | `from_security_event()` adapter (add to existing) |
| `tests/test_auth_v13.py` | Full v1.3 test suite |
| `tests/test_recovery.py` | Recovery subsystem tests |
| `tests/test_connector_permissions.py` | Permission enforcement tests |
| `.github/workflows/ci.yml` | CI/CD pipeline |
| `AUTH_v1.3.md` | Implementation report |

### Files to Modify (18)

| File | Change |
|------|--------|
| `saathi/security/store.py` | Add recovery_codes + trusted_devices tables; add CRUD methods |
| `saathi/security/registry.py` | Add `close_registry()` singleton helper |
| `saathi/security/timeline.py` | Add `close_timeline()` singleton helper |
| `saathi/server.py` | Wire OAuth callback to IdentityRegistry; add new endpoints |
| `saathi/sessions.py` | Ensure `_store()` respects monkeypatched get_store in tests |
| `saathi/missions/health.py` | Add `_security_score()` + include in overall |
| `saathi/missions/knowledge.py` | Add `"security"` to NODE_TYPES |
| `saathi/learning/failures.py` | Add `SECURITY` failure category |
| `saathi/learning/engine.py` | Add security lesson routing |
| `saathi/ceo_os.py` | Add `_security()` snapshot |
| `saathi/platform_maturity.py` | Add `security` layer score |
| `saathi/connectors/manager.py` | Add permission check before execute |
| `saathi/connectors/accounts.py` | Add `permissions` column + CRUD |
| `saathi-os/app/security/page.jsx` | Replace with Control Room |
| `saathi-os/lib/api.js` | Add new API functions |
| `tests/test_auth_v1.py` | Fix `_clean_stores` fixture for SQLite isolation |
| `pyproject.toml` | Add coverage config |
| `AUTH_v1.2_ARCHITECTURE.md` | Mark superseded, reference v1.3 |

---

## 17. Production Checklist

- [ ] All v1.2 endpoints still pass (regression test)
- [ ] New schema migrations run cleanly on existing databases
- [ ] OAuth callback connects to IdentityRegistry (test with Google skeleton)
- [ ] Connector permission checks gate all execute calls
- [ ] Security Learning Director generates recommendations (manual trigger)
- [ ] Recovery codes generate and verify correctly
- [ ] Emergency logout revokes all sessions + tokens
- [ ] Control Room loads all data in < 500ms
- [ ] CI pipeline runs green on push
- [ ] No plaintext secrets in new code
- [ ] All new tables have indexes
- [ ] Frontend build succeeds (`npm run build`)

---

## 18. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| OAuth callback breaks existing skeleton | Medium | Medium | Keep old callback as fallback; new path is `/api/v1/auth/oauth/callback/v2` |
| Connector permission check breaks existing accounts | Medium | High | Default permissions = `["*"]` for existing accounts (grandfathered) |
| Recovery code hash collision | Low | High | Use SHA256 + 8-char random; 1 in 4 billion collision chance |
| Mission health score drops due to new dimension | Medium | Low | Security dimension starts at 0.5 (neutral) until data populates |
| CI pipeline reveals hidden test failures | High | Low | Fix tests incrementally; don't block merge on pre-existing failures |
| Frontend bundle size increases | Medium | Low | Lazy-load Control Room components |

---

## 19. Future Roadmap

| Version | Feature |
|---------|---------|
| v1.3.1 | Trusted Contacts recovery (async email to trusted contact) |
| v1.3.2 | Security alert webhooks (notify on high-risk login) |
| v1.3.3 | Geo-fencing (alert on logins from new countries) |
| v1.4 | Multi-user: orgs, teams, RBAC enforcement |
| v1.5 | Hardware security keys (YubiKey support) |
| v1.6 | Automated security audit (weekly scan + report) |

---

*Security v1.3: From authentication to protection.*
