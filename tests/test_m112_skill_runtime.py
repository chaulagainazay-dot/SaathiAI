"""M112–M120 Skill Ecosystem Runtime — focused backend tests."""
from __future__ import annotations

import pytest

from saathi.platform.context import PlatformContextError
from saathi.platform.skills import (
    SkillLifecycleState,
    SkillRuntime,
    reset_skill_runtime_for_tests,
)
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture()
def env(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "skills.db")
    boot = platform.bootstrap_owner_secure(
        email="skill-owner@local",
        name="Skill Owner",
        password="SkillOwnerPass1!",
    )
    ctx = platform.require_context(boot["token"])
    svc = SkillRuntime(platform)
    yield platform, boot["token"], ctx, svc
    reset_skill_runtime_for_tests(platform)
    reset_platform_for_tests()
    reset_registry_for_tests()


def _register_enable(svc, ctx, package_id, skill_id):
    reg = svc.register(ctx, package_id=package_id)
    assert reg["skill"]["lifecycle_state"] == SkillLifecycleState.DISABLED.value
    en = svc.enable(ctx, skill_id)
    assert en["skill"]["lifecycle_state"] == SkillLifecycleState.ENABLED.value
    return en["skill"]


def test_discover_and_validate_local_packages(env):
    _, _, ctx, svc = env
    disc = svc.discover(ctx)
    assert disc["count"] >= 6
    assert disc["marketplace"] is False
    assert disc["remote_sources"] == []
    ids = {d["package_id"] for d in disc["discovered"]}
    assert "repo_audit" in ids
    assert "malicious_sample" in ids
    valid = [d for d in disc["discovered"] if d["package_id"] == "repo_audit"][0]
    assert valid["valid"] is True
    bad = [d for d in disc["discovered"] if d["package_id"] == "malicious_sample"][0]
    assert bad["valid"] is False


def test_malicious_package_fail_closed(env):
    _, _, ctx, svc = env
    v = svc.validate_package(ctx, package_id="malicious_sample")
    assert v["ok"] is False
    joined = " ".join(v["errors"])
    assert "forbidden_entrypoint" in joined or "shell" in joined
    with pytest.raises(PlatformContextError) as err:
        svc.register(ctx, package_id="malicious_sample")
    assert err.value.code == "SKILL_INVALID"


def test_register_disabled_enable_execute(env):
    _, _, ctx, svc = env
    reg = svc.register(ctx, package_id="repo_audit")
    assert reg["skill"]["lifecycle_state"] == "DISABLED"
    assert reg["skill"]["effective"] is False
    with pytest.raises(PlatformContextError) as err:
        svc.execute(ctx, "saathi.repo_audit", capability="repository.analyze")
    assert err.value.code == "SKILL_NOT_EXECUTABLE"
    en = svc.enable(ctx, "saathi.repo_audit")
    assert en["skill"]["effective"] is True
    out = svc.execute(
        ctx,
        "saathi.repo_audit",
        capability="repository.analyze",
        arguments={"text": "audit"},
    )
    assert out["direct_tool_execution"] is False
    assert "ExecutionGateway" in out["execution_path"] or "local" in out["execution_path"] or "Fleet" in out["execution_path"]
    assert out["execution"]["state"] == "COMPLETED"
    assert out["execution"]["result_hash"]


def test_manifest_cannot_grant_authority(env):
    _, _, ctx, svc = env
    svc.register(ctx, package_id="repo_audit")
    perms = svc.resolve_permissions(ctx, "saathi.repo_audit")
    assert perms["manifest_cannot_grant"] is True


def test_approval_required_execution(env):
    _, _, ctx, svc = env
    _register_enable(svc, ctx, "mutation_safe", "saathi.mutation_safe")
    with pytest.raises(PlatformContextError) as err:
        svc.execute(ctx, "saathi.mutation_safe", capability="mutation.safe_test")
    assert err.value.code == "APPROVAL_REQUIRED"
    out = svc.execute(
        ctx,
        "saathi.mutation_safe",
        capability="mutation.safe_test",
        approval_reference="appr-test-1",
        arguments={"text": "note"},
    )
    assert out["execution"]["state"] == "COMPLETED"


def test_disable_and_quarantine_block_execution(env):
    _, _, ctx, svc = env
    _register_enable(svc, ctx, "test_runner", "saathi.test_runner")
    svc.disable(ctx, "saathi.test_runner")
    with pytest.raises(PlatformContextError):
        svc.execute(ctx, "saathi.test_runner", capability="test.run")
    # re-enable then quarantine
    svc.enable(ctx, "saathi.test_runner")
    svc.quarantine(ctx, "saathi.test_runner", reason="policy")
    with pytest.raises(PlatformContextError) as err:
        svc.execute(ctx, "saathi.test_runner", capability="test.run")
    assert err.value.code in ("SKILL_NOT_EXECUTABLE", "SKILL_BLOCKED", "SKILL_UNTRUSTED")


def test_upgrade_and_rollback(env):
    _, _, ctx, svc = env
    _register_enable(svc, ctx, "repo_audit", "saathi.repo_audit")
    # execute to create evidence
    svc.execute(ctx, "saathi.repo_audit", capability="repository.read", arguments={"text": "v1"})
    up = svc.upgrade(
        ctx,
        "saathi.repo_audit",
        to_version="1.1.0",
        package_id="repo_audit_v1_1",
    )
    assert up["skill"]["version"] == "1.1.0"
    assert up["rollback_target"] == "1.0.0"
    # Prior version preserved
    versions = svc.get_skill(ctx, "saathi.repo_audit")["versions"]
    assert {v["version"] for v in versions} >= {"1.0.0", "1.1.0"}
    rb = svc.rollback(ctx, "saathi.repo_audit", reason="test")
    assert rb["to_version"] == "1.0.0"
    assert rb["evidence_preserved"] is True
    # Evidence still listed
    ex = svc.list_executions(ctx, "saathi.repo_audit")
    assert ex["count"] >= 1


