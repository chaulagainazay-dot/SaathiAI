"""D17 — ``/unlock`` must know that a stored owner password exists.

``/api/v1/auth/passkey/status`` answered ``has_password`` from
``bool(_PASSWORD_HASH)``: the *environment* fallback, and nothing else. D14
bootstrap stores the owner password as a scrypt row in the security store and
deliberately never writes it to ``.env``, so on every install created the
documented way -- and on every isolated run with ``SAATHI_LOAD_DOTENV=false``
-- that field read False while a perfectly good credential existed.

``/unlock`` renders from it: the sign-in button is gated on ``has_password``
and the first-time-setup form on its negation. The owner was therefore shown
"Choose a password", never saw the sign-in field, and the setup form's
``POST /auth/password`` answered 401 -- an owner who knew the password locked
out of the surface built to take it.

These tests pin the five states the field has to distinguish, and that it
carries no credential material in any of them.
"""
from __future__ import annotations

import os
import secrets

import pytest
from fastapi.testclient import TestClient

SYNTHETIC_PASSWORD = "T3st!Unlock#Pw"
LOOPBACK = ("127.0.0.1", 51234)


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """A fresh, empty security store per test, wired to every singleton."""
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SAATHI_STATE_ROOT", str(state_root))
    monkeypatch.setenv("SAATHI_LOAD_DOTENV", "false")
    monkeypatch.delenv("BAADAR_PASSWORD", raising=False)
    monkeypatch.delenv("BAADAR_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SAATHI_BOOTSTRAP_ENABLED", raising=False)
    monkeypatch.delenv("SAATHI_BOOTSTRAP_TOKEN_FILE", raising=False)

    from saathi import auth_bootstrap, authsec
    from saathi.security import store as store_mod
    from saathi.security.registry import close_registry
    from saathi.security.timeline import close_timeline

    store_mod.close_store()
    store_mod._default_store = None
    close_registry()
    close_timeline()

    fresh = store_mod.SecurityStore(db_path=tmp_path / "security.db")
    store_mod._default_store = fresh

    import saathi.server as svr
    monkeypatch.setattr(svr, "_PASSWORD_HASH", "", raising=False)
    monkeypatch.setattr(svr, "_RAW_PASSWORD", "", raising=False)
    monkeypatch.setattr(svr, "ACCESS_TOKEN", "", raising=False)

    authsec._WINDOWS.clear()
    auth_bootstrap.reset_rate_limit_for_tests()

    yield fresh

    fresh.close()
    store_mod.close_store()
    store_mod._default_store = None
    close_registry()
    close_timeline()


@pytest.fixture
def client():
    from saathi.server import app
    return TestClient(app, client=LOOPBACK)


def _arm(monkeypatch, tmp_path) -> str:
    token = secrets.token_urlsafe(32)
    path = tmp_path / "operator.token"
    path.write_text(token)
    os.chmod(path, 0o600)
    monkeypatch.setenv("SAATHI_BOOTSTRAP_ENABLED", "true")
    monkeypatch.setenv("SAATHI_BOOTSTRAP_TOKEN_FILE", str(path))
    return token


def _bootstrap(client, tmp_path, monkeypatch) -> None:
    token = _arm(monkeypatch, tmp_path)
    r = client.post("/api/v1/auth/bootstrap",
                    json={"operator_token": token, "new_password": SYNTHETIC_PASSWORD})
    assert r.status_code == 200, r.text


def _status(client) -> dict:
    r = client.get("/api/v1/auth/passkey/status")
    assert r.status_code == 200
    return r.json()


# ── the five states ─────────────────────────────────────────────────────────

def test_01_uninitialised_install_reports_no_password(client, isolated_store):
    """No owner, no credential: the setup form is the correct surface."""
    assert isolated_store.credential_census()["users"] == 0
    assert _status(client)["has_password"] is False


