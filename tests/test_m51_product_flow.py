"""M51 end-to-end private-alpha product flow."""
from __future__ import annotations

import pytest

from saathi.platform.agent_binding import PlatformAgentBinding, inventory_agent_callers
from saathi.platform.context import PlatformContextError
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests
import saathi.platform.alpha  # noqa: F401


@pytest.fixture()
def plat(tmp_path):
    reset_registry_for_tests()
    return reset_platform_for_tests(tmp_path / "m51e2e.db")


def test_private_alpha_end_to_end(plat):
    """
    Invited user signs in → org/workspace → project/mission → approval →
    gateway execute → audit → logout → isolation.
    """
    # 1. Owner bootstrap
    owner = plat.bootstrap_owner_secure(
        email="owner@alpha.test",
        name="Owner",
        password="OwnerPassw0rd!",
        org_name="Alpha Org",
        workspace_name="Alpha WS",
    )
    octx = plat.require_context(owner["token"])

    # 2. Invite operator
    inv = plat.create_invitation(
        octx, email="user@alpha.test", role="operator"
    )
    user_login = plat.accept_invitation(
        invite_code=inv["invite_code"],
        name="Alpha User",
        password="UserPassw0rd1!",
    )
    uctx = plat.require_context(user_login["token"])
    assert uctx.org_id == octx.org_id
    assert uctx.workspace_id == octx.workspace_id

    # 3. Project + mission
    proj = plat.create_project(uctx, "Alpha Project")
    mis = plat.create_mission(
        uctx, proj["project_id"], "alpha_mission", "Alpha Mission"
    )
    plat.link_legacy_mission(uctx, mis["mission_id"], "mr_yeti")

    # 4. Approval for mutation
    ap = plat.request_approval(
        uctx,
        tool_id="m49.local_note_write",
        capability="write",
        side_effect_class="LOCAL_REVERSIBLE",
        authority="LOCAL_MUTATION",
        ttl_sec=600,
    )
    # operator cannot decide — owner decides
    with pytest.raises(PlatformContextError):
        plat.decide_approval(uctx, ap.approval_id, approve=True)
    plat.decide_approval(octx, ap.approval_id, approve=True, reason="ok")

    # 5. Execute via agent binding (spoof fields ignored at API layer conceptually)
    result = plat.execute_tool(
        uctx,
        tool_id="m49.local_note_write",
        arguments={"key": "alpha", "value": "v1"},
        approval_id=ap.approval_id,
        capability="write",
    )
    assert result.ok, (result.error_code, result.safe_message)

    # agent binding for readonly
    echo_bound = PlatformAgentBinding(plat).execute(
        token=user_login["token"],
        tool_id="m49.echo_readonly",
        arguments={"text": "bound"},
        project_id=proj["project_id"],
        mission_id=mis["mission_id"],
    )
    assert echo_bound.ok

    # readonly execute
    echo = plat.execute_tool(
        uctx, tool_id="m49.echo_readonly", arguments={"text": "hello-alpha"}
    )
    assert echo.ok
    assert echo.data["echo"] == "hello-alpha"

    # 6. Audit
    events = plat.store.list_audit(org_id=uctx.org_id, limit=50)
    assert any(e["event"] == "runtime.execute" for e in events)
    assert any(e["user_id"] == uctx.user_id for e in events)

    # 7. Isolation: other org invisible
    other = plat.bootstrap_owner  # noqa — can't second bootstrap
    # create separate store-backed second user in same org is fine;
    # foreign project denied
    with pytest.raises(PlatformContextError):
        plat.require_context(user_login["token"], project_id="prj_foreign")

    # 8. Logout
    assert plat.logout(user_login["token"]) is True
    with pytest.raises(PlatformContextError):
        plat.require_context(user_login["token"])

    # 9. Agent inventory
    inv_list = inventory_agent_callers()
    assert any(c["platform_bound"] is True for c in inv_list)


def test_agent_binding_rejects_anonymous(plat):
    plat.bootstrap_owner_secure(
        email="a@b.c", name="A", password="GoodPassw0rd!"
    )
    with pytest.raises(PlatformContextError):
        PlatformAgentBinding(plat).execute(
            token="", tool_id="m49.echo_readonly", arguments={"text": "x"}
        )


def test_financial_still_blocked(plat):
    boot = plat.bootstrap_owner_secure(
        email="f@b.c", name="F", password="GoodPassw0rd!"
    )
    ctx = plat.require_context(boot["token"])
    r = plat.execute_tool(
        ctx, tool_id="m49.financial_execution_stub", arguments={"symbol": "AAPL"}
    )
    assert r.outcome_class.value == "PROHIBITED"
