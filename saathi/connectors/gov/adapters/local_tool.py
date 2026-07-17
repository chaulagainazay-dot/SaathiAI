"""M27 — Local tool wrapper: allowlisted commands only; no arbitrary shell."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional

from saathi.connectors.gov.models import ConnectorRequest, ConnectorResult
from saathi.connectors.gov.redaction import redact_payload

# Explicit allowlist — never shell=True, never user-controlled binary path
DEFAULT_ALLOWLIST: frozenset[str] = frozenset({
    "git_rev_parse",
    "git_status_short",
    "python_version",
    "echo_safe",
})


@dataclass
class LocalToolAdapter:
    name: str = "local_tool"
    allowlist: frozenset[str] = field(default_factory=lambda: DEFAULT_ALLOWLIST)
    runner: Optional[Any] = None  # injectable for tests

    def execute(self, request: ConnectorRequest, **_: Any) -> ConnectorResult:
        op = request.operation
        if op not in self.allowlist:
            return ConnectorResult(
                ok=False,
                connector_id=request.connector_id,
                operation=op,
                status="denied",
                detail=f"command_not_allowlisted:{op}",
                bypass=False,
            )

        try:
            if self.runner:
                out = self.runner(op, request.payload or {})
            else:
                out = self._run(op, request.payload or {})
            return ConnectorResult(
                ok=True,
                connector_id=request.connector_id,
                operation=op,
                status="success",
                detail="local_tool_ok",
                data=redact_payload(out) if isinstance(redact_payload(out), dict) else {"result": str(out)[:200]},
                privacy_safe=True,
                bypass=False,
            )
        except Exception as e:
            return ConnectorResult(
                ok=False,
                connector_id=request.connector_id,
                operation=op,
                status="error",
                detail=type(e).__name__,
                bypass=False,
            )

    def _run(self, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        if op == "git_rev_parse":
            r = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                shell=False,
            )
            return {"stdout": (r.stdout or "").strip()[:64], "returncode": r.returncode}
        if op == "git_status_short":
            r = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                timeout=5,
                shell=False,
            )
            # Do not dump full worktree; only count lines
            lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
            return {"dirty_lines": len(lines), "returncode": r.returncode}
        if op == "python_version":
            import sys
            return {"version": sys.version.split()[0]}
        if op == "echo_safe":
            msg = str(payload.get("message") or "ok")[:80]
            # No shell — pure python
            return {"message": msg}
        raise RuntimeError(f"unhandled_allowlisted_op:{op}")
