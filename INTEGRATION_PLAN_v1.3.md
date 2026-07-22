# Security v1.3 — Integration Plan

> **Status:** Architecture Audit Complete → Integration Plan  
> **Base:** v1.2 (production)  
> **Rule:** Evolve only. Never rewrite. Never duplicate. Never break compatibility.

---

## Architecture Audit Summary

### Systems Audited

| System | Files Read | Key Finding |
|--------|-----------|-------------|
| **Security Store** | `saathi/security/store.py` | 16 tables, singleton pattern, SQLite. `close_store()` exists. |
| **Token Registry** | `saathi/security/registry.py` | Permission patterns, legacy migration. Needs `close_registry()`. |
| **Security Timeline** | `saathi/security/timeline.py` | 18 event kinds, append-only. Needs `close_timeline()`. |
| **Mission Engine** | `saathi/missions/*.py` | 8-dimension health, Knowledge Graph nodes, Timeline store. |
| **Learning Engine** | `saathi/learning/*.py` | 3 Directors, deterministic pipeline, Recommendation store. |
| **Evidence System** | `saathi/evidence/*.py` | Universal schema, adapters per department, ingestion pipeline. |
| **Event Bus** | `saathi/events/*.py`, `saathi/events.py` | **Two buses**: Universal (SQLite, business) + Fabric (in-memory, infra). |
| **Knowledge Graph** | `saathi/missions/knowledge.py` | 29 node types, flat store, coverage scoring. |
| **Mission Timeline** | `saathi/missions/timeline.py` | 12 kinds, per-mission, no Security integration today. |
| **Connectors** | `saathi/connectors/*.py`, `saathi/infrastructure/connectors/*.py` | Two layers: AccountStore (legacy) + ConnectorRegistry (infra). |
| **CEO OS** | `saathi/ceo_os.py`, `saathi/platform_maturity.py` | Snapshot pattern, 5 maturity layers. |
| **Test Infra** | `tests/test_auth_v*.py` | v1.1 tests lack SQLite isolation. v1.2 tests use `tmp_path`. No CI. |

### Critical Architecture Decisions

1. **Event Bus is the integration backbone.** Security emits to the Universal Bus. The bus routes to Evidence. Learning subscribes to Evidence. Mission Timeline mirrors when `mission_id` is known. **No direct calls between subsystems.**

2. **Knowledge Graph is flat, not a graph.** Nodes have no edges. Relations are implicit via shared `mission_id`. Adding security node types requires only adding strings to `NODE_TYPES` — no schema migration.

3. **Two Connector layers exist.** `AccountStore` (SQLite, encrypted, mission-scoped) and `ConnectorRegistry` (infra, health-ranked). Permissions live in `AccountStore` because it already couples `provider + secret + missions + status`.

4. **Mission Timeline and Security Timeline are separate databases.** They share philosophy but no code. Bridge by dual-writing when `mission_id` is available.

---

## Integration Plan

### 1. Event-Driven Security Architecture

```
Security Action
      ↓
Security Store (persist)
      ↓
Emit to Universal Event Bus  ←──  type="security.*", source="security"
      ↓
      ├──────► Evidence Store  (via saathi/businesses/security.py handler)
      ├──────► Mission Timeline  (when mission_id known)
      ├──────► Knowledge Graph  (upsert security nodes)
      └──────► Subscribers  (Learning Director, CEO OS, Alerts)
```

### 2. Security Event Types

| Event Type | When Emitted | Payload |
|-----------|-------------|---------|
| `security.login.success` | After successful login | `{method, browser, os, ip, risk_score}` |
| `security.login.failed` | After failed login | `{reason, ip, attempt_count}` |
| `security.password.changed` | After password change | `{method, strength_score}` |
| `security.passkey.registered` | After passkey creation | `{device_name, browser, platform}` |
| `security.passkey.used` | After passkey auth | `{device_name, risk_score}` |
| `security.token.created` | After API token creation | `{name, permissions, expires_at}` |
| `security.token.revoked` | After token revocation | `{name, reason}` |
| `security.oauth.connected` | After OAuth identity link | `{provider, email, scopes}` |
| `security.oauth.disconnected` | After OAuth unlink | `{provider, reason}` |
| `security.session.revoked` | After session revocation | `{session_id, browser, reason}` |
| `security.recovery.code_used` | After recovery code verify | `{remaining}` |
| `security.device.trusted` | After device trust | `{fingerprint, browser, os}` |
| `security.permission.changed` | After connector permission update | `{account_id, provider, permissions}` |
| `security.risk.alert` | When risk score > 70 | `{risk_score, factors, ip, browser}` |

### 3. Business Handler (saathi/businesses/security.py)

All `security.*` events route through the Universal Bus to the Evidence Store:

