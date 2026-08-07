"""M51 invitations, membership admin, workspace context."""
from __future__ import annotations

import pytest

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformRole
from saathi.platform.service import reset_platform_for_tests
import saathi.platform.alpha  # noqa: F401


@pytest.fixture()
def plat(tmp_path):
    return reset_platform_for_tests(tmp_path / "m51i.db")


def _owner(plat):
    return plat.bootstrap_owner_secure(
        email="owner@org.local", name="Owner", password="GoodPassw0rd!"
    )


def test_invite_accept_flow(plat):
    boot = _owner(plat)
    ctx = plat.require_context(boot["token"])
    inv = plat.create_invitation(
        ctx, email="member@org.local", role=PlatformRole.OPERATOR.value
    )
    assert inv["local_private_alpha_invite"] is True
    code = inv["invite_code"]

    # replay after accept fails later; first accept works
    login = plat.accept_invitation(
        invite_code=code, name="Member", password="MemberPassw0rd!"
    )
    assert login["token"]
    mctx = plat.require_context(login["token"])
    assert mctx.role == PlatformRole.OPERATOR.value

    # single-use
    with pytest.raises(PlatformContextError):
        plat.accept_invitation(
            invite_code=code, name="X", password="MemberPassw0rd!"
        )


def test_cannot_invite_above_role(plat):
    boot = _owner(plat)
    ctx = plat.require_context(boot["token"])
    inv = plat.create_invitation(ctx, email="op@org.local", role="operator")
    plat.accept_invitation(
        invite_code=inv["invite_code"], name="Op", password="OperatorPass1!"
    )
    op = plat.authenticate_login(email="op@org.local", password="OperatorPass1!")
    octx = plat.require_context(op["token"])
    with pytest.raises(PlatformContextError) as ei:
        plat.create_invitation(octx, email="x@org.local", role="owner")
    assert ei.value.code in ("PERMISSION_DENIED", "ROLE_ESCALATION")


def test_last_owner_protection(plat):
    boot = _owner(plat)
    ctx = plat.require_context(boot["token"])
    with pytest.raises(PlatformContextError) as ei:
        plat.change_member_role(ctx, ctx.user_id, PlatformRole.VIEWER.value)
    assert ei.value.code == "LAST_OWNER"


def test_workspace_switch_rotates_and_isolates(plat):
    boot = _owner(plat)
    ctx = plat.require_context(boot["token"])
    # create second workspace
    ws2 = plat.store.create_workspace(ctx.org_id, "WS2", ctx.user_id)
    out = plat.select_workspace(
        boot["token"], org_id=ctx.org_id, workspace_id=ws2.workspace_id
    )
    assert out["token"] != boot["token"]
    with pytest.raises(PlatformContextError):
        plat.require_context(boot["token"])
    nctx = plat.require_context(out["token"])
    assert nctx.workspace_id == ws2.workspace_id
    # foreign workspace denied
    with pytest.raises(PlatformContextError):
        plat.select_workspace(
            out["token"], org_id=ctx.org_id, workspace_id="ws_nope"
        )


def test_remove_member_revokes_sessions(plat):
    boot = _owner(plat)
    ctx = plat.require_context(boot["token"])
    inv = plat.create_invitation(ctx, email="gone@org.local", role="viewer")
    mlogin = plat.accept_invitation(
        invite_code=inv["invite_code"], name="G", password="GoneUserPass1!"
    )
    mtok = mlogin["token"]
    assert plat.require_context(mtok).user_id
    mid = plat.require_context(mtok).user_id
    plat.remove_member(ctx, mid)
    with pytest.raises(PlatformContextError):
        plat.require_context(mtok)