def test_dependency_resolution_deterministic(env):
    _, _, ctx, svc = env
    svc.register(ctx, package_id="repo_audit")
    svc.register(ctx, package_id="documentation")
    d1 = svc.resolve_dependencies(ctx, "saathi.documentation")
    d2 = svc.resolve_dependencies(ctx, "saathi.documentation")
    assert d1["deterministic"] is True
    assert d1["resolved"] == d2["resolved"]


def test_idempotent_execution(env):
    _, _, ctx, svc = env
    _register_enable(svc, ctx, "knowledge_search", "saathi.knowledge_search")
    a = svc.execute(
        ctx,
        "saathi.knowledge_search",
        capability="knowledge.search",
        arguments={"query": "x"},
        idempotency_key="idem-1",
    )
    b = svc.execute(
        ctx,
        "saathi.knowledge_search",
        capability="knowledge.search",
        arguments={"query": "x"},
        idempotency_key="idem-1",
    )
    assert b.get("deduplicated") is True
    assert a["execution"]["execution_id"] == b["execution"]["execution_id"]


def test_tenant_isolation(env):
    platform, _, ctx, svc = env
    svc.register(ctx, package_id="hcg_ops_review")
    other_user = platform.store.create_user(email="other-skill@local", name="Other")
    other_org = platform.store.create_org("Other Skill Org", other_user.user_id)
    other_ws = platform.store.create_workspace(
        other_org.org_id, "Other WS", other_user.user_id
    )
    platform.store.add_member(other_org.org_id, other_user.user_id, "owner")
    _, tok = platform.store.create_session(
        other_user.user_id,
        "other-skill-tok",
        org_id=other_org.org_id,
        workspace_id=other_ws.workspace_id,
        role="owner",
    )
    octx = platform.require_context(tok)
    with pytest.raises(PlatformContextError):
        svc.get_skill(octx, "saathi.hcg_ops_review")


def test_viewer_cannot_register(env):
    platform, _, ctx, svc = env
    user = platform.store.create_user(email="viewer-skill@local", name="V")
    org = platform.store.list_orgs_for_user(ctx.user_id)[0]
    ws = platform.store.list_workspaces(org.org_id)[0]
    platform.store.add_member(org.org_id, user.user_id, "viewer")
    _, tok = platform.store.create_session(
        user.user_id, "vtok", org_id=org.org_id, workspace_id=ws.workspace_id, role="viewer"
    )
    vctx = platform.require_context(tok)
    with pytest.raises(PlatformContextError) as err:
        svc.register(vctx, package_id="repo_audit")
    assert err.value.code == "PERMISSION_DENIED"


def test_path_traversal_rejected(env):
    _, _, ctx, svc = env
    v = svc.validate_package(ctx, package_id="../etc/passwd")
    assert v["ok"] is False
    assert "path_traversal" in v["errors"]


def test_conversation_no_direct_execution(env):
    _, _, ctx, svc = env
    _register_enable(svc, ctx, "ielts_readiness", "saathi.ielts_readiness")
    r = svc.command_from_conversation(ctx, "Which skills are installed?")
    assert r["direct_execution"] is False
    assert r["remote_install"] is False
    assert r["executed"] is True


def test_recovery_after_mid_transition(env):
    _, _, ctx, svc = env
    reg = svc.register(ctx, package_id="repo_audit")
    # Force mid-transition state
    skills = svc._skills()
    key = [k for k in skills if "repo_audit" in k][0]
    skills[key]["lifecycle_state"] = "ENABLING"
    svc._save_skills(skills)
    out = svc.recover(ctx)
    assert out["count"] >= 1
    rec = svc.get_skill(ctx, "saathi.repo_audit")["skill"]
    assert rec["lifecycle_state"] == "DISABLED"


def test_certify_and_health(env):
    _, _, ctx, svc = env
    h = svc.health(ctx)
    assert h["replaces_tool_registry"] is False
    assert h["marketplace_authorized"] is False
    cert = svc.certify(ctx)
    assert "SKILL_ECOSYSTEM_CERTIFIED" in cert["verdict"]
    assert cert["direct_tool_execution"] is False


def test_duplicate_registration_rejected(env):
    _, _, ctx, svc = env
    svc.register(ctx, package_id="repo_audit")
    with pytest.raises(PlatformContextError) as err:
        svc.register(ctx, package_id="repo_audit")
    assert err.value.code == "SKILL_ALREADY_REGISTERED"


def test_downgrade_blocked_use_rollback(env):
    _, _, ctx, svc = env
    _register_enable(svc, ctx, "repo_audit", "saathi.repo_audit")
    svc.upgrade(
        ctx, "saathi.repo_audit", to_version="1.1.0", package_id="repo_audit_v1_1"
    )
    with pytest.raises(PlatformContextError) as err:
        svc.upgrade(
            ctx, "saathi.repo_audit", to_version="1.0.0", package_id="repo_audit"
        )
    assert err.value.code == "DOWNGRADE_BLOCKED"