```python
# saathi/businesses/security.py
from saathi.evidence.schema import Evidence
import time

def handle(event_type: str, payload: dict, *, subject: str = "") -> list[Evidence]:
    p = payload or {}
    base = {
        "department": "security",
        "project": p.get("mission", "platform"),
        "episode": subject or p.get("event_id", ""),
        "director": "security",
        "status": "ready",
        "timestamp": time.time(),
    }
    
    if event_type == "security.login.success":
        return [Evidence(**base, metrics={
            "method": p.get("method"),
            "browser": p.get("browser"),
            "os": p.get("os"),
            "risk_score": p.get("risk_score", 0),
            "ip": p.get("ip"),
        })]
    
    if event_type == "security.login.failed":
        return [Evidence(**base, status="alert", metrics={
            "reason": p.get("reason"),
            "attempt_count": p.get("attempt_count", 1),
            "ip": p.get("ip"),
        })]
    
    if event_type == "security.risk.alert":
        return [Evidence(**base, status="alert", metrics={
            "risk_score": p.get("risk_score"),
            "factors": p.get("factors", []),
            "severity": "high" if p.get("risk_score", 0) > 80 else "medium",
        })]
    
    if event_type in ("security.token.created", "security.token.revoked"):
        return [Evidence(**base, metrics={
            "name": p.get("name"),
            "permissions_count": len(p.get("permissions", [])),
        })]
    
    if event_type in ("security.oauth.connected", "security.oauth.disconnected"):
        return [Evidence(**base, metrics={
            "provider": p.get("provider"),
            "email": p.get("email"),
            "scopes": p.get("scopes", []),
        })]
    
    # Default: simple evidence row
    return [Evidence(**base, metrics={"event_type": event_type})]
```

### 4. Knowledge Graph Node Types

Add 8 security node types to `NODE_TYPES`:

```python
# saathi/missions/knowledge.py
NODE_TYPES = (
    # ... existing 29 types ...
    # Security layer (v1.3)
    "identity",        # User identity (email, name, verified)
    "connector",       # Generic connector account reference
    "oauth_account",   # OAuth-linked account
    "api_token",       # Named API token
    "permission",      # Scoped permission grant
    "role",            # Role definition
    "trusted_device",  # Trusted device fingerprint
    "provider",        # OAuth/SSO provider
)
```

**Not added to `_COVERAGE`** — security is operational infrastructure, not core business identity.

**Helper module:** `saathi/missions/security.py` — convenience functions for recording security nodes:

```python
def record_oauth_account(mission_id, provider, handle, scopes=None, graph=None):
def record_identity(mission_id, identity_key, email, name="", verified=False, graph=None):
def record_api_token(mission_id, token_name, permissions, graph=None):
def record_trusted_device(mission_id, device_id, fingerprint, graph=None):
def grant_role(mission_id, identity_key, role, permissions=None, graph=None):
```

### 5. Mission Timeline Bridge

When a security event has a `mission_id`, mirror it to the Mission Timeline:

```python
# saathi/security/timeline.py — in record() method
def record(self, user_id: str, kind: str, title: str, *, detail: str = "",
           meta: dict | None = None, ip: str = "", ua: str = "") -> str:
    # 1. Record in Security Timeline
    event_id = self.store.event_record(user_id, kind, title, ...)
    
    # 2. If mission_id in meta, mirror to Mission Timeline
    mission_id = (meta or {}).get("mission_id")
    if mission_id:
        from saathi.missions.timeline import default_store as mission_tl
        mission_tl().record(
            mission_id=mission_id,
            kind="note",
            title=f"[Security] {title}",
            detail=detail,
            meta={"security_event": kind, **(meta or {})}
        )
    
    # 3. Emit to Event Bus
    from saathi.events.bus import default_bus
    default_bus().emit(
        type=f"security.{kind}",
        source="security",
        payload={"kind": kind, "title": title, "detail": detail, "meta": meta, "ip": ip},
        project=meta.get("mission", "platform") if meta else "platform",
        subject=event_id,
    )
    
    return event_id
```

### 6. Connector Permission Model

**Store:** `AccountStore` (not SecurityStore) — it already has `provider + secret + missions + status`.

**Schema addition:** `permissions TEXT DEFAULT '[]'` in `accounts.db`.

**Permission format:**
```json
["social.post", "email.send", "mission:hcg video.upload"]
```

**Enforcement points:**
1. `ConnectorManager.execute()` — check before dispatch
2. `POST /api/v1/connectors/execute` — return 403 if denied
3. `ConnectorRegistry.execute()` — check when `account_id` provided

**Default for existing accounts:** `["*"]` (grandfathered — all permissions).

### 7. Security Learning Director

