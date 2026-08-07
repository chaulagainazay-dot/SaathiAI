"""M121–M129 Universal Application Runtime — focused tests."""
from __future__ import annotations

import pytest

from saathi.platform.apps import AppLifecycleState, AppRuntime, reset_app_runtime_for_tests
from saathi.platform.context import PlatformContextError
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture()
def env(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "apps.db")
    boot = platform.bootstrap_owner_secure(
        email="app-owner@local",
        name="App Owner",
        password="AppOwnerPass1!",
    )
    ctx = platform.require_context(boot["token"])
    svc = AppRuntime(platform)
    yield platform, boot["token"], ctx, svc
    reset_app_runtime_for_tests(platform)
    reset_platform_for_tests()
    reset_registry_for_tests()


def _install_enable(svc, ctx, package_id, app_id):
    reg = svc.register(ctx, package_id=package_id)
    assert reg["app"]["lifecycle_state"] == AppLifecycleState.INSTALLED.value
    en = svc.enable(ctx, app_id)
    assert en["app"]["lifecycle_state"] == AppLifecycleState.ENABLED.value
    return en["app"]


def test_discover_and_validate(env):
    _, _, ctx, svc = env
    d = svc.discover(ctx)
    assert d["count"] >= 6
    assert d["marketplace"] is False
    valid = [x for x in d["discovered"] if x["package_id"] == "platform_demo"][0]
    assert valid["valid"] is True
    bad = [x for x in d["discovered"] if x["package_id"] == "malicious_app"][0]
    assert bad["valid"] is False


def test_malicious_rejected(env):
    _, _, ctx, svc = env
    v = svc.validate_package(ctx, package_id="malicious_app")
    assert v["ok"] is False
    with pytest.raises(PlatformContextError) as err:
        svc.register(ctx, package_id="malicious_app")
    assert err.value.code == "APP_INVALID"


def test_install_enable_launch(env):
    _, _, ctx, svc = env
    _install_enable(svc, ctx, "crm_lite", "saathi.crm_lite")
    launch = svc.launch(ctx, "saathi.crm_lite")
    assert launch["app"]["lifecycle_state"] == "RUNNING"
    assert launch["bypass_gateway"] is False
    assert launch["workspace"]["isolated"] is True
    assert launch["navigation"]["items"]


def test_workspace_isolation_tenant(env):
    platform, _, ctx, svc = env
    svc.register(ctx, package_id="crm_lite")
    other = platform.store.create_user(email="other-app@local", name="O")
    org = platform.store.create_org("Other App Org", other.user_id)
    ws = platform.store.create_workspace(org.org_id, "OWS", other.user_id)
    platform.store.add_member(org.org_id, other.user_id, "owner")
    _, tok = platform.store.create_session(
        other.user_id, "o-app", org_id=org.org_id, workspace_id=ws.workspace_id, role="owner"
    )
    octx = platform.require_context(tok)
    with pytest.raises(PlatformContextError):
        svc.get_app(octx, "saathi.crm_lite")


def test_permissions_manifest_cannot_grant(env):
    _, _, ctx, svc = env
    svc.register(ctx, package_id="ielts_alert")
    p = svc.resolve_permissions(ctx, "saathi.ielts_alert")
    assert p["manifest_cannot_grant"] is True


def test_workflow_approval_and_no_bypass(env):
    _, _, ctx, svc = env
    # register skill for mutation + app
    from saathi.platform.skills import SkillRuntime

    skills = SkillRuntime(svc.platform)
    skills.register(ctx, package_id="mutation_safe")
    skills.enable(ctx, "saathi.mutation_safe")
    _install_enable(svc, ctx, "platform_demo", "saathi.platform_demo")
    with pytest.raises(PlatformContextError) as err:
        svc.run_workflow(ctx, "saathi.platform_demo", workflow_id="safe_mutation")
    assert err.value.code == "APPROVAL_REQUIRED"
    with pytest.raises(PlatformContextError) as err2:
        svc.run_workflow(
            ctx,
            "saathi.platform_demo",
            workflow_id="safe_mutation",
            approval_reference="appr-1",
            arguments={"bypass_gateway": True},
        )
    assert err2.value.code == "GATEWAY_BYPASS_FORBIDDEN"
    out = svc.run_workflow(
        ctx,
        "saathi.platform_demo",
        workflow_id="safe_mutation",
        approval_reference="appr-1",
        arguments={"text": "ok"},
    )
    assert out["direct_tool_execution"] is False
    assert out["bypass_gateway"] is False


