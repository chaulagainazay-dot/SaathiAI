"""M349 — Configuration protection.

Development agents must never quietly rewrite the machine they run on. The
protected set is the user-level AI and shell configuration surface: the place
where a single edited line changes the behaviour of every future session,
usually without anyone noticing.

The check is path-shaped and deliberately conservative — it classifies a
*proposed* path and refuses it, rather than trying to police writes after the
fact. Combined with the role contracts (no role holds a writable scope outside
``mission:`` or ``worktree:``) this gives two independent layers.

Any proposed change to a protected path requires a complete
:class:`ConfigChangeProposal`: inventory, backup plan, change diff, rollback
plan, and explicit owner approval. Four of the five can be produced by an
agent; the fifth cannot be, by construction.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

#: Path fragments that identify protected configuration. Matching is done on the
#: resolved, home-relative path so ``~``, ``$HOME`` and absolute forms all land
#: in the same place.
PROTECTED_HOME_PREFIXES: tuple[tuple[str, str], ...] = (
    (".claude", "claude_code_user_config"),
    (".config/claude", "claude_user_config"),
    (".config/opencode", "opencode_user_config"),
    (".opencode", "opencode_user_config"),
    (".codex", "codex_user_config"),
    (".cursor", "cursor_user_config"),
    (".gemini", "gemini_user_config"),
    (".aws", "cloud_credentials"),
    (".ssh", "ssh_credentials"),
    (".gnupg", "gpg_credentials"),
    (".netrc", "network_credentials"),
    (".docker/config.json", "registry_credentials"),
    (".kube", "cluster_credentials"),
    (".saathi", "saathi_user_state"),
)

#: Shell and login files. Matched on basename anywhere under the home directory.
PROTECTED_BASENAMES: dict[str, str] = {
    ".zshrc": "shell_startup",
    ".zshenv": "shell_startup",
    ".zprofile": "shell_startup",
    ".bashrc": "shell_startup",
    ".bash_profile": "shell_startup",
    ".profile": "shell_startup",
    ".zlogin": "shell_startup",
    ".netrc": "network_credentials",
    ".npmrc": "package_registry_credentials",
    ".pypirc": "package_registry_credentials",
    ".env": "secret_material",
    ".mcp.json": "mcp_configuration",
    "mcp.json": "mcp_configuration",
    "mcp-servers.json": "mcp_configuration",
    "settings.json": "agent_harness_settings",
    "settings.local.json": "agent_harness_settings",
    "hooks.json": "global_hooks",
    "credentials": "credential_store",
    "credentials.json": "credential_store",
    "id_rsa": "ssh_credentials",
    "id_ed25519": "ssh_credentials",
}

#: Names that mark a path as credential-bearing wherever it appears.
CREDENTIAL_MARKERS = ("secret", "credential", "token", "apikey", "api_key", "keychain")

REQUIRED_PROPOSAL_FIELDS = (
    "inventory",
    "backup_plan",
    "change_diff",
    "rollback_plan",
)


@dataclass
class ProtectionVerdict:
    path: str
    protected: bool
    reason: str = ""
    category: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def _under_home_config(resolved: Path) -> bool:
    """True when a generically-named file sits in the user-level config surface.

    ``settings.json`` inside a repository worktree is ordinary project
    configuration. The same basename under ``~/.claude`` is not.
    """
    home = _home()
    try:
        relative = str(resolved.relative_to(home))
    except ValueError:
        return False
    if resolved.parent == home:
        # ~/.mcp.json and friends sit directly in the home directory.
        return True
    return any(
        relative == prefix or relative.startswith(prefix + os.sep)
        for prefix, _ in PROTECTED_HOME_PREFIXES
    )


def classify_path(candidate: str | Path) -> ProtectionVerdict:
    """Decide whether a path is protected configuration.

    Conservative by design: an unexpanded ``~`` or ``$HOME`` is expanded first,
    so an agent cannot evade the check by choosing a different spelling.
    """
    raw = str(candidate)
    expanded = os.path.expandvars(os.path.expanduser(raw))
    path = Path(expanded)
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError):  # pragma: no cover — pathological input
        resolved = path

    name = resolved.name
    lowered = str(resolved).lower()

    if name in PROTECTED_BASENAMES:
        # A settings.json inside a repository worktree is ordinary project
        # configuration; only the user-level one is protected.
        if name in ("settings.json", "settings.local.json", "hooks.json", ".mcp.json"):
            if _under_home_config(resolved):
                return ProtectionVerdict(
                    str(resolved), True, f"user-level {name}", PROTECTED_BASENAMES[name]
                )
        else:
            return ProtectionVerdict(
                str(resolved), True, f"protected file {name}", PROTECTED_BASENAMES[name]
            )

    home = _home()
    try:
        relative = resolved.relative_to(home)
    except ValueError:
        relative = None

    if relative is not None:
        relative_str = str(relative)
        for prefix, category in PROTECTED_HOME_PREFIXES:
            if relative_str == prefix or relative_str.startswith(prefix + os.sep):
                return ProtectionVerdict(
                    str(resolved), True, f"~/{prefix}", category
                )

    for marker in CREDENTIAL_MARKERS:
        if marker in lowered:
            return ProtectionVerdict(
                str(resolved), True, f"credential marker {marker!r}", "credential_store"
            )

    return ProtectionVerdict(str(resolved), False)


def is_protected(candidate: str | Path) -> bool:
    return classify_path(candidate).protected


@dataclass
class ConfigChangeProposal:
    """A proposal to touch protected configuration.

    An agent can author the first four fields. ``owner_approved`` is not one an
    agent may set — :func:`validate_proposal` refuses a proposal whose approver
    is anything other than the owner.
    """

    path: str
    proposed_by: str
    rationale: str = ""
    inventory: list[str] = field(default_factory=list)
    backup_plan: str = ""
    change_diff: str = ""
    rollback_plan: str = ""
    owner_approved: bool = False
    owner_approval_actor: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConfigProtectionError(PermissionError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}" + (f" ({detail})" if detail else ""))


def validate_proposal(proposal: ConfigChangeProposal) -> list[str]:
    """Return the reasons this proposal may not proceed. Empty means allowed."""
    refusals: list[str] = []
    verdict = classify_path(proposal.path)

    if not verdict.protected:
        # Unprotected paths do not need a proposal at all; saying so is more
        # useful than silently approving one.
        return ["path_not_protected:no_proposal_required"]

    if not proposal.rationale.strip():
        refusals.append("missing_rationale")
    for field_name in REQUIRED_PROPOSAL_FIELDS:
        value = getattr(proposal, field_name)
        if not value or (isinstance(value, str) and not value.strip()):
            refusals.append(f"missing_{field_name}")

    if not proposal.owner_approved:
        refusals.append("owner_approval_required")
    elif proposal.owner_approval_actor != "owner":
        refusals.append(
            f"owner_approval_not_by_owner:{proposal.owner_approval_actor or 'unset'}"
        )

    return refusals


def assert_change_allowed(proposal: ConfigChangeProposal) -> None:
    """Raise unless a complete, owner-approved proposal exists."""
    refusals = validate_proposal(proposal)
    if refusals:
        raise ConfigProtectionError("config_change_refused", "; ".join(refusals))


def assert_write_allowed(candidate: str | Path, *, actor: str = "") -> None:
    """Refuse an unproposed write to protected configuration."""
    verdict = classify_path(candidate)
    if verdict.protected:
        raise ConfigProtectionError(
            "protected_configuration_path",
            f"{verdict.reason} [{verdict.category}]"
            + (f" attempted by {actor}" if actor else ""),
        )


def protected_surface() -> dict[str, Any]:
    """The protected set, as data for docs, tests and the CLI."""
    return {
        "home_prefixes": [
            {"path": f"~/{prefix}", "category": category}
            for prefix, category in PROTECTED_HOME_PREFIXES
        ],
        "basenames": [
            {"name": name, "category": category}
            for name, category in sorted(PROTECTED_BASENAMES.items())
        ],
        "credential_markers": list(CREDENTIAL_MARKERS),
        "required_proposal_fields": [
            *REQUIRED_PROPOSAL_FIELDS,
            "owner_approved (owner only)",
        ],
        "note": (
            "Repository-local settings.json, hooks.json and .mcp.json are "
            "ordinary project configuration and are not protected; only the "
            "user-level copies under the home directory are."
        ),
    }
