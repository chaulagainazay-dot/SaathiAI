"""Authentication v1.2 tests — Security Store, Token Registry, Risk Engine, Timeline."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from saathi import authsec
from saathi.security.store import SecurityStore
from saathi.security.registry import TokenRegistry
from saathi.security.risk import RiskEngine
from saathi.security.timeline import SecurityTimeline, EVENT_KINDS
from saathi.security.health import PasswordHealth
from saathi.security.diagnostics import passkey_diagnostic, passkey_diagnostic_from_exception, oauth_diagnostic
from saathi.server import app

client = TestClient(app)


@pytest.fixture
def store(tmp_path):
    db = SecurityStore(db_path=tmp_path / "security.db")
    db.migrate_from_legacy()
    return db


# ── PBKDF2 ───────────────────────────────────────────────────────────────────
class TestPBKDF2:
    def test_pbkdf2_format(self):
        h = authsec.hash_password("Secret123!")
        assert h.startswith("pbkdf2$sha256$600000$")
        parts = h.split("$")
        assert len(parts) == 5

    def test_different_salts(self):
        h1 = authsec.hash_password("same")
        h2 = authsec.hash_password("same")
        assert h1 != h2

    def test_verify_pbkdf2(self):
        h = authsec.hash_password("MyP@ssw0rd")
        assert authsec.verify_password("MyP@ssw0rd", h) is True
        assert authsec.verify_password("Wrong", h) is False

    def test_verify_legacy_sha256(self):
        import hashlib
        legacy = hashlib.sha256("oldpassword".encode()).hexdigest()
        assert authsec.verify_password("oldpassword", legacy) is True

    def test_needs_upgrade(self):
        import hashlib
        legacy = hashlib.sha256("x".encode()).hexdigest()
        assert authsec.needs_upgrade(legacy) is True
        assert authsec.needs_upgrade(authsec.hash_password("x")) is False


# ── Password Strength ────────────────────────────────────────────────────────
class TestPasswordStrength:
    def test_weak(self):
        s = authsec.password_strength("123")
        assert s["score"] <= 1

    def test_strong(self):
        s = authsec.password_strength("MyStr0ng!Pass")
        assert s["score"] == 4


# ── Rate Limiting ────────────────────────────────────────────────────────────
class TestRateLimiting:
    def test_allows_under_limit(self):
        authsec.rate_clear("test:key")
        allowed, _ = authsec.rate_check("test:key", limit=3, window=10)
        assert allowed is True

    def test_blocks_at_limit(self):
        authsec.rate_clear("test:key2")
        for _ in range(3):
            authsec.rate_hit("test:key2")
        allowed, retry = authsec.rate_check("test:key2", limit=3, window=10)
        assert allowed is False
        assert retry > 0


# ── Security Store ───────────────────────────────────────────────────────────
class TestSecurityStore:
    def test_schema_created(self, store):
        tables = {r["name"] for r in store.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"users", "sessions", "passkeys", "api_tokens", "security_events", "audit_log"} <= tables

    def test_owner_idempotent(self, store):
        uid1 = store.get_or_create_owner()
        uid2 = store.get_or_create_owner()
        assert uid1 == uid2

    def test_user_crud(self, store):
        uid = store.get_or_create_owner()
        store.db.execute("UPDATE users SET email=?, name=? WHERE id=?",
                        ("test@example.com", "Test", uid))
        store.db.commit()
        user = store.get_user(uid)
        assert user["email"] == "test@example.com"

    def test_password_save(self, store):
        uid = store.get_or_create_owner()
        store.save_password(uid, "hash1", strength_score=4)
        latest = store.latest_password(uid)
        assert latest["hash"] == "hash1"
        assert latest["strength_score"] == 4

    def test_active_owner_password_status_is_boolean_only(self, store):
        assert store.active_owner_has_password() is False
        uid = store.get_or_create_owner()
        store.save_password(uid, "hash1", strength_score=4)
        assert store.active_owner_has_password() is True

    def test_session_crud(self, store):
        uid = store.get_or_create_owner()
        store.session_create(uid, "hash123", browser="Chrome", ip_address="1.2.3.4")
        rec = store.session_by_hash("hash123")
        assert rec["browser"] == "Chrome"
        store.session_touch("hash123")
        store.session_revoke(rec["id"])
        assert store.session_by_hash("hash123") is None

    def test_passkey_crud(self, store):
        uid = store.get_or_create_owner()
        store.passkey_save(uid, "cred1", "pubkey1", "localhost", device_name="Mac")
        assert len(store.passkey_list(uid)) == 1
        store.passkey_update_sign_count("cred1", 5)
        assert store.passkey_get("cred1")["sign_count"] == 5
        store.passkey_delete("cred1")
        assert store.passkey_get("cred1") is None

    def test_api_token_crud(self, store):
        uid = store.get_or_create_owner()
        tid = store.api_token_create(uid, "Test", "hash_tok", permissions=["/api/*"])
        assert store.api_token_by_hash("hash_tok")["name"] == "Test"
        store.api_token_revoke(tid)
        assert store.api_token_by_hash("hash_tok") is None

    def test_security_events(self, store):
        uid = store.get_or_create_owner()
        eid = store.event_record(uid, "login_success", "Signed in", meta={"ip": "1.2.3.4"})
        events = store.event_list(uid)
        assert len(events) == 1
        assert events[0]["meta"]["ip"] == "1.2.3.4"

    def test_audit_log(self, store):
        store.audit("login", ok=True, user_id="u1", ip="1.2.3.4")
        assert len(store.audit_recent(user_id="u1")) == 1


# ── Token Registry ───────────────────────────────────────────────────────────
class TestTokenRegistry:
    def test_create_verify(self, store):
        reg = TokenRegistry(store=store)
        uid = store.get_or_create_owner()
        tid, raw = reg.create(uid, "Studio", permissions=["/api/v1/studio/*"])
        assert raw.startswith("tk_")
        assert reg.verify(raw)["name"] == "Studio"

    def test_revoke(self, store):
        reg = TokenRegistry(store=store)
        uid = store.get_or_create_owner()
        tid, raw = reg.create(uid, "Temp")
        reg.revoke(tid)
        assert reg.verify(raw) is None

    def test_permissions(self, store):
        reg = TokenRegistry(store=store)
        uid = store.get_or_create_owner()
        tid, raw = reg.create(uid, "Scoped", permissions=["/api/v1/studio/*"])
        rec = reg.verify(raw)
        assert reg.check_permission(rec, "/api/v1/studio/queue", "GET") is True
        assert reg.check_permission(rec, "/api/v1/other", "GET") is False

    def test_wildcard(self, store):
        reg = TokenRegistry(store=store)
        uid = store.get_or_create_owner()
        tid, raw = reg.create(uid, "Admin", permissions=["*"])
        assert reg.check_permission(reg.verify(raw), "/anything", "DELETE") is True


# ── Risk Engine ──────────────────────────────────────────────────────────────
class TestRiskEngine:
    def test_baseline_score(self, store):
        uid = store.get_or_create_owner()
        engine = RiskEngine(store=store)
        score = engine.score(uid, browser="Chrome", ip="1.2.3.4", device_name="Mac")
        assert 0 <= score <= 100

    def test_failed_attempts(self, store):
        uid = store.get_or_create_owner()
        engine = RiskEngine(store=store)
        assert engine.score(uid, failed_attempts=3) > engine.score(uid, failed_attempts=0)

    def test_labels(self, store):
        engine = RiskEngine(store=store)
        assert engine.label(10) == ("Low", "green")
        assert engine.label(90) == ("Critical", "red")


# ── Security Timeline ────────────────────────────────────────────────────────
class TestSecurityTimeline:
    def test_record_list(self, store):
        tl = SecurityTimeline(store=store)
        uid = store.get_or_create_owner()
        tl.record(uid, "password_changed", "Password changed")
        assert len(tl.list(uid)) == 1

    def test_kinds_defined(self):
        assert "password_changed" in EVENT_KINDS
        assert "login_success" in EVENT_KINDS


# ── Password Health ──────────────────────────────────────────────────────────
class TestPasswordHealth:
    def test_no_password(self, store):
        uid = store.get_or_create_owner()
        h = PasswordHealth(store=store)
        assert h.metrics(uid)["has_password"] is False

    def test_metrics(self, store):
        uid = store.get_or_create_owner()
        store.save_password(uid, "hash1", strength_score=4)
        h = PasswordHealth(store=store)
        m = h.metrics(uid)
        assert m["has_password"] is True
        assert m["strength"]["score"] == 4


# ── Diagnostics ──────────────────────────────────────────────────────────────
class TestDiagnostics:
    def test_passkey_cancelled(self):
        assert "cancelled" in passkey_diagnostic("NotAllowedError", "user_cancelled").lower()

    def test_oauth_error(self):
        assert "expired" in oauth_diagnostic("invalid_grant").lower()


# ── Security Headers ─────────────────────────────────────────────────────────
class TestSecurityHeaders:
    def test_headers_present(self):
        r = client.get("/api/v1/auth/passkey/status")
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert "frame-ancestors" in r.headers.get("content-security-policy", "")


# ── CORS ─────────────────────────────────────────────────────────────────────
class TestCORS:
    def test_middleware_present(self):
        from fastapi.middleware.cors import CORSMiddleware
        assert CORSMiddleware in [m.cls for m in app.user_middleware]


# ── Identity Provider ────────────────────────────────────────────────────────
class TestIdentityProvider:
    def test_router_has_providers(self):
        from saathi.security.identity import default_router
        router = default_router()
        assert "google" in router.all_names()

    def test_google_not_configured(self):
        from saathi.security.identity import GoogleIdentityProvider
        assert GoogleIdentityProvider().is_configured() is False


# ── Login Endpoint ───────────────────────────────────────────────────────────
class TestLoginEndpoint:
    def test_empty_body_rejected(self):
        assert client.post("/api/v1/auth/login", json={}).status_code == 422


# ── v1.2 Endpoints ───────────────────────────────────────────────────────────
class TestV12Endpoints:
    def test_providers_public(self):
        r = client.get("/api/v1/auth/providers")
        assert r.status_code == 200
        assert "available" in r.json()

    def test_diagnostics_public(self):
        r = client.get("/api/v1/auth/passkey/diagnostics?error=NotAllowedError")
        assert r.status_code == 200

    def test_timeline_requires_auth(self):
        assert client.get("/api/v1/security/timeline").status_code == 401

    def test_health_requires_auth(self):
        assert client.get("/api/v1/security/health").status_code == 401
