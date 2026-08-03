"""M345 — Development-agent role registry and contract validation.

Covers the declared registry, every per-role invariant, every cross-role
invariant, and the negative paths the loader must refuse.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.agentdev import roles as roles_mod
from saathi.agentdev.roles import (
    CAPABILITIES,
    GLOBAL_PROHIBITIONS,
    IMPLEMENTATION_ROLES,
    RoleValidationError,
    can_review,
    get_role,
    list_roles,
    load_registry,
    registry_summary,
    require_role,
    roles_with_capability,
)
from saathi.safety import Approval, SafetyLevel

EXPECTED_ROLE_IDS = {
    "ceo",
    "program-manager",
    "product-strategy",
    "research",
    "architecture",
    "security-governance",
    "ux-product-design",
    "backend-engineering",
    "frontend-engineering",
    "ai-model-systems",
    "testing-verification",
    "code-review",
    "documentation",
    "cost-resource",
}


# --------------------------------------------------------------------------
# The shipped registry
# --------------------------------------------------------------------------


def test_registry_declares_the_fourteen_required_roles():
    assert {r.agent_id for r in list_roles()} == EXPECTED_ROLE_IDS


def test_every_role_declares_a_complete_contract():
    for role in list_roles():
        assert role.role_name.strip(), role.agent_id
        assert role.mission.strip(), role.agent_id
        assert role.responsibilities, role.agent_id
        assert role.allowed_capabilities, role.agent_id
        assert role.prohibited_actions, role.agent_id
        assert role.readable_paths, role.agent_id
        assert role.required_inputs, role.agent_id
        assert role.required_outputs, role.agent_id
        assert role.escalation_to.strip(), role.agent_id
        assert role.completion_criteria, role.agent_id
        assert isinstance(role.max_authority, SafetyLevel), role.agent_id
        assert isinstance(role.approval, Approval), role.agent_id


def test_every_role_prohibits_every_global_prohibition():
    for role in list_roles():
        missing = [p for p in GLOBAL_PROHIBITIONS if not role.prohibits(p)]
        assert not missing, f"{role.agent_id} omits {missing}"


def test_no_role_may_review_itself():
    for role in list_roles():
        assert role.agent_id not in role.independent_review_by


def test_capabilities_are_drawn_from_the_closed_vocabulary():
    for role in list_roles():
        assert set(role.allowed_capabilities) <= CAPABILITIES, role.agent_id


def test_only_implementation_roles_may_write_code():
    writers = {r.agent_id for r in list_roles() if r.may_write_code}
    assert writers == set(IMPLEMENTATION_ROLES)


def test_only_code_writing_roles_hold_a_worktree_scope():
    for role in list_roles():
        has_worktree_write = any(s.startswith("worktree:") for s in role.writable_paths)
        assert has_worktree_write == role.may_write_code, role.agent_id


def test_no_writable_scope_escapes_the_sandbox():
    for role in list_roles():
        for scope in role.writable_paths:
            assert scope.split(":", 1)[0] in ("mission", "worktree"), (
                f"{role.agent_id} writes to {scope}"
            )
            assert not scope.startswith("/")
            assert not scope.startswith("~")


def test_ceo_may_synthesize_but_never_touch_implementation():
    ceo = require_role("ceo")
    assert ceo.has_capability("synthesize_decision")
    assert not ceo.may_write_code
    assert not any(s.startswith("worktree:") for s in ceo.writable_paths)
    assert ceo.prohibits("write_code")
    assert ceo.prohibits("modify_implementation")
    assert ceo.escalation_to == roles_mod.OWNER


def test_exactly_one_role_holds_the_security_veto():
    veto = roles_with_capability("security_veto")
    assert [r.agent_id for r in veto] == ["security-governance"]


def test_escalation_targets_resolve():
    ids = {r.agent_id for r in list_roles()}
    for role in list_roles():
        assert role.escalation_to == roles_mod.OWNER or role.escalation_to in ids


def test_declared_reviewers_can_actually_approve_gates():
    for role in list_roles():
        for reviewer in role.independent_review_by:
            ok, reason = can_review(reviewer, role.agent_id)
            assert ok, f"{reviewer} cannot review {role.agent_id}: {reason}"


def test_authority_never_exceeds_the_l3_ceiling():
    for role in list_roles():
        assert role.max_authority <= SafetyLevel.L3, role.agent_id


def test_registry_reuses_saathi_safety_and_defines_no_parallel_enum():
    """Duplicate-source-of-truth rule 1 (ADR-012)."""
    import enum

    import saathi.agentdev.roles as module

    safety_members = {m.name for m in SafetyLevel}
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and issubclass(obj, enum.Enum) and obj is not SafetyLevel:
            assert not safety_members <= {m.name for m in obj}, (
                f"{name} duplicates SafetyLevel"
            )


def test_agentdev_imports_nothing_beyond_safety_and_config():
    """ADR-012: the package's only non-stdlib dependencies are declared here.

    Growing this list is a governance decision, not an implementation detail.
    """
    import ast

    package = Path(roles_mod.__file__).parent
    external: set[str] = set()
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                external.add(node.module)
            elif isinstance(node, ast.Import):
                external.update(alias.name for alias in node.names)

    saathi_imports = {m for m in external if m.startswith("saathi")}
    outside_package = {
        m for m in saathi_imports if not m.startswith("saathi.agentdev")
    }
    assert outside_package == {"saathi.safety", "saathi.config"}, outside_package


def test_no_saathi_module_outside_agentdev_imports_agentdev():
    """ADR-012 rule 3: the dependency direction is one-way."""
    import ast

    package_root = Path(roles_mod.__file__).parent
    saathi_root = package_root.parent
    offenders: list[str] = []
    for path in saathi_root.rglob("*.py"):
        if package_root in path.parents or path.parent == package_root:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
            continue
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
            elif isinstance(node, ast.Import):
                module = ",".join(a.name for a in node.names)
            if "agentdev" in module:
                offenders.append(f"{path.relative_to(saathi_root)}:{module}")
    assert not offenders, offenders


def test_agentdev_does_not_import_trading_guardian():
    """The Trading Guardian is untouched by this milestone."""
    import ast

    package = Path(roles_mod.__file__).parent
    offenders: list[str] = []
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
            elif isinstance(node, ast.Import):
                module = ",".join(a.name for a in node.names)
            if any(
                marker in module
                for marker in ("trading_guardian", "platform.tg", "paper_trading")
            ):
                offenders.append(f"{path.name}:{module}")
    assert not offenders, offenders


def test_summary_reports_the_registry_shape():
    s = registry_summary()
    assert s["count"] == 14
    assert s["security_veto"] == ["security-governance"]
    assert set(s["implementation_roles"]) == set(IMPLEMENTATION_ROLES)
    assert len(s["roles"]) == 14


def test_get_role_returns_none_for_unknown_and_require_raises():
    assert get_role("no-such-agent") is None
    with pytest.raises(RoleValidationError) as exc:
        require_role("no-such-agent")
    assert exc.value.code == "unknown_agent_id"


# --------------------------------------------------------------------------
# Independent-review rules
# --------------------------------------------------------------------------


def test_self_review_is_refused_for_every_role():
    for role in list_roles():
        ok, reason = can_review(role.agent_id, role.agent_id)
        assert not ok
        assert reason == "self_review_forbidden"


def test_undeclared_reviewer_is_refused():
    ok, reason = can_review("research", "backend-engineering")
    assert not ok
    assert reason.startswith("reviewer_not_declared_for")


def test_unknown_reviewer_and_author_are_refused():
    ok, reason = can_review("ghost", "ceo")
    assert not ok and reason == "unknown_reviewer:ghost"
    ok, reason = can_review("ceo", "ghost")
    assert not ok and reason == "unknown_author:ghost"


# --------------------------------------------------------------------------
# Negative paths — the loader must refuse malformed registries
# --------------------------------------------------------------------------


def _base_role(**overrides) -> dict:
    role = {
        "agent_id": "sample-role",
        "role_name": "Sample",
        "mission": "Sample mission.",
        "responsibilities": ["do a thing"],
        "allowed_capabilities": ["read_repository", "write_artifact"],
        "prohibited_actions": list(GLOBAL_PROHIBITIONS),
        "readable_paths": ["repo:**"],
        "writable_paths": ["mission:artifacts/**"],
        "required_inputs": ["an input"],
        "required_outputs": ["an output"],
        "escalation_to": "owner",
        "independent_review_by": ["reviewer-role"],
        "max_authority": "L2",
        "approval": "human",
        "completion_criteria": ["done when evidenced"],
        "default_worktree_mode": "readonly",
    }
    role.update(overrides)
    return role


def _reviewer_role(**overrides) -> dict:
    role = _base_role(
        agent_id="reviewer-role",
        allowed_capabilities=["read_repository", "write_artifact", "approve_gate"],
        independent_review_by=["ceo"],
    )
    role.update(overrides)
    return role


def _ceo_role(**overrides) -> dict:
    role = _base_role(
        agent_id="ceo",
        allowed_capabilities=[
            "read_repository",
            "write_artifact",
            "approve_gate",
            "synthesize_decision",
        ],
        independent_review_by=["reviewer-role"],
    )
    role.update(overrides)
    return role


def _security_role(**overrides) -> dict:
    role = _base_role(
        agent_id="sec-role",
        allowed_capabilities=[
            "read_repository",
            "write_artifact",
            "approve_gate",
            "security_veto",
        ],
        independent_review_by=["reviewer-role"],
    )
    role.update(overrides)
    return role


def _write(tmp_path: Path, roles: list[dict]) -> Path:
    path = tmp_path / "roles.json"
    path.write_text(json.dumps({"roles": roles}), encoding="utf-8")
    return path


def _valid_set(*extra: dict) -> list[dict]:
    return [_ceo_role(), _reviewer_role(), _security_role(), *extra]


def test_a_minimal_valid_registry_loads(tmp_path):
    registry = load_registry(_write(tmp_path, _valid_set()))
    assert set(registry) == {"ceo", "reviewer-role", "sec-role"}


@pytest.mark.parametrize(
    "overrides,expected_code",
    [
        ({"agent_id": "Bad_Id"}, "invalid_agent_id"),
        ({"agent_id": ""}, "invalid_agent_id"),
        ({"max_authority": "L9"}, "invalid_max_authority"),
        ({"max_authority": "L5"}, "authority_above_ceiling"),
        ({"approval": "whatever"}, "invalid_approval"),
        ({"default_worktree_mode": "sudo"}, "invalid_worktree_mode"),
        ({"allowed_capabilities": ["read_repository", "launch_missiles"]}, "unknown_capability"),
        ({"allowed_capabilities": []}, "empty_capabilities"),
        ({"responsibilities": []}, "empty_responsibilities"),
        ({"required_outputs": []}, "empty_required_outputs"),
        ({"completion_criteria": []}, "empty_completion_criteria"),
        ({"prohibited_actions": ["push"]}, "missing_global_prohibition"),
        ({"independent_review_by": ["sample-role"]}, "self_review_declared"),
        ({"writable_paths": ["repo:saathi/**"]}, "writable_scope_outside_sandbox"),
        ({"readable_paths": ["/etc/passwd"]}, "invalid_path_scope"),
        ({"readable_paths": ["~/.claude/**"]}, "invalid_path_scope"),
        ({"writable_paths": ["worktree:**"]}, "worktree_scope_without_write_capability"),
        ({"default_worktree_mode": "writable"}, "writable_mode_without_write_code"),
    ],
)
def test_loader_refuses_invalid_contracts(tmp_path, overrides, expected_code):
    roles = _valid_set(_base_role(**overrides))
    with pytest.raises(RoleValidationError) as exc:
        load_registry(_write(tmp_path, roles))
    assert exc.value.code == expected_code


def test_duplicate_agent_ids_are_refused(tmp_path):
    roles = _valid_set(_base_role(), _base_role())
    with pytest.raises(RoleValidationError) as exc:
        load_registry(_write(tmp_path, roles))
    assert exc.value.code == "duplicate_agent_id"


def test_write_code_outside_implementation_roles_is_refused(tmp_path):
    rogue = _base_role(
        agent_id="rogue-writer",
        allowed_capabilities=["read_repository", "write_artifact", "write_code"],
        writable_paths=["worktree:**", "mission:artifacts/**"],
        default_worktree_mode="writable",
    )
    with pytest.raises(RoleValidationError) as exc:
        load_registry(_write(tmp_path, _valid_set(rogue)))
    assert exc.value.code == "write_code_not_permitted_for_role"


def test_implementation_role_without_worktree_scope_is_refused(tmp_path):
    broken = _base_role(
        agent_id="backend-engineering",
        allowed_capabilities=["read_repository", "write_artifact", "write_code"],
        writable_paths=["mission:artifacts/**"],
        default_worktree_mode="writable",
    )
    with pytest.raises(RoleValidationError) as exc:
        load_registry(_write(tmp_path, _valid_set(broken)))
    assert exc.value.code == "write_code_without_worktree_scope"


def test_implementation_role_needs_writable_mode(tmp_path):
    broken = _base_role(
        agent_id="backend-engineering",
        allowed_capabilities=["read_repository", "write_artifact", "write_code"],
        writable_paths=["worktree:**"],
        default_worktree_mode="readonly",
    )
    with pytest.raises(RoleValidationError) as exc:
        load_registry(_write(tmp_path, _valid_set(broken)))
    assert exc.value.code == "write_code_requires_writable_worktree"


def test_unresolved_escalation_target_is_refused(tmp_path):
    roles = _valid_set(_base_role(escalation_to="nobody"))
    with pytest.raises(RoleValidationError) as exc:
        load_registry(_write(tmp_path, roles))
    assert exc.value.code == "unresolved_escalation_target"


def test_unresolved_reviewer_is_refused(tmp_path):
    roles = _valid_set(_base_role(independent_review_by=["ghost-role"]))
    with pytest.raises(RoleValidationError) as exc:
        load_registry(_write(tmp_path, roles))
    assert exc.value.code == "unresolved_reviewer"


def test_artifact_author_without_a_reviewer_is_refused(tmp_path):
    roles = _valid_set(_base_role(independent_review_by=[]))
    with pytest.raises(RoleValidationError) as exc:
        load_registry(_write(tmp_path, roles))
    assert exc.value.code == "no_independent_reviewer"


def test_registry_without_a_ceo_is_refused(tmp_path):
    roles = [_reviewer_role(independent_review_by=["sec-role"]), _security_role()]
    with pytest.raises(RoleValidationError) as exc:
        load_registry(_write(tmp_path, roles))
    assert exc.value.code == "missing_ceo_role"


def test_registry_without_a_security_veto_is_refused(tmp_path):
    roles = [_ceo_role(), _reviewer_role()]
    with pytest.raises(RoleValidationError) as exc:
        load_registry(_write(tmp_path, roles))
    assert exc.value.code == "no_security_veto_role"


def test_ceo_that_can_write_code_is_refused(tmp_path):
    ceo = _ceo_role(
        allowed_capabilities=[
            "read_repository",
            "write_artifact",
            "approve_gate",
            "synthesize_decision",
            "write_code",
        ],
        writable_paths=["worktree:**", "mission:artifacts/**"],
        default_worktree_mode="writable",
    )
    with pytest.raises(RoleValidationError) as exc:
        load_registry(_write(tmp_path, [ceo, _reviewer_role(), _security_role()]))
    # The per-role check fires first: "ceo" is not an implementation role.
    assert exc.value.code == "write_code_not_permitted_for_role"


def test_missing_registry_file_is_refused(tmp_path):
    with pytest.raises(RoleValidationError) as exc:
        load_registry(tmp_path / "absent.json")
    assert exc.value.code == "registry_not_found"


def test_malformed_registry_json_is_refused(tmp_path):
    path = tmp_path / "roles.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(RoleValidationError) as exc:
        load_registry(path)
    assert exc.value.code == "registry_not_json"


def test_registry_missing_roles_key_is_refused(tmp_path):
    path = tmp_path / "roles.json"
    path.write_text(json.dumps({"agents": []}), encoding="utf-8")
    with pytest.raises(RoleValidationError) as exc:
        load_registry(path)
    assert exc.value.code == "registry_missing_roles_key"


def test_empty_registry_is_refused(tmp_path):
    with pytest.raises(RoleValidationError) as exc:
        load_registry(_write(tmp_path, []))
    assert exc.value.code == "empty_registry"


def test_missing_required_field_is_refused(tmp_path):
    role = _base_role()
    del role["required_inputs"]
    with pytest.raises(RoleValidationError) as exc:
        load_registry(_write(tmp_path, _valid_set(role)))
    assert exc.value.code == "missing_field"
    assert exc.value.detail == "required_inputs"
