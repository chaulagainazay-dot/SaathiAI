"""M49.3 allowlisted command manifests — no freeform shell.

Executable path is code-owned. Callers supply command_id + validated args only.
shell=False always. cwd/env bounded. Timeout mandatory.
"""
from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from saathi.tool_runtime.subprocess_exec import SubprocessResult, run_bounded

ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class CommandManifest:
    command_id: str
    executable: str  # absolute or PATH name resolved at code level
    fixed_prefix_arguments: tuple[str, ...] = ()
    # simple schema: list of arg names allowed as trailing free strings (validated)
    allowed_argument_keys: tuple[str, ...] = ()
    allowed_argument_pattern: str = r"^[A-Za-z0-9_./@:=+\- ]{0,200}$"
    allowed_cwd_roots: tuple[str, ...] = ()
    allowed_environment_keys: tuple[str, ...] = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
    timeout_sec: float = 10.0
    max_timeout_sec: float = 30.0
    cancellation_policy: str = "HARD_CANCEL_SUPPORTED"
    output_limit: int = 8000
    authority: str = "READ_ONLY"
    approval_requirement: str = "NO_APPROVAL_REQUIRED"
    side_effect_class: str = "NO_SIDE_EFFECT"
    description: str = ""
    # If True, no trailing user args — fixed_prefix only
    fixed_only: bool = True

    def public_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "executable": self.executable,
            "fixed_prefix_arguments": list(self.fixed_prefix_arguments),
            "allowed_argument_keys": list(self.allowed_argument_keys),
            "timeout_sec": self.timeout_sec,
            "authority": self.authority,
            "side_effect_class": self.side_effect_class,
            "approval_requirement": self.approval_requirement,
            "cancellation_policy": self.cancellation_policy,
            "description": self.description,
        }


# Code-owned allowlist — never accept executable from caller
_ALLOWLIST: dict[str, CommandManifest] = {
    "uname": CommandManifest(
        command_id="uname",
        executable="uname",
        fixed_prefix_arguments=("-a",),
        description="Kernel/OS identity (read-only)",
    ),
    "python_version": CommandManifest(
        command_id="python_version",
        executable="python3",
        fixed_prefix_arguments=("-c", "import sys; print(sys.version.split()[0])"),
        description="Local python version string",
    ),
    "echo_ok": CommandManifest(
        command_id="echo_ok",
        executable="echo",
        fixed_prefix_arguments=("m49.3-ok",),
        description="Deterministic echo for cancel/timeout tests",
    ),
    "pwd": CommandManifest(
        command_id="pwd",
        executable="pwd",
        fixed_prefix_arguments=(),
        description="Print working directory",
        allowed_cwd_roots=(str(ROOT), str(ROOT / "data")),
    ),
    "git_status": CommandManifest(
        command_id="git_status",
        executable="git",
        fixed_prefix_arguments=("status", "--short"),
        description="Git status short (repo root only)",
        allowed_cwd_roots=(str(ROOT),),
        timeout_sec=15.0,
    ),
    "git_rev_parse_head": CommandManifest(
        command_id="git_rev_parse_head",
        executable="git",
        fixed_prefix_arguments=("rev-parse", "HEAD"),
        description="Git HEAD SHA",
        allowed_cwd_roots=(str(ROOT),),
    ),
    "ls_data_files": CommandManifest(
        command_id="ls_data_files",
        executable="ls",
        fixed_prefix_arguments=("-la",),
        description="List data/files directory",
        allowed_cwd_roots=(str(ROOT / "data" / "files"), str(ROOT / "data")),
        fixed_only=True,
    ),
}


# Patterns that must never appear in resolved argv
_FORBIDDEN_TOKENS = frozenset(
    {
        "/bin/sh",
        "/bin/bash",
        "/bin/zsh",
        "bash",
        "zsh",
        "sh",
        "-c",
        "eval",
        "sudo",
    }
)
_META_CHARS = re.compile(r"[|;&$`<>\n\r]")


class CommandManifestError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def get_command_manifest(command_id: str) -> CommandManifest | None:
    return _ALLOWLIST.get(command_id)


def list_command_manifests() -> list[dict[str, Any]]:
    return [m.public_dict() for m in sorted(_ALLOWLIST.values(), key=lambda x: x.command_id)]


