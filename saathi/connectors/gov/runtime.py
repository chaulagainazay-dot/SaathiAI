"""M27 — Governed connector runtime (single execute path).

Every request: policy → rollout → lifecycle → auth → adapter → evidence.
No bypasses. Cloud/trading blocked. Secrets never in evidence.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.connectors.gov.auth import resolve_auth
from saathi.connectors.gov.models import (
    CONNECTOR_INCIDENT_TYPES,
    AuthMode,
    ConnectorKind,
    ConnectorLifecycle,
    ConnectorManifest,
    ConnectorRequest,
    ConnectorResult,
)
from saathi.connectors.gov.policy import ConnectorPolicy
from saathi.connectors.gov.redaction import redact_payload
from saathi.connectors.gov.registry import ConnectorRegistry, get_registry

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "m27"

# Reuse M26 rollout modes
try:
    from saathi.inference.ops.models import RolloutMode
except Exception:  # pragma: no cover
    from enum import Enum

    class RolloutMode(str, Enum):  # type: ignore
        OFF = "OFF"
        SHADOW = "SHADOW"
        CANARY = "CANARY"
        ACTIVE = "ACTIVE"
        DRAINING = "DRAINING"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


class GovernedConnectorRuntime:
    """Canonical execute path for all connector kinds."""

    def __init__(
        self,
        *,
        registry: Optional[ConnectorRegistry] = None,
        policy: Optional[ConnectorPolicy] = None,
        rollout_mode: str | RolloutMode = RolloutMode.OFF,
        production_certified_probe: Optional[Callable[[], bool]] = None,
        evidence_dir: Optional[Path] = None,
        approval_required_ops: Optional[frozenset[str]] = None,
        approval_store: Optional[set[str]] = None,
        rate_window: Optional[dict[str, list[float]]] = None,
        clock: Optional[Callable[[], float]] = None,
        use_m26_incidents: bool = True,
    ):
        self.registry = registry or get_registry()
        self.policy = policy or ConnectorPolicy()
        self._mode = RolloutMode(rollout_mode) if not isinstance(rollout_mode, RolloutMode) else rollout_mode
        self.production_certified_probe = production_certified_probe or self._default_prod_cert
        self.evidence_dir = Path(evidence_dir) if evidence_dir else EVIDENCE_DIR
        self.approval_required_ops = approval_required_ops or frozenset({
            "write", "delete", "post", "put", "patch", "mutate",
        })
        self.approval_store = approval_store if approval_store is not None else set()
        self.rate_window = rate_window if rate_window is not None else {}
        self.clock = clock or time.time
        self.use_m26_incidents = use_m26_incidents
        self._events: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def _default_prod_cert(self) -> bool:
        try:
            from saathi.inference.runtime_gate import evaluate_runtime_gate
            return bool(evaluate_runtime_gate(include_live_probe=True).production_certified)
        except Exception:
            return False

    @property
    def mode(self) -> RolloutMode:
        return self._mode

    def set_mode(self, mode: str | RolloutMode) -> dict[str, Any]:
        target = RolloutMode(mode) if not isinstance(mode, RolloutMode) else mode
        if target is RolloutMode.ACTIVE:
            if not self.production_certified_probe():
                return {
                    "ok": False,
                    "error": "active_requires_production_certification",
                    "mode": self._mode.value,
                }
        prev = self._mode
        self._mode = target
        self._emit("connector.mode_changed", {"from": prev.value, "to": target.value})
        return {"ok": True, "mode": target.value, "from": prev.value}

    def grant_approval(self, token: str) -> None:
        self.approval_store.add(token)

    def _emit(self, event_type: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        ev = {
            "schema": "m27.connector_event.v1",
            "event_type": event_type,
            "ts": _utc(),
            "payload": redact_payload(payload or {}),
            "privacy_safe": True,
            "mode": self._mode.value,
        }
        self._events.append(ev)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        with open(self.evidence_dir / "connector_events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, default=str) + "\n")
        return ev

    def _open_incident(self, incident_type: str, *, summary: str, check_ids: list[str]) -> str:
        if incident_type not in CONNECTOR_INCIDENT_TYPES:
            incident_type = "policy_violation"
        if self.use_m26_incidents:
            try:
                from saathi.inference.ops.service import get_ops_service
                # Map to M26 types loosely or use provider_unreachable bucket
                m26_type = {
                    "auth_failure": "provider_unreachable",
                    "timeout": "repeated_timeout",
                    "unavailable": "provider_unreachable",
                    "rate_limit": "circuit_open",
                }.get(incident_type, "provider_unreachable")
                rec = get_ops_service().open_incident(
                    m26_type,
                    severity="medium",
                    check_ids=check_ids,
                    safe_summary=summary[:200],
                    recommended_action=f"connector:{incident_type}",
                )
                return rec.incident_id
            except Exception:
                pass
        iid = uuid.uuid4().hex[:12]
        path = self.evidence_dir / "incidents.json"
        data = {"incidents": []}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {"incidents": []}
        # dedupe open by type+summary
        for inc in data.get("incidents") or []:
            if inc.get("state") == "open" and inc.get("incident_type") == incident_type and inc.get("safe_summary") == summary[:200]:
                return inc.get("incident_id") or iid
        data.setdefault("incidents", []).append({
            "incident_id": iid,
            "incident_type": incident_type,
            "state": "open",
            "opened_at": _utc(),
            "safe_summary": summary[:200],
            "check_ids": check_ids,
            "privacy_safe": True,
        })
        _atomic_write(path, data)
        self._emit("connector.incident", {"incident_id": iid, "incident_type": incident_type})
        return iid

    def _rate_ok(self, connector_id: str, limit_per_minute: int) -> bool:
        now = self.clock()
        window = [t for t in self.rate_window.get(connector_id, []) if now - t < 60.0]
        self.rate_window[connector_id] = window
        if len(window) >= max(1, int(limit_per_minute)):
            return False
        window.append(now)
        self.rate_window[connector_id] = window
        return True

    def register_builtin_adapters(self) -> list[str]:
        """Register default HTTP/MCP/browser/local_tool connectors (no live accounts)."""
        from saathi.connectors.gov.adapters.browser import BrowserAdapter
        from saathi.connectors.gov.adapters.http import HttpAdapter
        from saathi.connectors.gov.adapters.local_tool import LocalToolAdapter
        from saathi.connectors.gov.adapters.mcp import McpAdapter

        specs = [
            (
                ConnectorManifest(
                    connector_id="gov.http",
                    kind=ConnectorKind.HTTP,
                    capabilities=(
                        "http_request", "get", "post", "put", "patch", "delete",
                        "health", "validate",
                    ),
                    supported_operations=(
                        "http_request", "get", "post", "put", "patch", "delete",
                        "health", "validate",
                    ),
                    allowed_domains=("127.0.0.1", "localhost", "example.com"),
                    timeout_seconds=10.0,
                    max_retries=1,
                    description="Governed HTTP adapter",
                ),
                HttpAdapter(),
            ),
            (
                ConnectorManifest(
                    connector_id="gov.mcp",
                    kind=ConnectorKind.MCP,
                    capabilities=("health", "validate", "status", "inventory"),
                    supported_operations=("health", "validate", "status", "inventory"),
                    auth_mode=AuthMode.NONE,
                    description="MCP governance reuse",
                ),
                McpAdapter(),
            ),
            (
                ConnectorManifest(
                    connector_id="gov.browser",
                    kind=ConnectorKind.BROWSER,
                    capabilities=("health", "validate", "policy_check", "navigate"),
                    supported_operations=("health", "validate", "policy_check", "navigate"),
                    description="Browser governance reuse",
                ),
                BrowserAdapter(),
            ),
            (
                ConnectorManifest(
                    connector_id="gov.local_tool",
                    kind=ConnectorKind.LOCAL_TOOL,
                    capabilities=("git_rev_parse", "git_status_short", "python_version", "echo_safe", "health", "validate"),
                    supported_operations=("git_rev_parse", "git_status_short", "python_version", "echo_safe", "health", "validate"),
                    auth_mode=AuthMode.NONE,
                    description="Allowlisted local tools",
                ),
                LocalToolAdapter(),
            ),
        ]
        ids = []
        for manifest, adapter in specs:
            self.registry.register(manifest, adapter=adapter)
            self.registry.validate(manifest.connector_id)
            self.registry.mark_ready(manifest.connector_id)
            self._emit("connector.registered", {"connector_id": manifest.connector_id, "kind": manifest.kind.value})
            self._emit("connector.ready", {"connector_id": manifest.connector_id})
            ids.append(manifest.connector_id)
        return ids

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        t0 = time.perf_counter()
        rid = request.request_id or uuid.uuid4().hex[:12]
        request.request_id = rid
        self._emit("connector.request", {
            "request_id": rid,
            "connector_id": request.connector_id,
            "operation": request.operation,
            "method": request.method,
        })

        rec = self.registry.get(request.connector_id)
        if not rec:
            res = ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail="connector_not_registered", bypass=False,
            )
            return self._finalize(request, res, t0, incident="unavailable")

        manifest = rec.manifest
        # Rollout mode
        mode = self._mode
        if mode is RolloutMode.OFF:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail="mode:OFF", mode=mode.value, lifecycle=rec.lifecycle.value, bypass=False,
            ), t0)
        if mode is RolloutMode.DRAINING or rec.lifecycle is ConnectorLifecycle.DRAINING:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="draining", detail="mode:DRAINING", mode=mode.value, lifecycle=rec.lifecycle.value, bypass=False,
            ), t0)
        if rec.lifecycle is ConnectorLifecycle.DISABLED:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail="lifecycle:DISABLED", mode=mode.value, lifecycle=rec.lifecycle.value, bypass=False,
            ), t0, incident="unavailable")
        if rec.lifecycle is ConnectorLifecycle.FAILED:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail="lifecycle:FAILED", mode=mode.value, lifecycle=rec.lifecycle.value, bypass=False,
            ), t0, incident="unavailable")
        if rec.lifecycle not in (ConnectorLifecycle.READY, ConnectorLifecycle.DEGRADED, ConnectorLifecycle.VALIDATED):
            if request.operation not in ("health", "validate"):
                return self._finalize(request, ConnectorResult(
                    ok=False, connector_id=request.connector_id, operation=request.operation,
                    status="denied", detail=f"lifecycle:{rec.lifecycle.value}", mode=mode.value,
                    lifecycle=rec.lifecycle.value, bypass=False,
                ), t0)

        # ACTIVE requires certification
        if mode is RolloutMode.ACTIVE:
            if not self.production_certified_probe():
                return self._finalize(request, ConnectorResult(
                    ok=False, connector_id=request.connector_id, operation=request.operation,
                    status="denied", detail="active_requires_production_certification",
                    mode=mode.value, lifecycle=rec.lifecycle.value, bypass=False,
                ), t0, incident="policy_violation")
            if rec.lifecycle not in (ConnectorLifecycle.READY, ConnectorLifecycle.DEGRADED):
                return self._finalize(request, ConnectorResult(
                    ok=False, connector_id=request.connector_id, operation=request.operation,
                    status="denied", detail="active_requires_connector_READY",
                    mode=mode.value, lifecycle=rec.lifecycle.value, bypass=False,
                ), t0)

        # SHADOW: validation/health only
        if mode is RolloutMode.SHADOW and request.operation not in ("health", "validate", "policy_check", "status", "inventory"):
            return self._finalize(request, ConnectorResult(
                ok=True, connector_id=request.connector_id, operation=request.operation,
                status="shadow", detail="shadow_no_side_effect", mode=mode.value,
                lifecycle=rec.lifecycle.value, data={"shadow": True}, bypass=False,
            ), t0)

        # Policy
        decision = self.policy.evaluate(manifest, request)
        if not decision.allowed:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail=decision.reason, mode=mode.value,
                lifecycle=rec.lifecycle.value, bypass=False,
            ), t0, incident="policy_violation")

        # Approval for high-impact ops
        op_l = request.operation.lower()
        needs_approval = any(x in op_l for x in self.approval_required_ops) or request.method.upper() in ("POST", "PUT", "PATCH", "DELETE")
        if needs_approval and request.operation not in ("health", "validate", "get", "http_request") and request.method.upper() != "GET":
            if request.method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
                if not request.approval_token or request.approval_token not in self.approval_store:
                    # GET-like health exempt; mutating needs token
                    if request.operation not in ("health", "validate"):
                        return self._finalize(request, ConnectorResult(
                            ok=False, connector_id=request.connector_id, operation=request.operation,
                            status="denied", detail="approval_required", mode=mode.value,
                            lifecycle=rec.lifecycle.value, bypass=False,
                        ), t0, incident="permission_denied")

        # Auth
        auth = resolve_auth(manifest)
        if manifest.auth_mode is not AuthMode.NONE and not auth.ok:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail=f"auth:{auth.detail}", mode=mode.value,
                lifecycle=rec.lifecycle.value, bypass=False,
            ), t0, incident="auth_failure")

        # Rate limit
        if not self._rate_ok(request.connector_id, manifest.rate_limit_per_minute):
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail="rate_limit", mode=mode.value,
                lifecycle=rec.lifecycle.value, bypass=False,
            ), t0, incident="rate_limit")

        if request.dry_run or request.operation in ("validate",):
            return self._finalize(request, ConnectorResult(
                ok=True, connector_id=request.connector_id, operation=request.operation,
                status="success", detail="dry_run_or_validate", mode=mode.value,
                lifecycle=rec.lifecycle.value, data={"validated": True}, bypass=False,
            ), t0)

        adapter = self.registry.get_adapter(request.connector_id)
        if adapter is None:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="error", detail="adapter_missing", mode=mode.value,
                lifecycle=rec.lifecycle.value, bypass=False,
            ), t0, incident="unavailable")

        # Map operation shortcuts for HTTP
        if manifest.kind is ConnectorKind.HTTP and request.operation in ("get", "post", "put", "patch", "delete"):
            request.method = request.operation.upper()
            if request.operation == "http_request":
                pass

        try:
            if hasattr(adapter, "execute"):
                if manifest.kind is ConnectorKind.HTTP:
                    raw = adapter.execute(
                        request,
                        timeout_seconds=manifest.timeout_seconds,
                        max_retries=manifest.max_retries,
                    )
                else:
                    raw = adapter.execute(request)
            else:
                return self._finalize(request, ConnectorResult(
                    ok=False, connector_id=request.connector_id, operation=request.operation,
                    status="error", detail="adapter_not_executable", bypass=False,
                ), t0)
        except TimeoutError:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="timeout", detail="timeout", mode=mode.value, lifecycle=rec.lifecycle.value, bypass=False,
            ), t0, incident="timeout")
        except Exception as e:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="error", detail=type(e).__name__, mode=mode.value, lifecycle=rec.lifecycle.value, bypass=False,
            ), t0, incident="invalid_response")

        if isinstance(raw, ConnectorResult):
            raw.mode = mode.value
            raw.lifecycle = rec.lifecycle.value
            raw.bypass = False
            return self._finalize(request, raw, t0, incident=None if raw.ok else "invalid_response")

        return self._finalize(request, ConnectorResult(
            ok=True, connector_id=request.connector_id, operation=request.operation,
            status="success", detail="ok", mode=mode.value, lifecycle=rec.lifecycle.value,
            data=redact_payload(raw) if isinstance(raw, dict) else {"result": str(raw)[:200]},
            bypass=False,
        ), t0)

    def _finalize(
        self,
        request: ConnectorRequest,
        result: ConnectorResult,
        t0: float,
        *,
        incident: Optional[str] = None,
    ) -> ConnectorResult:
        result.latency_ms = result.latency_ms or round((time.perf_counter() - t0) * 1000, 2)
        result.mode = result.mode or self._mode.value
        result.privacy_safe = True
        result.bypass = False
        self.registry.bump_request(request.connector_id, ok=result.ok)
        eid = uuid.uuid4().hex[:12]
        result.evidence_id = eid
        evidence = {
            "schema": "m27.connector_evidence.v1",
            "evidence_id": eid,
            "ts": _utc(),
            "request": {
                "request_id": request.request_id,
                "connector_id": request.connector_id,
                "operation": request.operation,
                "method": request.method,
            },
            "result": redact_payload(result.to_dict()),
            "privacy_safe": True,
            "usage": {"counted": True, "connector_id": request.connector_id},
        }
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.evidence_dir / f"evidence_{eid}.json", evidence)
        self._emit("connector.response", {
            "request_id": request.request_id,
            "ok": result.ok,
            "status": result.status,
            "evidence_id": eid,
        })
        if not result.ok and incident:
            result.incident_id = self._open_incident(
                incident,
                summary=f"{request.connector_id}:{request.operation}:{result.detail}"[:200],
                check_ids=[f"connector.{incident}"],
            )
            if result.status == "timeout":
                self._emit("connector.timeout", {"request_id": request.request_id})
        if not result.ok and result.status == "error":
            self._emit("connector.failed", {"connector_id": request.connector_id, "detail": result.detail})
        return result

    def status(self) -> dict[str, Any]:
        return {
            "schema": "m27.connector_runtime.v1",
            "mode": self._mode.value,
            "production_certified": bool(self.production_certified_probe()),
            "connectors": [r.to_dict() for r in self.registry.all_records()],
            "events_buffered": len(self._events),
            "cloud_fallback": False,
            "trading_guardian": "UNCHANGED_UNENGAGED",
            "privacy_safe": True,
        }


_default_runtime: Optional[GovernedConnectorRuntime] = None
_rt_lock = threading.Lock()


def get_runtime(**kwargs: Any) -> GovernedConnectorRuntime:
    global _default_runtime
    with _rt_lock:
        if kwargs:
            return GovernedConnectorRuntime(**kwargs)
        if _default_runtime is None:
            _default_runtime = GovernedConnectorRuntime()
        return _default_runtime


def reset_runtime() -> None:
    global _default_runtime
    with _rt_lock:
        _default_runtime = None