Follows the exact pattern of Technical, Educational, Business Directors.

```python
# saathi/learning/directors.py — SecurityLearningDirector
class SecurityLearningDirector:
    def analyze(self, since_days=7) -> list[Recommendation]:
        # Query Evidence Store for security department
        # Query Security Store for password health, sessions, tokens
        # Generate recommendations
        pass
```

**Recommendations:**
- Password overdue → "Rotate password"
- 3+ failed logins → "Enable passkeys"
- Unused token > 30 days → "Revoke token"
- No passkey → "Set up Face ID / Touch ID"
- High-risk event → "Review sessions"

All recommendations have `requires_approval=True`.

### 8. Recovery Center

**Tables:** `recovery_codes`, `trusted_devices` in `SecurityStore`.

**Recovery codes:**
- Generate: 8 codes, SHA256 hashed, shown once
- Verify: consume one-time use
- Store: `code_hash`, `used`, `created_at`, `used_at`

**Trusted devices:**
- Fingerprint: hash of browser + OS + screen + user agent
- Status: `active` | `revoked`
- Check: used to skip 2FA in future (v1.3.1)

**Emergency logout:**
- Revoke ALL sessions
- Revoke ALL tokens (except current?)
- Record recovery timeline event

### 9. Test Infrastructure

**Root cause of v1.1 test failures:**
- `_clean_stores` does NOT delete `~/.saathi/security.db`
- Does NOT call `close_store()` to reset singleton
- `TestClient(app)` shares global app singleton

**Fix:**
```python
@pytest.fixture(autouse=True)
def _clean_stores(tmp_path, monkeypatch):
    from saathi.security import store as _store_mod
    from saathi.security.registry import close_registry
    from saathi.security.timeline import close_timeline
    
    _store_mod.close_store()
    _store_mod._default_store = None
    close_registry()
    close_timeline()
    
    fresh = _store_mod.SecurityStore(db_path=tmp_path / "security.db")
    fresh.migrate_from_legacy()
    monkeypatch.setattr(_store_mod, "get_store", lambda _dp=None: fresh)
    
    # Clean legacy files
    for p in (Path.home() / ".saathi").glob("*.json"):
        p.unlink(missing_ok=True)
    for p in (Path.home() / ".saathi").glob("*.db"):
        p.unlink(missing_ok=True)
    
    authsec._WINDOWS.clear()
    passkey._pending.clear()
    yield
    fresh.close()
```

**Target:** 100% deterministic, parallel-safe, no skipped tests.

### 10. CI/CD Pipeline

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -e ".[voice,generation]" pytest pytest-cov ruff mypy
      - run: ruff check saathi/ tests/
      - run: pytest tests/test_auth_v12.py tests/test_auth_v1.py -v --cov=saathi --cov-report=xml
  frontend-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd saathi-os && npm ci && npm run build
```

---

## Implementation Order

| Phase | Task | Files | Risk |
|-------|------|-------|------|
| **0** | Fix test isolation | `tests/test_auth_v1.py`, `saathi/security/*.py` | Low |
| **1** | Schema migration | `saathi/security/store.py` | Low |
| **2** | Identity Registry | `saathi/security/identity_registry.py` | Low |
| **3** | Recovery Manager | `saathi/security/recovery.py` | Low |
| **4** | Event Bus integration | `saathi/security/timeline.py`, `saathi/businesses/security.py` | Medium |
| **5** | Knowledge Graph nodes | `saathi/missions/knowledge.py`, `saathi/missions/security.py` | Low |
| **6** | Connector Permissions | `saathi/connectors/permissions.py`, `saathi/connectors/manager.py` | Medium |
| **7** | Security Learning Director | `saathi/learning/directors.py` | Low |
| **8** | Mission Health + Evidence | `saathi/missions/health.py`, `saathi/evidence/adapters.py` | Low |
| **9** | Control Room backend | `saathi/server.py` | Medium |
| **10** | Control Room frontend | `saathi-os/app/security/page.jsx`, `saathi-os/lib/api.js` | Medium |
| **11** | CI/CD | `.github/workflows/ci.yml` | Low |
| **12** | Tests + merge | `tests/test_auth_v13.py` | Low |

---

## Backward Compatibility Checklist

- [ ] All v1.2 API endpoints work identically
- [ ] `SAATHI_TOKEN` still authenticates
- [ ] `BAADAR_PASSWORD` still works
- [ ] Session cookies work identically
- [ ] Passkey APIs unchanged
- [ ] OAuth endpoints unchanged (skeleton still works)
- [ ] No migration requiring user action
- [ ] New columns have defaults
- [ ] New tables use `IF NOT EXISTS`

---

*Integration Plan v1.0 — Ready for implementation.*
