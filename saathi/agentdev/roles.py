"""M345 — Development-agent role contracts.

Roles are **declared** in ``data/roles.json`` and **validated** here. The
validator is hand-written rather than ``jsonschema``-based on purpose: adding a
dependency for one file would violate the milestone's own constraint, and a
hand-written validator can produce SaathiOS-shaped, actionable error codes.

Authority vocabulary is not invented here. ``max_authority`` is a
:class:`saathi.safety.SafetyLevel` and ``approval`` is a
:class:`saathi.safety.Approval`; there is no parallel enum in this package.

Path scopes use an explicit prefix grammar so a contract can be validated
without touching the filesystem:

===============  =============================================================
``repo:``        repository-relative path, read-only unless the role is an
                 implementation role writing inside its own worktree
``mission:``     the mission's own artifact directory
``worktree:``    the worktree assigned to this agent for this mission
``reference:``   a named external read-only reference (never a filesystem path)
===============  =============================================================

Invariants enforced at load time (all schema-validated, tier 2):

* agent ids are unique, kebab-case, and stable;
* every role prohibits the twelve globally forbidden actions;
* no role may review its own output;
* ``worktree:`` scopes only exist for roles that may write code;
* only implementation roles may write code;
* escalation targets resolve to another declared role or to ``owner``;
* every capability is drawn from the closed capability vocabulary;
* the CEO role may synthesize decisions but declares no code-writing capability
  and no ``worktree:`` scope.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from saathi.safety import Approval, SafetyLevel

DATA_PATH = Path(__file__).resolve().parent / "data" / "roles.json"

_ID_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
_SCOPE_RE = re.compile(r"^(repo|mission|worktree|reference):[A-Za-z0-9_.*/\-]+$")

OWNER = "owner"

#: Closed capability vocabulary. A contract naming anything else fails to load.
CAPABILITIES = frozenset({
    "read_repository",
    "read_external_reference",
    "write_artifact",
    "create_proposal",
    "create_challenge",
    "respond_to_challenge",
    "chair_meeting",
    "participate_meeting",
    "decompose_mission",
    "assign_task",
    "request_worktree",
    "write_code",
    "run_tests",
    "review_code",
    "review_security",
    "security_veto",
    "approve_gate",
    "synthesize_decision",
    "estimate_cost",
    "author_documentation",
})

#: Every role must prohibit all of these. Absence is a load-time failure, so a
#: future contributor cannot quietly widen a role by omission.
GLOBAL_PROHIBITIONS = (
    "push",
    "merge",
    "deploy",
    "force_push",
    "delete_branch",
    "git_reset_hard",
    "git_clean",
    "force_worktree_removal",
    "modify_global_config",
    "access_credentials",
    "execute_trade",
    "approve_own_work",
)

#: Roles permitted to declare ``write_code`` and a ``worktree:`` scope.
IMPLEMENTATION_ROLES = frozenset({
    "backend-engineering",
    "frontend-engineering",
    "ai-model-systems",
})


class RoleValidationError(ValueError):
    """Raised with a stable ``code`` and the offending ``agent_id``."""

    def __init__(self, code: str, agent_id: str = "", detail: str = ""):
        self.code = code
        self.agent_id = agent_id
        self.detail = detail
        message = f"{code}"
        if agent_id:
            message += f":{agent_id}"
        if detail:
            message += f" ({detail})"
        super().__init__(message)


@dataclass(frozen=True)
class RoleContract:
    """One development-agent role. Immutable once loaded."""

    agent_id: str
    role_name: str
    mission: str
    responsibilities: tuple[str, ...]
    allowed_capabilities: tuple[str, ...]
    prohibited_actions: tuple[str, ...]
    readable_paths: tuple[str, ...]
    writable_paths: tuple[str, ...]
    required_inputs: tuple[str, ...]
    required_outputs: tuple[str, ...]
    escalation_to: str
    independent_review_by: tuple[str, ...]
    max_authority: SafetyLevel
    approval: Approval
    completion_criteria: tuple[str, ...]
    default_worktree_mode: str  # "none" | "readonly" | "writable"

    # ---- derived predicates -------------------------------------------------

    @property
    def may_write_code(self) -> bool:
        return "write_code" in self.allowed_capabilities

    @property
    def may_approve_gates(self) -> bool:
        return "approve_gate" in self.allowed_capabilities

    def has_capability(self, capability: str) -> bool:
        return capability in self.allowed_capabilities

    def prohibits(self, action: str) -> bool:
        return action in self.prohibited_actions

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["max_authority"] = self.max_authority.name
        d["approval"] = self.approval.value
        d["may_write_code"] = self.may_write_code
        d["may_approve_gates"] = self.may_approve_gates
        return d


def _as_tuple(raw: Any, *, code: str, agent_id: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or any(not isinstance(x, str) for x in raw):
        raise RoleValidationError(code, agent_id, "expected a list of strings")
    return tuple(raw)


def _require(raw: dict, key: str, agent_id: str) -> Any:
    if key not in raw:
        raise RoleValidationError("missing_field", agent_id, key)
    return raw[key]


def _parse_role(raw: dict[str, Any]) -> RoleContract:
    agent_id = str(raw.get("agent_id") or "")
    if not _ID_RE.match(agent_id):
        raise RoleValidationError("invalid_agent_id", agent_id or "<empty>")

    for key in ("role_name", "mission", "escalation_to", "default_worktree_mode"):
        value = _require(raw, key, agent_id)
        if not isinstance(value, str) or not value.strip():
            raise RoleValidationError("invalid_field", agent_id, key)

    try:
        authority = SafetyLevel[str(_require(raw, "max_authority", agent_id))]
    except KeyError as exc:
        raise RoleValidationError(
            "invalid_max_authority", agent_id, str(raw.get("max_authority"))
        ) from exc
    try:
        approval = Approval(str(raw.get("approval") or Approval.HUMAN.value))
    except ValueError as exc:
        raise RoleValidationError(
            "invalid_approval", agent_id, str(raw.get("approval"))
        ) from exc

    mode = str(raw["default_worktree_mode"])
    if mode not in ("none", "readonly", "writable"):
        raise RoleValidationError("invalid_worktree_mode", agent_id, mode)

    contract = RoleContract(
        agent_id=agent_id,
        role_name=str(raw["role_name"]),
        mission=str(raw["mission"]),
        responsibilities=_as_tuple(
            _require(raw, "responsibilities", agent_id),
            code="invalid_responsibilities", agent_id=agent_id,
        ),
        allowed_capabilities=_as_tuple(
            _require(raw, "allowed_capabilities", agent_id),
            code="invalid_capabilities", agent_id=agent_id,
        ),
        prohibited_actions=_as_tuple(
            _require(raw, "prohibited_actions", agent_id),
            code="invalid_prohibitions", agent_id=agent_id,
        ),
        readable_paths=_as_tuple(
            _require(raw, "readable_paths", agent_id),
            code="invalid_readable_paths", agent_id=agent_id,
        ),
        writable_paths=_as_tuple(
            _require(raw, "writable_paths", agent_id),
            code="invalid_writable_paths", agent_id=agent_id,
        ),
        required_inputs=_as_tuple(
            _require(raw, "required_inputs", agent_id),
            code="invalid_required_inputs", agent_id=agent_id,
        ),
        required_outputs=_as_tuple(
            _require(raw, "required_outputs", agent_id),
            code="invalid_required_outputs", agent_id=agent_id,
        ),
        escalation_to=str(raw["escalation_to"]),
        independent_review_by=_as_tuple(
            _require(raw, "independent_review_by", agent_id),
            code="invalid_reviewers", agent_id=agent_id,
        ),
        max_authority=authority,
        approval=approval,
        completion_criteria=_as_tuple(
            _require(raw, "completion_criteria", agent_id),
            code="invalid_completion_criteria", agent_id=agent_id,
        ),
        default_worktree_mode=mode,
    )
    _validate_contract(contract)
    return contract


def _validate_contract(role: RoleContract) -> None:
    """Per-role invariants. Cross-role checks happen in :func:`_validate_registry`."""
    if not role.responsibilities:
        raise RoleValidationError("empty_responsibilities", role.agent_id)
    if not role.allowed_capabilities:
        raise RoleValidationError("empty_capabilities", role.agent_id)
    if not role.required_outputs:
        raise RoleValidationError("empty_required_outputs", role.agent_id)
    if not role.completion_criteria:
        raise RoleValidationError("empty_completion_criteria", role.agent_id)

    unknown = sorted(set(role.allowed_capabilities) - CAPABILITIES)
    if unknown:
        raise RoleValidationError(
            "unknown_capability", role.agent_id, ", ".join(unknown)
        )

    missing = [p for p in GLOBAL_PROHIBITIONS if p not in role.prohibited_actions]
    if missing:
        raise RoleValidationError(
            "missing_global_prohibition", role.agent_id, ", ".join(missing)
        )

    if role.agent_id in role.independent_review_by:
        raise RoleValidationError("self_review_declared", role.agent_id)

    for scope in role.readable_paths + role.writable_paths:
        if not _SCOPE_RE.match(scope):
            raise RoleValidationError("invalid_path_scope", role.agent_id, scope)
        if scope.startswith("/") or scope.startswith("~"):
            raise RoleValidationError("absolute_path_scope", role.agent_id, scope)

    for scope in role.writable_paths:
        prefix = scope.split(":", 1)[0]
        if prefix not in ("mission", "worktree"):
            raise RoleValidationError(
                "writable_scope_outside_sandbox", role.agent_id, scope
            )
        if prefix == "worktree" and not role.may_write_code:
            raise RoleValidationError(
                "worktree_scope_without_write_capability", role.agent_id, scope
            )

    if role.may_write_code:
        if role.agent_id not in IMPLEMENTATION_ROLES:
            raise RoleValidationError("write_code_not_permitted_for_role", role.agent_id)
        if role.default_worktree_mode != "writable":
            raise RoleValidationError(
                "write_code_requires_writable_worktree", role.agent_id
            )
        if not any(s.startswith("worktree:") for s in role.writable_paths):
            raise RoleValidationError("write_code_without_worktree_scope", role.agent_id)
    else:
        # A ``worktree:`` writable scope on a non-code role is already refused by
        # the writable-scope loop above (``worktree_scope_without_write_capability``).
        if role.default_worktree_mode == "writable":
            raise RoleValidationError(
                "writable_mode_without_write_code", role.agent_id
            )

    if role.max_authority > SafetyLevel.L3:
        raise RoleValidationError(
            "authority_above_ceiling", role.agent_id, role.max_authority.name
        )
    if role.may_write_code and role.max_authority < SafetyLevel.L2:
        raise RoleValidationError("write_code_authority_too_low", role.agent_id)


def _validate_registry(roles: dict[str, RoleContract]) -> None:
    """Cross-role invariants."""
    if not roles:
        raise RoleValidationError("empty_registry")

    for role in roles.values():
        if role.escalation_to != OWNER and role.escalation_to not in roles:
            raise RoleValidationError(
                "unresolved_escalation_target", role.agent_id, role.escalation_to
            )
        for reviewer in role.independent_review_by:
            if reviewer not in roles:
                raise RoleValidationError(
                    "unresolved_reviewer", role.agent_id, reviewer
                )

    ceo = roles.get("ceo")
    if ceo is None:
        raise RoleValidationError("missing_ceo_role")
    if ceo.may_write_code:
        raise RoleValidationError("ceo_may_not_write_code", "ceo")
    if any(s.startswith("worktree:") for s in ceo.writable_paths):
        raise RoleValidationError("ceo_worktree_scope", "ceo")
    if "synthesize_decision" not in ceo.allowed_capabilities:
        raise RoleValidationError("ceo_cannot_synthesize", "ceo")

    # At least one role must be able to veto on security grounds, or the
    # security gate is decorative.
    if not any("security_veto" in r.allowed_capabilities for r in roles.values()):
        raise RoleValidationError("no_security_veto_role")

    # Every role that produces reviewable output must name a reviewer that is
    # not itself. Roles that only consume (none today) are exempt.
    for role in roles.values():
        if "write_artifact" in role.allowed_capabilities and not role.independent_review_by:
            raise RoleValidationError("no_independent_reviewer", role.agent_id)


def load_registry(path: Path | str | None = None) -> dict[str, RoleContract]:
    """Parse and validate the declarative role registry.

    Raises :class:`RoleValidationError` on the first violation. Never returns a
    partially valid registry.
    """
    source = Path(path) if path else DATA_PATH
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RoleValidationError("registry_not_found", detail=str(source)) from exc
    except json.JSONDecodeError as exc:
        raise RoleValidationError("registry_not_json", detail=str(exc)) from exc

    if not isinstance(raw, dict) or "roles" not in raw:
        raise RoleValidationError("registry_missing_roles_key", detail=str(source))
    entries = raw["roles"]
    if not isinstance(entries, list):
        raise RoleValidationError("registry_roles_not_list", detail=str(source))

    roles: dict[str, RoleContract] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise RoleValidationError("role_not_object")
        contract = _parse_role(entry)
        if contract.agent_id in roles:
            raise RoleValidationError("duplicate_agent_id", contract.agent_id)
        roles[contract.agent_id] = contract

    _validate_registry(roles)
    return roles


@lru_cache(maxsize=1)
def _default_registry() -> dict[str, RoleContract]:
    return load_registry()


def list_roles() -> list[RoleContract]:
    return sorted(_default_registry().values(), key=lambda r: r.agent_id)


def get_role(agent_id: str) -> RoleContract | None:
    return _default_registry().get(agent_id)


def require_role(agent_id: str) -> RoleContract:
    role = get_role(agent_id)
    if role is None:
        raise RoleValidationError("unknown_agent_id", agent_id)
    return role


def roles_with_capability(capability: str) -> list[RoleContract]:
    return [r for r in list_roles() if r.has_capability(capability)]


def can_review(reviewer_id: str, author_id: str) -> tuple[bool, str]:
    """Whether ``reviewer_id`` may independently review ``author_id``'s output.

    Orchestration-checked, not merely advisory: :mod:`saathi.agentdev.gates`
    calls this before recording any approval.
    """
    if reviewer_id == author_id:
        return False, "self_review_forbidden"
    author = get_role(author_id)
    if author is None:
        return False, f"unknown_author:{author_id}"
    reviewer = get_role(reviewer_id)
    if reviewer is None:
        return False, f"unknown_reviewer:{reviewer_id}"
    if reviewer_id not in author.independent_review_by:
        return False, f"reviewer_not_declared_for:{author_id}"
    if not reviewer.may_approve_gates:
        return False, f"reviewer_cannot_approve:{reviewer_id}"
    return True, "ok"


def registry_summary(roles: Iterable[RoleContract] | None = None) -> dict[str, Any]:
    items = list(roles) if roles is not None else list_roles()
    return {
        "count": len(items),
        "implementation_roles": sorted(r.agent_id for r in items if r.may_write_code),
        "gate_approvers": sorted(r.agent_id for r in items if r.may_approve_gates),
        "security_veto": sorted(
            r.agent_id for r in items if r.has_capability("security_veto")
        ),
        "roles": [r.to_dict() for r in items],
    }
