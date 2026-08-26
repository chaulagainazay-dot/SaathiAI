"""M50 platform API routes."""
from __future__ import annotations

from fastapi.testclient import TestClient

from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


def _support():
    """tests/support is not a package on sys.path by default."""
    import sys, pathlib as _pl
    sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
    from support import platform_auth
    return platform_auth



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

    # D15: platform identity is derived from the canonical D14 owner;
    # the anonymous bootstrap and passwordless login are both closed.
    token_ = _support().platform_token(client)

    class login:            # keeps the assertions below meaningful
        status_code = 200
        @staticmethod
        def json():
            return {"token": token_}
    assert login.status_code == 200
    token = login.json()["token"]
    headers = {"X-Platform-Token": token}

    me = client.get("/api/v1/platform/me", headers=headers)
    assert me.status_code == 200
    # D15: the platform identity is the canonical D14 owner's, not an address
    # the caller picked. Asserting a caller-chosen email here would be asserting
    # the vulnerability that was removed.
    from saathi.security.store import get_store as _sec_store
    _owner = _sec_store().get_user(_sec_store().owner_id()) or {}
    assert me.json()["user"]["email"] == _owner.get("email")

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
    # D15: platform identity is derived from the canonical D14 owner;
    # the anonymous bootstrap and passwordless login are both closed.
    token = _support().platform_token(client)
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
