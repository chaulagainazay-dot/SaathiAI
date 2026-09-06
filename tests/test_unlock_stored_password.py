"""Regression coverage for canonical Security Store password unlock."""
from __future__ import annotations

import hashlib
import secrets

import pytest
from fastapi.testclient import TestClient


def _scrypt_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32
    )
    return f"scrypt${2**14}$8$1${salt.hex()}${digest.hex()}"


@pytest.fixture
def stored_owner(tmp_path, monkeypatch):
    from saathi import authsec
    from saathi.security import store as store_module
    from saathi.security.registry import close_registry
    from saathi.security.timeline import close_timeline
    import saathi.server as server

    store_module.close_store()
    close_registry()
    close_timeline()
    store = store_module.SecurityStore(tmp_path / "security.db")
    store_module._default_store = store
    authsec._WINDOWS.clear()
    monkeypatch.setattr(authsec, "_DIR", tmp_path / "audit")
    monkeypatch.setattr(authsec, "_AUDIT", tmp_path / "audit" / "auth_audit.log")
    monkeypatch.setattr(server, "_PASSWORD_HASH", "")
    monkeypatch.setattr(server, "_RAW_PASSWORD", "")
    monkeypatch.setattr(server, "ACCESS_TOKEN", "")

    owner_id = store.get_or_create_owner()
    password = secrets.token_urlsafe(24)
    store.save_password(owner_id, _scrypt_hash(password), strength_score=4)
    yield server, store, password

    close_timeline()
    close_registry()
    store_module.close_store()
    authsec._WINDOWS.clear()


def test_unlock_accepts_canonical_stored_owner_password(stored_owner):
    server, store, password = stored_owner

    assert store.active_owner_has_password() is True
    assert store.verify_active_owner_password(password) is True
    response = TestClient(server.app).post(
        "/api/v1/auth/login", json={"password": password}
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_unlock_rejects_wrong_password_when_only_stored_credential_exists(stored_owner):
    server, store, _password = stored_owner

    assert store.active_owner_has_password() is True
    response = TestClient(server.app).post(
        "/api/v1/auth/login", json={"password": secrets.token_urlsafe(24)}
    )

    assert response.status_code == 401
    assert response.json() == {"ok": False, "error": "Wrong password"}


def test_unlock_status_reports_stored_owner_password(stored_owner):
    server, _store, _password = stored_owner

    response = TestClient(server.app).get("/api/v1/auth/passkey/status")

    assert response.status_code == 200
    assert response.json()["has_password"] is True


def test_shared_verifier_preserves_legacy_formats():
    from saathi import authsec

    password = secrets.token_urlsafe(24)
    assert authsec.verify_password(password, authsec.hash_password(password)) is True
    legacy_hash = hashlib.sha256(password.encode()).hexdigest()
    assert authsec.verify_password(password, legacy_hash) is True


def test_shared_verifier_rejects_malformed_scrypt_without_raising():
    from saathi import authsec

    assert authsec.verify_password(secrets.token_urlsafe(24), "scrypt$bad") is False
