"""M61 — workflow persistence: plans, notifications, saved views, templates,
drafts, attention mutations, server search. Concurrency, RBAC, tenant isolation,
audit, and HTTP contracts."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.service import reset_platform_for_tests
from saathi.platform.workflow_service import WorkflowService


@pytest.fixture()
def alpha(tmp_path):
    platform = reset_platform_for_tests(tmp_path / "m61.db")
    owner = platform.bootstrap_owner_secure(
        email="owner@m61.local", name="Owner", password="OwnerPassw0rd!",
        org_name="M61 Org", workspace_name="M61 Workspace",
    )
    ctx = platform.require_context(owner["token"])
    return platform, owner["token"], ctx


def _wf(alpha):
    platform, _, _ = alpha
    return WorkflowService(platform.store)


# ── plans ──────────────────────────────────────────────────────────────────
def test_plan_persist_version_and_conflict(alpha):
    platform, _, ctx = alpha
    wf = _wf(alpha)
    p = wf.upsert_plan(ctx, mission_id="m1", body={"stages": ["a"]})
    assert p["version"] == 1 and p["state"] == "draft"
    p2 = wf.upsert_plan(ctx, mission_id="m1", body={"stages": ["a", "b"]}, expected_version=1)
    assert p2["version"] == 2
    assert wf.get_plan(ctx, mission_id="m1")["body"]["stages"] == ["a", "b"]
    with pytest.raises(PlatformContextError) as e:
        wf.upsert_plan(ctx, mission_id="m1", body={"x": 1}, expected_version=1)  # stale
    assert e.value.code == "STALE_STATE"
    revs = wf.plan_revisions(ctx, plan_id=p["plan_id"])
    assert len(revs) == 2


def test_plan_publish_not_automatic(alpha):
    _, _, ctx = alpha
    wf = _wf(alpha)
    p = wf.upsert_plan(ctx, mission_id="m2", body={})
    assert p["state"] == "draft"  # never auto-published
    pub = wf.publish_plan(ctx, mission_id="m2", expected_version=p["version"])
    assert pub["state"] == "published"


# ── notifications ───────────────────────────────────────────────────────────
def test_notification_create_dedupe_flags(alpha):
    _, _, ctx = alpha
    wf = _wf(alpha)
    n = wf.create_notification(ctx, type="approval_requested", title="A", dedupe_key="k")
    n_dup = wf.create_notification(ctx, type="approval_requested", title="A", dedupe_key="k")
    assert n["notification_id"] == n_dup["notification_id"]  # deduped
    assert wf.list_notifications(ctx)[0]["read"] == 0
    upd = wf.set_notification(ctx, n["notification_id"], read=True)
    assert upd["read"] == 1
    wf.set_notification(ctx, n["notification_id"], archived=True)
    assert len(wf.list_notifications(ctx)) == 0
    assert len(wf.list_notifications(ctx, include_archived=True)) == 1


# ── saved views ─────────────────────────────────────────────────────────────
def test_saved_view_crud_and_secret_rejection(alpha):
    _, _, ctx = alpha
    wf = _wf(alpha)
    v = wf.create_view(ctx, name="High risk", route="/platform/approvals", config={"risk": "high"})
    assert v["config"]["risk"] == "high" and v["version"] == 1
    v2 = wf.update_view(ctx, v["view_id"], expected_version=1, name="Renamed")
    assert v2["name"] == "Renamed" and v2["version"] == 2
    with pytest.raises(PlatformContextError) as e:
        wf.update_view(ctx, v["view_id"], expected_version=1, name="stale")
    assert e.value.code == "STALE_STATE"
    with pytest.raises(PlatformContextError) as e:
        wf.create_view(ctx, name="bad", route="/x", config={"token": "sekret"})
    assert e.value.code == "UNSAFE_CONFIG"
    wf.delete_view(ctx, v["view_id"])
    assert wf.list_views(ctx) == []


# ── templates ───────────────────────────────────────────────────────────────
def test_template_crud(alpha):
    _, _, ctx = alpha
    wf = _wf(alpha)
    t = wf.create_template(ctx, name="Review", body={"stages": ["a"]})
    assert t["version"] == 1
    t2 = wf.update_template(ctx, t["template_id"], expected_version=1, name="Review v2")
    assert t2["name"] == "Review v2" and t2["version"] == 2
    assert len(wf.list_templates(ctx)) == 1
    wf.update_template(ctx, t["template_id"], expected_version=2, state="archived")
    assert wf.list_templates(ctx) == []  # archived hidden


# ── drafts ──────────────────────────────────────────────────────────────────
def test_draft_upsert_and_discard(alpha):
    _, _, ctx = alpha
    wf = _wf(alpha)
    d = wf.save_draft(ctx, kind="mission", body={"title": "t1"})
    assert d["version"] == 1
    d2 = wf.save_draft(ctx, kind="mission", body={"title": "t2"})
    assert d2["version"] == 2 and wf.get_draft(ctx, kind="mission")["body"]["title"] == "t2"
    wf.discard_draft(ctx, kind="mission")
    assert wf.get_draft(ctx, kind="mission") is None


# ── attention mutations ─────────────────────────────────────────────────────
def test_attention_lifecycle_and_audit(alpha):
    platform, _, ctx = alpha
    wf = _wf(alpha)
    assert wf.attention_state(ctx, "e1")["state"] == "open"
    a = wf.attention_transition(ctx, "e1", action="acknowledge", note="looking")
    assert a["state"] == "acknowledged" and a["version"] == 1
    r = wf.attention_transition(ctx, "e1", action="resolve")
    assert r["state"] == "resolved"
    ro = wf.attention_transition(ctx, "e1", action="reopen")
    assert ro["state"] == "open"
    with pytest.raises(PlatformContextError):
        wf.attention_transition(ctx, "e1", action="bogus")
    # audit written for each mutation
    audits = [a["event"] for a in platform.store.list_audit(org_id=ctx.org_id, limit=50)]
    assert "attention.acknowledge" in audits and "attention.resolve" in audits


# ── RBAC + tenant isolation ─────────────────────────────────────────────────
def test_viewer_cannot_write(alpha):
    _, _, ctx = alpha
    wf = _wf(alpha)
    viewer = PlatformExecutionContext(user_id="v", role="viewer", org_id=ctx.org_id, workspace_id=ctx.workspace_id)
    with pytest.raises(PlatformContextError) as e:
        wf.create_view(viewer, name="x", route="/platform/x", config={})
    assert e.value.code == "PERMISSION_DENIED"
    with pytest.raises(PlatformContextError):
        wf.attention_transition(viewer, "e", action="acknowledge")
    # viewer CAN read
    assert wf.list_notifications(viewer) == []


def test_tenant_isolation(alpha):
    _, _, ctx = alpha
    wf = _wf(alpha)
    wf.upsert_plan(ctx, mission_id="mine", body={"secret_ish": "no"})
    other = PlatformExecutionContext(user_id="o", role="operator", org_id="other-org", workspace_id="other-ws")
    assert wf.get_plan(other, mission_id="mine") is None
    assert wf.search(other, "mine")["results"] == []


# ── server search ───────────────────────────────────────────────────────────
def test_server_search_scope(alpha):
    platform, _, ctx = alpha
    wf = _wf(alpha)
    proj = platform.create_project(ctx, "Search Project")
    platform.create_mission(ctx, proj["project_id"], "SRCH", "Searchable Mission")
    res = wf.search(ctx, "searchable")
    assert res["scope"] == "SERVER_AUTHORIZED"
    assert any(r["type"] == "mission" for r in res["results"])
    assert wf.search(ctx, "")["results"] == []


# ── HTTP contract ───────────────────────────────────────────────────────────
def test_http_contracts(alpha):
    _, token, _ = alpha
    from saathi.server import app
    client = TestClient(app)
    h = {"X-Platform-Token": token}
    # plan
    r = client.put("/api/v1/platform/workflow/plans", json={"mission_id": "hm", "body": {"a": 1}}, headers=h)
    assert r.status_code == 200 and r.json()["plan"]["version"] == 1
    ver = r.json()["plan"]["version"]
    # stale write → 409
    r_conf = client.put("/api/v1/platform/workflow/plans", json={"mission_id": "hm", "body": {"a": 2}, "expected_version": 999}, headers=h)
    assert r_conf.status_code == 409
    # saved view
    r = client.post("/api/v1/platform/workflow/saved-views", json={"name": "v", "route": "/platform/missions", "config": {}}, headers=h)
    assert r.status_code == 200
    vid = r.json()["view"]["view_id"]
    assert client.get("/api/v1/platform/workflow/saved-views", headers=h).json()["views"][0]["view_id"] == vid
    # secret rejection → 400
    r_bad = client.post("/api/v1/platform/workflow/saved-views", json={"name": "b", "route": "/x", "config": {"password": "p"}}, headers=h)
    assert r_bad.status_code == 400
    # attention action
    r = client.post("/api/v1/platform/workflow/attention/ex1/action", json={"action": "acknowledge"}, headers=h)
    assert r.status_code == 200 and r.json()["attention"]["state"] == "acknowledged"
    # notifications
    assert client.get("/api/v1/platform/workflow/notifications", headers=h).status_code == 200
    # unauthenticated → 401
    assert client.get("/api/v1/platform/workflow/saved-views").status_code == 401
