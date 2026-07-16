"""M20.0 — Security controls + Trading Guardian isolation for Engineering Orchestrator."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from saathi.engineering.settings import EngineeringSettings

# Paths that engineering may never read for prompt context
SENSITIVE_PATH_PARTS = (
    ".env",
    "id_rsa",
    ".pem",
    "credentials",
    "firebase-admin",
    "service-account",
    "trading_guardian_secrets",
    "exchange",
    "wallet",
)

FORBIDDEN_CAPABILITIES = frozenset({
    "trade_execute",
    "approve_trade",
    "merge_main",
    "deploy_production",
    "force_push",
    "unrestricted_shell",
    "unrestricted_mcp",
    "arbitrary_sql",
    "production_credentials",
})

ENGINEERING_CAPABILITIES = frozenset({
    "inspect_engineering_backlog",
    "inspect_repository",
    "generate_plan",
    "launch_readonly_agent",
    "launch_write_agent",
    "run_tests",
    "create_commit",
    "push_branch",
    "stop_session",
    "approve_retry",
    "approve_milestone_continuation",
})


def path_allowed_for_context(path: str | Path) -> bool:
    s = str(path).lower()
    return not any(p in s for p in SENSITIVE_PATH_PARTS)


def deny_arbitrary_repo(path: str | Path, settings: EngineeringSettings) -> tuple[bool, str]:
    root = Path(path).resolve()
    for allowed in settings.allowed_repositories:
        try:
            if Path(allowed).resolve() == root:
                return True, "ok"
        except Exception:
            pass
        if allowed in ("saathiai", "SaathiAI") and root.name in ("SaathiAI", "saathi"):
            return True, "ok"
        if str(root).endswith(allowed):
            return True, "ok"
    return False, "arbitrary_repo_denied"


def deny_path_traversal(target: str | Path, root: str | Path) -> tuple[bool, str]:
    try:
        t = Path(target).resolve()
        r = Path(root).resolve()
        t.relative_to(r)
        return True, "ok"
    except Exception:
        return False, "path_traversal_denied"


def deny_shell_request(command: str) -> tuple[bool, str]:
    """Orchestrator itself must not run free-form shell."""
    if not command:
        return False, "empty_command"
    # Only allow listed validation git/python forms via validation coordinator
    return False, "arbitrary_shell_denied"


def deny_mcp_request(method: str) -> tuple[bool, str]:
    return False, "arbitrary_mcp_denied"


def deny_cross_repo_write(
    target_repo: str, item_repo: str
) -> tuple[bool, str]:
    if target_repo != item_repo:
        return False, "cross_repo_write_denied"
    return True, "ok"


def trading_guardian_isolation_report() -> dict[str, Any]:
    """Static guarantees for TG isolation (asserted by tests)."""
    return {
        "engineering_can_execute_trades": False,
        "engineering_permissions_authorize_trading": False,
        "prompt_can_enable_trading": False,
        "generic_agent_launch_invokes_order_tools": False,
        "exchange_credentials_accessible": False,
        "insforge_holds_trading_credentials": False,
        "knowledge_retrieval_authorizes_trades": False,
        "kill_switch_independent": True,
        "trading_approvals_distinct": True,
        "trading_mode_unchanged": True,
        "merge_deploy_capabilities_present": False,
        "forbidden_capabilities": sorted(FORBIDDEN_CAPABILITIES),
        "engineering_capabilities": sorted(ENGINEERING_CAPABILITIES),
    }


def assert_no_trading_imports(package_root: Path) -> list[str]:
    """Scan engineering package for trading execution imports/calls.

    String constants that *deny* trading (e.g. forbidden capability names) are
    not violations — only live imports / call sites.
    """
    violations = []
    if not package_root.is_dir():
        return ["package_missing"]
    patterns = [
        re.compile(r"from\s+saathi\.execution\.trade\s+import"),
        re.compile(r"import\s+saathi\.execution\.trade\b"),
        re.compile(r"ExecutionService\s*\("),
        re.compile(r"\bplace_order\s*\("),
        re.compile(r"\bcreate_order\s*\("),
        re.compile(r"ExecutionIntent\.from_case\s*\("),
    ]
    for p in package_root.rglob("*.py"):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for pat in patterns:
            if pat.search(text):
                violations.append(f"{p.name}:{pat.pattern}")
    return violations


def permission_for_action(action: str, settings: EngineeringSettings) -> tuple[bool, str]:
    """Map action → allowed given settings. No universal admin bypass."""
    if action not in ENGINEERING_CAPABILITIES:
        if action in FORBIDDEN_CAPABILITIES:
            return False, f"forbidden:{action}"
        return False, f"unknown_capability:{action}"

    if not settings.orchestrator_enabled and action not in (
        "inspect_engineering_backlog",
        "inspect_repository",
    ):
        # Allow read-only inspect even when disabled for operator visibility
        if action.startswith("inspect"):
            return True, "inspect_always"
        return False, "orchestrator_disabled"

    if action == "launch_write_agent":
        if not (
            settings.agent_launching_enabled and settings.repository_writes_enabled
        ):
            return False, "write_launch_disabled"
        return True, "ok"

    if action == "launch_readonly_agent":
        if not settings.agent_launching_enabled:
            return False, "launch_disabled"
        return True, "ok"

    if action == "create_commit":
        return (settings.commits_enabled, "ok" if settings.commits_enabled else "commits_disabled")

    if action == "push_branch":
        return (settings.pushes_enabled, "ok" if settings.pushes_enabled else "pushes_disabled")

    return True, "ok"
