"""Auth v1.0 integration tests — sessions, passkeys, forgot password, account security.

Run with:  python -m pytest tests/test_auth_v1.py -v

Safe by construction, not by convention. This module used to unlink the
operator's real ``~/.saathi/security.db``, ``sessions.json``, ``passkeys.json``,
``reset_tokens.json`` and ``auth_audit.log`` on every run, and a later revision
only moved that hazard behind ``SAATHI_STATE_ROOT`` — which meant a developer
running the file directly still destroyed their own auth state.

Now the fixture points ``SAATHI_STATE_ROOT`` at its own ``tmp_path`` before it
imports or constructs anything that resolves a state path, and the only deletion
helper refuses a target outside that directory. Nothing here depends on the
caller supplying an environment variable, and importing or collecting this
module touches no file at all.
"""
import json
import pathlib
import time

import pytest
from fastapi.testclient import TestClient


class UnsafeCleanupTarget(AssertionError):
    """A test tried to delete something it does not own."""


def _unlink_within(root: "pathlib.Path", target: "pathlib.Path") -> None:
    """Delete ``target`` only if it genuinely lives under ``root``.

    ``root`` is this test's ``tmp_path``. Resolving both sides first means a
    symlink or a ``..`` cannot walk the deletion back out to the real home
    directory; anything that does not land inside raises instead of unlinking.
    """
    root = pathlib.Path(root).resolve()
    resolved = pathlib.Path(target).resolve()
    if not resolved.is_relative_to(root):
        raise UnsafeCleanupTarget(
            f"refusing to delete {resolved} — outside the test-owned root {root}"
        )
    resolved.unlink(missing_ok=True)


# Clear session/passkey/reset stores + Security Store singleton before each test
@pytest.fixture(autouse=True)
def _clean_stores(tmp_path, monkeypatch):
    # 0. Redirect ALL state-root-derived paths into this test's own directory
    #    before anything below resolves one. Every later step — the legacy
    #    migration read included — therefore addresses tmp_path, never $HOME.
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SAATHI_STATE_ROOT", str(state_root))

    from saathi import passkey, authsec
    from saathi.security import store as _store_mod
    from saathi.security.registry import close_registry
    from saathi.security.timeline import close_timeline
    from saathi.runtime_paths import state_path

    # 1. Close and reset all security singletons
    _store_mod.close_store()
    _store_mod._default_store = None
    close_registry()
    close_timeline()

    # 2. Create a fresh temp Security Store and wire all singletons to it.
    #    The path is explicit, so it holds even if the resolver misbehaves.
    fresh = _store_mod.SecurityStore(db_path=tmp_path / "security.db")
    fresh.migrate_from_legacy()
    # D14: authentication now requires an ACTIVE installation. These tests are
    # about sessions, passkeys and revocation on an owned system, so put the
    # store in the state a completed bootstrap would leave it in.
    import sys, pathlib as _pl
    sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
    from support.auth_state import make_active
    make_active(fresh)
    # Set the module-level singleton directly — all imported get_store()
    # references execute the same code that checks _default_store
    _store_mod._default_store = fresh

    # 3. Clear the legacy JSON files for tests that still touch them. These
    #    resolve under the state root set in step 0, and _unlink_within refuses
    #    anything that somehow does not.
    for name in ("sessions.json", "passkeys.json", "reset_tokens.json",
                 "auth_audit.log", "security.db", "oauth_states.json"):
        _unlink_within(tmp_path, state_path(name))

    # 4. Clear in-memory rate-limit windows
    authsec._WINDOWS.clear()
    passkey._pending.clear()

    yield

    # 5. Cleanup after test
    fresh.close()
    _store_mod.close_store()
    _store_mod._default_store = None
    close_registry()
    close_timeline()


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
        # it should validate in the session store
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
        from support.auth_state import DEFAULT_TEST_PASSWORD as PW

        # login on two "devices"
        r1 = client.post("/api/v1/auth/login", json={"password": PW}, headers={"user-agent": "DeviceA"})
        tok1 = r1.json()["token"]
        r2 = client.post("/api/v1/auth/login", json={"password": PW}, headers={"user-agent": "DeviceB"})
        tok2 = r2.json()["token"]

        from saathi import sessions
        assert sessions.validate(tok1) is True
        assert sessions.validate(tok2) is True

        # D14: change password from device A via the canonical authenticated
        # route. /api/v1/auth/change-password is retired -- it was the
        # unauthenticated fresh-install provisioning path.
        r = client.post("/api/v1/auth/password", json={"current": PW, "new_password": "NewPassw0rd!23"}, headers={"x-baadar-session": tok1})
        assert r.status_code == 200
        # both old tokens are invalidated
        assert sessions.validate(tok1) is False
        assert sessions.validate(tok2) is False
        # a new token is issued in the response
        new_tok = r.json()["token"]
        assert sessions.validate(new_tok) is True

    def test_legacy_deterministic_token_is_rejected(self, client, monkeypatch):
        """D14: the deterministic transition token is gone, and must stay gone.

        It hashed ``_PASSWORD_HASH or ACCESS_TOKEN or ""`` with a fixed suffix.
        A system bootstrapped the secure way stores its credential in the
        security store and leaves that global empty, so the "secret" reduced to
        ``sha256(":baadar-session")`` -- a constant anyone can compute. Both the
        seeded and the unseeded form are refused here.
        """
        import hashlib
        import saathi.server as svr

        assert not hasattr(svr, "_session_token")
        for seed in ("", hashlib.sha256(b"legacy123").hexdigest()):
            forged = hashlib.sha256((seed + ":baadar-session").encode()).hexdigest()
            r = client.get("/api/v1/auth/sessions",
                           headers={"x-baadar-session": forged})
            assert r.status_code == 401, seed


