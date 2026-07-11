"""M15.1 authenticated connector API — unit + security + isolation + redaction."""
import tempfile

import pytest
from fastapi import HTTPException

from saathi.connectors.platform import api
from saathi.connectors.platform import store as S
from saathi.connectors.platform.execution import ExecutionEngine


def _req(user="ajay"):
    return type("R", (), {"state": type("S", (), {"user_id": user})()})()


@pytest.fixture
def store(monkeypatch):
    st = S.ConnectorStore(tempfile.mktemp(suffix=".db"))
    monkeypatch.setattr(api, "_store", lambda: st)
    monkeypatch.setattr(api, "_engine", lambda: ExecutionEngine(store=st))
    return st


def test_unauthenticated_rejected():
    from fastapi.testclient import TestClient
    from saathi.server import app
    # remote (TestClient) without token → 401
    assert TestClient(app).get("/api/v1/connectors/tools").status_code == 401
    assert TestClient(app).get("/api/v1/connectors/health/platform").status_code == 401


def test_registry_routes(store):
    assert api.list_connectors(_req(), limit=100, offset=0)["total"] >= 10
    assert api.tools(_req())["total"] >= 20
    assert "categories" in api.categories(_req())
    assert api.capabilities(_req())["capabilities"]
    t = api.tool(_req(), "github.list_issues")
    assert t["tool_id"] == "github.list_issues"
    with pytest.raises(HTTPException):
        api.tool(_req(), "nope.nope")


def test_health_and_metrics(store):
    ph = api.platform_health(_req())
    assert ph["total"] >= 10
    m = api.metrics(_req())
    assert "sample_size" in m and "success_rate" in m


def test_account_lifecycle_owner_scoped(store):
    body = api.AccountIn(connector_id="github", label="gh", backend="env",
                         backend_key="GITHUB_TOKEN")
    res = api.connect_account(_req("ajay"), body)
    aid = res["account_id"]
    got = api.get_account(_req("ajay"), aid)
    assert got["account"]["connector_id"] == "github"
    # credential metadata only — the env var NAME, never a value
    assert got["credential_ref"]["backend_key"] == "GITHUB_TOKEN"
    assert "value" not in got["credential_ref"] and "secret" not in got["credential_ref"]
    # cross-user access rejected
    with pytest.raises(HTTPException) as e:
        api.get_account(_req("mallory"), aid)
    assert e.value.status_code == 403


def test_execution_requires_account_ownership(store):
    aid = store.add_account(owner="ajay", connector_id="github", label="g", state="healthy")
    # cross-user execution on someone else's account → 403
    with pytest.raises(HTTPException) as e:
        api.execute(_req("mallory"), api.ExecIn(tool_id="github.list_issues",
                    account_id=aid, args={"_fixture": "success"}))
    assert e.value.status_code == 403
    # owner can execute
    r = api.execute(_req("ajay"), api.ExecIn(tool_id="github.list_issues",
                    account_id=aid, args={"_fixture": "success"}))
    assert r["status"] == "success"
    assert "gateway_ref" in r["provenance"]  # gateway-routed, no bypass


def test_side_effect_needs_bound_approval_via_api(store):
    aid = store.add_account(owner="ajay", connector_id="github", label="g", state="healthy")
    body = api.ExecIn(tool_id="github.create_issue", account_id=aid, args={"title": "x"})
    assert api.execute(_req("ajay"), body)["status"] == "approval_required"
    appr = api.request_approval(_req("ajay"), api.ApprovalReqIn(
        tool_id="github.create_issue", account_id=aid, args={"title": "x"}))
    api.decide(_req("ajay"), appr["approval_id"], approved=True)
    body.approval_id = appr["approval_id"]
    assert api.execute(_req("ajay"), body)["status"] == "success"
    # changed input invalidates the approval
    body2 = api.ExecIn(tool_id="github.create_issue", account_id=aid,
                       args={"title": "DIFFERENT"}, approval_id=appr["approval_id"])
    assert api.execute(_req("ajay"), body2)["status"] == "approval_required"


def test_approval_cross_user_rejected(store):
    aid = store.add_account(owner="ajay", connector_id="github", label="g", state="healthy")
    appr = api.request_approval(_req("ajay"), api.ApprovalReqIn(
        tool_id="github.create_issue", account_id=aid, args={"title": "x"}))
    with pytest.raises(HTTPException) as e:
        api.decide(_req("mallory"), appr["approval_id"], approved=True)
    assert e.value.status_code == 404


def test_disconnected_account_cannot_execute(store):
    aid = store.add_account(owner="ajay", connector_id="github", label="g",
                            state="disconnected")
    r = api.execute(_req("ajay"), api.ExecIn(tool_id="github.list_issues",
                    account_id=aid, args={"_fixture": "success"}))
    assert r["status"] == "failed"


def test_no_secret_in_error_body(store):
    aid = store.add_account(owner="ajay", connector_id="github", label="g", state="healthy")
    r = api.execute(_req("ajay"), api.ExecIn(tool_id="github.list_issues",
                    account_id=aid, args={"_fixture": "auth_fail"}))
    body = str(r)
    assert "token=" not in body.lower() or "[redacted]" in body.lower()


def test_execution_history_owner_scoped(store):
    aid = store.add_account(owner="ajay", connector_id="github", label="g", state="healthy")
    api.execute(_req("ajay"), api.ExecIn(tool_id="github.list_issues",
                account_id=aid, args={"_fixture": "success"}))
    mine = api.list_executions(_req("ajay"))
    assert len(mine["items"]) >= 1
    other = api.list_executions(_req("mallory"))
    assert other["items"] == []
