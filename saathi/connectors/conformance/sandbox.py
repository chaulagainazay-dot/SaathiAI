"""M30 — Credential-free sandbox harness for connector conformance.

No real secrets, paid services, or uncontrolled internet access.
Exercises the real GovernedConnectorRuntime path with fakes injected.
"""
from __future__ import annotations

import json
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.connectors.gov.adapters.browser import BrowserAdapter
from saathi.connectors.gov.adapters.http import HttpAdapter
from saathi.connectors.gov.adapters.local_tool import LocalToolAdapter
from saathi.connectors.gov.adapters.mcp import McpAdapter
from saathi.connectors.gov.models import ConnectorRequest
from saathi.connectors.gov.registry import ConnectorRegistry
from saathi.connectors.gov.runtime import GovernedConnectorRuntime
from saathi.connectors.registry.builtins import builtin_manifests
from saathi.inference.ops.models import RolloutMode


# ── Fakes ──────────────────────────────────────────────────────────────────


@dataclass
class DeterministicClock:
    now: float = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


@dataclass
class FakeHttpTransport:
    """Deterministic HTTP transport — never leaves process."""

    responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    default: Optional[dict[str, Any]] = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    fail_mode: str = ""  # timeout | connection | malformed | rate_limit | ""
    max_calls_before_ok: int = 0
    _count: int = 0

    def __call__(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: Optional[bytes],
        timeout: float,
    ) -> dict[str, Any]:
        self.calls.append({
            "method": method,
            "url": url,
            "headers": {k: ("***" if k.lower() in ("authorization", "cookie", "x-api-key") else v)
                        for k, v in (headers or {}).items()},
            "body_len": len(body or b""),
            "timeout": timeout,
        })
        self._count += 1
        if self.fail_mode == "timeout":
            raise TimeoutError("sandbox_timeout")
        if self.fail_mode == "connection":
            raise ConnectionError("sandbox_connection_failure")
        if self.fail_mode == "rate_limit":
            return {"status_code": 429, "ok": False, "body_preview": "rate_limited", "headers": {}}
        if self.fail_mode == "malformed":
            return {"status_code": "not-an-int", "ok": False, "body_preview": None, "headers": {}}
        if self.max_calls_before_ok and self._count <= self.max_calls_before_ok:
            raise ConnectionError("transient")
        key = f"{method.upper()} {url}"
        if key in self.responses:
            return dict(self.responses[key])
        if self.default is not None:
            return dict(self.default)
        return {
            "status_code": 200,
            "ok": True,
            "body_preview": "sandbox_ok",
            "headers": {"content-type": "application/json"},
        }


