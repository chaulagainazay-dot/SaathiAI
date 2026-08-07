"""M50 identity, RBAC, sessions, and isolation."""
from __future__ import annotations

import pytest

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformPermission, PlatformRole, role_has_permission
from saathi.platform.service import reset_platform_for_tests


@pytest.fixture()
def plat(tmp_path):
    return reset_platform_for_tests(tmp_path / "p.db")


def test_bootstrap_and_login(plat):
    boot = plat.bootstrap_owner(email="ajay@local", name="Ajay")
    assert boot["bootstrapped"] is True
    assert boot["user"]["email"] == "ajay@local"
    assert boot["org"]["org_id"]
    assert boot["workspace"]["workspace_id"]

    login = plat.login(email="ajay@local")
    assert login["token"]
    assert login["session"]["role"] == PlatformRole.OWNER.value
    assert PlatformPermission.APPROVAL_DECIDE.value in login["permissions"]


def test_anonymous_prohibited(plat):
    plat.bootstrap_owner()
    with pytest.raises(PlatformContextError) as ei:
        plat.require_context(None)
    assert ei.value.code == "ANONYMOUS_PROHIBITED"
    with pytest.raises(PlatformContextError) as ei2:
        plat.require_context("")
    assert ei2.value.code == "ANONYMOUS_PROHIBITED"


def test_session_expiry_and_revocation(plat, tmp_path):
    plat.bootstrap_owner(email="u@local")
    login = plat.login(email="u@local", ttl_sec=3600)
    token = login["token"]
    ctx = plat.require_context(token)
    assert ctx.user_id

    assert plat.logout(token) is True
    with pytest.raises(PlatformContextError) as ei:
        plat.require_context(token)
    assert ei.value.code == "SESSION_INVALID"


def test_rbac_viewer_cannot_decide_or_execute(plat):
    plat.bootstrap_owner(email="owner@local")
    # create second user as viewer
    viewer = plat.store.create_user(email="viewer@local", name="V")
    org = plat.store.list_orgs_for_user(
        plat.store.get_user_by_email("owner@local").user_id
    )[0]
    plat.store.add_member(org.org_id, viewer.user_id, PlatformRole.VIEWER.value)
    # login as viewer needs membership - login uses first org
    # bootstrap session as owner, then create session for viewer manually
    from saathi.platform.models import PlatformRole as R
    import secrets

    ws = plat.store.list_workspaces(org.org_id)[0]
    raw = secrets.token_urlsafe(16)
    plat.store.create_session(
        viewer.user_id,
        raw,
        org_id=org.org_id,
        workspace_id=ws.workspace_id,
        role=R.VIEWER.value,
    )
    ctx = plat.require_context(raw)
    assert role_has_permission(ctx.role, PlatformPermission.PROJECT_READ)
    assert not role_has_permission(ctx.role, PlatformPermission.RUNTIME_EXECUTE)
    with pytest.raises(PlatformContextError) as ei:
        ctx.require_permission(PlatformPermission.APPROVAL_DECIDE)
    assert ei.value.code == "PERMISSION_DENIED"


def test_workspace_isolation(plat):
    plat.bootstrap_owner(email="a@local")
    login = plat.login(email="a@local")
    token = login["token"]
    # foreign project id
    with pytest.raises(PlatformContextError) as ei:
        plat.require_context(token, project_id="prj_does_not_exist")
    assert ei.value.code == "PROJECT_ISOLATION"


def test_cross_user_project_create_denied_for_viewer(plat):
    plat.bootstrap_owner(email="owner@local")
    owner = plat.store.get_user_by_email("owner@local")
    org = plat.store.list_orgs_for_user(owner.user_id)[0]
    ws = plat.store.list_workspaces(org.org_id)[0]
    viewer = plat.store.create_user(email="v@local", name="V")
    plat.store.add_member(org.org_id, viewer.user_id, PlatformRole.VIEWER.value)
    import secrets

    raw = secrets.token_urlsafe(16)
    plat.store.create_session(
        viewer.user_id,
        raw,
        org_id=org.org_id,
        workspace_id=ws.workspace_id,
        role=PlatformRole.VIEWER.value,
    )
    ctx = plat.require_context(raw)
    with pytest.raises(PlatformContextError):
        plat.create_project(ctx, "Nope")