# ═══════════════════════════════════════════════════════════════════════════════
#  Phase 1 — Forgot Password
# ═══════════════════════════════════════════════════════════════════════════════

class TestForgotPassword:
    def test_forgot_endpoint_is_retired(self, client):
        """D14: /auth/forgot minted a recovery token for an anonymous caller.

        Rate limiting it was never the fix: an unauthenticated request caused a
        credential to be written and a redemption link to be mailed to whatever
        address the caller supplied, on a system that need not have had an owner
        at all. Its redeemer is retired, so there is nothing left to preserve.
        """
        from saathi.runtime_paths import state_path

        r = client.post("/api/v1/auth/forgot", json={"email": "a@b.com"})
        assert r.status_code == 410
        assert r.json()["error"] == "LEGACY_AUTH_RETIRED"
        assert not state_path("reset_tokens.json").exists()

    def test_reset_endpoint_is_retired(self, client):
        """D14: /api/v1/auth/reset is gone, and it cannot set a password.

        This class used to prove the reset flow end to end. That flow was one of
        the two plaintext writers: it set the process-global ``_PASSWORD_HASH``
        and persisted the new password as cleartext in the checkout's ``.env``,
        reachable without a session. What must now be true is that it changes
        nothing at all -- for a good token, a bad token, and a weak password
        alike, so no input shape can still reach a writer.
        """
        for body in ({"token": "testtok123", "new_password": "NewStrong1!23"},
                     {"token": "badtoken", "new_password": "NewStrong1!23"},
                     {"token": "testtok123", "new_password": "123"}):
            r = client.post("/api/v1/auth/reset", json=body)
            assert r.status_code == 410, body
            assert r.json()["error"] == "LEGACY_AUTH_RETIRED"
            assert "token" not in r.json()

    def test_recovery_token_store_has_no_writer_left(self):
        """Nothing may mint a reset token any more, from any code path."""
        import saathi.server as svr

        for gone in ("_save_reset_tokens", "_load_reset_tokens", "_reset_store"):
            assert not hasattr(svr, gone), gone


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
