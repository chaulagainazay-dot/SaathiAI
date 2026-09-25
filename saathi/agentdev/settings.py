"""M344 — Disabled-by-default controls for the development-agent environment.

Follows the ``saathi.engineering.settings`` contract deliberately: the
environment may enable *convenience*, never *authority*. The denial block at the
end of :func:`load_settings` is re-applied after overrides, so neither an
environment variable nor a caller keyword can turn a denial into a permission.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from saathi.config import ROOT

ENV_ENABLED = "SAATHI_AGENTDEV_ENABLED"
ENV_WORKTREES = "SAATHI_AGENTDEV_WORKTREES"
ENV_WORKTREE_PARENT = "SAATHI_AGENTDEV_WORKTREE_PARENT"
ENV_STORE_DIR = "SAATHI_AGENTDEV_STORE"
ENV_MAX_REASONING = "SAATHI_AGENTDEV_MAX_REASONING_AGENTS"
ENV_MAX_CODING = "SAATHI_AGENTDEV_MAX_CODING_AGENTS"
ENV_MAX_TESTING = "SAATHI_AGENTDEV_MAX_TESTING_AGENTS"
ENV_MAX_MODELS = "SAATHI_AGENTDEV_MAX_LOCAL_MODELS"

DEFAULT_WORKTREE_PARENT = str(Path.home() / "SaathiAI-agent-worktrees")


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class AgentDevSettings:
    """All development-environment controls. Defaults: fully disabled."""

    agentdev_enabled: bool = False
    worktree_creation_enabled: bool = False

    # Resource ceilings for an 8 GB Apple Silicon host (see docs/ai-development).
    max_reasoning_agents: int = 2
    max_coding_agents: int = 1
    max_testing_agents: int = 1
    max_local_model_instances: int = 1

    worktree_parent: str = DEFAULT_WORKTREE_PARENT
    store_dir: str = ""

    # Hard denials. Not overridable by environment or keyword — re-applied after
    # every override pass in load_settings().
    push_allowed: bool = False
    merge_allowed: bool = False
    deploy_allowed: bool = False
    force_push_allowed: bool = False
    branch_delete_allowed: bool = False
    destructive_git_allowed: bool = False
    force_worktree_removal_allowed: bool = False
    global_config_writes_allowed: bool = False
    credential_access_allowed: bool = False
    trading_allowed: bool = False
    external_paid_calls_allowed: bool = False
    unrestricted_shell_allowed: bool = False

    repo_root: str = field(default_factory=lambda: str(ROOT))

    def store_path(self) -> Path:
        if self.store_dir:
            return Path(self.store_dir)
        return Path(self.repo_root) / "data" / "agentdev"

    def worktree_parent_path(self) -> Path:
        return Path(self.worktree_parent)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["store_path"] = str(self.store_path())
        d["worktree_parent_path"] = str(self.worktree_parent_path())
        d["disable_procedure"] = disable_procedure()
        return d

    def assert_enabled(self) -> None:
        if not self.agentdev_enabled:
            raise PermissionError(
                "agentdev_disabled: set "
                f"{ENV_ENABLED}=1 to enable (still no worktree creation by default)"
            )

    def assert_worktree_creation_allowed(self) -> None:
        self.assert_enabled()
        if not self.worktree_creation_enabled:
            raise PermissionError(
                "worktree_creation_disabled: set "
                f"{ENV_WORKTREES}=1 after an approved implementation handoff"
            )

    def denials(self) -> dict[str, bool]:
        """The non-overridable denial block, for display and for tests."""
        return {name: getattr(self, name) for name in _DENIAL_FIELDS}


_DENIAL_FIELDS = (
    "push_allowed",
    "merge_allowed",
    "deploy_allowed",
    "force_push_allowed",
    "branch_delete_allowed",
    "destructive_git_allowed",
    "force_worktree_removal_allowed",
    "global_config_writes_allowed",
    "credential_access_allowed",
    "trading_allowed",
    "external_paid_calls_allowed",
    "unrestricted_shell_allowed",
)


def load_settings(**overrides: Any) -> AgentDevSettings:
    s = AgentDevSettings(
        agentdev_enabled=_truthy(ENV_ENABLED, False),
        worktree_creation_enabled=_truthy(ENV_WORKTREES, False),
        max_reasoning_agents=max(1, _int(ENV_MAX_REASONING, 2)),
        max_coding_agents=max(1, _int(ENV_MAX_CODING, 1)),
        max_testing_agents=max(1, _int(ENV_MAX_TESTING, 1)),
        max_local_model_instances=max(1, _int(ENV_MAX_MODELS, 1)),
        worktree_parent=os.getenv(ENV_WORKTREE_PARENT, "") or DEFAULT_WORKTREE_PARENT,
        store_dir=os.getenv(ENV_STORE_DIR, "") or "",
    )
    for k, v in overrides.items():
        if hasattr(s, k):
            setattr(s, k, v)
    # Absolute denials, applied last so no override can flip them.
    for name in _DENIAL_FIELDS:
        setattr(s, name, False)
    return s


def disable_procedure() -> dict[str, str]:
    return {
        "unset_or_zero": ", ".join([ENV_ENABLED, ENV_WORKTREES]),
        "note": "Defaults are already disabled; unsetting is sufficient.",
        "inspect": "python -m saathi.agentdev doctor",
    }
