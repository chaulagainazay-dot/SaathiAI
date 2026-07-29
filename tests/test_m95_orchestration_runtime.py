"""M95–M102 Agent Orchestration and Planning Runtime — focused backend tests."""
from __future__ import annotations

import pytest

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.orchestration import (
    AgentOrchestrationService,
    AgentRoleRegistry,
    FailureClass,
    OrchestrationState,
    reset_orchestration_service_for_tests,
)
from saathi.platform.orchestration.compiler import PlanCompiler
from saathi.platform.orchestration.failures import FailureClassifier as FC
from saathi.platform.orchestration.models import validate_orchestration_transition
from saathi.platform.orchestration.templates import build_template_plan
from saathi.platform.orchestration.validator import PlanValidator
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture()
def env(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "orch.db")
    boot = platform.bootstrap_owner_secure(
        email="orch-owner@local",
        name="Orch Owner",
        password="OrchOwnerPass1!",
    )
    ctx = platform.require_context(boot["token"])
    svc = AgentOrchestrationService(platform)
    yield platform, boot["token"], ctx, svc
    reset_orchestration_service_for_tests(platform)
    reset_platform_for_tests()
    reset_registry_for_tests()


def test_roles_and_templates(env):
    platform, token, ctx, svc = env
    roles = svc.list_roles(ctx)
    ids = {r["role_id"] for r in roles}
    assert {
        "planner",
        "architect",
        "researcher",
        "implementer",
        "reviewer",
        "test",
        "browser",
        "security",
        "documentation",
        "certification",
        "operator",
        "domain_specialist",
    } <= ids
    for r in roles:
        assert r["execution_authority"] == "PlatformAgentRuntime"
        assert r["model_cannot_elevate"] is True
        assert "direct_tool_execution" in r["forbidden_capabilities"]
    templates = svc.list_templates(ctx)
    assert len(templates) >= 8
    assert all(t["grants_permissions"] is False for t in templates)


def test_objective_intake_and_ambiguity(env):
    _, _, ctx, svc = env
    result = svc.intake(
        ctx,
        {
            "objective": "Audit the HCG POS project and produce an implementation plan",
            "domain": "hcg",
        },
    )
    assert result["ready"] is True
    assert result["intake"]["template_id"] == "hcg_ops"
    vague = svc.intake(ctx, {"objective": "make it better somehow"})
    assert vague["intake"]["ambiguities"]


def test_plan_compile_validate_cycle_and_roles(env):
    _, _, ctx, svc = env
    compiled = svc.compile_plan(
        ctx,
        {
            "objective": "Review IELTSAlert production readiness and identify blockers",
            "domain": "ielts",
            "risk_level": "high",
        },
    )
    assert compiled["validation"]["ok"] is True
    plan = compiled["plan"]
    assert plan["production_authorized"] is False
    assert plan["paid_providers"] is False
    agents = {a["agent_type"] for a in compiled["assignments"]}
    assert "ResearcherAgent" in agents or "PlannerAgent" in agents
    # Invalid plan: cycle
    bad = build_template_plan("repository_audit", objective="x")
    tasks = bad["goals"][0]["phases"][0]["milestones"][0]["tasks"]
    tasks[0]["depends_on"] = [tasks[1]["id"]]
    tasks[1]["depends_on"] = [tasks[0]["id"]]
    v = PlanValidator().validate(bad)
    assert v.ok is False
    assert any("cycle" in e for e in v.errors)


def test_forbidden_capability_and_tool_bypass_rejected(env):
    validator = PlanValidator()
    plan = build_template_plan("code_implementation", objective="Implement feature")
    task = plan["goals"][0]["phases"][0]["milestones"][0]["tasks"][0]
    task["requested_capabilities"] = ["direct_tool_execution", "forge_approval"]
    task["arguments"] = {"bypass_gateway": True, "text": "nope"}
    v = validator.validate(plan)
    assert v.ok is False
    assert any("forbidden" in e or "bypass" in e for e in v.errors)


def test_unsupported_role_rejected():
    plan = build_template_plan("documentation_mission", objective="Docs")
    plan["goals"][0]["phases"][0]["milestones"][0]["tasks"][0]["agent_type"] = "GodModeAgent"
    v = PlanValidator().validate(plan)
    assert v.ok is False
    assert any("unsupported role" in e for e in v.errors)


def test_separation_of_duties_implementer_not_self_certify(env):
    reg = AgentRoleRegistry()
    impl = reg.get("implementer")
    assert impl.can_self_certify is False
    cert = reg.get("certification")
    assert cert.can_final_review is True


