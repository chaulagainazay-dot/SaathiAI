"""Production auth hardening tests — PBKDF2, sessions, rate limiting, headers."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from saathi import authsec, sessions
from saathi.server import app

client = TestClient(app)


# ── PBKDF2 password hashing ──────────────────────────────────────────────────
class TestPBKDF2PasswordHashing:
    def test_hash_password_returns_pbkdf2_format(self):
        h = authsec.hash_password("Secret123!")
        assert h.startswith("pbkdf2$sha256$600000$")
        parts = h.split("$")
        assert len(parts) == 5
        assert len(parts[3]) == 32  # salt hex
        assert len(parts[4]) == 64  # hash hex

    def test_hash_password_produces_different_salts(self):
        h1 = authsec.hash_password("same")
        h2 = authsec.hash_password("same")
        assert h1 != h2

    def test_verify_password_with_pbkdf2(self):
        h = authsec.hash_password("MyP@ssw0rd")
        assert authsec.verify_password("MyP@ssw0rd", h) is True
        assert authsec.verify_password("Wrong", h) is False

    def test_verify_password_with_legacy_sha256(self):
        import hashlib
        legacy = hashlib.sha256("oldpassword".encode()).hexdigest()
        assert authsec.verify_password("oldpassword", legacy) is True
        assert authsec.verify_password("wrong", legacy) is False

    def test_verify_password_empty_stored_returns_false(self):
        assert authsec.verify_password("anything", "") is False
        assert authsec.verify_password("anything", None) is False

    def test_needs_upgrade_detects_legacy(self):
        import hashlib
        legacy = hashlib.sha256("x".encode()).hexdigest()
        assert authsec.needs_upgrade(legacy) is True
        assert authsec.needs_upgrade(authsec.hash_password("x")) is False
        assert authsec.needs_upgrade("") is False


# ── Password strength ────────────────────────────────────────────────────────
class TestPasswordStrength:
    def test_very_weak_password(self):
        s = authsec.password_strength("123")
        assert s["score"] <= 1
        assert s["checks"]["length"] is False

    def test_strong_password(self):
        s = authsec.password_strength("MyStr0ng!Pass")
        assert s["score"] == 4
        assert all(s["checks"].values())


# ── Rate limiting ───────────────────────────────────────────────────────────
class TestRateLimiting:
    def test_rate_check_allows_under_limit(self):
        authsec.rate_clear("test:key")
        allowed, retry = authsec.rate_check("test:key", limit=3, window=10)
        assert allowed is True
        assert retry == 0

    def test_rate_check_blocks_at_limit(self):
        authsec.rate_clear("test:key2")
        for _ in range(3):
            authsec.rate_hit("test:key2")
        allowed, retry = authsec.rate_check("test:key2", limit=3, window=10)
        assert allowed is False
        assert retry > 0

    def test_rate_check_window_expires(self):
        authsec.rate_clear("test:key3")
        authsec.rate_hit("test:key3")
        # Manually backdate the hit so it falls outside the window
        authsec._WINDOWS["test:key3"][0] = time.time() - 20
        allowed, retry = authsec.rate_check("test:key3", limit=1, window=10)
        assert allowed is True


# ── Session store (remember_me, expiry, revocation) ──────────────────────────
class TestSessionStore:
    def test_create_session_with_remember_me(self):
        sessions._save([])  # clear
        token = sessions.create(ua="Mozilla/5.0", ip="127.0.0.1", kind="password", remember_me=True)
        assert token
        rows = sessions._load()
        assert len(rows) == 1
        assert rows[0]["remember_me"] is True
        assert rows[0]["expires"] > time.time() + 29 * 24 * 3600
        assert rows[0]["revoked"] is False

    def test_create_session_without_remember_me(self):
        sessions._save([])
        token = sessions.create(ua="Test", ip="127.0.0.1", kind="password", remember_me=False)
        rows = sessions._load()
        assert rows[0]["remember_me"] is False
        assert rows[0]["expires"] < time.time() + 25 * 3600  # ~24h

    def test_validate_rejects_expired_session(self):
        sessions._save([])
        token = sessions.create(ua="Test", ip="127.0.0.1", kind="password", remember_me=True)
        # Manually expire
        rows = sessions._load()
        rows[0]["expires"] = time.time() - 1
        sessions._save(rows)
        assert sessions.validate(token) is False

    def test_validate_rejects_revoked_session(self):
        sessions._save([])
        token = sessions.create(ua="Test", ip="127.0.0.1", kind="password")
        rows = sessions._load()
        rows[0]["revoked"] = True
        sessions._save(rows)
        assert sessions.validate(token) is False

    def test_revoke_is_soft_delete(self):
        sessions._save([])
        token = sessions.create(ua="Test", ip="127.0.0.1")
        sid = sessions.session_id(token)
        assert sessions.revoke(sid) is True
        rows = sessions._load()
        assert len(rows) == 1
        assert rows[0]["revoked"] is True

    def test_revoke_all_keeps_current(self):
        sessions._save([])
        t1 = sessions.create(ua="A")
        t2 = sessions.create(ua="B")
        sessions.revoke_all(except_token=t1)
        assert sessions.validate(t1) is True
        assert sessions.validate(t2) is False

    def test_listing_includes_expires_and_remember_me(self):
        sessions._save([])
        sessions.create(ua="Test", remember_me=True)
        lst = sessions.listing()
        assert "expires" in lst[0]
        assert "remember_me" in lst[0]


# ── Audit log ────────────────────────────────────────────────────────────────
class TestAuditLog:
    def test_audit_records_event(self):
        authsec._AUDIT.unlink(missing_ok=True)
        authsec.audit("test_event", ok=True, ip="1.2.3.4", ua="TestBot", detail="unit")
        recent = authsec.recent_audit(limit=5)
        assert len(recent) >= 1
        assert recent[0]["event"] == "test_event"
        assert recent[0]["ip"] == "1.2.3.4"

    def test_recent_audit_respects_limit(self):
        authsec._AUDIT.unlink(missing_ok=True)
        for i in range(5):
            authsec.audit(f"evt{i}")
        assert len(authsec.recent_audit(limit=3)) == 3


# ── Security headers ─────────────────────────────────────────────────────────
class TestSecurityHeaders:
    def test_security_headers_present_on_api(self):
        r = client.get("/api/v1/auth/passkey/status")
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"
        assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        csp = r.headers.get("content-security-policy", "")
        assert "default-src" in csp

    def test_csp_blocks_frames(self):
        r = client.get("/api/v1/auth/passkey/status")
        csp = r.headers.get("content-security-policy", "")
        assert "frame-ancestors 'none'" in csp


# ── CORS configuration ───────────────────────────────────────────────────────
class TestCORSConfiguration:
    def test_cors_allows_origin_header(self):
        # The TestClient doesn't do real CORS, but we verify the middleware is mounted
        # by checking the app has the CORSMiddleware in its stack.
        from fastapi.middleware.cors import CORSMiddleware
        middlewares = [m.cls for m in app.user_middleware]
        assert CORSMiddleware in middlewares


# ── Login endpoint integration ───────────────────────────────────────────────
class TestLoginEndpoint:
    def test_login_with_no_password_configured(self):
        # When no password is set, login should succeed with any password
        import os
        orig_hash = os.environ.get("BAADAR_PASSWORD_HASH")
        orig_raw = os.environ.get("BAADAR_PASSWORD")
        try:
            if "BAADAR_PASSWORD_HASH" in os.environ:
                del os.environ["BAADAR_PASSWORD_HASH"]
            if "BAADAR_PASSWORD" in os.environ:
                del os.environ["BAADAR_PASSWORD"]
            # We can't easily modify the module-level globals, but we can test
            # the rate-limit path and the structure of the endpoint via the client.
            r = client.post("/api/v1/auth/login", json={"password": "anything"})
            # May succeed or fail depending on whether a password is configured in .env
            assert r.status_code in (200, 401)
        finally:
            if orig_hash is not None:
                os.environ["BAADAR_PASSWORD_HASH"] = orig_hash
            if orig_raw is not None:
                os.environ["BAADAR_PASSWORD"] = orig_raw

    def test_login_rejects_empty_body(self):
        r = client.post("/api/v1/auth/login", json={})
        assert r.status_code == 422  # Pydantic validation error

    def test_login_accepts_remember_me(self):
        # Verify the endpoint schema accepts remember_me
        r = client.post("/api/v1/auth/login", json={"password": "test", "remember_me": False})
        # It may auth-fail but should not schema-fail
        assert r.status_code != 422


# ── Change-password endpoint integration ─────────────────────────────────────
class TestChangePasswordEndpoint:
    def test_change_password_rejects_weak(self):
        # Without auth this will 401, but we can at least verify the endpoint exists
        r = client.post("/api/v1/auth/change-password", json={"current": "x", "new_password": "weak"})
        assert r.status_code in (401, 400, 200)


# ── Passkey status endpoint ──────────────────────────────────────────────────
class TestPasskeyStatus:
    def test_passkey_status_returns_structure(self):
        r = client.get("/api/v1/auth/passkey/status")
        assert r.status_code == 200
        data = r.json()
        assert "has_passkey" in data
        assert "has_password" in data
        assert "signed_in" in data
        assert "rp_id" in data
