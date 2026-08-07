"""M64 — module discovery HTTP endpoints: authentication, permission gating,
authoritative discovery payload, safe 404. Uses the real FastAPI app + a real
bootstrapped platform token (same harness as M50 API tests).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


def _client(tmp_path, monkeypatch):
    reset_registry_for_tests()
    svc = reset_platform_for_tests(tmp_path / "api.db")
    import saathi.platform.service as svcmod
    import saathi.platform.api as apimod
    monkeypatch.setattr(svcmod, "_DEFAULT", svc)
    monkeypatch.setattr(apimod, "default_platform", lambda: svc)
    from saathi.server import app
    return TestClient(app), svc


def _token(client):
    client.post("/api/v1/platform/bootstrap", json={"email": "m64@local", "name": "M64"})
    login = client.post("/api/v1/platform/auth/login", json={"email": "m64@local"})
    return login.json()["token"]


def test_modules_requires_authentication(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    for path in ("/modules", "/dashboard", "/navigation", "/modules/trading/health"):
        r = client.get(f"/api/v1/platform{path}")
        assert r.status_code == 401, path


def test_authenticated_discovery_is_authoritative(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    headers = {"X-Platform-Token": _token(client)}
    r = client.get("/api/v1/platform/modules", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["contract_version"] == "m64.1"
    ids = {m["id"] for m in body["installed"]}
    assert "trading" in ids
    trading = next(m for m in body["installed"] if m["id"] == "trading")
    assert trading["state"] == "available"
    assert trading["enabled"] is True and trading["implemented"] is True
    # IELTSAlert is now the second implemented module.
    ielts = next(m for m in body["installed"] if m["id"] == "ielts")
    assert ielts["state"] == "available"
    assert ielts["operational"] is True
    assert ielts["feature_flags"]["provider_assisted_scoring"] is False


def test_dashboard_and_navigation_endpoints(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    headers = {"X-Platform-Token": _token(client)}
    dash = client.get("/api/v1/platform/dashboard", headers=headers).json()
    assert dash["contract_version"] == "m64.1"
    trading_card = next(c for c in dash["cards"] if c["module_id"] == "trading")
    assert trading_card["primary_route"] == "/trading"
    nav = client.get("/api/v1/platform/navigation", headers=headers).json()
    assert nav["group"] == "applications"
    assert any(m["id"] == "trading" and m["actionable"] for m in nav["modules"])


def test_unknown_module_safe_404(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    headers = {"X-Platform-Token": _token(client)}
    r = client.get("/api/v1/platform/modules/nope-not-real", headers=headers)
    assert r.status_code == 404


def test_module_detail_and_health(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    headers = {"X-Platform-Token": _token(client)}
    d = client.get("/api/v1/platform/modules/trading", headers=headers).json()
    assert d["module"]["id"] == "trading"
    h = client.get("/api/v1/platform/modules/trading/health", headers=headers).json()
    assert h["module_id"] == "trading"
    assert h["state"] == "available"


def test_no_internal_paths_in_response(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    headers = {"X-Platform-Token": _token(client)}
    raw = client.get("/api/v1/platform/modules", headers=headers).text.lower()
    for needle in ("/users/", "health_fn", "moduledescriptor", "db_path", "sqlite"):
        assert needle not in raw, needle