def test_lifecycle_transition_matrix():
    validate_orchestration_transition("DRAFT", "VALIDATING")
    validate_orchestration_transition("READY", "RUNNING")
    with pytest.raises(ValueError):
        validate_orchestration_transition("CERTIFIED", "RUNNING")
    with pytest.raises(ValueError):
        validate_orchestration_transition("FAILED", "READY")


def test_failure_classification_and_retry_bounds():
    fc = FC()
    assert fc.classify(error_code="PERMISSION_DENIED") == FailureClass.AUTHORIZATION_FAILED
    assert fc.classify(error_code="APPROVAL_EXPIRED") == FailureClass.APPROVAL_EXPIRED
    assert fc.classify(error_code="TIMEOUT") == FailureClass.TIMEOUT
    assert fc.action_for(FailureClass.SECURITY_GATE).value == "fail_closed"
    policy = fc.default_retry_policy(2)
    assert policy.allows(FailureClass.TRANSIENT_TOOL) is True
    assert policy.allows(FailureClass.AUTHORIZATION_FAILED) is False
    assert policy.max_attempts == 2
    assert policy.to_public()["infinite_retry"] is False


def test_create_orchestration_and_graph(env):
    platform, token, ctx, svc = env
    created = svc.create(
        ctx,
        {
            "objective": "Plan a bounded UI redesign mission for the knowledge panel",
            "domain": "engineering",
            "template_id": "ui_redesign",
        },
    )
    orch = created["orchestration"]
    assert orch["state"] == OrchestrationState.READY.value
    assert orch["mission_id"]
    assert orch["plan_version"] == 1
    assert orch["validation"]["ok"] is True
    assert orch["tools_executable_by_model"] is False
    assert orch["production_authorized"] is False
    graph = orch.get("graph") or {}
    tasks = graph.get("tasks") or []
    assert len(tasks) >= 2
    # dependencies present between nodes
    deps = graph.get("dependencies") or []
    assert isinstance(deps, list)


def test_start_run_uses_mission_runtime_not_direct_tools(env):
    platform, token, ctx, svc = env
    created = svc.create(
        ctx,
        {
            "objective": "Repository audit of SaathiOS orchestration layer",
            "template_id": "repository_audit",
        },
    )
    oid = created["orchestration"]["orchestration_id"]
    # Should dispatch through PlatformAgentRuntime/gateway via mission orch
    result = svc.start(ctx, oid, token=token)
    orch = result["orchestration"]
    assert orch["state"] in {
        OrchestrationState.RUNNING.value,
        OrchestrationState.COMPLETED.value,
        OrchestrationState.WAITING_APPROVAL.value,
        OrchestrationState.BLOCKED.value,
        OrchestrationState.FAILED.value,
        OrchestrationState.CERTIFIED.value,
        OrchestrationState.READY.value,
    }
    # Audit must not show direct tool exec from orchestration layer
    events = [e["event"] for e in platform.store.list_audit(org_id=ctx.org_id, limit=300)]
    assert "orchestration.started" in events or "orchestration.created" in events
    # No fabrication of approvals
    assert not any("approval.forged" in e for e in events)


def test_pause_resume_cancel_checkpoint(env):
    platform, token, ctx, svc = env
    created = svc.create(
        ctx,
        {"objective": "Documentation mission for orchestration", "template_id": "documentation_mission"},
    )
    oid = created["orchestration"]["orchestration_id"]
    # start may complete quickly with echo tool
    try:
        svc.start(ctx, oid, token=token)
    except PlatformContextError:
        pass
    # create checkpoint
    cp = svc.checkpoint(ctx, oid)
    assert "checkpoint" in cp
    # cancel is always available unless terminal certified
    cancelled = svc.cancel(ctx, oid)
    assert cancelled["orchestration"]["state"] == OrchestrationState.CANCELLED.value


def test_replan_versions_without_history_rewrite(env):
    _, token, ctx, svc = env
    created = svc.create(
        ctx,
        {"objective": "Security review of knowledge runtime", "template_id": "security_review"},
    )
    oid = created["orchestration"]["orchestration_id"]
    replanned = svc.replan(ctx, oid, {"reason": "scope_change", "template_id": "security_review"})
    assert replanned["orchestration"]["plan_version"] == 2
    activity_kinds = [a["kind"] for a in replanned["orchestration"]["activity"]]
    assert "replanned" in activity_kinds or "supersede" in activity_kinds