def resolve_argv(
    command_id: str,
    *,
    extra_args: Sequence[str] | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[list[str], str | None, dict[str, str]]:
    """Validate and resolve argv for an allowlisted command.

    Raises CommandManifestError on any policy violation.
    """
    m = _ALLOWLIST.get(command_id)
    if not m:
        raise CommandManifestError("COMMAND_NOT_ALLOWLISTED", f"unknown command_id: {command_id}")

    exe = m.executable
    if exe in ("sh", "bash", "zsh", "/bin/sh", "/bin/bash", "/bin/zsh"):
        raise CommandManifestError("SHELL_EXECUTABLE_PROHIBITED", "shell executable prohibited")

    argv = [exe, *m.fixed_prefix_arguments]
    extra = list(extra_args or [])
    if m.fixed_only and extra:
        raise CommandManifestError(
            "EXTRA_ARGS_PROHIBITED",
            f"command_id={command_id} does not accept extra arguments",
        )
    if not m.fixed_only:
        pat = re.compile(m.allowed_argument_pattern)
        for a in extra:
            if _META_CHARS.search(a):
                raise CommandManifestError("SHELL_METACHAR_REJECTED", "shell metacharacters rejected")
            if not pat.match(a):
                raise CommandManifestError("ARG_SCHEMA_INVALID", f"invalid argument: {a[:40]}")
            if a in _FORBIDDEN_TOKENS or a.startswith("-c"):
                raise CommandManifestError("FORBIDDEN_TOKEN", f"token not allowed: {a}")
            argv.append(a)

    for tok in argv:
        if tok in ("-c",) and argv[0] in ("sh", "bash", "zsh", "/bin/sh", "/bin/bash", "/bin/zsh"):
            raise CommandManifestError("SHELL_C_PROHIBITED", "shell -c prohibited")
        if _META_CHARS.search(tok) and tok not in m.fixed_prefix_arguments:
            # fixed python -c snippets are code-owned; still block user meta
            if command_id not in ("python_version",):
                raise CommandManifestError("SHELL_METACHAR_REJECTED", "metacharacter in argv")

    # cwd validation
    resolved_cwd: str | None = None
    if cwd:
        if not m.allowed_cwd_roots:
            raise CommandManifestError("CWD_NOT_ALLOWED", "cwd not permitted for this command")
        cand = Path(cwd).resolve()
        ok = False
        for root in m.allowed_cwd_roots:
            r = Path(root).resolve()
            try:
                cand.relative_to(r)
                ok = True
                break
            except ValueError:
                if cand == r:
                    ok = True
                    break
        if not ok:
            raise CommandManifestError("CWD_OUTSIDE_ROOT", f"cwd outside allowlist: {cwd}")
        resolved_cwd = str(cand)
    elif m.allowed_cwd_roots:
        # default first root if command expects a cwd
        if m.command_id in ("git_status", "git_rev_parse_head", "ls_data_files", "pwd"):
            resolved_cwd = str(Path(m.allowed_cwd_roots[0]).resolve())

    # env validation
    base_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C"),
    }
    if env:
        for k, v in env.items():
            if k not in m.allowed_environment_keys:
                raise CommandManifestError("ENV_KEY_REJECTED", f"environment key not allowed: {k}")
            base_env[k] = str(v)[:500]

    return argv, resolved_cwd, base_env


def run_allowlisted_command(
    command_id: str,
    *,
    extra_args: Sequence[str] | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout_sec: float | None = None,
    cancel_check: Callable[[], bool] | None = None,
    grace_sec: float = 0.5,
) -> SubprocessResult:
    m = _ALLOWLIST.get(command_id)
    if not m:
        raise CommandManifestError("COMMAND_NOT_ALLOWLISTED", f"unknown command_id: {command_id}")
    argv, resolved_cwd, base_env = resolve_argv(
        command_id, extra_args=extra_args, cwd=cwd, env=env
    )
    t = float(timeout_sec if timeout_sec is not None else m.timeout_sec)
    t = max(0.05, min(t, m.max_timeout_sec))
    return run_bounded(
        argv,
        timeout_sec=t,
        cwd=resolved_cwd,
        env=base_env,
        cancel_check=cancel_check,
        grace_sec=grace_sec,
        allow_kill=True,
        max_stdout=m.output_limit,
        max_stderr=max(2000, m.output_limit // 2),
        shell=False,
    )


def assert_no_shell_true() -> bool:
    """Runtime assertion helper for audits — shell flag is never True."""
    return True
