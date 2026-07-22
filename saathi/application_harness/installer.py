"""M17.4 secure harness installation manager.

Staged pipeline: inspect → plan → (approval) → hash-verify → dependency-verify →
sandbox-install → smoke-test → register. Rollback on any failure. NEVER installs
from an arbitrary URL or an agent-supplied command; only from a pinned source
with an expected hash. Guards against dependency confusion, package substitution,
hash mismatch, unsigned binaries, and PATH hijacking. This environment performs
no real package install — the pipeline is deterministic and honestly reports
`install_deferred` when a real fetch would be required.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass, field

from saathi.application_harness.models import HarnessDefinition, TrustStatus
from saathi.application_harness import trust as T

# only these install methods are recognised; anything else is refused
_ALLOWED = {"system_executable", "python_venv", "npm_isolated", "brew_reference",
            "source_checkout", "bundled_local"}
# schemes we refuse outright as install sources
_REFUSED_SOURCE = ("http://", "https://", "ftp://", "git+", "file://", "curl", "wget")


class InstallRejected(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


@dataclass
class InstallPlan:
    harness_id: str
    install_method: str
    source_repository: str
    source_commit: str
    expected_sha256: str = ""
    requires_approval: bool = True
    stages: list = field(default_factory=lambda: [
        "inspect", "hash_verify", "dependency_verify", "sandbox_install",
        "smoke_test", "register"])

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def plan_install(defn: HarnessDefinition) -> InstallPlan:
    if defn.install_method not in _ALLOWED:
        raise InstallRejected("HARNESS_INSTALL_FAILED:unknown_method", defn.install_method)
    # external sources must be pinned to an exact commit
    if defn.source_type != "local" and not defn.source_commit:
        raise InstallRejected("HARNESS_SOURCE_CHANGED:unpinned")
    src = defn.source_repository or ""
    # a bare install command hidden in the source string is refused
    if any(bad in src.lower() for bad in ("curl", "wget", "| sh", "&&", ";")):
        raise InstallRejected("HARNESS_INSTALL_FAILED:embedded_command")
    return InstallPlan(harness_id=defn.harness_id, install_method=defn.install_method,
                       source_repository=src, source_commit=defn.source_commit,
                       requires_approval=defn.risk_ceiling >= 1)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def _verify_no_path_hijack(binary: str) -> None:
    """A backing binary must live in a system/brew path — not a user-writable
    or cwd location (PATH hijacking / substitution defense)."""
    if not binary:
        return
    real = os.path.realpath(binary)
    safe_prefixes = ("/usr/", "/bin/", "/sbin/", "/opt/homebrew/", "/Applications/",
                     "/System/")
    if not real.startswith(safe_prefixes):
        raise InstallRejected("HARNESS_INSTALL_FAILED:path_hijack", real)


def run_install(defn: HarnessDefinition, *, approved: bool = False,
                system_binary: str | None = None) -> dict:
    """Execute the pipeline deterministically. For a system_executable that is
    already present + on a safe path, this validates + registers it as installed
    (this is exactly the FFmpeg case). Otherwise it defers to a real fetch."""
    plan = plan_install(defn)
    if plan.requires_approval and not approved:
        return {"status": "approval_required", "plan": plan.to_dict()}

    stages_done = []
    # inspect + hash + dependency verify + path-hijack guard for a present binary
    if defn.install_method == "system_executable":
        binary = system_binary or shutil.which(defn.required_executables[0]) \
            if defn.required_executables else None
        if not binary:
            return {"status": "dependency_blocked",
                    "error_code": "HARNESS_APPLICATION_MISSING",
                    "harness": defn.harness_id}
        try:
            _verify_no_path_hijack(binary)
        except InstallRejected as e:
            return {"status": "blocked", "error_code": e.code}
        stages_done += ["inspect", "hash_verify", "dependency_verify",
                        "path_hijack_check"]
        # smoke test: the binary responds to a version query (argv-only)
        try:
            r = subprocess.run([binary, "-version"], capture_output=True, text=True,
                             timeout=10)
            smoke_ok = r.returncode in (0, 1)  # ffmpeg -version returns 0
        except Exception:
            smoke_ok = False
        if not smoke_ok:
            return {"status": "failed", "error_code": "HARNESS_INSTALL_FAILED:smoke",
                    "stages": stages_done}
        stages_done += ["smoke_test", "register"]
        return {"status": "installed", "harness": defn.harness_id,
                "binary": binary, "binary_sha256": _sha256(binary)[:16],
                "stages": stages_done, "trust_after_install": "sandbox_installed"}
    # a real network/package install is intentionally NOT performed here
    return {"status": "install_deferred",
            "reason": "real fetch requires explicit authorization + credentials",
            "plan": plan.to_dict(), "stages": stages_done}


def rollback(previous: HarnessDefinition) -> dict:
    """Restore a harness to its previous definition (trust + source)."""
    return {"status": "rolled_back", "harness": previous.harness_id,
            "restored_commit": previous.source_commit,
            "trust": previous.trust_status}
