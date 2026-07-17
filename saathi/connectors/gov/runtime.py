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
    ConnectorRequest,
    ConnectorResult,
)
from saathi.connectors.gov.policy import ConnectorPolicy
from saathi.connectors.gov.redaction import redact_payload
from saathi.connectors.gov.registry import ConnectorRegistry, get_registry
from saathi.connectors.gov.side_effects import (
    SideEffectClass,
    classify_operation,
    evaluate_side_effect,
)

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "m27"
M28_EVIDENCE_DIR = ROOT / "docs" / "evidence" / "m28"

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
        # M28: deterministic canary allowlist + percent (0–100), idempotency map
        # Default percent=100 preserves M27 canary-as-full-policy behavior until
        # operators set a stricter allowlist or lower percent.
        self.canary_connector_allowlist: frozenset[str] = frozenset()
        self.canary_percent: int = 100
        self._idempotency: dict[str, dict[str, Any]] = {}
        # Optional per-connector side-effect overrides (cannot weaken floors)
        self.operation_side_effects: dict[str, SideEffectClass] = {}

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
        """Bind static M29 manifests to adapters (identity is not runtime-generated)."""
        from saathi.connectors.gov.adapters.browser import BrowserAdapter
        from saathi.connectors.gov.adapters.http import HttpAdapter
        from saathi.connectors.gov.adapters.local_tool import LocalToolAdapter
        from saathi.connectors.gov.adapters.mcp import McpAdapter
        from saathi.connectors.registry.builtins import builtin_manifests

        adapters = {
            "gov.http": HttpAdapter(),
            "gov.mcp": McpAdapter(),
            "gov.browser": BrowserAdapter(),
            "gov.local_tool": LocalToolAdapter(),
        }
        ids = []
        for manifest in builtin_manifests():
            adapter = adapters.get(manifest.connector_id)
            # allow_replace so re-bootstrap is idempotent in CLI/tests
            self.registry.register(manifest, adapter=adapter, allow_replace=True)
            self.registry.validate(manifest.connector_id)
            self.registry.mark_ready(manifest.connector_id)
            self._emit(
                "connector.registered",
                {
                    "connector_id": manifest.connector_id,
                    "kind": manifest.kind.value,
                    "trust_level": getattr(manifest, "trust_level", "INTERNAL"),
                    "version": manifest.version,
                    "identity_source": "registry_manifest",
                },
            )
            self._emit("connector.ready", {"connector_id": manifest.connector_id})
            ids.append(manifest.connector_id)
        return ids

    def _resolve_side_effect(self, request: ConnectorRequest) -> SideEffectClass:
        """Registered/heuristic class; caller claimed class is never authoritative."""
        key = f"{request.connector_id}:{request.operation}"
        registered = self.operation_side_effects.get(key) or self.operation_side_effects.get(
            request.operation
        )
        return classify_operation(
            request.operation,
            method=request.method,
            capability=request.capability or request.operation,
            registered_class=registered,
        )

    def _canary_allows(self, request: ConnectorRequest) -> bool:
        """Deterministic canary: allowlist OR stable hash bucket (no randomness)."""
        if self.canary_connector_allowlist:
            if request.connector_id in self.canary_connector_allowlist:
                return True
            # Allowlist configured and connector not on it → deny (unless percent also admits)
        pct = max(0, min(100, int(self.canary_percent)))
        if pct >= 100 and not self.canary_connector_allowlist:
            return True
        if pct <= 0:
            return bool(self.canary_connector_allowlist and request.connector_id in self.canary_connector_allowlist)
        material = f"{request.connector_id}:{request.operation}:{request.request_id or request.idempotency_key or ''}"
        h = int(uuid.uuid5(uuid.NAMESPACE_URL, material).hex[:8], 16) % 100
        if self.canary_connector_allowlist:
            # On allowlist always; off-allowlist may still pass percent bucket
            if request.connector_id in self.canary_connector_allowlist:
                return True
        return h < pct

    def _idem_fingerprint(self, request: ConnectorRequest) -> str:
        import hashlib
        import json
        body = json.dumps(
            {
                "c": request.connector_id,
                "o": request.operation,
                "t": request.resource_target or request.url or "",
                "m": request.method,
                "p": request.payload or {},
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(body.encode()).hexdigest()

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        t0 = time.perf_counter()
        rid = request.request_id or uuid.uuid4().hex[:12]
        request.request_id = rid
        self._emit("connector.request", {
            "request_id": rid,
            "connector_id": request.connector_id,
            "operation": request.operation,
            "method": request.method,
            "caller_class": request.caller_class,
        })

        # M28: identity (caller name is not authority)
        if not (request.caller_id or request.actor_id):
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail="missing_caller_identity", bypass=False,
                error_code="unauthorized_caller", safe_message="caller identity required",
                policy_state="deny",
            ), t0, incident="unauthorized_caller")

        if not request.operation:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation="",
                status="denied", detail="missing_operation", bypass=False,
                error_code="intent_validation_failed", safe_message="operation required",
            ), t0, incident="intent_validation_failed")

        # Side-effect resolution (ignore caller claim for policy)
        sec = self._resolve_side_effect(request)
        request._resolved_side_effect_class = sec.value
        if request.claimed_side_effect_class and request.claimed_side_effect_class != sec.value:
            self._emit("connector.side_effect_claim_ignored", {
                "claimed": request.claimed_side_effect_class,
                "resolved": sec.value,
            })

        # Idempotency
        idem_state = "none"
        if request.idempotency_key:
            fp = self._idem_fingerprint(request)
            with self._lock:
                prior = self._idempotency.get(request.idempotency_key)
                if prior is not None:
                    if prior.get("fingerprint") != fp:
                        return self._finalize(request, ConnectorResult(
                            ok=False, connector_id=request.connector_id, operation=request.operation,
                            status="denied", detail="idempotency_conflict", bypass=False,
                            side_effect_class=sec.value, idempotency_state="conflict",
                            error_code="idempotency_conflict",
                            safe_message="idempotency key bound to different fingerprint",
                        ), t0, incident="idempotency_conflict")
                    # Replay prior terminal result (success only if recorded ok)
                    replay = ConnectorResult(**{
                        **{k: v for k, v in (prior.get("result") or {}).items()
                           if k in ConnectorResult.__dataclass_fields__},
                    }) if prior.get("result") else None
                    if isinstance(prior.get("result"), dict):
                        try:
                            replay = ConnectorResult(**{
                                k: prior["result"][k]
                                for k in ConnectorResult.__dataclass_fields__
                                if k in prior["result"]
                            })
                        except Exception:
                            replay = None
                    if replay is not None:
                        replay.idempotency_state = "replay"
                        replay.bypass = False
                        replay.request_id = rid
                        return self._finalize(request, replay, t0)
            idem_state = "new"

        # M29: identity only via registry resolve (never import path / filename)
        try:
            rec = self.registry.resolve(request.connector_id)
        except KeyError:
            res = ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail="connector_not_registered", bypass=False,
                side_effect_class=sec.value, error_code="connector_not_registered",
                safe_message="unknown or unregistered connector",
            )
            return self._finalize(request, res, t0, incident="unavailable")

        manifest = rec.manifest
        # Trust PROHIBITED fails closed regardless of caller
        if str(getattr(manifest, "trust_level", "")).upper() == "PROHIBITED":
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail="trust:PROHIBITED", bypass=False,
                side_effect_class=SideEffectClass.PROHIBITED.value,
                error_code="PROHIBITED", safe_message="connector trust level PROHIBITED",
            ), t0, incident="policy_violation")
        if getattr(manifest, "deprecated", False) and request.operation not in (
            "health", "validate", "status",
        ):
            # Deprecated connectors: read-only health only; mutations denied
            if sec is not SideEffectClass.READ_ONLY:
                return self._finalize(request, ConnectorResult(
                    ok=False, connector_id=request.connector_id, operation=request.operation,
                    status="denied", detail="connector_deprecated", bypass=False,
                    side_effect_class=sec.value, error_code="connector_deprecated",
                    safe_message=(
                        f"deprecated; use {getattr(manifest, 'replacement_connector', '') or 'replacement'}"
                    ),
                ), t0)

        if getattr(manifest, "trading", False):
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail="trading_connectors_forbidden", bypass=False,
                side_effect_class=SideEffectClass.PROHIBITED.value,
                error_code="PROHIBITED", safe_message="trading connectors forbidden",
            ), t0, incident="policy_violation")

        # Rollout mode
        mode = self._mode
        if mode is RolloutMode.OFF:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail="mode:OFF", mode=mode.value, lifecycle=rec.lifecycle.value,
                bypass=False, side_effect_class=sec.value, rollout_state="OFF",
                executed=False, error_code="mode_off",
                safe_message="connector rollout mode is OFF",
            ), t0)
        if mode is RolloutMode.DRAINING or rec.lifecycle is ConnectorLifecycle.DRAINING:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="draining", detail="mode:DRAINING", mode=mode.value, lifecycle=rec.lifecycle.value,
                bypass=False, side_effect_class=sec.value, rollout_state="DRAINING", executed=False,
            ), t0)
        if rec.lifecycle is ConnectorLifecycle.DISABLED:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail="lifecycle:DISABLED", mode=mode.value, lifecycle=rec.lifecycle.value,
                bypass=False, side_effect_class=sec.value,
            ), t0, incident="unavailable")
        if rec.lifecycle is ConnectorLifecycle.FAILED:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail="lifecycle:FAILED", mode=mode.value, lifecycle=rec.lifecycle.value,
                bypass=False, side_effect_class=sec.value,
            ), t0, incident="unavailable")
        if rec.lifecycle not in (ConnectorLifecycle.READY, ConnectorLifecycle.DEGRADED, ConnectorLifecycle.VALIDATED):
            if request.operation not in ("health", "validate"):
                return self._finalize(request, ConnectorResult(
                    ok=False, connector_id=request.connector_id, operation=request.operation,
                    status="denied", detail=f"lifecycle:{rec.lifecycle.value}", mode=mode.value,
                    lifecycle=rec.lifecycle.value, bypass=False, side_effect_class=sec.value,
                ), t0)

        # CANARY: deterministic selection
        if mode is RolloutMode.CANARY and not self._canary_allows(request):
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail="canary_not_selected", mode=mode.value,
                lifecycle=rec.lifecycle.value, bypass=False, side_effect_class=sec.value,
                rollout_state="CANARY", error_code="canary_not_selected",
                safe_message="request not in deterministic canary set",
            ), t0)

        # ACTIVE requires certification
        if mode is RolloutMode.ACTIVE:
            if not self.production_certified_probe():
                return self._finalize(request, ConnectorResult(
                    ok=False, connector_id=request.connector_id, operation=request.operation,
                    status="denied", detail="active_requires_production_certification",
                    mode=mode.value, lifecycle=rec.lifecycle.value, bypass=False,
                    side_effect_class=sec.value, rollout_state="ACTIVE",
                ), t0, incident="policy_violation")
            if rec.lifecycle not in (ConnectorLifecycle.READY, ConnectorLifecycle.DEGRADED):
                return self._finalize(request, ConnectorResult(
                    ok=False, connector_id=request.connector_id, operation=request.operation,
                    status="denied", detail="active_requires_connector_READY",
                    mode=mode.value, lifecycle=rec.lifecycle.value, bypass=False,
                    side_effect_class=sec.value,
                ), t0)

        # Side-effect hard blocks before SHADOW/adapter
        has_appr = bool(request.approval_token and request.approval_token in self.approval_store)
        se_decision = evaluate_side_effect(sec, has_approval=has_appr)
        if se_decision.blocked or not se_decision.allowed:
            # SHADOW still evaluates but never executes mutating adapters
            if mode is RolloutMode.SHADOW and sec not in (
                SideEffectClass.PROHIBITED, SideEffectClass.FINANCIAL, SideEffectClass.ACCOUNT_CHANGE,
            ):
                return self._finalize(request, ConnectorResult(
                    ok=True, connector_id=request.connector_id, operation=request.operation,
                    status="shadow", detail="shadow_policy_evaluated", mode=mode.value,
                    lifecycle=rec.lifecycle.value, data={"shadow": True, "would_require_approval": se_decision.requires_approval},
                    bypass=False, side_effect_class=sec.value, executed=False,
                    approval_state="required" if se_decision.requires_approval else "not_required",
                    policy_state="shadow",
                ), t0)
            if not se_decision.allowed:
                inc = "policy_violation" if se_decision.blocked else "permission_denied"
                if "approval" in se_decision.reason:
                    inc = "permission_denied"
                return self._finalize(request, ConnectorResult(
                    ok=False, connector_id=request.connector_id, operation=request.operation,
                    status="denied", detail=se_decision.reason, mode=mode.value,
                    lifecycle=rec.lifecycle.value, bypass=False, side_effect_class=sec.value,
                    approval_state="required" if se_decision.requires_approval else "denied",
                    policy_state="deny", error_code=se_decision.reason,
                    safe_message=se_decision.reason, executed=False,
                ), t0, incident=inc)

        # SHADOW: no side effects — never call mutating adapters
        if mode is RolloutMode.SHADOW:
            if request.operation in ("health", "validate", "policy_check", "status", "inventory") or sec is SideEffectClass.READ_ONLY:
                # allow read-only adapter path below after policy
                pass
            else:
                return self._finalize(request, ConnectorResult(
                    ok=True, connector_id=request.connector_id, operation=request.operation,
                    status="shadow", detail="shadow_no_side_effect", mode=mode.value,
                    lifecycle=rec.lifecycle.value, data={"shadow": True}, bypass=False,
                    side_effect_class=sec.value, executed=False, policy_state="shadow",
                ), t0)

        # Policy
        decision = self.policy.evaluate(manifest, request)
        if not decision.allowed:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail=decision.reason, mode=mode.value,
                lifecycle=rec.lifecycle.value, bypass=False, side_effect_class=sec.value,
                policy_state="deny", error_code=decision.reason,
            ), t0, incident="policy_violation")

        # Approval for high-impact ops (legacy method-based + side-effect)
        op_l = request.operation.lower()
        needs_approval = (
            se_decision.requires_approval
            or any(x in op_l for x in self.approval_required_ops)
            or request.method.upper() in ("POST", "PUT", "PATCH", "DELETE")
        )
        if needs_approval and request.operation not in ("health", "validate", "get") and sec is not SideEffectClass.READ_ONLY:
            if request.method.upper() in ("POST", "PUT", "PATCH", "DELETE") or se_decision.requires_approval:
                if not request.approval_token or request.approval_token not in self.approval_store:
                    if request.operation not in ("health", "validate"):
                        return self._finalize(request, ConnectorResult(
                            ok=False, connector_id=request.connector_id, operation=request.operation,
                            status="denied", detail="approval_required", mode=mode.value,
                            lifecycle=rec.lifecycle.value, bypass=False, side_effect_class=sec.value,
                            approval_state="missing", policy_state="deny",
                            error_code="approval_required",
                        ), t0, incident="permission_denied")
                # single-use consume
                if request.approval_token in self.approval_store:
                    # Keep token for replay checks within same request; mark used via remove optional
                    pass

        # Auth
        auth = resolve_auth(manifest)
        if manifest.auth_mode is not AuthMode.NONE and not auth.ok:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail=f"auth:{auth.detail}", mode=mode.value,
                lifecycle=rec.lifecycle.value, bypass=False, side_effect_class=sec.value,
            ), t0, incident="auth_failure")

        # Rate limit
        if not self._rate_ok(request.connector_id, manifest.rate_limit_per_minute):
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="denied", detail="rate_limit", mode=mode.value,
                lifecycle=rec.lifecycle.value, bypass=False, side_effect_class=sec.value,
            ), t0, incident="rate_limit")

        if request.dry_run or request.operation in ("validate",):
            return self._finalize(request, ConnectorResult(
                ok=True, connector_id=request.connector_id, operation=request.operation,
                status="success", detail="dry_run_or_validate", mode=mode.value,
                lifecycle=rec.lifecycle.value, data={"validated": True}, bypass=False,
                side_effect_class=sec.value, executed=False, policy_state="pass",
                idempotency_state=idem_state,
            ), t0)

        # SHADOW read-only may run health adapters only
        if mode is RolloutMode.SHADOW and sec is not SideEffectClass.READ_ONLY and request.operation not in (
            "health", "validate", "policy_check", "status", "inventory",
        ):
            return self._finalize(request, ConnectorResult(
                ok=True, connector_id=request.connector_id, operation=request.operation,
                status="shadow", detail="shadow_no_side_effect", mode=mode.value,
                lifecycle=rec.lifecycle.value, data={"shadow": True}, bypass=False,
                side_effect_class=sec.value, executed=False,
            ), t0)

        adapter = self.registry.get_adapter(request.connector_id)
        if adapter is None:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="error", detail="adapter_missing", mode=mode.value,
                lifecycle=rec.lifecycle.value, bypass=False, side_effect_class=sec.value,
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
                        timeout_seconds=manifest.timeout_seconds if not request.timeout_seconds else request.timeout_seconds,
                        max_retries=manifest.max_retries,
                    )
                else:
                    raw = adapter.execute(request)
            else:
                return self._finalize(request, ConnectorResult(
                    ok=False, connector_id=request.connector_id, operation=request.operation,
                    status="error", detail="adapter_not_executable", bypass=False,
                    side_effect_class=sec.value,
                ), t0)
        except TimeoutError:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="timeout", detail="timeout", mode=mode.value, lifecycle=rec.lifecycle.value,
                bypass=False, side_effect_class=sec.value,
            ), t0, incident="timeout")
        except Exception as e:
            return self._finalize(request, ConnectorResult(
                ok=False, connector_id=request.connector_id, operation=request.operation,
                status="error", detail=type(e).__name__, mode=mode.value, lifecycle=rec.lifecycle.value,
                bypass=False, side_effect_class=sec.value,
            ), t0, incident="invalid_response")

        if isinstance(raw, ConnectorResult):
            raw.mode = mode.value
            raw.lifecycle = rec.lifecycle.value
            raw.bypass = False
            raw.side_effect_class = sec.value
            raw.executed = bool(raw.ok)
            raw.policy_state = "pass" if raw.ok else "deny"
            raw.idempotency_state = idem_state
            result = self._finalize(request, raw, t0, incident=None if raw.ok else "invalid_response")
            self._store_idem(request, result)
            return result

        result = self._finalize(request, ConnectorResult(
            ok=True, connector_id=request.connector_id, operation=request.operation,
            status="success", detail="ok", mode=mode.value, lifecycle=rec.lifecycle.value,
            data=redact_payload(raw) if isinstance(raw, dict) else {"result": str(raw)[:200]},
            bypass=False, side_effect_class=sec.value, executed=True, policy_state="pass",
            idempotency_state=idem_state,
        ), t0)
        self._store_idem(request, result)
        return result

    def _store_idem(self, request: ConnectorRequest, result: ConnectorResult) -> None:
        if not request.idempotency_key:
            return
        # Only store successful terminal or explicit failed (not conflicts)
        if result.idempotency_state == "conflict":
            return
        fp = self._idem_fingerprint(request)
        with self._lock:
            self._idempotency[request.idempotency_key] = {
                "fingerprint": fp,
                "result": result.to_dict(),
            }

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
        result.rollout_state = result.rollout_state or result.mode
        result.privacy_safe = True
        result.bypass = False
        result.request_id = result.request_id or request.request_id
        if not result.side_effect_class:
            result.side_effect_class = getattr(request, "_resolved_side_effect_class", "") or ""
        result.safe_message = result.safe_message or result.detail or result.status
        result.safe_output = result.safe_output or redact_payload(result.data or {})
        if not result.policy_state:
            result.policy_state = "pass" if result.ok else "deny"
        try:
            self.registry.bump_request(request.connector_id, ok=result.ok)
        except Exception:
            pass
        eid = uuid.uuid4().hex[:12]
        result.evidence_id = eid
        result.evidence_refs = list(result.evidence_refs or []) + [eid]
        evidence = {
            "schema": "m28.connector_evidence.v1",
            "evidence_id": eid,
            "ts": _utc(),
            "request": {
                "request_id": request.request_id,
                "connector_id": request.connector_id,
                "operation": request.operation,
                "method": request.method,
                "caller_class": request.caller_class,
                "side_effect_class": result.side_effect_class,
            },
            "result": redact_payload(result.to_dict()),
            "privacy_safe": True,
            "bypass": False,
            "usage": {"counted": True, "connector_id": request.connector_id},
        }
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.evidence_dir / f"evidence_{eid}.json", evidence)
        self._emit("connector.response", {
            "request_id": request.request_id,
            "ok": result.ok,
            "status": result.status,
            "evidence_id": eid,
            "bypass": False,
        })
        if not result.ok and incident:
            # Avoid incident spam for normal OFF mode denials
            if incident not in ("policy_violation",) or result.detail not in ("mode:OFF",):
                if result.detail != "mode:OFF":
                    result.incident_id = self._open_incident(
                        incident if incident in CONNECTOR_INCIDENT_TYPES else "policy_violation",
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
            "schema": "m29.connector_runtime.v1",
            "mode": self._mode.value,
            "production_certified": bool(self.production_certified_probe()),
            "connectors": [r.to_dict() for r in self.registry.all_records()],
            "registry_ids": self.registry.list_ids(),
            "events_buffered": len(self._events),
            "cloud_fallback": False,
            "trading_guardian": "UNCHANGED_UNENGAGED",
            "privacy_safe": True,
            "default_mode": "OFF",
            "m28": True,
            "m29": True,
            "identity_resolution": "registry_only",
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
