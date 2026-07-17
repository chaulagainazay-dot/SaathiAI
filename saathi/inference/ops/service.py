"""M26 — Governed inference operations service.

Lifecycle: start / status / readiness / health / drain / stop / restart / recover
Does not own the external Ollama process. Does not enable cloud fallback.
Default rollout mode: OFF.
"""
from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.inference.ops.models import (
    INCIDENT_TYPES,
    VALID_MODE_TRANSITIONS,
    VALID_PROVIDER_TRANSITIONS,
    CheckResult,
    HealthReport,
    HealthStatus,
    IncidentRecord,
    ProviderOpsState,
    ReadinessReport,
    ReadinessStatus,
    RolloutMode,
    ServicePhase,
)
from saathi.inference.ops.state import OpsStateStore, _utc_now

# Canonical M25 memory rule — never redefine
from saathi.inference.certification import (
    SELECTION_SAFETY_MARGIN_GB,
    memory_selection_ok,
    minimum_model_budget_gb,
)

PRODUCER = "saathi.inference.ops"
SCHEMA = "m26.inference_ops.v1"
DEFAULT_STARTUP_TIMEOUT_S = 30.0
DEFAULT_SHUTDOWN_TIMEOUT_S = 15.0
DEFAULT_DRAIN_GRACE_S = 10.0
DEFAULT_MAX_CONCURRENT = 1  # 8 GB host
DEFAULT_CANARY_PERCENT = 10
DEFAULT_COOLDOWN_S = 30.0
DEFAULT_DISK_MIN_GB = 5.0
DEFAULT_FAILURE_THRESHOLD = 3
DEFAULT_FAILURE_WINDOW_S = 120.0

FORBIDDEN_EVENT_KEYS = frozenset({
    "prompt", "output", "text", "message", "messages", "raw", "token",
    "api_key", "authorization", "secret", "password", "credential",
})


def _now() -> float:
    return time.time()


def _iso_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat()


def redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip forbidden keys and truncate long strings."""
    out: dict[str, Any] = {}
    for k, v in (payload or {}).items():
        lk = str(k).lower()
        if lk in FORBIDDEN_EVENT_KEYS or any(x in lk for x in ("prompt", "secret", "token", "password")):
            continue
        if isinstance(v, str) and len(v) > 500:
            out[k] = v[:500] + "…"
        elif isinstance(v, dict):
            out[k] = redact_payload(v)
        else:
            out[k] = v
    out["privacy_safe"] = True
    return out


@dataclass
class ResourceSnapshot:
    available_memory_gb: float
    free_disk_gb: float
    memory_ok: bool
    disk_ok: bool
    model_id: str = "qwen2.5:1.5b"
    required_memory_gb: float = 1.8
    source: str = "probe"

    def to_dict(self) -> dict[str, Any]:
        return {
            "available_memory_gb": self.available_memory_gb,
            "free_disk_gb": self.free_disk_gb,
            "memory_ok": self.memory_ok,
            "disk_ok": self.disk_ok,
            "model_id": self.model_id,
            "required_memory_gb": self.required_memory_gb,
            "source": self.source,
            "safety_margin_gb": SELECTION_SAFETY_MARGIN_GB,
        }


def probe_resources(
    *,
    model_id: str = "qwen2.5:1.5b",
    min_disk_gb: float = DEFAULT_DISK_MIN_GB,
) -> ResourceSnapshot:
    from saathi.inference.hardware import profile_local_hardware

    hw = profile_local_hardware()
    avail = float(hw.available_memory_gb or 0.0)
    disk = float(hw.free_disk_gb or 0.0)
    budget = minimum_model_budget_gb(model_id)
    mem_ok = memory_selection_ok(avail, minimum_model_budget_gb=budget)
    return ResourceSnapshot(
        available_memory_gb=avail,
        free_disk_gb=disk,
        memory_ok=mem_ok,
        disk_ok=disk >= min_disk_gb,
        model_id=model_id,
        required_memory_gb=SELECTION_SAFETY_MARGIN_GB + budget,
        source="hardware.profile_local",
    )


class InferenceOpsService:
    """Canonical SaathiOS inference operations lifecycle (not Ollama PID owner)."""

    def __init__(
        self,
        *,
        store: Optional[OpsStateStore] = None,
        clock: Optional[Callable[[], float]] = None,
        resource_probe: Optional[Callable[[], ResourceSnapshot]] = None,
        production_certified_probe: Optional[Callable[[], bool]] = None,
        provider_reachable_probe: Optional[Callable[[], bool]] = None,
        model_available_probe: Optional[Callable[[], bool]] = None,
        circuit_open_probe: Optional[Callable[[], bool]] = None,
        governance_ready_probe: Optional[Callable[[], bool]] = None,
        recover_reservations: Optional[Callable[[], dict[str, Any]]] = None,
        emit_bus: bool = False,
        startup_timeout_s: float = DEFAULT_STARTUP_TIMEOUT_S,
        shutdown_timeout_s: float = DEFAULT_SHUTDOWN_TIMEOUT_S,
        drain_grace_s: float = DEFAULT_DRAIN_GRACE_S,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        canary_percent: int = DEFAULT_CANARY_PERCENT,
        cooldown_s: float = DEFAULT_COOLDOWN_S,
        min_disk_gb: float = DEFAULT_DISK_MIN_GB,
    ):
        self.store = store or OpsStateStore()
        self.clock = clock or _now
        self.resource_probe = resource_probe or (lambda: probe_resources(min_disk_gb=min_disk_gb))
        self.production_certified_probe = production_certified_probe or self._default_prod_cert
        self.provider_reachable_probe = provider_reachable_probe or self._default_provider_reachable
        self.model_available_probe = model_available_probe or self._default_model_available
        self.circuit_open_probe = circuit_open_probe or self._default_circuit_open
        self.governance_ready_probe = governance_ready_probe or self._default_governance_ready
        self.recover_reservations = recover_reservations or self._default_recover_reservations
        self.emit_bus = emit_bus
        self.startup_timeout_s = float(startup_timeout_s)
        self.shutdown_timeout_s = float(shutdown_timeout_s)
        self.drain_grace_s = float(drain_grace_s)
        self.max_concurrent = int(max_concurrent)
        self.canary_percent = int(canary_percent)
        self.cooldown_s = float(cooldown_s)
        self.min_disk_gb = float(min_disk_gb)
        self._lock = threading.RLock()
        self._inflight = 0
        self._force_stop_after: Optional[float] = None

    # ── default probes ────────────────────────────────────────────────────

    def _default_prod_cert(self) -> bool:
        try:
            from saathi.inference.runtime_gate import evaluate_runtime_gate

            rep = evaluate_runtime_gate(include_live_probe=True)
            return bool(rep.production_certified)
        except Exception:
            return False

    def _default_provider_reachable(self) -> bool:
        try:
            from saathi.inference.live_cert_m25 import discover_environment

            env = discover_environment()
            return bool(env.get("runtime_reachable"))
        except Exception:
            return False

    def _default_model_available(self) -> bool:
        try:
            from saathi.inference.live_cert_m25 import discover_environment

            env = discover_environment()
            models = env.get("installed_approved_models") or []
            return bool(models)
        except Exception:
            return False

    def _default_circuit_open(self) -> bool:
        try:
            from saathi.inference.circuit_breaker import CircuitState, get_circuit_registry

            reg = get_circuit_registry()
            snap = reg.snapshot("ollama")
            return snap.state is CircuitState.OPEN
        except Exception:
            return False

    def _default_governance_ready(self) -> bool:
        try:
            from saathi.inference.governance_store import get_governance_store

            store = get_governance_store()
            return store is not None and hasattr(store, "reserve_budget")
        except Exception:
            return False

    def _default_recover_reservations(self) -> dict[str, Any]:
        try:
            from saathi.inference.governance_store import get_governance_store

            return get_governance_store().recover_stale_reservations()
        except Exception as e:
            return {"schema": "m24.reservation_recovery.v1", "error": type(e).__name__, "processed": 0}

    # ── events / incidents ────────────────────────────────────────────────

    def _emit(self, event_type: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        safe = redact_payload(dict(payload or {}))
        event = {
            "schema": "m26.ops_event.v1",
            "event_type": event_type,
            "ts": _utc_now(),
            "clock": self.clock(),
            "producer": PRODUCER,
            "payload": safe,
            "privacy_safe": True,
        }
        self.store.append_event(event)
        if self.emit_bus:
            try:
                from saathi.events import bus

                bus.publish_sync(event_type, safe)
            except Exception:
                pass
        return event

    def open_incident(
        self,
        incident_type: str,
        *,
        severity: str = "medium",
        check_ids: Optional[list[str]] = None,
        safe_summary: str = "",
        recommended_action: str = "",
        provider: str = "ollama",
        model: str = "",
    ) -> IncidentRecord:
        if incident_type not in INCIDENT_TYPES:
            incident_type = "provider_unreachable"
        fp = hashlib.sha256(
            f"{incident_type}|{provider}|{','.join(sorted(check_ids or []))}|{safe_summary[:80]}".encode()
        ).hexdigest()[:16]
        incidents = self.store.load_incidents()
        # Dedupe open incidents with same fingerprint
        for raw in incidents:
            if raw.get("fingerprint") == fp and raw.get("state") == "open":
                raw["updated_at"] = _utc_now()
                self.store.save_incidents(incidents)
                return IncidentRecord(**{k: raw[k] for k in IncidentRecord.__dataclass_fields__ if k in raw})

        rec = IncidentRecord(
            incident_id=uuid.uuid4().hex[:12],
            incident_type=incident_type,
            severity=severity,
            state="open",
            opened_at=_utc_now(),
            updated_at=_utc_now(),
            provider=provider,
            model=model,
            check_ids=list(check_ids or []),
            safe_summary=safe_summary[:300],
            evidence_refs=[str(self.store.incidents_path.name)],
            recommended_action=recommended_action[:300],
            fingerprint=fp,
        )
        incidents.append(rec.to_dict())
        self.store.save_incidents(incidents)
        self._emit(
            "inference.incident.opened",
            {
                "incident_id": rec.incident_id,
                "incident_type": rec.incident_type,
                "severity": rec.severity,
                "check_ids": rec.check_ids,
            },
        )
        return rec

    def resolve_incident(self, incident_id: str, resolution: str = "resolved") -> Optional[IncidentRecord]:
        incidents = self.store.load_incidents()
        found = None
        for raw in incidents:
            if raw.get("incident_id") == incident_id and raw.get("state") == "open":
                raw["state"] = "resolved"
                raw["resolved_at"] = _utc_now()
                raw["updated_at"] = _utc_now()
                raw["resolution"] = resolution[:300]
                found = IncidentRecord(**{k: raw[k] for k in IncidentRecord.__dataclass_fields__ if k in raw})
                break
        if found:
            self.store.save_incidents(incidents)
            self._emit(
                "inference.incident.resolved",
                {"incident_id": incident_id, "resolution": resolution[:100]},
            )
        return found

    # ── provider state ────────────────────────────────────────────────────

    def _set_provider_state(self, new: ProviderOpsState, *, reason: str = "") -> ProviderOpsState:
        st = self.store.load()
        try:
            cur = ProviderOpsState(st.get("provider_state") or "UNKNOWN")
        except ValueError:
            cur = ProviderOpsState.UNKNOWN
        allowed = VALID_PROVIDER_TRANSITIONS.get(cur, frozenset(ProviderOpsState))
        if new not in allowed and new is not cur:
            # Allow forced STOPPED always for shutdown
            if new is not ProviderOpsState.STOPPED:
                return cur
        if new is not cur:
            self.store.update(provider_state=new.value, last_error=reason[:200] if reason else st.get("last_error", ""))
            self._emit(
                "inference.provider.state_changed",
                {"from": cur.value, "to": new.value, "reason": reason[:120]},
            )
        return new

    # ── rollout ───────────────────────────────────────────────────────────

    def set_mode(
        self,
        mode: RolloutMode | str,
        *,
        force: bool = False,
        reason: str = "",
    ) -> dict[str, Any]:
        target = RolloutMode(mode) if not isinstance(mode, RolloutMode) else mode
        st = self.store.load()
        try:
            current = RolloutMode(st.get("rollout_mode") or "OFF")
        except ValueError:
            current = RolloutMode.OFF

        if target is current:
            return {"ok": True, "mode": target.value, "idempotent": True}

        allowed = VALID_MODE_TRANSITIONS.get(current, frozenset())
        if target not in allowed and not force:
            return {
                "ok": False,
                "error": "invalid_mode_transition",
                "from": current.value,
                "to": target.value,
                "allowed": sorted(m.value for m in allowed),
            }

        # ACTIVE requires production certification
        if target is RolloutMode.ACTIVE:
            certified = bool(self.production_certified_probe())
            if not certified:
                return {
                    "ok": False,
                    "error": "active_requires_production_certification",
                    "from": current.value,
                    "to": target.value,
                    "production_certified": False,
                }

        self.store.update(rollout_mode=target.value)
        rec = {
            "ts": _utc_now(),
            "from": current.value,
            "to": target.value,
            "reason": reason[:200],
            "privacy_safe": True,
        }
        self.store.append_mode_history(rec)
        self._emit("inference.ops.mode_changed", rec)
        if target is RolloutMode.DRAINING:
            self._emit("inference.ops.draining", {"from": current.value})
        return {"ok": True, "mode": target.value, "from": current.value}

    def rollback(self, *, reason: str = "operator_rollback") -> dict[str, Any]:
        """Safe rollback: drain then OFF; preserve cert evidence and incidents."""
        drain = self.drain(grace_s=self.drain_grace_s)
        mode = self.set_mode(RolloutMode.OFF, force=True, reason=reason)
        self.store.update(
            phase=ServicePhase.STOPPED.value,
            provider_state=ProviderOpsState.STOPPED.value,
            active_requests=0,
            queued_requests=0,
        )
        self._emit("inference.ops.stopped", {"reason": reason, "rollback": True})
        return {
            "ok": True,
            "mode": "OFF",
            "drain": drain,
            "mode_result": mode,
            "reason": reason,
            "cert_evidence_preserved": True,
        }

    # ── accept work ───────────────────────────────────────────────────────

    def accepts_new_work(self, *, request_key: str = "", caller_id: str = "") -> tuple[bool, str]:
        """Whether a new governed production request may be accepted."""
        st = self.store.load()
        try:
            mode = RolloutMode(st.get("rollout_mode") or "OFF")
        except ValueError:
            mode = RolloutMode.OFF
        phase = st.get("phase") or "STOPPED"

        if phase in ("STOPPED", "STOPPING", "STARTING"):
            return False, f"phase:{phase}"
        if mode is RolloutMode.OFF:
            return False, "mode:OFF"
        if mode is RolloutMode.DRAINING or phase == "DRAINING":
            return False, "mode:DRAINING"
        if mode is RolloutMode.SHADOW:
            return False, "mode:SHADOW"  # validation only — no production serve
        if mode is RolloutMode.CANARY:
            if not self._canary_admit(request_key=request_key, caller_id=caller_id, st=st):
                return False, "mode:CANARY_not_selected"
        # ACTIVE and admitted CANARY
        cooldown = st.get("cooldown_until")
        if cooldown and self.clock() < float(cooldown):
            return False, "provider:COOLDOWN"
        if int(st.get("active_requests") or 0) >= int(st.get("max_concurrent") or self.max_concurrent):
            return False, "concurrency:capped"
        res = self.resource_probe()
        if not res.memory_ok:
            return False, "resource:memory_pressure"
        if not res.disk_ok:
            return False, "resource:disk_pressure"
        if self.circuit_open_probe():
            return False, "circuit:open"
        return True, "ok"

    def _canary_admit(self, *, request_key: str, caller_id: str, st: dict[str, Any]) -> bool:
        allow = list(st.get("canary_allowlist") or [])
        if caller_id and caller_id in allow:
            return True
        if request_key and request_key in allow:
            return True
        key = (request_key or caller_id or "default").encode()
        # Deterministic: first 2 hex digits of sha256 → 0-255 mapped to percent
        h = int(hashlib.sha256(key).hexdigest()[:8], 16)
        pct = int(st.get("canary_percent") or self.canary_percent)
        return (h % 100) < max(0, min(100, pct))

    def begin_request(self, *, request_key: str = "", caller_id: str = "") -> dict[str, Any]:
        with self._lock:
            ok, reason = self.accepts_new_work(request_key=request_key, caller_id=caller_id)
            if not ok:
                self._emit(
                    "inference.request.rejected",
                    {"reason": reason, "request_key_hash": hashlib.sha256((request_key or "").encode()).hexdigest()[:12]},
                )
                if "memory" in reason:
                    self.open_incident(
                        "memory_pressure",
                        severity="high",
                        check_ids=["resource.memory"],
                        safe_summary="New work rejected due to memory pressure",
                        recommended_action="Free RAM or wait; historical cert preserved",
                    )
                return {"accepted": False, "reason": reason}
            st = self.store.load()
            active = int(st.get("active_requests") or 0) + 1
            self._inflight = active
            self.store.update(active_requests=active)
            return {"accepted": True, "reason": "ok", "active_requests": active}

    def end_request(self) -> dict[str, Any]:
        with self._lock:
            st = self.store.load()
            active = max(0, int(st.get("active_requests") or 0) - 1)
            self._inflight = active
            self.store.update(active_requests=active)
            # If draining and no inflight, complete drain
            if st.get("phase") == ServicePhase.DRAINING.value and active == 0:
                if self._force_stop_after and self.clock() >= self._force_stop_after:
                    pass  # stop path will handle
            return {"active_requests": active}

    def record_provider_failure(self, *, reason: str = "timeout") -> dict[str, Any]:
        """Record failure for cooldown / circuit contribution (no gateway bypass)."""
        st = self.store.load()
        now = self.clock()
        window = [float(x) for x in (st.get("failure_window") or []) if now - float(x) < DEFAULT_FAILURE_WINDOW_S]
        window.append(now)
        updates: dict[str, Any] = {"failure_window": window}
        opened_circuit = False
        if len(window) >= DEFAULT_FAILURE_THRESHOLD:
            updates["cooldown_until"] = now + self.cooldown_s
            self._set_provider_state(ProviderOpsState.COOLDOWN, reason=reason)
            self.open_incident(
                "repeated_timeout" if "timeout" in reason else "circuit_open",
                severity="high",
                check_ids=["provider.failures"],
                safe_summary=f"Repeated provider failures ({len(window)})",
                recommended_action="Wait for cooldown; inspect provider logs",
            )
            self._emit("inference.circuit.opened", {"failures": len(window), "reason": reason[:80]})
            opened_circuit = True
            # Contribute to existing circuit registry if available
            try:
                from saathi.inference.circuit_breaker import get_circuit_registry

                get_circuit_registry().record_failure("ollama", reason=reason[:80])
            except Exception:
                pass
        self.store.update(**updates)
        return {"failures": len(window), "cooldown": opened_circuit}

    def record_provider_success(self) -> None:
        st = self.store.load()
        self.store.update(failure_window=[], cooldown_until=None, last_error="")
        if st.get("provider_state") in (ProviderOpsState.COOLDOWN.value, ProviderOpsState.DEGRADED.value):
            self._set_provider_state(ProviderOpsState.READY, reason="success")
        try:
            from saathi.inference.circuit_breaker import get_circuit_registry

            get_circuit_registry().record_success("ollama")
            self._emit("inference.circuit.closed", {"provider": "ollama"})
        except Exception:
            pass

    # ── lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> dict[str, Any]:
        with self._lock:
            st = self.store.load()
            if st.get("phase") in (ServicePhase.RUNNING.value, ServicePhase.DRAINING.value):
                return {
                    "ok": True,
                    "idempotent": True,
                    "phase": st.get("phase"),
                    "service_id": st.get("service_id"),
                    "rollout_mode": st.get("rollout_mode"),
                }
            service_id = st.get("service_id") or uuid.uuid4().hex[:12]
            owner = uuid.uuid4().hex
            t0 = self.clock()
            self.store.update(
                phase=ServicePhase.STARTING.value,
                service_id=service_id,
                owner_token=owner,
                started_at=_iso_from_ts(t0),
                stopped_at=None,
                max_concurrent=self.max_concurrent,
                canary_percent=self.canary_percent,
                idle_unload_enabled=False,
            )
            self._set_provider_state(ProviderOpsState.STARTING, reason="ops_start")

            # Bounded startup work — inspect only, no model download
            try:
                res = self.resource_probe()
                reachable = bool(self.provider_reachable_probe())
                models = bool(self.model_available_probe())
                if self.clock() - t0 > self.startup_timeout_s:
                    raise TimeoutError("startup_timeout")
                if not reachable:
                    self._set_provider_state(ProviderOpsState.UNAVAILABLE, reason="provider_unreachable")
                elif not models:
                    self._set_provider_state(ProviderOpsState.UNAVAILABLE, reason="model_unavailable")
                elif not res.memory_ok:
                    self._set_provider_state(ProviderOpsState.DEGRADED, reason="memory_pressure")
                else:
                    self._set_provider_state(ProviderOpsState.READY, reason="start_ok")
                # Default mode remains OFF unless already set
                mode = st.get("rollout_mode") or RolloutMode.OFF.value
                if mode not in {m.value for m in RolloutMode}:
                    mode = RolloutMode.OFF.value
                self.store.update(phase=ServicePhase.RUNNING.value, rollout_mode=mode)
                self._emit(
                    "inference.ops.started",
                    {
                        "service_id": service_id,
                        "rollout_mode": mode,
                        "provider_state": self.store.load().get("provider_state"),
                        "memory_ok": res.memory_ok,
                    },
                )
                return {
                    "ok": True,
                    "idempotent": False,
                    "phase": ServicePhase.RUNNING.value,
                    "service_id": service_id,
                    "rollout_mode": mode,
                    "owns_external_provider_process": False,
                    "resources": res.to_dict(),
                }
            except Exception as e:
                self.store.update(phase=ServicePhase.STOPPED.value, last_error=type(e).__name__)
                self._set_provider_state(ProviderOpsState.STOPPED, reason=type(e).__name__)
                self.open_incident(
                    "startup_failed",
                    severity="critical",
                    check_ids=["lifecycle.start"],
                    safe_summary=f"Startup failed: {type(e).__name__}",
                    recommended_action="Inspect logs; retry start",
                )
                return {"ok": False, "error": type(e).__name__, "phase": ServicePhase.STOPPED.value}

    def stop(self, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            st = self.store.load()
            if st.get("phase") == ServicePhase.STOPPED.value:
                return {"ok": True, "idempotent": True, "phase": "STOPPED"}
            t0 = self.clock()
            self.store.update(phase=ServicePhase.STOPPING.value)
            # Grace for inflight
            deadline = t0 + (0 if force else self.shutdown_timeout_s)
            while int(self.store.load().get("active_requests") or 0) > 0 and self.clock() < deadline:
                time.sleep(0.01)  # tests use zero inflight / short timeouts
            forced = int(self.store.load().get("active_requests") or 0) > 0
            self.store.update(
                phase=ServicePhase.STOPPED.value,
                stopped_at=_iso_from_ts(self.clock()),
                active_requests=0 if force or forced else int(self.store.load().get("active_requests") or 0),
                provider_state=ProviderOpsState.STOPPED.value,
            )
            if force or forced:
                self.store.update(active_requests=0)
            self._emit(
                "inference.ops.stopped",
                {"forced": bool(force or forced), "service_id": st.get("service_id")},
            )
            return {
                "ok": True,
                "idempotent": False,
                "phase": "STOPPED",
                "forced": bool(force or forced),
                "shutdown_evidence": True,
            }

    def drain(self, *, grace_s: Optional[float] = None) -> dict[str, Any]:
        with self._lock:
            st = self.store.load()
            if st.get("phase") == ServicePhase.STOPPED.value:
                # Still set mode to DRAINING semantics for readiness
                self.set_mode(RolloutMode.DRAINING, force=True, reason="drain_while_stopped")
                return {"ok": True, "phase": "STOPPED", "draining": True, "active_requests": 0}
            grace = float(grace_s if grace_s is not None else self.drain_grace_s)
            deadline = self.clock() + grace
            self._force_stop_after = deadline
            self.store.update(
                phase=ServicePhase.DRAINING.value,
                drain_started_at=_iso_from_ts(self.clock()),
                drain_deadline_at=_iso_from_ts(deadline),
                rollout_mode=RolloutMode.DRAINING.value,
            )
            self._set_provider_state(ProviderOpsState.DRAINING, reason="drain")
            self.set_mode(RolloutMode.DRAINING, force=True, reason="drain")
            self._emit("inference.ops.draining", {"grace_s": grace, "active": st.get("active_requests")})
            # Wait bounded grace for inflight
            while int(self.store.load().get("active_requests") or 0) > 0 and self.clock() < deadline:
                time.sleep(0.01)
            remaining = int(self.store.load().get("active_requests") or 0)
            forced = remaining > 0 and self.clock() >= deadline
            return {
                "ok": True,
                "phase": ServicePhase.DRAINING.value,
                "active_requests": remaining,
                "forced_after_grace": forced,
                "grace_s": grace,
            }

    def restart(self) -> dict[str, Any]:
        stop = self.stop()
        # Ensure no duplicate ownership — clear owner then start
        self.store.update(owner_token="", service_id="")
        start = self.start()
        return {
            "ok": bool(start.get("ok")),
            "stop": stop,
            "start": start,
            "duplicate_ownership": False,
        }

    def recover(self) -> dict[str, Any]:
        with self._lock:
            self.store.update(phase=ServicePhase.RECOVERING.value)
            recovery = self.recover_reservations()
            # Stale ownership: if phase was RUNNING without fresh update, reclaim
            st = self.store.load()
            reclaimed = False
            if not st.get("owner_token") and st.get("phase") not in (ServicePhase.STOPPED.value,):
                self.store.update(owner_token=uuid.uuid4().hex, phase=ServicePhase.RUNNING.value)
                reclaimed = True
            elif st.get("phase") == ServicePhase.RECOVERING.value:
                # Return to running if was operational, else stopped
                prev_mode = st.get("rollout_mode") or "OFF"
                if prev_mode == "OFF" and not st.get("started_at"):
                    self.store.update(phase=ServicePhase.STOPPED.value)
                else:
                    self.store.update(phase=ServicePhase.RUNNING.value if st.get("started_at") else ServicePhase.STOPPED.value)
            self._emit(
                "inference.reservation.reconciled",
                {
                    "processed": recovery.get("processed", 0),
                    "unresolved": recovery.get("unresolved_count", 0),
                    "reclaimed_ownership": reclaimed,
                },
            )
            self._emit("inference.ops.recovered", {"ok": True})
            if recovery.get("error"):
                self.open_incident(
                    "reservation_reconciliation_failed",
                    severity="high",
                    check_ids=["recover.reservations"],
                    safe_summary="Reservation recovery reported error",
                    recommended_action="Inspect governance store",
                )
            return {
                "ok": True,
                "recovery": recovery,
                "reclaimed_ownership": reclaimed,
                "phase": self.store.load().get("phase"),
            }

    # ── health / readiness / status ───────────────────────────────────────

    def health(self) -> HealthReport:
        st = self.store.load()
        phase = ServicePhase(st.get("phase") or "STOPPED") if st.get("phase") in ServicePhase.__members__ else ServicePhase.STOPPED
        checks = [
            CheckResult("ops.state_readable", True, "state store readable"),
            CheckResult(
                "ops.ownership_explicit",
                bool(st.get("owner_token")) or phase is ServicePhase.STOPPED,
                "owner token present or stopped",
            ),
            CheckResult(
                "ops.no_external_pid_claim",
                st.get("owns_external_provider_process") is False,
                "does not claim Ollama PID ownership",
            ),
        ]
        if phase is ServicePhase.STOPPED:
            status = HealthStatus.STOPPED
            detail = "ops service stopped"
        elif all(c.ok for c in checks):
            status = HealthStatus.HEALTHY
            detail = "ops process functioning"
        else:
            status = HealthStatus.UNHEALTHY
            detail = "ops process unhealthy"
        return HealthReport(
            status=status,
            phase=phase,
            detail=detail,
            checks=checks,
            ownership={
                "service_id": st.get("service_id"),
                "owner_token_present": bool(st.get("owner_token")),
                "owns_external_provider_process": False,
            },
        )

    def readiness(self) -> ReadinessReport:
        st = self.store.load()
        try:
            mode = RolloutMode(st.get("rollout_mode") or "OFF")
        except ValueError:
            mode = RolloutMode.OFF
        try:
            provider = ProviderOpsState(st.get("provider_state") or "UNKNOWN")
        except ValueError:
            provider = ProviderOpsState.UNKNOWN
        try:
            phase = ServicePhase(st.get("phase") or "STOPPED")
        except ValueError:
            phase = ServicePhase.STOPPED

        res = self.resource_probe()
        certified = bool(self.production_certified_probe())
        reachable = bool(self.provider_reachable_probe())
        models = bool(self.model_available_probe())
        circuit_open = bool(self.circuit_open_probe())
        gov_ok = bool(self.governance_ready_probe())

        checks: list[CheckResult] = []
        blockers: list[str] = []
        recs: list[str] = []

        def add(cid: str, ok: bool, detail: str, blocking: bool = True) -> None:
            checks.append(CheckResult(cid, ok, detail, blocking=blocking))
            if not ok and blocking:
                blockers.append(f"{cid}:{detail}")

        add("ops.phase_running", phase is ServicePhase.RUNNING, f"phase={phase.value}")
        add("rollout.mode_accepts_work", mode is RolloutMode.ACTIVE or mode is RolloutMode.CANARY, f"mode={mode.value}")
        if mode is RolloutMode.OFF:
            blockers.append("rollout.mode:OFF")
        if mode is RolloutMode.SHADOW:
            blockers.append("rollout.mode:SHADOW")
        if mode is RolloutMode.DRAINING or phase is ServicePhase.DRAINING:
            blockers.append("rollout.mode:DRAINING")
            add("rollout.not_draining", False, "draining")
        add("cert.production_certified", certified, "production_certified" if certified else "not_certified")
        add("provider.reachable", reachable, "reachable" if reachable else "unreachable")
        add("provider.model_available", models, "models_present" if models else "no_approved_model")
        add("resource.memory", res.memory_ok, f"avail={res.available_memory_gb:.2f} need={res.required_memory_gb:.2f}")
        add("resource.disk", res.disk_ok, f"free={res.free_disk_gb:.2f} min={self.min_disk_gb}", blocking=True)
        add("circuit.closed", not circuit_open, "open" if circuit_open else "closed")
        add("governance.store_ready", gov_ok, "ready" if gov_ok else "unavailable")
        add(
            "concurrency.capacity",
            int(st.get("active_requests") or 0) < int(st.get("max_concurrent") or self.max_concurrent),
            f"active={st.get('active_requests')} max={st.get('max_concurrent') or self.max_concurrent}",
        )
        cooldown = st.get("cooldown_until")
        in_cd = bool(cooldown and self.clock() < float(cooldown))
        add("provider.not_cooldown", not in_cd, "cooldown" if in_cd else "ok")

        # Historical cert package note (never erased by RAM)
        hist_path = Path(__file__).resolve().parents[3] / "docs" / "evidence" / "m25" / "LAST_SUCCESSFUL_LIVE_CERTIFICATION.json"
        hist_ok = hist_path.is_file()

        # Precedence: DRAINING > STOPPED/OFF/SHADOW policy > env > degraded > ready
        if mode is RolloutMode.DRAINING or phase is ServicePhase.DRAINING:
            status = ReadinessStatus.DRAINING
            if not any(b.startswith("rollout.mode:DRAINING") for b in blockers):
                blockers.append("rollout.mode:DRAINING")
            recs.append("Drain in progress; no new work")
        elif phase is ServicePhase.STOPPED:
            status = ReadinessStatus.POLICY_BLOCKED
            if "ops.phase:STOPPED" not in blockers:
                blockers.append("ops.phase:STOPPED")
        elif mode in (RolloutMode.OFF, RolloutMode.SHADOW):
            status = ReadinessStatus.POLICY_BLOCKED
        elif mode in (RolloutMode.ACTIVE, RolloutMode.CANARY) and not certified:
            status = ReadinessStatus.POLICY_BLOCKED
        elif not res.memory_ok or not models or not reachable or not res.disk_ok:
            status = ReadinessStatus.ENVIRONMENT_BLOCKED
            if not res.memory_ok:
                recs.append("Free memory or reduce load; historical certification preserved")
                self._emit("inference.resource.pressure", res.to_dict())
            if not reachable:
                recs.append("Start external Ollama (operator); SaathiOS does not own the process")
            if not models:
                recs.append("Install approved small model (operator); M26 does not pull models")
            if not res.disk_ok:
                recs.append("Free disk space (no automatic destructive cleanup)")
        elif circuit_open or in_cd:
            status = ReadinessStatus.DEGRADED
            recs.append("Wait for circuit cooldown")
        elif phase is ServicePhase.RUNNING and mode in (RolloutMode.ACTIVE, RolloutMode.CANARY) and all(
            c.ok for c in checks if c.blocking
        ):
            status = ReadinessStatus.READY
            blockers = []  # clean ready
        else:
            status = ReadinessStatus.DEGRADED

        ready = status is ReadinessStatus.READY

        if status is ReadinessStatus.READY:
            self._emit("inference.ops.ready", {"mode": mode.value})
        elif status is ReadinessStatus.DEGRADED:
            self._emit("inference.ops.degraded", {"blockers": blockers[:8]})

        # Certification package — separate from readiness
        cert_info = {
            "production_certified": certified,
            "historical_live_present": hist_ok,
            "package_evidence_dir": "docs/evidence/m25/cert",
            "note": "RAM pressure does not erase historical certification",
        }

        return ReadinessReport(
            status=status,
            ready=ready,
            production_certified=certified,
            rollout_mode=mode,
            provider_state=provider,
            checks=checks,
            blockers=blockers,
            recommendations=recs,
            resources=res.to_dict(),
            certification=cert_info,
        )

    def status(self) -> dict[str, Any]:
        st = self.store.load()
        h = self.health()
        r = self.readiness()
        incidents = [i for i in self.store.load_incidents() if i.get("state") == "open"]
        latest_incident = incidents[-1] if incidents else None
        # Dual live evidence pointers
        root = Path(__file__).resolve().parents[3]
        hist = root / "docs" / "evidence" / "m25" / "LAST_SUCCESSFUL_LIVE_CERTIFICATION.json"
        latest = root / "docs" / "evidence" / "m25" / "LATEST_ENVIRONMENT_OBSERVATION.json"
        return {
            "schema": SCHEMA,
            "milestone": "M26",
            "health": h.to_dict(),
            "readiness": r.to_dict(),
            "production_certification": r.production_certified,
            "current_readiness": r.status.value,
            "rollout_mode": st.get("rollout_mode"),
            "provider_state": st.get("provider_state"),
            "phase": st.get("phase"),
            "selected_model": r.resources.get("model_id"),
            "memory_headroom_gb": round(
                float(r.resources.get("available_memory_gb") or 0)
                - float(r.resources.get("required_memory_gb") or 0),
                3,
            ),
            "disk_headroom_gb": r.resources.get("free_disk_gb"),
            "active_requests": st.get("active_requests"),
            "queue_depth": st.get("queued_requests"),
            "max_concurrent": st.get("max_concurrent") or self.max_concurrent,
            "circuit_open": bool(self.circuit_open_probe()),
            "latest_incident": latest_incident,
            "last_successful_live_certification": str(hist.relative_to(root)) if hist.is_file() else "",
            "latest_environment_observation": str(latest.relative_to(root)) if latest.is_file() else "",
            "owns_external_provider_process": False,
            "idle_unload_enabled": bool(st.get("idle_unload_enabled")),
            "cloud_fallback": False,
            "trading_guardian": "UNCHANGED_UNENGAGED",
            "service_id": st.get("service_id"),
            "privacy_safe": True,
        }

    def optional_idle_unload(self, *, enabled_override: Optional[bool] = None) -> dict[str, Any]:
        """Policy-controlled idle unload — disabled by default; never deletes models."""
        st = self.store.load()
        enabled = bool(st.get("idle_unload_enabled")) if enabled_override is None else bool(enabled_override)
        if not enabled:
            return {
                "ok": False,
                "performed": False,
                "reason": "idle_unload_disabled_by_default",
                "model_deleted": False,
            }
        # Even when enabled, only record intent — do not shell out to delete
        self._emit(
            "inference.resource.pressure",
            {"action": "idle_unload_requested", "model_deleted": False},
        )
        return {
            "ok": True,
            "performed": False,
            "reason": "unload_is_operator_mediated_no_auto_delete",
            "model_deleted": False,
        }


# Module-level default service (tests inject their own)
_default_service: Optional[InferenceOpsService] = None
_default_lock = threading.Lock()


def get_ops_service(**kwargs: Any) -> InferenceOpsService:
    global _default_service
    with _default_lock:
        if kwargs:
            return InferenceOpsService(**kwargs)
        if _default_service is None:
            _default_service = InferenceOpsService()
        return _default_service


def reset_ops_service() -> None:
    global _default_service
    with _default_lock:
        _default_service = None
