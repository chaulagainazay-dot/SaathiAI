"""M15 connector adapters — deterministic (test) + real-local.

Every production connector ships deterministic fixtures for success / auth-fail
/ permission-fail / timeout / rate-limit / malformed / partial / uncertain, so
unit + integration tests never touch live credentials. Real-local adapters
(filesystem, git inspect) genuinely execute with no external service. Cloud/
OAuth adapters are contract-ready and honestly report environment-blocked.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from saathi.connectors.platform.models import ToolResult, _now_iso

ROOT = Path(__file__).resolve().parent.parent.parent.parent


class FailureClass:
    AUTH = "authentication"
    AUTHZ = "authorization"
    VALIDATION = "validation"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    TRANSIENT = "transient_network"
    UNAVAILABLE = "provider_unavailable"
    UNSUPPORTED = "unsupported_operation"
    POLICY = "policy_denied"
    APPROVAL = "approval_required"
    APPROVAL_EXPIRED = "approval_expired"
    SECRET = "secret_unavailable"
    CONFLICT = "external_conflict"
    UNCERTAIN = "uncertain_side_effect"
    MALFORMED = "malformed_response"
    INTERNAL = "internal_error"


_RETRYABLE = {FailureClass.RATE_LIMIT, FailureClass.TIMEOUT, FailureClass.TRANSIENT,
              FailureClass.UNAVAILABLE}
# never retry these — includes uncertain non-idempotent side effects
_NEVER_RETRY = {FailureClass.AUTH, FailureClass.AUTHZ, FailureClass.VALIDATION,
                FailureClass.POLICY, FailureClass.UNCERTAIN, FailureClass.APPROVAL,
                FailureClass.APPROVAL_EXPIRED, FailureClass.UNSUPPORTED}


def is_retryable(failure_class: str, *, idempotent: bool = True) -> bool:
    if failure_class in _NEVER_RETRY:
        return False
    if failure_class == FailureClass.UNCERTAIN:
        return False
    # a non-idempotent action can double-apply on retry (e.g. a timed-out send
    # may have landed) — never auto-retry it, even on transient classes
    if not idempotent:
        return False
    return failure_class in _RETRYABLE


class Adapter:
    name = "base"

    def available(self) -> bool:
        return False

    def execute(self, *, tool, account_id: str, args: dict,
                secret_getter=None) -> ToolResult:  # pragma: no cover
        raise NotImplementedError

    def health(self) -> dict:
        return {"status": "unknown"}


class DeterministicAdapter(Adapter):
    """Test adapter — returns a fixture keyed by args['_fixture']."""
    name = "deterministic"

    def available(self) -> bool:
        return True

    def health(self) -> dict:
        return {"status": "healthy", "adapter": "deterministic"}

    def execute(self, *, tool, account_id, args, secret_getter=None) -> ToolResult:
        started = _now_iso()
        fixture = (args or {}).get("_fixture", "success")
        base = dict(connector_id=tool.connector_id, tool_id=tool.tool_id,
                    capability_id=tool.capability_id, started_at=started,
                    completed_at=_now_iso(),
                    provenance={"adapter": "deterministic", "adapter_version": 1})
        if fixture == "success":
            return ToolResult(status="success", data={"ok": True, "echo": args},
                              evidence=[{"external_reference": "det-obj-1",
                                        "status_code": 200, "checksum": "det123"}],
                              external_reference="det-obj-1", **base)
        if fixture == "partial":
            return ToolResult(status="partial", data={"done": 1, "remaining": 1},
                              warnings=["partial completion"], **base)
        if fixture == "auth_fail":
            return ToolResult(status="failed", errors=[{"class": FailureClass.AUTH,
                             "message": "invalid credentials"}], retryable=False, **base)
        if fixture == "permission_fail":
            return ToolResult(status="failed", errors=[{"class": FailureClass.AUTHZ,
                             "message": "insufficient scope"}], retryable=False, **base)
        if fixture == "timeout":
            return ToolResult(status="failed", errors=[{"class": FailureClass.TIMEOUT,
                             "message": "deadline exceeded"}], retryable=True, **base)
        if fixture == "rate_limit":
            return ToolResult(status="failed", errors=[{"class": FailureClass.RATE_LIMIT,
                             "message": "429"}], retryable=True,
                             rate_limit={"remaining": 0, "retry_after": 30}, **base)
        if fixture == "malformed":
            return ToolResult(status="failed", errors=[{"class": FailureClass.MALFORMED,
                             "message": "unparseable response"}], retryable=False, **base)
        if fixture == "uncertain":
            return ToolResult(status="uncertain", warnings=["side effect may have applied"],
                             errors=[{"class": FailureClass.UNCERTAIN,
                                     "message": "no confirmation received"}],
                             retryable=False, **base)
        return ToolResult(status="failed", errors=[{"class": FailureClass.INTERNAL,
                         "message": f"unknown fixture {fixture}"}], **base)


class LocalFilesystemAdapter(Adapter):
    """Real-local filesystem read (Risk 0/1). No external service."""
    name = "local-fs"

    def available(self) -> bool:
        return True

    def health(self) -> dict:
        return {"status": "healthy", "adapter": "local-fs"}

    def execute(self, *, tool, account_id, args, secret_getter=None) -> ToolResult:
        started = _now_iso()
        base = dict(connector_id=tool.connector_id, tool_id=tool.tool_id,
                    capability_id=tool.capability_id, started_at=started,
                    provenance={"adapter": "local-fs"})
        cap = tool.capability_id
        try:
            if cap == "read_local_file":
                p = (ROOT / str(args.get("path", ""))).resolve()
                if ROOT.resolve() not in p.parents and p != ROOT.resolve():
                    return ToolResult(status="blocked", completed_at=_now_iso(),
                                     errors=[{"class": FailureClass.POLICY,
                                             "message": "path escapes repo"}], **base)
                text = p.read_text(errors="replace")[:4000]
                import hashlib
                cs = hashlib.sha256(text.encode()).hexdigest()[:16]
                return ToolResult(status="success", data={"text": text},
                                 evidence=[{"checksum": cs, "path": str(p.name)}],
                                 completed_at=_now_iso(), **base)
            if cap == "inspect_disk":
                import shutil as _sh
                du = _sh.disk_usage(str(ROOT))
                return ToolResult(status="success",
                                 data={"free_gb": round(du.free / 1e9, 1)},
                                 completed_at=_now_iso(), **base)
        except FileNotFoundError:
            return ToolResult(status="failed", completed_at=_now_iso(),
                             errors=[{"class": FailureClass.VALIDATION,
                                     "message": "file not found"}], **base)
        return ToolResult(status="failed", completed_at=_now_iso(),
                         errors=[{"class": FailureClass.UNSUPPORTED,
                                 "message": f"local-fs has no {cap}"}], **base)


class LocalGitAdapter(Adapter):
    """Real-local git inspection (Risk 1). Read-only git commands only."""
    name = "local-git"

    def available(self) -> bool:
        return shutil.which("git") is not None

    def health(self) -> dict:
        return {"status": "healthy" if self.available() else "unavailable",
                "adapter": "local-git"}

    def execute(self, *, tool, account_id, args, secret_getter=None) -> ToolResult:
        started = _now_iso()
        base = dict(connector_id=tool.connector_id, tool_id=tool.tool_id,
                    capability_id=tool.capability_id, started_at=started,
                    provenance={"adapter": "local-git"})
        if not self.available():
            return ToolResult(status="failed", completed_at=_now_iso(),
                             errors=[{"class": FailureClass.UNAVAILABLE,
                                     "message": "git not installed"}], **base)
        # only allow read-only inspection subcommands (argument-safe list form)
        allowed = {"inspect_repository": ["rev-parse", "--abbrev-ref", "HEAD"],
                   "list_issues": None}
        cap = tool.capability_id
        if cap == "inspect_repository":
            r = subprocess.run(["git", *allowed[cap]], cwd=str(ROOT),
                               capture_output=True, text=True, timeout=10)
            return ToolResult(status="success",
                             data={"branch": r.stdout.strip()},
                             evidence=[{"status_code": r.returncode}],
                             completed_at=_now_iso(), **base)
        return ToolResult(status="failed", completed_at=_now_iso(),
                         errors=[{"class": FailureClass.UNSUPPORTED,
                                 "message": f"local-git read-only; no {cap}"}], **base)