def test_02_owner_without_stored_password_reports_no_password(client, isolated_store):
    """An owner row alone is not a credential."""
    owner = isolated_store.get_or_create_owner()
    assert isolated_store.latest_password(owner) is None
    assert _status(client)["has_password"] is False


def test_03_environment_fallback_alone_still_reports_password(client, monkeypatch):
    """The env fallback keeps working: it is one source of truth, not the only one."""
    import saathi.server as svr
    monkeypatch.setattr(svr, "_PASSWORD_HASH", "deadbeef" * 8, raising=False)
    assert _status(client)["has_password"] is True


def test_04_stored_credential_alone_reports_password(client, tmp_path, monkeypatch):
    """The regression: bootstrap's own credential, no env fallback at all."""
    import saathi.server as svr

    _bootstrap(client, tmp_path, monkeypatch)
    client.cookies.clear()

    assert svr._PASSWORD_HASH == ""          # nothing in the environment
    assert _status(client)["has_password"] is True


def test_05_stored_credential_plus_fallback_reports_password(
        client, tmp_path, monkeypatch):
    import saathi.server as svr

    _bootstrap(client, tmp_path, monkeypatch)
    monkeypatch.setattr(svr, "_PASSWORD_HASH", "deadbeef" * 8, raising=False)
    assert _status(client)["has_password"] is True


# ── the field must stay a boolean, not a leak ───────────────────────────────

def test_06_status_never_returns_credential_material(client, tmp_path, monkeypatch):
    """Presence is the whole answer: no hash, no salt, no metadata, no token."""
    _bootstrap(client, tmp_path, monkeypatch)
    client.cookies.clear()

    body = _status(client)
    assert body["has_password"] is True
    assert set(body) == {"has_passkey", "rp_id", "has_password", "signed_in"}

    blob = repr(body)
    for banned in ("hash", "scrypt", "salt", SYNTHETIC_PASSWORD):
        assert banned not in blob


def test_07_store_presence_helper_returns_no_hash(isolated_store, client,
                                                  tmp_path, monkeypatch):
    """The abstraction answers the presence question without fetching a secret."""
    _bootstrap(client, tmp_path, monkeypatch)
    from saathi.security.store import get_store

    store = get_store()
    owner = store.owner_id()
    assert store.has_password(owner) is True
    assert store.owner_has_password() is True
    assert isinstance(store.owner_has_password(), bool)


def test_08_unauthenticated_status_read_does_not_contaminate(client, isolated_store):
    """The unlock page polls this before anyone signs in; it must plant nothing."""
    from saathi import auth_bootstrap

    for _ in range(3):
        assert _status(client)["has_password"] is False
    assert isolated_store.credential_census()["users"] == 0
    assert auth_bootstrap.auth_state(isolated_store) is not \
        auth_bootstrap.AuthState.CONTAMINATED_UNINITIALIZED


def test_09_status_does_not_claim_a_session(client, tmp_path, monkeypatch):
    """has_password is about the credential, never about being signed in."""
    _bootstrap(client, tmp_path, monkeypatch)
    client.cookies.clear()

    body = _status(client)
    assert body["has_password"] is True and body["signed_in"] is False


def test_10_stored_password_login_behavior_is_unchanged(
        client, tmp_path, monkeypatch):
    """The status repair neither replaces nor bypasses canonical verification."""
    _bootstrap(client, tmp_path, monkeypatch)
    client.cookies.clear()

    accepted = client.post(
        "/api/v1/auth/login",
        json={"password": SYNTHETIC_PASSWORD, "remember_me": False},
    )
    assert accepted.status_code == 200
    assert accepted.json().get("ok") is True

    client.cookies.clear()
    rejected = client.post(
        "/api/v1/auth/login",
        json={"password": "Definitely-Wrong!9", "remember_me": False},
    )
    assert rejected.status_code == 401
    assert rejected.json() == {"ok": False, "error": "Wrong password"}