def test_backup_restore(env):
    _, _, ctx, svc = env
    _install_enable(svc, ctx, "document_hub", "saathi.document_hub")
    # mutate workspace settings
    rec = svc._find(ctx, "saathi.document_hub")
    rec.workspace_config["settings"] = {"theme": "dark"}
    svc._persist(rec)
    b = svc.backup(ctx, "saathi.document_hub", reason="test")
    assert b["backup"]["backup_id"]
    # change settings
    rec = svc._find(ctx, "saathi.document_hub")
    rec.workspace_config["settings"] = {"theme": "light"}
    svc._persist(rec)
    r = svc.restore(ctx, "saathi.document_hub", backup_id=b["backup"]["backup_id"])
    assert r["evidence_preserved"] is True
    assert r["app"]["workspace_config"]["settings"].get("theme") == "dark"


def test_upgrade_rollback(env):
    _, _, ctx, svc = env
    _install_enable(svc, ctx, "platform_demo", "saathi.platform_demo")
    up = svc.upgrade(
        ctx,
        "saathi.platform_demo",
        to_version="1.1.0",
        package_id="platform_demo_v1_1",
    )
    assert up["app"]["version"] == "1.1.0"
    rb = svc.rollback(ctx, "saathi.platform_demo")
    assert rb["to_version"] == "1.0.0"


def test_disable_blocks_launch(env):
    _, _, ctx, svc = env
    _install_enable(svc, ctx, "travel_planner", "saathi.travel_planner")
    svc.disable(ctx, "saathi.travel_planner")
    with pytest.raises(PlatformContextError):
        svc.launch(ctx, "saathi.travel_planner")


def test_quarantine_blocks(env):
    _, _, ctx, svc = env
    _install_enable(svc, ctx, "hcg_pos", "saathi.hcg_pos")
    svc.quarantine(ctx, "saathi.hcg_pos", reason="policy")
    with pytest.raises(PlatformContextError):
        svc.launch(ctx, "saathi.hcg_pos")


def test_launcher_and_favorites(env):
    _, _, ctx, svc = env
    _install_enable(svc, ctx, "crm_lite", "saathi.crm_lite")
    svc.set_favorite(ctx, "saathi.crm_lite", favorite=True)
    svc.launch(ctx, "saathi.crm_lite")
    launch = svc.launcher(ctx)
    assert launch["marketplace"] is False
    assert any(a["app_id"] == "saathi.crm_lite" for a in launch["favorites"])
    assert launch["recent"]


def test_integrations_declare_platform_services(env):
    _, _, ctx, svc = env
    svc.register(ctx, package_id="document_hub")
    integ = svc.integrations(ctx, "saathi.document_hub")
    assert integ["conversation"] == "ConversationService"
    assert integ["knowledge"] == "KnowledgeService"
    assert integ["execution_gateway"] == "required"
    assert integ["bypass_forbidden"] is True


def test_health_and_certify(env):
    _, _, ctx, svc = env
    h = svc.health(ctx)
    assert h["replaces_module_registry"] is False
    assert h["apps_may_bypass_gateway"] is False
    cert = svc.certify(ctx)
    assert "APPLICATION_RUNTIME_CERTIFIED" in cert["verdict"]
    assert cert["marketplace_authorized"] is False


def test_recovery_mid_transition(env):
    _, _, ctx, svc = env
    svc.register(ctx, package_id="erp_lite")
    apps = svc._apps()
    key = [k for k in apps if "erp_lite" in k][0]
    apps[key]["lifecycle_state"] = "UPGRADING"
    svc._save_apps(apps)
    out = svc.recover(ctx)
    assert out["count"] >= 1


def test_viewer_cannot_register(env):
    platform, _, ctx, svc = env
    user = platform.store.create_user(email="viewer-app@local", name="V")
    org = platform.store.list_orgs_for_user(ctx.user_id)[0]
    ws = platform.store.list_workspaces(org.org_id)[0]
    platform.store.add_member(org.org_id, user.user_id, "viewer")
    _, tok = platform.store.create_session(
        user.user_id, "v-app", org_id=org.org_id, workspace_id=ws.workspace_id, role="viewer"
    )
    vctx = platform.require_context(tok)
    with pytest.raises(PlatformContextError) as err:
        svc.register(vctx, package_id="crm_lite")
    assert err.value.code == "PERMISSION_DENIED"


def test_path_traversal(env):
    _, _, ctx, svc = env
    v = svc.validate_package(ctx, package_id="../etc")
    assert v["ok"] is False
    assert "path_traversal" in v["errors"]


def test_multiple_business_apps(env):
    _, _, ctx, svc = env
    for pkg, aid in [
        ("ielts_alert", "saathi.ielts_alert"),
        ("hcg_pos", "saathi.hcg_pos"),
        ("crm_lite", "saathi.crm_lite"),
        ("portfolio_readonly", "saathi.portfolio_readonly"),
    ]:
        _install_enable(svc, ctx, pkg, aid)
    apps = svc.list_apps(ctx)["apps"]
    enabled = [a for a in apps if a["lifecycle_state"] == "ENABLED"]
    assert len(enabled) >= 4