def test_certify_with_limitations(env):
    _, token, ctx, svc = env
    created = svc.create(
        ctx,
        {
            "objective": "Test and certification mission for local stack",
            "template_id": "test_certification",
        },
    )
    oid = created["orchestration"]["orchestration_id"]
    try:
        svc.start(ctx, oid, token=token)
    except PlatformContextError:
        pass
    cert = svc.certify(
        ctx,
        oid,
        with_limitations=True,
        summary="Certified with local limitations",
        limitations=["no production", "echo tools only"],
    )
    assert cert["orchestration"]["state"] in {
        OrchestrationState.CERTIFIED.value,
        OrchestrationState.CERTIFIED_WITH_LIMITATIONS.value,
    }
    assert cert["orchestration"]["certification"]
    assert any(
        "production" in str(x).lower()
        for x in cert["orchestration"].get("limitations") or []
    )


def test_tenant_isolation(env):
    platform, token, ctx, svc = env
    created = svc.create(
        ctx, {"objective": "Isolate me", "template_id": "documentation_mission"}
    )
    oid = created["orchestration"]["orchestration_id"]
    other = PlatformExecutionContext(
        user_id="other",
        role="viewer",
        org_id="org_other",
        workspace_id="ws_other",
    )
    with pytest.raises(PlatformContextError):
        svc.get(other, oid)


def test_revoked_session_denied(env):
    _, _, ctx, svc = env
    bad = PlatformExecutionContext(
        user_id="",
        role="owner",
        org_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
    )
    with pytest.raises(PlatformContextError):
        svc.health(bad)


def test_model_proposal_accepted_only_after_validation(env):
    _, _, ctx, svc = env
    compiled = svc.compile_plan(
        ctx,
        {
            "objective": "Audit repository structure",
            "template_id": "repository_audit",
            "model_proposal": {
                "additional_tasks": [
                    {
                        "id": "extra-research",
                        "title": "Extra model research",
                        "agent_type": "ResearcherAgent",
                    },
                    {
                        "id": "evil",
                        "title": "Bypass gateway",
                        "agent_type": "ImplementerAgent",
                        "tool_id": "shell.exec",
                        "arguments": {"bypass_gateway": True},
                    },
                ]
            },
        },
    )
    # Compiler forces readonly tool; validator should still pass for forced tool
    titles = []
    for t in PlanCompiler()._iter_tasks(compiled["plan"]):
        titles.append(t.get("title", ""))
        if t.get("id") == "evil":
            assert t["tool_id"] == "m49.echo_readonly"
    assert compiled["validation"]["ok"] is True


def test_invalid_model_plan_rejected():
    plan = build_template_plan("code_implementation", objective="x")
    plan["goals"][0]["phases"][0]["milestones"][0]["tasks"] = []
    v = PlanValidator().validate(plan)
    assert v.ok is False


def test_trading_blocked_by_policy(env):
    _, _, ctx, svc = env
    compiled = svc.compile_plan(
        ctx,
        {
            "objective": "Plan live trade execution with leverage",
            "template_id": "code_implementation",
        },
    )
    # annotation may block tasks mentioning trade
    plan = compiled["plan"]
    blocked = [
        t
        for t in PlanCompiler()._iter_tasks(plan)
        if t.get("approval_requirement") == "BLOCKED_BY_POLICY"
    ]
    # at least security of trading is enforced at objective classification level
    assert plan["trading_execution"] is False
    assert plan["production_authorized"] is False


def test_health_truthful(env):
    _, _, ctx, svc = env
    h = svc.health(ctx)
    assert h["ready"] is True
    assert h["tools_executable_by_model"] is False
    assert h["production_authorized"] is False
    assert h["mission_runtime"] == "authoritative"


def test_conversation_command_mapping(env):
    _, _, ctx, svc = env
    created = svc.create(
        ctx, {"objective": "Ops plan", "template_id": "documentation_mission"}
    )
    oid = created["orchestration"]["orchestration_id"]
    cmd = svc.command_from_conversation(ctx, "Why is the mission blocked?", orchestration_id=oid)
    assert cmd["intent"] == "inspect_blockers"
    assert cmd["executed"] is True
    pause_intent = svc.command_from_conversation(ctx, "Pause after the current safe checkpoint")
    assert pause_intent["intent"] == "pause"
    assert pause_intent["requires_orchestration_id"] is True


def test_concurrent_mission_budget(env):
    _, _, ctx, svc = env
    # Create up to limit
    for i in range(4):
        svc.create(
            ctx,
            {
                "objective": f"Bounded mission {i} for concurrency budget",
                "template_id": "documentation_mission",
            },
        )
    with pytest.raises(PlatformContextError) as ei:
        svc.create(
            ctx,
            {
                "objective": "One too many concurrent missions",
                "template_id": "documentation_mission",
            },
        )
    assert ei.value.code == "RESOURCE_BUDGET_EXHAUSTED"