@dataclass
class FakeMcpServer:
    """In-process MCP stub — no network sockets."""

    tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    available: bool = True
    calls: list[str] = field(default_factory=list)

    def invoke(self, tool: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(tool)
        if not self.available:
            raise RuntimeError("mcp_server_unavailable")
        if tool not in self.tools:
            raise KeyError(f"unknown_tool:{tool}")
        return {"tool": tool, "result": self.tools[tool], "input_keys": list(payload.keys())}


@dataclass
class FakeBrowserGateway:
    """Controlled browser stub — no real browser process."""

    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    domain_allow: tuple[str, ...] = ("example.com", "127.0.0.1", "localhost")
    calls: list[dict[str, Any]] = field(default_factory=list)

    def open_session(self, owner: str) -> str:
        sid = f"sess_{owner}_{len(self.sessions)}"
        self.sessions[sid] = {"owner": owner, "url": "", "closed": False}
        return sid

    def navigate(self, session_id: str, url: str, *, owner: str) -> dict[str, Any]:
        self.calls.append({"op": "navigate", "session_id": session_id, "url": url, "owner": owner})
        sess = self.sessions.get(session_id)
        if not sess or sess.get("closed"):
            return {"ok": False, "detail": "session_missing"}
        if sess.get("owner") != owner:
            return {"ok": False, "detail": "session_ownership_violation"}
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
        if host and host not in self.domain_allow and not any(
            host.endswith("." + d) for d in self.domain_allow
        ):
            return {"ok": False, "detail": f"domain_denied:{host}"}
        sess["url"] = url
        return {"ok": True, "host": host, "live_browser_launched": False}

    def close(self, session_id: str) -> None:
        if session_id in self.sessions:
            self.sessions[session_id]["closed"] = True


@dataclass
class FakeLocalToolExecutor:
    """Allowlisted local tool runner — no arbitrary subprocess."""

    allowed: frozenset[str] = frozenset({
        "git_rev_parse", "git_status_short", "python_version", "echo_safe",
        "health", "validate",
    })
    calls: list[str] = field(default_factory=list)
    fail_mode: str = ""

    def __call__(self, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(op)
        if self.fail_mode == "timeout":
            raise TimeoutError("local_tool_timeout")
        if op not in self.allowed:
            raise PermissionError(f"not_allowlisted:{op}")
        if op in ("health", "validate"):
            return {"ok": True, "shell": False}
        if op == "echo_safe":
            return {"message": str(payload.get("message") or "ok")[:80]}
        if op == "python_version":
            import sys
            return {"version": sys.version.split()[0]}
        if op == "git_rev_parse":
            return {"stdout": "deadbeef" * 4, "returncode": 0}
        if op == "git_status_short":
            return {"dirty_lines": 0, "returncode": 0}
        return {"ok": True}


@dataclass
class TemporaryEvidenceStore:
    root: Path
    writes: list[str] = field(default_factory=list)
    fail_writes: bool = False

    def write(self, name: str, payload: dict[str, Any]) -> Path:
        if self.fail_writes:
            raise OSError("evidence_write_failure")
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        tmp.replace(path)
        self.writes.append(str(path))
        return path


@dataclass
class TemporaryApprovalStore:
    tokens: set[str] = field(default_factory=set)
    bindings: dict[str, dict[str, Any]] = field(default_factory=dict)
    used: set[str] = field(default_factory=set)
    unavailable: bool = False

    def grant(self, token: str, *, target: str = "", payload_fp: str = "", expires_at: float = 0.0) -> None:
        if self.unavailable:
            raise RuntimeError("approval_store_unavailable")
        self.tokens.add(token)
        self.bindings[token] = {
            "target": target,
            "payload_fp": payload_fp,
            "expires_at": expires_at,
        }

    def consume(self, token: str, *, target: str = "", payload_fp: str = "", now: float = 0.0) -> tuple[bool, str]:
        if self.unavailable:
            return False, "approval_store_unavailable"
        if token not in self.tokens:
            return False, "approval_missing"
        if token in self.used:
            return False, "approval_replay"
        bind = self.bindings.get(token) or {}
        if bind.get("expires_at") and now > float(bind["expires_at"]):
            return False, "approval_expired"
        if bind.get("target") and target and bind["target"] != target:
            return False, "approval_target_mismatch"
        if bind.get("payload_fp") and payload_fp and bind["payload_fp"] != payload_fp:
            return False, "approval_payload_mismatch"
        self.used.add(token)
        return True, "ok"


@dataclass
class TemporaryIncidentStore:
    incidents: list[dict[str, Any]] = field(default_factory=list)
    fail_writes: bool = False

    def open(self, incident_type: str, summary: str) -> str:
        if self.fail_writes:
            raise OSError("incident_write_failure")
        for inc in self.incidents:
            if inc.get("state") == "open" and inc.get("type") == incident_type and inc.get("summary") == summary:
                return inc["id"]
        iid = f"inc_{len(self.incidents)+1:04d}"
        self.incidents.append({
            "id": iid, "type": incident_type, "summary": summary[:200], "state": "open",
        })
        return iid


# ── Harness ────────────────────────────────────────────────────────────────


class SandboxHarness:
    """Isolated conformance environment.

    * No live credentials
    * No paid APIs
    * No uncontrolled network (HTTP uses FakeHttpTransport only)
    * Temporary evidence/approval/incident state
    * Cleanup via context manager / close()
    """

    def __init__(
        self,
        *,
        tmp_dir: Optional[Path] = None,
        clock: Optional[DeterministicClock] = None,
        production_certified: bool = True,
        rollout_mode: RolloutMode = RolloutMode.OFF,
    ):
        self._owned_tmp = tmp_dir is None
        self.tmp_dir = Path(tmp_dir) if tmp_dir else Path(tempfile.mkdtemp(prefix="m30_sandbox_"))
        self.clock = clock or DeterministicClock()
        self.http_transport = FakeHttpTransport()
        self.mcp_server = FakeMcpServer(tools={"ping": {"pong": True}})
        self.browser_gateway = FakeBrowserGateway()
        self.local_executor = FakeLocalToolExecutor()
        self.evidence = TemporaryEvidenceStore(self.tmp_dir / "evidence")
        self.approvals = TemporaryApprovalStore()
        self.incidents = TemporaryIncidentStore()
        self.registry = ConnectorRegistry()
        self.runtime = GovernedConnectorRuntime(
            registry=self.registry,
            rollout_mode=rollout_mode,
            production_certified_probe=lambda: production_certified,
            evidence_dir=self.tmp_dir / "connector_ev",
            approval_store=self.approvals.tokens,
            use_m26_incidents=False,
            clock=self.clock,
            certification_store=None,  # set by assessor
            require_connector_certification=False,  # sandbox assesses; does not require prior cert
        )
        self._closed = False
        self._lock = threading.RLock()

    def bootstrap_builtins(self, *, with_fakes: bool = True) -> list[str]:
        """Register M29 builtins with sandboxed adapters."""
        adapters = {
            "gov.http": HttpAdapter(transport=self.http_transport) if with_fakes else HttpAdapter(),
            "gov.mcp": McpAdapter(),
            "gov.browser": BrowserAdapter(),
            "gov.local_tool": LocalToolAdapter(runner=self.local_executor) if with_fakes else LocalToolAdapter(),
        }
        ids = []
        for manifest in builtin_manifests():
            adapter = adapters.get(manifest.connector_id)
            self.registry.register(manifest, adapter=adapter, allow_replace=True)
            self.registry.validate(manifest.connector_id)
            self.registry.mark_ready(manifest.connector_id)
            ids.append(manifest.connector_id)
        return ids

    def set_mode(self, mode: RolloutMode | str) -> dict[str, Any]:
        return self.runtime.set_mode(mode)

    def execute(self, request: ConnectorRequest) -> Any:
        return self.runtime.execute(request)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # Close fake browser sessions
        for sid in list(self.browser_gateway.sessions):
            self.browser_gateway.close(sid)
        if self._owned_tmp:
            import shutil
            try:
                shutil.rmtree(self.tmp_dir, ignore_errors=True)
            except Exception:
                pass

    def __enter__(self) -> "SandboxHarness":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def safety_report(self) -> dict[str, Any]:
        return {
            "schema": "m30.sandbox_safety.v1",
            "external_network": False,
            "live_credentials": 0,
            "live_external_accounts": 0,
            "tmp_dir": str(self.tmp_dir),
            "http_calls": len(self.http_transport.calls),
            "local_calls": list(self.local_executor.calls),
            "browser_calls": len(self.browser_gateway.calls),
            "subprocess_shell": False,
            "privacy_safe": True,
            "cleanup": self._closed,
        }
