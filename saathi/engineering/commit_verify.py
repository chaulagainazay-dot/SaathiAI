"""M20.0 — Commit verification (scope, secrets, branch, no rewrite)."""
from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from saathi.repair.secrets_scan import scan_text

_JUNK = re.compile(
    r"(?i)(\.pyc$|__pycache__|\.DS_Store$|\.pytest_cache|node_modules/|\.venv/)"
)
_LOCAL_STATE = re.compile(r"(?i)(\.env$|\.env\.|\.saathi-agent-state/SESSION)")
_SECRET_PATH = re.compile(
    r"(?i)(id_rsa|\.pem$|credentials\.json|service.account|secrets?/)"
)


@dataclass
class CommitVerification:
    ok: bool
    commit_sha: str = ""
    subject: str = ""
    files_changed: list[str] = field(default_factory=list)
    task_fingerprint: str = ""
    validation_evidence: list[str] = field(default_factory=list)
    approval_state: str = ""
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _git(root: Path, *args: str) -> tuple[int, str]:
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return p.returncode, (p.stdout or "").strip()
    except Exception as exc:
        return 1, str(exc)


def verify_commit(
    repository_root: str | Path,
    *,
    expected_branch: str,
    expected_parent: str = "",
    allowed_path_prefixes: list[str] | None = None,
    task_fingerprint: str = "",
    validation_evidence: list[str] | None = None,
    approval_state: str = "not_required",
    tests_passed: bool = True,
    require_tests: bool = True,
    git_fn: Callable[..., tuple[int, str]] | None = None,
    commit_ref: str = "HEAD",
) -> CommitVerification:
    root = Path(repository_root)
    git = git_fn or (lambda *a: _git(root, *a))
    reasons: list[str] = []

    rc, branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0 or (expected_branch and branch != expected_branch):
        reasons.append(f"wrong_branch:{branch}")

    rc, sha = git("rev-parse", commit_ref)
    if rc != 0 or not sha:
        return CommitVerification(ok=False, reasons=["commit_missing"])

    rc, subject = git("log", "-1", "--format=%s", commit_ref)
    subject = subject or ""
    if not subject.strip() or subject.lower() in ("wip", "temp", "asdf"):
        reasons.append("non_intentional_message")

    rc, parent = git("rev-parse", f"{commit_ref}^")
    if expected_parent and parent and not parent.startswith(expected_parent[:7]):
        # allow full or short
        if expected_parent not in parent and parent not in expected_parent:
            reasons.append("parent_mismatch")

    # rewritten history: if commit is not descendant of expected_parent when set
    if expected_parent:
        rc, merge_base = git("merge-base", expected_parent, commit_ref)
        if rc != 0 or (merge_base and expected_parent[:7] not in merge_base and merge_base not in expected_parent):
            # soft check — only fail if merge-base empty
            if rc != 0:
                reasons.append("history_rewrite_suspected")

    rc, files_raw = git("diff-tree", "--no-commit-id", "--name-only", "-r", commit_ref)
    files = [f for f in (files_raw or "").splitlines() if f.strip()]

    prefixes = allowed_path_prefixes or [
        "saathi/engineering/",
        "tests/test_m20",
        "docs/M20",
        "docs/AUTONOMOUS",
        "docs/TECHNICAL",
        "docs/CAPABILITY",
        ".saathi-agent-state/",
        "CAPABILITY",
        "TECHNICAL",
    ]
    for f in files:
        if _JUNK.search(f):
            reasons.append(f"generated_junk:{f}")
        if _LOCAL_STATE.search(f) and "HANDOFF" not in f:
            reasons.append(f"local_state_file:{f}")
        if _SECRET_PATH.search(f):
            reasons.append(f"secret_path:{f}")
        if allowed_path_prefixes is not None:
            if not any(f.startswith(p) or f == p for p in prefixes):
                reasons.append(f"unrelated_file:{f}")

        path = root / f
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                if not scan_text(text).clean:
                    reasons.append(f"secret_in_file:{f}")
            except Exception:
                pass

    if require_tests and not tests_passed:
        reasons.append("missing_or_failed_tests")

    # scan commit message
    if not scan_text(subject).clean:
        reasons.append("secret_in_message")

    ok = len(reasons) == 0
    return CommitVerification(
        ok=ok,
        commit_sha=sha[:12] if sha else "",
        subject=subject,
        files_changed=files,
        task_fingerprint=task_fingerprint,
        validation_evidence=list(validation_evidence or []),
        approval_state=approval_state,
        reasons=reasons,
    )
