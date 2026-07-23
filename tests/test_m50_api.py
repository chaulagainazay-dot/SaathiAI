"""M50 platform API routes."""
from __future__ import annotations

from fastapi.testclient import TestClient

from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


def _client(tmp_path, monkeypatch):
    reset_registry_for_tests()
    svc = reset_platform_for_tests(tmp_path / "api.db")
    # ensure default_platform used by API is this instance
    import saathi.platform.service as svcmod
    import saathi.platform.api as apimod

    monkeypatch.setattr(svcmod, "_DEFAULT", svc)
    monkeypatch.setattr(apimod, "default_platform", lambda: svc)
    from saathi.server import app

    return TestClient(app), svc


def test_health_and_bootstrap_login_execute(tmp_path, monkeypatch):
    client, svc = _client(tmp_path, monkeypatch)
    h = client.get("/api/v1/platform/health")
    assert h.status_code == 200
    assert h.json()["identity"] == "ACTIVE"
    assert h.json()["runtime"]["gateway"] == "TOOL_GATEWAY_ENFORCED"

    b = client.post(
        "/api/v1/platform/bootstrap",
        json={"email": "api@local", "name": "API"},
    )
    assert b.status_code == 200
    assert b.json()["bootstrapped"] is True

    login = client.post("/api/v1/platform/auth/login", json={"email": "api@local"})
    assert login.status_code == 200
    token = login.json()["token"]
    headers = {"X-Platform-Token": token}

    me = client.get("/api/v1/platform/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "api@local"

    # anonymous blocked
    assert client.get("/api/v1/platform/me").status_code == 401

    ex = client.post(
        "/api/v1/platform/execute",
        headers=headers,
        json={"tool_id": "m49.echo_readonly", "arguments": {"text": "via-api"}},
    )
    assert ex.status_code == 200
    body = ex.json()
    assert body["ok"] is True
    assert body["data"]["echo"] == "via-api"


def test_api_approval_inbox(tmp_path, monkeypatch):
    client, svc = _client(tmp_path, monkeypatch)
    client.post("/api/v1/platform/bootstrap", json={"email": "a@local"})
    token = client.post(
        "/api/v1/platform/auth/login", json={"email": "a@local"}
    ).json()["token"]
    headers = {"X-Platform-Token": token}
    r = client.post(
        "/api/v1/platform/approvals",
        headers=headers,
        json={
            "tool_id": "m49.local_note_write",
            "capability": "write",
            "side_effect_class": "LOCAL_REVERSIBLE",
            "authority": "LOCAL_MUTATION",
        },
    )
    assert r.status_code == 200
    aid = r.json()["approval"]["approval_id"]
    d = client.post(
        f"/api/v1/platform/approvals/{aid}/decide",
        headers=headers,
        json={"approve": True, "reason": "ship"},
    )
    assert d.status_code == 200
    assert d.json()["approval"]["status"] == "approved"
    inbox = client.get("/api/v1/platform/approvals?status=approved", headers=headers)
    assert inbox.status_code == 200
    assert any(x["approval_id"] == aid for x in inbox.json()["approvals"])
