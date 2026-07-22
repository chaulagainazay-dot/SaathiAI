"""M20.0 — Disabled-by-default Engineering Orchestrator controls.

Security denials cannot be silently overridden by ambient env for trading or
merge/deploy. Enable flags default false.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from saathi.config import ROOT

# Canonical env keys
ENV_ENABLED = "SAATHI_ENG_ORCH_ENABLED"
ENV_LAUNCH = "SAATHI_ENG_ORCH_LAUNCH"
ENV_WRITES = "SAATHI_ENG_ORCH_WRITES"
ENV_COMMITS = "SAATHI_ENG_ORCH_COMMITS"
ENV_PUSHES = "SAATHI_ENG_ORCH_PUSHES"
ENV_MAX_SESSIONS = "SAATHI_ENG_ORCH_MAX_SESSIONS"
ENV_MAX_MILESTONES = "SAATHI_ENG_ORCH_MAX_MILESTONES"
ENV_MAX_RETRIES = "SAATHI_ENG_ORCH_MAX_RETRIES"
ENV_SESSION_TIMEOUT = "SAATHI_ENG_ORCH_SESSION_TIMEOUT_SEC"
ENV_STALL_TIMEOUT = "SAATHI_ENG_ORCH_STALL_TIMEOUT_SEC"
ENV_ALLOWED_REPOS = "SAATHI_ENG_ORCH_ALLOWED_REPOS"
ENV_ALLOWED_ADAPTERS = "SAATHI_ENG_ORCH_ALLOWED_ADAPTERS"
ENV_ALLOWED_BRANCHES = "SAATHI_ENG_ORCH_ALLOWED_BRANCHES"
ENV_STORE_DIR = "SAATHI_ENG_ORCH_STORE"


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


def _csv(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return list(default)
    return [p.strip() for p in raw.split(",") if p.strip()]


@dataclass
class EngineeringSettings:
    """All orchestration controls. Defaults: fully disabled."""

    orchestrator_enabled: bool = False
    agent_launching_enabled: bool = False
    repository_writes_enabled: bool = False
    commits_enabled: bool = False
    pushes_enabled: bool = False
    max_active_sessions: int = 1
    max_milestone_count: int = 1
    max_retries: int = 3
    session_timeout_sec: float = 3600.0
    stall_timeout_sec: float = 600.0
    allowed_repositories: list[str] = field(
        default_factory=lambda: ["saathiai", str(ROOT)]
    )
    allowed_agent_adapters: list[str] = field(
        default_factory=lambda: ["mock", "claude_code"]
    )
    allowed_branches: list[str] = field(
        default_factory=lambda: ["milestone/*", "feat/*", "fix/*"]
    )
    store_dir: str = ""
    # Hard non-overridable denials
    merge_allowed: bool = False
    deploy_allowed: bool = False
    force_push_allowed: bool = False
    trading_allowed: bool = False
    unrestricted_shell_allowed: bool = False
    unrestricted_mcp_allowed: bool = False

    def store_path(self) -> Path:
        if self.store_dir:
            return Path(self.store_dir)
        return Path(ROOT) / "data" / "engineering"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["store_path"] = str(self.store_path())
        d["disable_procedure"] = disable_procedure()
        return d

    def assert_orchestrator_enabled(self) -> None:
        if not self.orchestrator_enabled:
            raise PermissionError(
                "engineering_orchestrator_disabled: set "
                f"{ENV_ENABLED}=1 to enable (still no launches by default)"
            )

    def assert_launch_allowed(self) -> None:
        self.assert_orchestrator_enabled()
        if not self.agent_launching_enabled:
            raise PermissionError(
                "agent_launching_disabled: set "
                f"{ENV_LAUNCH}=1 after readiness + approval"
            )

    def assert_writes_allowed(self) -> None:
        self.assert_launch_allowed()
        if not self.repository_writes_enabled:
            raise PermissionError(
                "repository_writes_disabled: set "
                f"{ENV_WRITES}=1 for write-enabled agent sessions"
            )


def load_settings(**overrides: Any) -> EngineeringSettings:
    """Load settings from env with hard safety defaults."""
    s = EngineeringSettings(
        orchestrator_enabled=_truthy(ENV_ENABLED, False),
        agent_launching_enabled=_truthy(ENV_LAUNCH, False),
        repository_writes_enabled=_truthy(ENV_WRITES, False),
        commits_enabled=_truthy(ENV_COMMITS, False),
        pushes_enabled=_truthy(ENV_PUSHES, False),
        max_active_sessions=max(1, _int(ENV_MAX_SESSIONS, 1)),
        max_milestone_count=max(1, _int(ENV_MAX_MILESTONES, 1)),
        max_retries=max(0, _int(ENV_MAX_RETRIES, 3)),
        session_timeout_sec=float(_int(ENV_SESSION_TIMEOUT, 3600)),
        stall_timeout_sec=float(_int(ENV_STALL_TIMEOUT, 600)),
        allowed_repositories=_csv(
            ENV_ALLOWED_REPOS, ["saathiai", str(ROOT)]
        ),
        allowed_agent_adapters=_csv(
            ENV_ALLOWED_ADAPTERS, ["mock", "claude_code"]
        ),
        allowed_branches=_csv(
            ENV_ALLOWED_BRANCHES, ["milestone/*", "feat/*", "fix/*"]
        ),
        store_dir=os.getenv(ENV_STORE_DIR, "") or "",
    )
    for k, v in overrides.items():
        if hasattr(s, k):
            setattr(s, k, v)
    # Absolute denials — env cannot enable these in M20.0
    s.merge_allowed = False
    s.deploy_allowed = False
    s.force_push_allowed = False
    s.trading_allowed = False
    s.unrestricted_shell_allowed = False
    s.unrestricted_mcp_allowed = False
    return s


def disable_procedure() -> dict[str, str]:
    return {
        "unset_or_zero": ", ".join([
            ENV_ENABLED, ENV_LAUNCH, ENV_WRITES, ENV_COMMITS, ENV_PUSHES,
        ]),
        "note": "Defaults are already disabled; unsetting is sufficient.",
        "kill_active": "python -m saathi.engineering stop <session_id>",
    }
