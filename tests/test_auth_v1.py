"""Auth v1.0 integration tests — sessions, passkeys, forgot password, account security.

Run with:  python -m pytest tests/test_auth_v1.py -v
"""
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Clear session/passkey/reset stores before each test class
@pytest.fixture(autouse=True)
def _clean_stores():
    from saathi import sessions, passkey, authsec
    stores = [
        Path.home() / ".saathi" / "sessions.json",
        Path.home() / ".saathi" / "passkeys.json",
        Path.home() / ".saathi" / "reset_tokens.json",
        Path.home() / ".saathi" / "auth_audit.log",
    ]
    for p in stores:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
    authsec._WINDOWS.clear()
    passkey._pending.clear()
    yield


@pytest.fixture
def client():
    from saathi.server import app
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════════
#  Phase 0 — Session store integration (the critical fix)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionIntegration:
    """Verify that sessions.py is wired into login, passkey, logout, change-password."""

    def test_login_issues_random_session(self, client, monkeypatch):
        monkeypatch.setenv("BAADAR_PASSWORD", "test1234")
        # reload server module so env is picked up
        import saathi.server as svr
        svr._RAW_PASSWORD = "test1234"
        svr._PASSWORD_HASH = __import__("hashlib").sha256("test1234".encode()).hexdigest()

        r = client.post("/api/v1/auth/login", json={"password": "test1234"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["token"]
        # token should NOT be the old deterministic hash
        old = svr._session_token()
        assert data["token"] != old
        # and it should validate in the session store
        from saathi import sessions
        assert sessions.validate(data["token"]) is True

    def test_login_rate_limit(self, client, monkeypatch):
        monkeypatch.setenv("BAADAR_PASSWORD", "test1234")
        import saathi.server as svr
        svr._RAW_PASSWORD = "test1234"
        svr._PASSWORD_HASH = __import__("hashlib").sha256("test1234".encode()).hexdigest()

        for _ in range(5):
            r = client.post("/api/v1/auth/login", json={"password": "wrong"})
        # 6th attempt should be rate limited
        r = client.post("/api/v1/auth/login", json={"password": "wrong"})
        assert r.status_code == 429
        assert "Too many attempts" in r.json()["error"]

    def test_logout_revokes_session(self, client, monkeypatch):
        monkeypatch.setenv("BAADAR_PASSWORD", "test1234")
        import saathi.server as svr
        svr._RAW_PASSWORD = "test1234"
        svr._PASSWORD_HASH = __import__("hashlib").sha256("test1234".encode()).hexdigest()

        r = client.post("/api/v1/auth/login", json={"password": "test1234"})
        token = r.json()["token"]
        from saathi import sessions
        assert sessions.validate(token) is True

        # logout with the token
        r = client.post("/api/v1/auth/logout", headers={"x-baadar-session": token})
        assert r.status_code == 200
        assert sessions.validate(token) is False

    def test_change_password_revokes_all_sessions(self, client, monkeypatch):
        monkeypatch.setenv("BAADAR_PASSWORD", "oldpass123")
        import saathi.server as svr
        svr._RAW_PASSWORD = "oldpass123"
        svr._PASSWORD_HASH = __import__("hashlib").sha256("oldpass123".encode()).hexdigest()

        # login on two "devices"
        r1 = client.post("/api/v1/auth/login", json={"password": "oldpass123"}, headers={"user-agent": "DeviceA"})
        tok1 = r1.json()["token"]
        r2 = client.post("/api/v1/auth/login", json={"password": "oldpass123"}, headers={"user-agent": "DeviceB"})
        tok2 = r2.json()["token"]

        from saathi import sessions
        assert sessions.validate(tok1) is True
        assert sessions.validate(tok2) is True

        # change password from device A
        r = client.post("/api/v1/auth/change-password", json={"current": "oldpass123", "new_password": "NewPass123!"}, headers={"x-baadar-session": tok1})
        assert r.status_code == 200
        # both old tokens are invalidated
        assert sessions.validate(tok1) is False
        assert sessions.validate(tok2) is False
        # a new token is issued in the response
        new_tok = r.json()["token"]
        assert sessions.validate(new_tok) is True

    def test_legacy_deterministic_token_still_works(self, client, monkeypatch):
        """Backward compatibility: old deterministic token still accepted during transition."""
        monkeypatch.setenv("BAADAR_PASSWORD", "legacy123")
        import saathi.server as svr
        svr._RAW_PASSWORD = "legacy123"
        svr._PASSWORD_HASH = __import__("hashlib").sha256("legacy123".encode()).hexdigest()
        old_token = svr._session_token()

        r = client.get("/api/v1/auth/sessions", headers={"x-baadar-session": old_token})
        # should be authed (returns 200, not 401)
        assert r.status_code != 401


# ═══════════════════════════════════════════════════════════════════════════════
#  Phase 1 — Forgot Password
# ═══════════════════════════════════════════════════════════════════════════════

class TestForgotPassword:
    def test_forgot_always_returns_success_to_prevent_enumeration(self, client):
        r = client.post("/api/v1/auth/forgot", json={"email": "nobody@example.com"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert "registered" in r.json()["message"]

    def test_forgot_rate_limit(self, client):
        for _ in range(3):
            r = client.post("/api/v1/auth/forgot", json={"email": "a@b.com"})
            assert r.status_code == 200
        r = client.post("/api/v1/auth/forgot", json={"email": "a@b.com"})
        assert r.status_code == 429

    def test_reset_with_valid_token(self, client, monkeypatch):
        monkeypatch.setenv("BAADAR_PASSWORD", "oldpass")
        import saathi.server as svr
        svr._RAW_PASSWORD = "oldpass"
        svr._PASSWORD_HASH = __import__("hashlib").sha256("oldpass".encode()).hexdigest()

        # request reset
        r = client.post("/api/v1/auth/forgot", json={"email": "ajay@example.com"})
        assert r.status_code == 200

        # peek at the stored token (in real test we'd mock mailer)
        store = Path.home() / ".saathi" / "reset_tokens.json"
        rows = json.loads(store.read_text()) if store.exists() else []
        assert len(rows) == 1
        token = rows[0]["token"]

        # reset with token
        r = client.post("/api/v1/auth/reset", json={"token": token, "new_password": "NewStrong1!"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # new password works
        r = client.post("/api/v1/auth/login", json={"password": "NewStrong1!"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_reset_rejects_invalid_token(self, client):
        r = client.post("/api/v1/auth/reset", json={"token": "badtoken", "new_password": "NewStrong1!"})
        assert r.status_code == 400
        assert "Invalid or expired" in r.json()["error"]

    def test_reset_rejects_weak_password(self, client):
        # create a valid token first
        from saathi.server import _save_reset_tokens, _load_reset_tokens
        token = "testtok123"
        _save_reset_tokens([{"token": token, "email": "", "created": time.time(), "expires": time.time() + 900, "ip": "", "used": False}])
        r = client.post("/api/v1/auth/reset", json={"token": token, "new_password": "123"})
        assert r.status_code == 400
        assert "weak" in r.json()["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
#  Phase 2 — Passkey Management
# ═══════════════════════════════════════════════════════════════════════════════

class TestPasskeyManagement:
    def test_list_passkeys_requires_auth(self, client):
        r = client.get("/api/v1/auth/passkeys")
        assert r.status_code == 401

    def test_delete_passkey_requires_auth(self, client):
        r = client.delete("/api/v1/auth/passkeys/fake-id")
        assert r.status_code == 401

    def test_rename_passkey_requires_auth(self, client):
        r = client.patch("/api/v1/auth/passkeys/fake-id", json={"label": "x"})
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
#  Phase 3 — Account Security (Sessions)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAccountSecurity:
    def test_list_sessions_requires_auth(self, client):
        r = client.get("/api/v1/auth/sessions")
        assert r.status_code == 401

    def test_list_sessions_returns_device_info(self, client, monkeypatch):
        monkeypatch.setenv("BAADAR_PASSWORD", "test1234")
        import saathi.server as svr
        svr._RAW_PASSWORD = "test1234"
        svr._PASSWORD_HASH = __import__("hashlib").sha256("test1234".encode()).hexdigest()

        r = client.post("/api/v1/auth/login", json={"password": "test1234"}, headers={"user-agent": "TestBrowser/1.0"})
        token = r.json()["token"]

        r = client.get("/api/v1/auth/sessions", headers={"x-baadar-session": token})
        assert r.status_code == 200
        sess = r.json()["sessions"]
        assert len(sess) == 1
        assert sess[0]["browser"] == "Unknown"  # TestBrowser not in the parser list
        assert sess[0]["current"] is True

    def test_revoke_session(self, client, monkeypatch):
        monkeypatch.setenv("BAADAR_PASSWORD", "test1234")
        import saathi.server as svr
        svr._RAW_PASSWORD = "test1234"
        svr._PASSWORD_HASH = __import__("hashlib").sha256("test1234".encode()).hexdigest()

        r = client.post("/api/v1/auth/login", json={"password": "test1234"})
        tok = r.json()["token"]

        from saathi import sessions
        sid = sessions.session_id(tok)
        r = client.delete(f"/api/v1/auth/sessions/{sid}", headers={"x-baadar-session": tok})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert sessions.validate(tok) is False

    def test_revoke_all_sessions(self, client, monkeypatch):
        monkeypatch.setenv("BAADAR_PASSWORD", "test1234")
        import saathi.server as svr
        svr._RAW_PASSWORD = "test1234"
        svr._PASSWORD_HASH = __import__("hashlib").sha256("test1234".encode()).hexdigest()

        r = client.post("/api/v1/auth/login", json={"password": "test1234"})
        tok = r.json()["token"]
        r = client.post("/api/v1/auth/sessions/revoke-all", headers={"x-baadar-session": tok})
        assert r.status_code == 200
        assert r.json()["revoked"] >= 0

    def test_rotate_session(self, client, monkeypatch):
        monkeypatch.setenv("BAADAR_PASSWORD", "test1234")
        import saathi.server as svr
        svr._RAW_PASSWORD = "test1234"
        svr._PASSWORD_HASH = __import__("hashlib").sha256("test1234".encode()).hexdigest()

        r = client.post("/api/v1/auth/login", json={"password": "test1234"})
        old_tok = r.json()["token"]

        r = client.post("/api/v1/auth/session/rotate", headers={"x-baadar-session": old_tok})
        assert r.status_code == 200
        new_tok = r.json()["token"]
        assert new_tok != old_tok
        from saathi import sessions
        assert sessions.validate(old_tok) is False
        assert sessions.validate(new_tok) is True

    def test_rename_session(self, client, monkeypatch):
        monkeypatch.setenv("BAADAR_PASSWORD", "test1234")
        import saathi.server as svr
        svr._RAW_PASSWORD = "test1234"
        svr._PASSWORD_HASH = __import__("hashlib").sha256("test1234".encode()).hexdigest()

        r = client.post("/api/v1/auth/login", json={"password": "test1234"})
        tok = r.json()["token"]
        sid = __import__("saathi.sessions", fromlist=["session_id"]).session_id(tok)

        r = client.post(f"/api/v1/auth/sessions/{sid}/rename", json={"label": "Work Mac"}, headers={"x-baadar-session": tok})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_audit_requires_auth(self, client):
        r = client.get("/api/v1/auth/audit")
        assert r.status_code == 401

    def test_audit_returns_events(self, client, monkeypatch):
        monkeypatch.setenv("BAADAR_PASSWORD", "test1234")
        import saathi.server as svr
        svr._RAW_PASSWORD = "test1234"
        svr._PASSWORD_HASH = __import__("hashlib").sha256("test1234".encode()).hexdigest()

        r = client.post("/api/v1/auth/login", json={"password": "test1234"})
        tok = r.json()["token"]
        r = client.get("/api/v1/auth/audit", headers={"x-baadar-session": tok})
        assert r.status_code == 200
        assert "events" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
#  Phase 5 — OAuth Architecture
# ═══════════════════════════════════════════════════════════════════════════════

class TestOAuthArchitecture:
    def test_oauth_providers_list(self, client):
        r = client.get("/api/v1/auth/oauth/providers")
        assert r.status_code == 200
        providers = r.json()["providers"]
        names = [p["name"] for p in providers]
        assert "google" in names
        assert "apple" in names
        assert "github" in names
        assert "microsoft" in names
        assert "facebook" in names
        assert "telegram" in names
        # all disabled by default
        for p in providers:
            assert p["enabled"] is False

    def test_oauth_authorize_rejects_unknown_provider(self, client):
        r = client.get("/api/v1/auth/oauth/unknown/authorize")
        assert r.status_code == 400

    def test_oauth_authorize_rejects_unconfigured_provider(self, client):
        r = client.get("/api/v1/auth/oauth/google/authorize")
        assert r.status_code == 400
        assert "not configured" in r.json()["error"]

    def test_oauth_callback_rejects_invalid_state(self, client):
        r = client.get("/api/v1/auth/oauth/callback?code=abc&state=bad")
        assert r.status_code == 400
        assert "Invalid or expired state" in r.json()["error"]


# ═══════════════════════════════════════════════════════════════════════════════
#  Phase 7 — Security Headers
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecurityHeaders:
    def test_security_headers_present(self, client):
        r = client.get("/api/v1/auth/passkey/status")
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"
        assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert "Content-Security-Policy" in r.headers
        assert "default-src 'self'" in r.headers["content-security-policy"]
