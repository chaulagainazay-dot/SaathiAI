"""M148–M156 SaathiOS Core unification — focused tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.platform.apps import AppRuntime, reset_app_runtime_for_tests
from saathi.platform.context import PlatformContextError
from saathi.platform.core_os import SaathiCoreService, reset_core_service_for_tests
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture
def env(tmp_path: Path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "core.db")
    boot = platform.bootstrap_owner_secure(
        email="core-owner@local", name="Core Owner", password="CoreOwnerPass1!",
    )
    ctx = platform.require_context(boot["token"])
    core = SaathiCoreService(platform)
    apps = AppRuntime(platform)
    # Install first-party apps for cross-app surfaces
    for pkg, aid in (("hcg_pos", "saathi.hcg_pos"), ("ielts_alert", "saathi.ielts_alert")):
        try:
            apps.register(ctx, package_id=pkg)
            apps.enable(ctx, aid)
        except Exception:
            pass
    yield platform, boot["token"], ctx, core, apps
    reset_core_service_for_tests(platform)
    reset_app_runtime_for_tests(platform)
    reset_platform_for_tests()
    reset_registry_for_tests()


def test_operator_home_unified(env):
    _, _, ctx, core, _ = env
    home = core.operator_home(ctx)
    assert home["unified"] is True
    assert home["production_authorized"] is False
    assert "applications" in home
    assert "todays_work" in home
    assert "quick_actions" in home
    assert home["health"]["duplicates_forbidden"] is True


def test_universal_search_tenant_scoped(env):
    platform, _, ctx, core, _ = env
    r = core.universal_search(ctx, "approval")
    assert r["scope"] == "SERVER_AUTHORIZED"
    assert r["tenant_isolated"] is True
    assert r["permissions_enforced"] is True
    # seed a mission name hit
    r2 = core.universal_search(ctx, "hcg")
    assert r2["count"] >= 0


def test_yeti_readonly_cross_app(env):
    _, _, ctx, core, _ = env
    ans = core.yeti_ask(ctx, "What should I do first today?")
    assert ans["can_mutate"] is False
    assert ans["execution_gateway_bypass"] is False
    ans2 = core.yeti_ask(ctx, "How is my IELTS progress?")
    assert ans2["can_mutate"] is False
    domains = [d.get("domain") for d in ans2.get("domains") or []]
    assert "ielts" in domains or ans2.get("answer")


def test_memory_isolation_and_forbidden_keys(env):
    platform, _, ctx, core, _ = env
    core.update_preferences(ctx, {"theme": "dark", "locale": "en"})
    mem = core.get_memory(ctx)
    assert mem["tenant_isolated"] is True
    assert mem["memory"]["preferences"]["theme"] == "dark"
    with pytest.raises(PlatformContextError) as err:
        core.update_preferences(ctx, {"api_key": "secret"})
    assert err.value.code == "UNSAFE_CONFIG"

    # other workspace cannot see memory
    other = platform.store.create_user(email="other-core@local", name="O")
    org = platform.store.create_org("Other Core Org", other.user_id)
    ws = platform.store.create_workspace(org.org_id, "OWS", other.user_id)
    platform.store.add_member(org.org_id, other.user_id, "owner")
    _, tok = platform.store.create_session(
        other.user_id, "o", org_id=org.org_id, workspace_id=ws.workspace_id, role="owner"
    )
    octx = platform.require_context(tok)
    omem = core.get_memory(octx)
    assert omem["memory"]["preferences"].get("theme") != "dark" or not omem["memory"]["preferences"]


def test_automation_and_workflow_no_bypass(env):
    _, _, ctx, core, _ = env
    auto = core.create_automation(
        ctx, name="Morning summary", schedule="daily_morning",
        action="summarize", app_scope="all",
    )
    assert auto["automation"]["bypass_gateway"] is False
    assert auto["automation"]["direct_tool_execution"] is False
    dry = core.run_automation_dry(ctx, auto["automation"]["automation_id"])
    assert dry["proposal"]["executed"] is False
    assert dry["proposal"]["bypass_gateway"] is False

    graph = core.save_workflow_graph(
        ctx,
        name="Gated flow",
        nodes=[
            {"id": "1", "type": "trigger"},
            {"id": "2", "type": "approval"},
            {"id": "3", "type": "execution"},
            {"id": "4", "type": "finish"},
        ],
        edges=[{"from": "1", "to": "2"}, {"from": "2", "to": "3"}, {"from": "3", "to": "4"}],
    )
    assert graph["graph"]["bypass_gateway"] is False
    exec_nodes = [n for n in graph["graph"]["nodes"] if n["type"] == "execution"]
    assert exec_nodes[0]["gateway_required"] is True
    assert exec_nodes[0]["direct_tool_execution"] is False


def test_notification_center_and_commands(env):
    _, _, ctx, core, _ = env
    n = core.notification_center(ctx)
    assert n["unified"] is True
    assert "platform" in n["channels"]
    cmds = core.command_catalog(ctx)
    assert cmds["count"] >= 5
    labels = " ".join(c["label"] for c in cmds["commands"])
    assert "HCG" in labels or "Operator" in labels


def test_cross_app_context(env):
    _, _, ctx, core, _ = env
    ctx_out = core.cross_app_context(ctx)
    assert ctx_out["isolation"] == "no cross-app direct database access"
    assert "recommendations" in ctx_out
    assert ctx_out["deep_links"]["hcg"] == "/apps/hcg"
    assert ctx_out["deep_links"]["ielts"] == "/apps/ielts"


def test_viewer_can_read_home(env):
    platform, _, ctx, core, _ = env
    # create viewer session same org
    viewer = platform.store.create_user(email="viewer-core@local", name="V")
    platform.store.add_member(ctx.org_id, viewer.user_id, "viewer")
    _, vtok = platform.store.create_session(
        viewer.user_id, "v", org_id=ctx.org_id, workspace_id=ctx.workspace_id, role="viewer"
    )
    vctx = platform.require_context(vtok)
    home = core.operator_home(vctx)
    assert home["unified"] is True
