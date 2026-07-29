"""Distributed Worker Execution and Fleet Runtime (M103–M111).

Extends M56 ClusterCoordinator — does not replace it, PlatformAgentRuntime,
ExecutionGateway, Approval Center, Evidence, or Agent Orchestration Runtime.

Authority flow:
  Validated Work Node → Orchestration → WorkerScheduler → Lease/fencing
  → PlatformAgentRuntime → ExecutionGateway → Approval when required
  → Evidence/Audit → Result reconciliation → Mission checkpoint

Phase A only: single-host multi-process / in-process workers over loopback.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import threading
from typing import Any

from saathi.platform.cluster import (
    CLUSTER_SCHEMA_VERSION,
    ClusterCoordinator,
    LOCAL_NODE_ID,
)
from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.fleet import limits
from saathi.platform.fleet.models import (
    AdmissionState,
    ArtifactClass,
    ExecutionEvent,
    ExecutionEventType,
    LeaseState,
    ReconciliationOutcome,
    ReconciliationRecord,
    SchedulingDecision,
    WorkerHealthState,
    WorkerHeartbeat,
    WorkerIdentity,
    WorkerTrustState,
    WorkLease,
    content_hash,
    now_ts,
)
from saathi.platform.models import PlatformPermission, new_id

# Config keys (platform store) — separate from m56_* but coordinated.
FLEET_WORKERS_KEY = "m103_fleet_workers"
FLEET_LEASES_KEY = "m103_fleet_leases"
FLEET_EVENTS_KEY = "m103_fleet_events"
FLEET_RESULTS_KEY = "m103_fleet_results"
FLEET_DECISIONS_KEY = "m103_fleet_decisions"
FLEET_METRICS_KEY = "m103_fleet_metrics"
FLEET_FENCING_KEY = "m103_fleet_fencing"
FLEET_DISPATCH_KEY = "m103_fleet_dispatch"
FLEET_RECOVERY_KEY = "m103_fleet_recovery"
FLEET_SCHEMA = "m103.fleet.v1"


class DistributedWorkerRuntime:
    """Worker control plane + distributed execution coordination.

    Composes M56 ClusterCoordinator for foundational registry/lease surfaces.
    All tool execution still routes through PlatformAgentRuntime → ExecutionGateway.
    """

    def __init__(self, platform=None, cluster: ClusterCoordinator | None = None):
        if platform is None:
            from saathi.platform.service import default_platform

            platform = default_platform()
        self.platform = platform
        self.store = platform.store
        self.cluster = cluster or ClusterCoordinator(platform)
        self._lock = threading.RLock()

    # ── permissions ──────────────────────────────────────────────────────
    def read_ctx(self, token: str) -> PlatformExecutionContext:
        ctx = self.platform.require_context(token)
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        return ctx

    def operate_ctx(self, token: str) -> PlatformExecutionContext:
        ctx = self.platform.require_context(token)
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        return ctx

    def _read(self, ctx: PlatformExecutionContext) -> None:
        ctx.require_permission(PlatformPermission.RUNTIME_READ)

    def _operate(self, ctx: PlatformExecutionContext) -> None:
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)

    def _audit(self, ctx, event: str, *, outcome: str = "OK", detail: dict | None = None) -> None:
        self.platform._audit(event, ctx, outcome=outcome, detail=detail or {})

    # ── persistence ──────────────────────────────────────────────────────
    def _workers(self) -> dict[str, dict]:
        return dict(self.store.get_config(FLEET_WORKERS_KEY, {}) or {})

    def _save_workers(self, workers: dict, actor: str = "m103") -> None:
        self.store.set_config(FLEET_WORKERS_KEY, workers, updated_by=actor)

    def _leases(self) -> dict[str, dict]:
        return dict(self.store.get_config(FLEET_LEASES_KEY, {}) or {})

    def _save_leases(self, leases: dict, actor: str = "m103") -> None:
        self.store.set_config(FLEET_LEASES_KEY, leases, updated_by=actor)

    def _events(self) -> list[dict]:
        return list(self.store.get_config(FLEET_EVENTS_KEY, []) or [])

    def _save_events(self, events: list, actor: str = "m103") -> None:
        # Retain bounded history
        self.store.set_config(
            FLEET_EVENTS_KEY, events[-limits.MAX_RETAINED_EVENTS :], updated_by=actor
        )

    def _results(self) -> dict[str, dict]:
        return dict(self.store.get_config(FLEET_RESULTS_KEY, {}) or {})

    def _save_results(self, results: dict, actor: str = "m103") -> None:
        self.store.set_config(FLEET_RESULTS_KEY, results, updated_by=actor)

    def _decisions(self) -> list[dict]:
        return list(self.store.get_config(FLEET_DECISIONS_KEY, []) or [])

    def _save_decision(self, decision: SchedulingDecision) -> None:
        items = self._decisions()
        items.append(decision.to_public())
        self.store.set_config(
            FLEET_DECISIONS_KEY, items[-limits.MAX_RETAINED_EVENTS :], updated_by="m103"
        )

    def _metrics(self) -> dict[str, Any]:
        return dict(self.store.get_config(FLEET_METRICS_KEY, {}) or {})

    def _bump_metric(self, key: str, n: int = 1) -> None:
        m = self._metrics()
        m[key] = int(m.get(key, 0) or 0) + n
        self.store.set_config(FLEET_METRICS_KEY, m, updated_by="m103")

    def _next_fencing_token(self) -> int:
        with self._lock:
            cur = int(self.store.get_config(FLEET_FENCING_KEY, 0) or 0) + 1
            self.store.set_config(FLEET_FENCING_KEY, cur, updated_by="m103-fence")
            return cur

    def _dispatch_state(self) -> dict[str, Any]:
        return dict(self.store.get_config(FLEET_DISPATCH_KEY, {}) or {})

    def _save_dispatch(self, state: dict) -> None:
        self.store.set_config(FLEET_DISPATCH_KEY, state, updated_by="m103")

    # ── health ───────────────────────────────────────────────────────────
    def health(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._read(ctx)
        workers = [
            WorkerIdentity.from_dict(w)
            for w in self._workers().values()
            if w.get("org_id") == ctx.org_id and w.get("workspace_id") == ctx.workspace_id
        ]
        # Also accept workers scoped empty (test local) when same session
        if not workers:
            workers = [
                WorkerIdentity.from_dict(w)
                for w in self._workers().values()
                if not w.get("org_id") or w.get("org_id") == ctx.org_id
            ]
        now = now_ts()
        for w in workers:
            self._refresh_health(w, now)
        by_trust: dict[str, int] = {}
        by_health: dict[str, int] = {}
        for w in workers:
            by_trust[w.trust_state] = by_trust.get(w.trust_state, 0) + 1
            by_health[w.health_state] = by_health.get(w.health_state, 0) + 1
        leases = [
            WorkLease.from_dict(l)
            for l in self._leases().values()
            if l.get("org_id") == ctx.org_id and l.get("workspace_id") == ctx.workspace_id
        ]
        active = [l for l in leases if l.is_active(now)]
        metrics = self._metrics()
        return {
            "schema_version": FLEET_SCHEMA,
            "extends": "M56_ClusterCoordinator",
            "phase": limits.PHASE_A_SINGLE_HOST,
            "authorized_phases": sorted(limits.AUTHORIZED_PHASES),
            "production_authorized": False,
            "lan_authorized": False,
            "cloud_authorized": False,
            "public_listener": False,
            "transport": "loopback_only",
            "protocol_version": limits.PROTOCOL_VERSION,
            "runtime_version": limits.RUNTIME_VERSION,
            "m56_schema": CLUSTER_SCHEMA_VERSION,
            "registered_workers": len(workers),
            "trust_counts": by_trust,
            "health_counts": by_health,
            "active_leases": len(active),
            "total_leases": len(leases),
            "dispatch_paused": bool(self._dispatch_state().get("paused", False)),
            "resource_limits": {
                "max_active_workers": limits.MAX_ACTIVE_WORKERS,
                "max_active_leases": limits.MAX_ACTIVE_LEASES,
                "max_concurrent_model_jobs": limits.MAX_CONCURRENT_MODEL_JOBS,
                "max_concurrent_browser_jobs": limits.MAX_CONCURRENT_BROWSER_JOBS,
                "lease_ttl_sec": limits.DEFAULT_LEASE_TTL_SEC,
                "heartbeat_timeout_sec": limits.HEARTBEAT_TIMEOUT_SEC,
            },
            "metrics": metrics,
            "execution_authority": "PlatformAgentRuntime→ExecutionGateway",
            "direct_tool_execution": False,
            "trading_guardian": "UNCHANGED",
        }

    def _refresh_health(self, w: WorkerIdentity, now: float) -> None:
        if w.trust_state in (
            WorkerTrustState.REVOKED.value,
            WorkerTrustState.QUARANTINED.value,
        ):
            w.health_state = (
                WorkerHealthState.QUARANTINED.value
                if w.trust_state == WorkerTrustState.QUARANTINED.value
                else WorkerHealthState.OFFLINE.value
            )
            return
        if w.trust_state == WorkerTrustState.DRAINING.value:
            w.health_state = WorkerHealthState.DRAINING.value
            return
        if w.admission_state != AdmissionState.ADMITTED.value:
            if w.last_heartbeat and (now - w.last_heartbeat) > limits.HEARTBEAT_TIMEOUT_SEC:
                w.health_state = WorkerHealthState.STALE.value
            return
        if not w.last_heartbeat:
            w.health_state = WorkerHealthState.OFFLINE.value
            return
        age = now - w.last_heartbeat
        if age > limits.HEARTBEAT_TIMEOUT_SEC * 3:
            w.health_state = WorkerHealthState.OFFLINE.value
            if w.trust_state == WorkerTrustState.TRUSTED_LOCAL.value:
                w.trust_state = WorkerTrustState.OFFLINE.value
        elif age > limits.HEARTBEAT_TIMEOUT_SEC:
            w.health_state = WorkerHealthState.STALE.value
            if w.trust_state == WorkerTrustState.TRUSTED_LOCAL.value:
                w.trust_state = WorkerTrustState.UNHEALTHY.value
        elif w.health_state not in (
            WorkerHealthState.HEALTHY.value,
            WorkerHealthState.DEGRADED.value,
        ):
            w.health_state = WorkerHealthState.HEALTHY.value

    # ── registration & admission (M103) ──────────────────────────────────
    def register_worker(
        self, ctx: PlatformExecutionContext, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Register a worker and run deterministic admission. No lease until admitted."""
        self._operate(ctx)
        with self._lock:
            worker_id = str(payload.get("worker_id") or "").strip() or new_id("wrk_")
            reported_caps = [
                str(c).strip()
                for c in (payload.get("capability_set") or payload.get("capabilities") or [])
                if str(c).strip()
            ]
            bind_host = str(payload.get("bind_host") or "127.0.0.1").strip()
            process_instance_id = str(
                payload.get("process_instance_id") or new_id("proc_")
            )
            now = now_ts()
            identity = WorkerIdentity(
                worker_id=worker_id,
                node_id=str(payload.get("node_id") or LOCAL_NODE_ID),
                runtime_version=str(
                    payload.get("runtime_version") or limits.RUNTIME_VERSION
                ),
                protocol_version=str(
                    payload.get("protocol_version") or limits.PROTOCOL_VERSION
                ),
                process_instance_id=process_instance_id,
                startup_timestamp=float(payload.get("startup_timestamp") or now),
                platform=str(payload.get("platform") or "darwin"),
                architecture=str(payload.get("architecture") or "arm64"),
                capability_set=sorted(set(reported_caps)),
                resource_limits=dict(payload.get("resource_limits") or {}),
                workspace_eligibility=list(
                    payload.get("workspace_eligibility") or [ctx.workspace_id]
                ),
                tenant_eligibility=list(
                    payload.get("tenant_eligibility") or [ctx.org_id]
                ),
                trust_state=WorkerTrustState.PENDING_ADMISSION.value,
                health_state=WorkerHealthState.HEALTHY.value,
                admission_state=AdmissionState.PENDING.value,
                last_heartbeat=now,
                bind_host=bind_host,
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                labels=dict(payload.get("labels") or {}),
                created_at=now,
                updated_at=now,
            )
            workers = self._workers()
            # Duplicate identity / stale process detection
            existing = workers.get(worker_id)
            if existing:
                prev = WorkerIdentity.from_dict(existing)
                if prev.trust_state == WorkerTrustState.REVOKED.value:
                    raise PlatformContextError(
                        "WORKER_REVOKED", "revoked worker cannot re-register"
                    )
                if (
                    prev.process_instance_id
                    and prev.process_instance_id != process_instance_id
                    and prev.trust_state
                    in (
                        WorkerTrustState.TRUSTED_LOCAL.value,
                        WorkerTrustState.PENDING_ADMISSION.value,
                    )
                    and (now - prev.last_heartbeat) < limits.HEARTBEAT_TIMEOUT_SEC
                ):
                    # Live duplicate identity — quarantine both
                    identity.trust_state = WorkerTrustState.QUARANTINED.value
                    identity.admission_state = AdmissionState.REJECTED.value
                    identity.quarantine_reason = "duplicate_identity_live_process"
                    identity.admission_reasons = ["duplicate_identity"]
                    workers[worker_id] = identity.to_public()
                    self._save_workers(workers)
                    self._audit(
                        ctx,
                        "fleet.worker_quarantined",
                        outcome="DUPLICATE",
                        detail={"worker_id": worker_id},
                    )
                    self._bump_metric("quarantine_events")
                    raise PlatformContextError(
                        "DUPLICATE_WORKER_IDENTITY",
                        "duplicate worker identity while prior process still live",
                    )

            decision = self.admit_worker(ctx, identity, payload)
            workers[worker_id] = identity.to_public()
            self._save_workers(workers)

            # Mirror registration into M56 registry for topology continuity
            try:
                self.cluster.register_worker(
                    ctx,
                    worker_id=worker_id,
                    node_id=identity.node_id,
                    capabilities=identity.capability_set,
                )
            except PlatformContextError:
                # M56 may already have the worker; non-fatal for fleet path
                pass

            self._audit(
                ctx,
                "fleet.worker_registered",
                outcome=identity.admission_state,
                detail={
                    "worker_id": worker_id,
                    "trust_state": identity.trust_state,
                    "admitted": decision["admitted"],
                    "reasons": decision["reasons"],
                },
            )
            self._bump_metric("registrations")
            return {
                "worker": identity.to_public(),
                "admission": decision,
            }

    def admit_worker(
        self,
        ctx: PlatformExecutionContext,
        identity: WorkerIdentity,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Deterministic admission checks. Mutates identity in place."""
        payload = payload or {}
        reasons: list[str] = []
        ok = True

        # Protocol / runtime
        if identity.protocol_version != limits.PROTOCOL_VERSION:
            ok = False
            reasons.append(f"protocol_mismatch:{identity.protocol_version}")
        if not identity.runtime_version.startswith("m103.") and identity.runtime_version != limits.RUNTIME_VERSION:
            # Allow exact RUNTIME_VERSION or m103.* prefix
            if identity.runtime_version != CLUSTER_SCHEMA_VERSION:
                ok = False
                reasons.append(f"runtime_version_mismatch:{identity.runtime_version}")

        # Capabilities
        caps = set(identity.capability_set)
        if caps & limits.FORBIDDEN_CAPABILITIES:
            ok = False
            reasons.append(
                "forbidden_capabilities:" + ",".join(sorted(caps & limits.FORBIDDEN_CAPABILITIES))
            )
        unknown = caps - limits.KNOWN_CAPABILITIES
        if unknown:
            ok = False
            reasons.append("unknown_capabilities:" + ",".join(sorted(unknown)))
        if not caps:
            ok = False
            reasons.append("empty_capability_set")

        # Resource bounds
        rl = identity.resource_limits or {}
        max_leases = int(rl.get("max_active_leases", 2) or 2)
        if max_leases > limits.MAX_ACTIVE_LEASES:
            ok = False
            reasons.append("resource_limits_exceed_fleet")

        # Loopback-only for Phase A certification
        if identity.bind_host not in limits.LOOPBACK_HOSTS:
            ok = False
            reasons.append(f"non_loopback_bind:{identity.bind_host}")
        if payload.get("public_listener") or payload.get("listen_host") not in (
            None,
            "",
            "127.0.0.1",
            "localhost",
            "::1",
        ):
            if payload.get("public_listener") or (
                payload.get("listen_host")
                and payload.get("listen_host") not in limits.LOOPBACK_HOSTS
            ):
                ok = False
                reasons.append("public_listener_forbidden")

        # Forbidden credentials / unauthorized tools
        if payload.get("credentials") or payload.get("secrets"):
            ok = False
            reasons.append("credentials_forbidden")
        tools = set(payload.get("unauthorized_tools") or [])
        if tools:
            ok = False
            reasons.append("unauthorized_tools")
        if payload.get("shell_transport"):
            ok = False
            reasons.append("shell_transport_forbidden")

        # Tenant / workspace
        if ctx.org_id and identity.tenant_eligibility:
            if ctx.org_id not in identity.tenant_eligibility and "*" not in identity.tenant_eligibility:
                ok = False
                reasons.append("tenant_not_eligible")
        if ctx.workspace_id and identity.workspace_eligibility:
            if (
                ctx.workspace_id not in identity.workspace_eligibility
                and "*" not in identity.workspace_eligibility
            ):
                ok = False
                reasons.append("workspace_not_eligible")

        # Active worker cap
        trusted = [
            w
            for w in self._workers().values()
            if w.get("trust_state") == WorkerTrustState.TRUSTED_LOCAL.value
            and w.get("worker_id") != identity.worker_id
        ]
        if len(trusted) >= limits.MAX_ACTIVE_WORKERS:
            ok = False
            reasons.append("max_active_workers")

        # Safe environment
        if payload.get("phase") and payload.get("phase") not in limits.AUTHORIZED_PHASES:
            ok = False
            reasons.append("phase_not_authorized")

        # Health check success required
        if payload.get("health_check_failed"):
            ok = False
            reasons.append("health_check_failed")

        if ok:
            identity.admission_state = AdmissionState.ADMITTED.value
            identity.trust_state = WorkerTrustState.TRUSTED_LOCAL.value
            identity.health_state = WorkerHealthState.HEALTHY.value
            identity.admission_reasons = ["all_checks_passed"]
            reasons = ["all_checks_passed"]
        else:
            identity.admission_state = AdmissionState.REJECTED.value
            identity.trust_state = WorkerTrustState.QUARANTINED.value
            identity.health_state = WorkerHealthState.QUARANTINED.value
            identity.quarantine_reason = ";".join(reasons)
            identity.admission_reasons = reasons

        return {
            "admitted": ok,
            "reasons": reasons,
            "trust_state": identity.trust_state,
            "admission_state": identity.admission_state,
        }

    def list_workers(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._read(ctx)
        now = now_ts()
        out = []
        workers = self._workers()
        changed = False
        for wid, raw in workers.items():
            if raw.get("org_id") and raw.get("org_id") != ctx.org_id:
                continue
            if raw.get("workspace_id") and raw.get("workspace_id") != ctx.workspace_id:
                continue
            w = WorkerIdentity.from_dict(raw)
            prev_health = w.health_state
            prev_trust = w.trust_state
            self._refresh_health(w, now)
            if w.health_state != prev_health or w.trust_state != prev_trust:
                workers[wid] = w.to_public()
                changed = True
            out.append(w.to_public())
        if changed:
            self._save_workers(workers)
        out.sort(key=lambda x: x["worker_id"])
        return {"workers": out, "count": len(out)}

    def get_worker(self, ctx: PlatformExecutionContext, worker_id: str) -> dict[str, Any]:
        self._read(ctx)
        raw = self._workers().get(worker_id)
        if not raw:
            raise PlatformContextError("WORKER_NOT_FOUND", "unknown worker")
        if raw.get("org_id") and raw.get("org_id") != ctx.org_id:
            raise PlatformContextError("WORKER_NOT_FOUND", "worker not in tenant")
        if raw.get("workspace_id") and raw.get("workspace_id") != ctx.workspace_id:
            raise PlatformContextError("WORKER_NOT_FOUND", "worker not in workspace")
        w = WorkerIdentity.from_dict(raw)
        self._refresh_health(w, now_ts())
        leases = [
            WorkLease.from_dict(l).to_public()
            for l in self._leases().values()
            if l.get("worker_id") == worker_id
            and l.get("org_id") == ctx.org_id
        ]
        return {"worker": w.to_public(), "leases": leases}

    # ── heartbeats (M105) ────────────────────────────────────────────────
    def heartbeat(
        self, ctx: PlatformExecutionContext, worker_id: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self._operate(ctx)
        payload = payload or {}
        raw_size = len(json.dumps(payload, default=str).encode("utf-8"))
        if raw_size > limits.MAX_HEARTBEAT_PAYLOAD_BYTES:
            raise PlatformContextError("HEARTBEAT_TOO_LARGE", "heartbeat exceeds size limit")
        # Strip secrets-like keys
        for banned in ("secrets", "credentials", "password", "token", "prompt", "audio", "env"):
            if banned in payload:
                raise PlatformContextError(
                    "HEARTBEAT_FORBIDDEN_FIELD", f"heartbeat must not include {banned}"
                )
        workers = self._workers()
        if worker_id not in workers:
            raise PlatformContextError("WORKER_NOT_FOUND", "unknown worker")
        w = WorkerIdentity.from_dict(workers[worker_id])
        if w.org_id and w.org_id != ctx.org_id:
            raise PlatformContextError("WORKER_NOT_FOUND", "worker not in tenant")
        if w.trust_state == WorkerTrustState.REVOKED.value:
            raise PlatformContextError("WORKER_REVOKED", "revoked worker")
        now = now_ts()
        w.last_heartbeat = now
        w.updated_at = now
        w.active_lease_count = int(payload.get("active_leases", w.active_lease_count) or 0)
        cpu = float(payload.get("cpu_pressure", 0) or 0)
        mem = float(payload.get("memory_pressure", 0) or 0)
        if w.trust_state == WorkerTrustState.DRAINING.value:
            w.health_state = WorkerHealthState.DRAINING.value
        elif cpu >= limits.CPU_PRESSURE_PAUSE or mem >= limits.MEMORY_PRESSURE_PAUSE:
            w.health_state = WorkerHealthState.DEGRADED.value
        elif w.trust_state == WorkerTrustState.TRUSTED_LOCAL.value:
            w.health_state = WorkerHealthState.HEALTHY.value
        elif w.trust_state == WorkerTrustState.QUARANTINED.value:
            w.health_state = WorkerHealthState.QUARANTINED.value
        workers[worker_id] = w.to_public()
        self._save_workers(workers)
        # Mirror M56 heartbeat
        try:
            self.cluster.heartbeat(ctx, worker_id=worker_id)
        except PlatformContextError:
            pass
        hb = WorkerHeartbeat(
            worker_id=worker_id,
            at=now,
            protocol_version=str(payload.get("protocol_version") or limits.PROTOCOL_VERSION),
            active_leases=w.active_lease_count,
            queue_depth=int(payload.get("queue_depth", 0) or 0),
            cpu_pressure=cpu,
            memory_pressure=mem,
            disk_pressure=float(payload.get("disk_pressure", 0) or 0),
            model_status=str(payload.get("model_status") or "unavailable"),
            browser_availability=bool(payload.get("browser_availability", False)),
            error_state=str(payload.get("error_state") or ""),
            last_successful_action=str(payload.get("last_successful_action") or ""),
            sequence=int(payload.get("sequence", 0) or 0),
        )
        self._bump_metric("heartbeats")
        return {"heartbeat": hb.to_public(), "worker": w.to_public()}

    # ── matching & scheduling (M104) ─────────────────────────────────────
    def match_worker(
        self,
        ctx: PlatformExecutionContext,
        work_node: dict[str, Any],
        *,
        seed: str = "",
    ) -> SchedulingDecision:
        """Deterministic worker matching. Model recommendations are not authoritative."""
        self._read(ctx)
        now = now_ts()
        required_caps = set(
            work_node.get("required_capabilities")
            or work_node.get("capabilities")
            or []
        )
        role = str(work_node.get("role") or work_node.get("agent_type") or "")
        risk = str(work_node.get("risk_classification") or work_node.get("risk_level") or "low")
        approval_state = str(work_node.get("approval_state") or "not_required")
        tenant = str(work_node.get("org_id") or ctx.org_id)
        workspace = str(work_node.get("workspace_id") or ctx.workspace_id)
        work_node_id = str(work_node.get("work_node_id") or work_node.get("id") or "")
        anti_affinity = set(work_node.get("anti_affinity_workers") or [])
        preferred = list(work_node.get("affinity_workers") or [])
        prior_failures = set(work_node.get("prior_failure_workers") or [])
        needs_browser = "browser" in required_caps
        needs_model = "local_model_inference" in required_caps
        needs_mutation = "approved_mutation" in required_caps

        decision = SchedulingDecision(
            work_node_id=work_node_id,
            at=now,
            seed=seed or work_node_id,
            authority_checks=[],
            resource_checks=[],
        )

        if self._dispatch_state().get("paused"):
            decision.reason = "dispatch_paused"
            decision.lease_result = "NOT_ATTEMPTED"
            self._save_decision(decision)
            return decision

        if approval_state in ("required", "pending", "WAITING_APPROVAL"):
            decision.reason = "approval_pending"
            decision.authority_checks.append("approval_not_granted")
            decision.lease_result = "BLOCKED_APPROVAL"
            self._save_decision(decision)
            return decision

        if approval_state == "denied":
            decision.reason = "approval_denied"
            decision.authority_checks.append("approval_denied")
            decision.lease_result = "BLOCKED_APPROVAL"
            self._save_decision(decision)
            return decision

        decision.authority_checks.append("approval_ok")

        # Dependency completion
        deps = work_node.get("depends_on") or work_node.get("dependencies") or []
        incomplete = work_node.get("incomplete_dependencies") or []
        if incomplete or work_node.get("dependencies_complete") is False:
            decision.reason = "dependencies_incomplete"
            decision.lease_result = "BLOCKED_DEPENDENCY"
            self._save_decision(decision)
            return decision
        if deps and work_node.get("dependencies_complete") is not True and incomplete is None:
            # If depends_on present without explicit complete flag, require flag
            if work_node.get("dependencies_complete") is not True:
                # Treat as complete only if empty deps already handled; non-empty needs flag
                if deps:
                    decision.reason = "dependencies_incomplete"
                    decision.lease_result = "BLOCKED_DEPENDENCY"
                    self._save_decision(decision)
                    return decision

        workers = []
        for raw in self._workers().values():
            w = WorkerIdentity.from_dict(raw)
            self._refresh_health(w, now)
            workers.append(w)

        candidates: list[WorkerIdentity] = []
        for w in workers:
            reject_reason = None
            if w.org_id and w.org_id != tenant:
                reject_reason = "tenant_mismatch"
            elif w.workspace_id and w.workspace_id != workspace:
                reject_reason = "workspace_mismatch"
            elif w.trust_state not in (
                WorkerTrustState.TRUSTED_LOCAL.value,
            ):
                reject_reason = f"trust:{w.trust_state}"
            elif w.admission_state != AdmissionState.ADMITTED.value:
                reject_reason = f"admission:{w.admission_state}"
            elif w.health_state not in (
                WorkerHealthState.HEALTHY.value,
                WorkerHealthState.DEGRADED.value,
            ):
                reject_reason = f"health:{w.health_state}"
            elif w.trust_state == WorkerTrustState.DRAINING.value or w.health_state == WorkerHealthState.DRAINING.value:
                reject_reason = "draining"
            elif w.worker_id in anti_affinity:
                reject_reason = "anti_affinity"
            elif required_caps and not required_caps.issubset(set(w.capability_set)):
                reject_reason = "missing_capabilities"
            elif w.active_lease_count >= int(
                (w.resource_limits or {}).get("max_active_leases", 2) or 2
            ):
                reject_reason = "workload_full"
                decision.resource_checks.append(f"{w.worker_id}:workload_full")
            elif needs_browser and not (w.resource_limits or {}).get("allow_browser", True):
                # default allow if not specified for testing workers with browser cap
                if "browser" not in w.capability_set:
                    reject_reason = "browser_unavailable"
            elif needs_model and "local_model_inference" not in w.capability_set:
                reject_reason = "model_unavailable"
            elif needs_mutation and "approved_mutation" not in w.capability_set:
                reject_reason = "mutation_not_allowed"
            elif w.worker_id in prior_failures and len(prior_failures) < len(
                [x for x in workers if x.trust_state == WorkerTrustState.TRUSTED_LOCAL.value]
            ):
                # Prefer workers without prior failure when alternatives exist
                reject_reason = "prior_failure_preference"

            if reject_reason:
                decision.rejected.append(
                    {"worker_id": w.worker_id, "reason": reject_reason}
                )
            else:
                candidates.append(w)
                decision.candidates.append(
                    {
                        "worker_id": w.worker_id,
                        "capabilities": sorted(w.capability_set),
                        "active_leases": w.active_lease_count,
                        "health": w.health_state,
                    }
                )

        if not candidates:
            # Retry without prior_failure preference
            retry = [
                WorkerIdentity.from_dict(self._workers()[r["worker_id"]])
                for r in decision.rejected
                if r["reason"] == "prior_failure_preference"
                and r["worker_id"] in self._workers()
            ]
            # re-check eligibility for prior-failure workers only
            for w in list(retry):
                if (
                    w.trust_state == WorkerTrustState.TRUSTED_LOCAL.value
                    and w.health_state
                    in (WorkerHealthState.HEALTHY.value, WorkerHealthState.DEGRADED.value)
                    and (not required_caps or required_caps.issubset(set(w.capability_set)))
                ):
                    candidates.append(w)
                    decision.candidates.append(
                        {
                            "worker_id": w.worker_id,
                            "capabilities": sorted(w.capability_set),
                            "active_leases": w.active_lease_count,
                            "health": w.health_state,
                            "note": "prior_failure_fallback",
                        }
                    )
                    decision.rejected = [
                        r
                        for r in decision.rejected
                        if not (
                            r["worker_id"] == w.worker_id
                            and r["reason"] == "prior_failure_preference"
                        )
                    ]

        if not candidates:
            decision.reason = "no_eligible_worker"
            decision.lease_result = "NO_MATCH"
            self._save_decision(decision)
            return decision

        # Separation of duties: reviewer/implementer anti-pairing if provided
        sod_exclude = set(work_node.get("sod_exclude_workers") or [])
        if sod_exclude:
            filtered = [c for c in candidates if c.worker_id not in sod_exclude]
            if filtered:
                for c in candidates:
                    if c.worker_id in sod_exclude:
                        decision.rejected.append(
                            {"worker_id": c.worker_id, "reason": "separation_of_duties"}
                        )
                candidates = filtered
                decision.authority_checks.append("sod_enforced")

        # Resource-aware sort: fewer active leases, then preferred affinity, then id
        def sort_key(w: WorkerIdentity):
            pref = 0 if w.worker_id in preferred else 1
            return (w.active_lease_count, pref, w.worker_id)

        candidates.sort(key=sort_key)
        selected = candidates[0]
        decision.selected_worker_id = selected.worker_id
        decision.tie_breaking_rule = "active_leases_asc,affinity,lexicographic_worker_id"
        decision.reason = "matched"
        decision.resource_checks.append(
            f"selected_load={selected.active_lease_count}"
        )
        decision.lease_result = "READY"
        # Role eligibility note
        if role:
            decision.authority_checks.append(f"role_requested:{role}")
        if risk:
            decision.authority_checks.append(f"risk:{risk}")
        self._save_decision(decision)
        self._bump_metric("match_decisions")
        return decision

    def explain_schedule(
        self, ctx: PlatformExecutionContext, work_node_id: str = ""
    ) -> dict[str, Any]:
        self._read(ctx)
        items = self._decisions()
        if work_node_id:
            items = [d for d in items if d.get("work_node_id") == work_node_id]
        return {"decisions": items[-50:], "count": len(items)}

    # ── leases & fencing (M105) ──────────────────────────────────────────
    def acquire_lease(
        self,
        ctx: PlatformExecutionContext,
        *,
        work_node: dict[str, Any],
        worker_id: str = "",
        ttl_sec: float | None = None,
        approval_reference: str = "",
        mission_id: str = "",
        orchestration_id: str = "",
        plan_version: str = "",
        m56_execution_id: str = "",
    ) -> dict[str, Any]:
        """Atomic lease acquisition with fencing. Approvals checked before issue."""
        self._operate(ctx)
        with self._lock:
            now = now_ts()
            work_node_id = str(
                work_node.get("work_node_id") or work_node.get("id") or ""
            )
            if not work_node_id:
                raise PlatformContextError("VALIDATION_FAILED", "work_node_id required")

            approval_state = str(
                work_node.get("approval_state")
                or ("granted" if approval_reference else "not_required")
            )
            if work_node.get("approval_required") and not approval_reference:
                if approval_state not in ("granted", "not_required", "approved"):
                    raise PlatformContextError(
                        "APPROVAL_REQUIRED",
                        "approval must be granted before lease issuance",
                    )
            if approval_state in ("required", "pending", "WAITING_APPROVAL", "denied"):
                raise PlatformContextError(
                    "APPROVAL_REQUIRED",
                    "approval must be granted before lease issuance",
                )

            # One active lease per exclusive work node
            leases = self._leases()
            for lid, raw in leases.items():
                rec = WorkLease.from_dict(raw)
                if (
                    rec.work_node_id == work_node_id
                    and rec.is_active(now)
                    and rec.org_id == ctx.org_id
                ):
                    raise PlatformContextError(
                        "LEASE_ALREADY_HELD",
                        f"work node already leased to {rec.worker_id}",
                    )

            # Match if worker not forced
            node_for_match = dict(work_node)
            node_for_match["approval_state"] = (
                "granted" if approval_reference or approval_state in ("granted", "approved", "not_required") else approval_state
            )
            node_for_match["dependencies_complete"] = work_node.get(
                "dependencies_complete", True
            )
            decision = self.match_worker(ctx, node_for_match)
            if worker_id:
                if decision.selected_worker_id and worker_id != decision.selected_worker_id:
                    # Forced worker must still be eligible
                    eligible_ids = {c["worker_id"] for c in decision.candidates}
                    if worker_id not in eligible_ids and decision.selected_worker_id:
                        # Re-check forced worker alone
                        forced_node = dict(node_for_match)
                        forced_node["affinity_workers"] = [worker_id]
                        decision2 = self.match_worker(ctx, forced_node)
                        if worker_id != decision2.selected_worker_id:
                            raise PlatformContextError(
                                "WORKER_NOT_ELIGIBLE",
                                "requested worker is not eligible for this node",
                            )
                selected = worker_id
            else:
                if decision.lease_result != "READY" or not decision.selected_worker_id:
                    raise PlatformContextError(
                        "NO_ELIGIBLE_WORKER",
                        decision.reason or "no eligible worker",
                    )
                selected = decision.selected_worker_id

            wraw = self._workers().get(selected)
            if not wraw:
                raise PlatformContextError("WORKER_NOT_FOUND", "unknown worker")
            worker = WorkerIdentity.from_dict(wraw)
            self._refresh_health(worker, now)
            if worker.trust_state != WorkerTrustState.TRUSTED_LOCAL.value:
                raise PlatformContextError(
                    "WORKER_NOT_TRUSTED", f"trust_state={worker.trust_state}"
                )
            if worker.health_state not in (
                WorkerHealthState.HEALTHY.value,
                WorkerHealthState.DEGRADED.value,
            ):
                raise PlatformContextError(
                    "WORKER_UNHEALTHY", f"health={worker.health_state}"
                )

            # Global active lease cap
            active_count = sum(
                1 for r in leases.values() if WorkLease.from_dict(r).is_active(now)
            )
            if active_count >= limits.MAX_ACTIVE_LEASES:
                raise PlatformContextError(
                    "LEASE_CAPACITY", "max active leases reached"
                )

            ttl = float(ttl_sec if ttl_sec is not None else limits.DEFAULT_LEASE_TTL_SEC)
            ttl = min(max(ttl, 1.0), limits.MAX_LEASE_TTL_SEC)
            fence = self._next_fencing_token()
            attempt = int(work_node.get("attempt") or 1)
            idem = str(
                work_node.get("idempotency_key")
                or f"{work_node_id}:{selected}:{attempt}:{fence}"
            )
            lease = WorkLease(
                lease_id=new_id("lease_"),
                work_node_id=work_node_id,
                mission_id=mission_id or str(work_node.get("mission_id") or ""),
                orchestration_id=orchestration_id
                or str(work_node.get("orchestration_id") or ""),
                worker_id=selected,
                attempt=attempt,
                issued_at=now,
                starts_at=now,
                expires_at=now + ttl,
                heartbeat_deadline=now + limits.HEARTBEAT_TIMEOUT_SEC,
                fencing_token=fence,
                idempotency_key=idem,
                authority_snapshot={
                    "org_id": ctx.org_id,
                    "workspace_id": ctx.workspace_id,
                    "user_id": ctx.user_id,
                    "role": ctx.role,
                    "approval_reference": approval_reference,
                    "approval_state": approval_state,
                    "production_authorized": False,
                    "execution_path": "PlatformAgentRuntime→ExecutionGateway",
                },
                approval_reference=approval_reference,
                state=LeaseState.HELD.value,
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                role=str(work_node.get("role") or ""),
                required_capabilities=list(
                    work_node.get("required_capabilities")
                    or work_node.get("capabilities")
                    or []
                ),
                plan_version=plan_version or str(work_node.get("plan_version") or "1"),
                resource_budget={
                    "timeout_sec": limits.PER_TASK_TIMEOUT_SEC,
                    "memory_mb": limits.PER_TASK_MEMORY_MB,
                },
                m56_execution_id=m56_execution_id,
            )
            leases[lease.lease_id] = lease.to_public()
            self._save_leases(leases)

            # Update worker active count
            workers = self._workers()
            ww = WorkerIdentity.from_dict(workers[selected])
            ww.active_lease_count = int(ww.active_lease_count) + 1
            workers[selected] = ww.to_public()
            self._save_workers(workers)

            # Optional M56 lease mirror when execution_id provided
            if m56_execution_id:
                try:
                    self.cluster.acquire_lease(
                        ctx, execution_id=m56_execution_id, worker_id=selected, ttl_sec=ttl
                    )
                except PlatformContextError:
                    pass

            decision.lease_result = "ISSUED"
            decision.selected_worker_id = selected
            self._save_decision(decision)
            self._audit(
                ctx,
                "fleet.lease_acquired",
                detail={
                    "lease_id": lease.lease_id,
                    "worker_id": selected,
                    "fencing_token": fence,
                    "work_node_id": work_node_id,
                },
            )
            self._bump_metric("leases_issued")
            return {
                "lease": lease.to_public(),
                "scheduling": decision.to_public(),
            }

    def renew_lease(
        self,
        ctx: PlatformExecutionContext,
        *,
        lease_id: str,
        worker_id: str,
        fencing_token: int,
        ttl_sec: float | None = None,
    ) -> dict[str, Any]:
        self._operate(ctx)
        with self._lock:
            leases = self._leases()
            if lease_id not in leases:
                raise PlatformContextError("LEASE_NOT_FOUND", "unknown lease")
            rec = WorkLease.from_dict(leases[lease_id])
            if rec.org_id != ctx.org_id or rec.workspace_id != ctx.workspace_id:
                raise PlatformContextError("LEASE_NOT_FOUND", "lease not in workspace")
            if rec.worker_id != worker_id:
                raise PlatformContextError("LEASE_OWNER_MISMATCH", "worker does not own lease")
            if rec.fencing_token != int(fencing_token):
                raise PlatformContextError("FENCING_MISMATCH", "stale fencing token")
            now = now_ts()
            if not rec.is_active(now):
                raise PlatformContextError("LEASE_EXPIRED", "cannot renew inactive lease")
            if rec.renewals >= limits.MAX_LEASE_RENEWALS:
                raise PlatformContextError("LEASE_RENEWAL_LIMIT", "max renewals reached")
            wraw = self._workers().get(worker_id)
            if not wraw:
                raise PlatformContextError("WORKER_NOT_FOUND", "unknown worker")
            worker = WorkerIdentity.from_dict(wraw)
            self._refresh_health(worker, now)
            if worker.health_state not in (
                WorkerHealthState.HEALTHY.value,
                WorkerHealthState.DEGRADED.value,
            ):
                raise PlatformContextError("WORKER_UNHEALTHY", "renewal denied")
            if worker.trust_state != WorkerTrustState.TRUSTED_LOCAL.value:
                raise PlatformContextError("WORKER_NOT_TRUSTED", "renewal denied")
            ttl = float(ttl_sec if ttl_sec is not None else limits.DEFAULT_LEASE_TTL_SEC)
            ttl = min(max(ttl, 1.0), limits.MAX_LEASE_TTL_SEC)
            rec.state = LeaseState.RENEWED.value
            rec.renewals += 1
            rec.expires_at = now + ttl
            rec.heartbeat_deadline = now + limits.HEARTBEAT_TIMEOUT_SEC
            leases[lease_id] = rec.to_public()
            self._save_leases(leases)
            self._bump_metric("leases_renewed")
            return {"lease": rec.to_public()}

    def verify_lease(
        self,
        ctx: PlatformExecutionContext,
        *,
        lease_id: str,
        worker_id: str = "",
        fencing_token: int | None = None,
    ) -> dict[str, Any]:
        self._read(ctx)
        leases = self._leases()
        if lease_id not in leases:
            return {"valid": False, "reason": "NO_LEASE"}
        rec = WorkLease.from_dict(leases[lease_id])
        if rec.org_id != ctx.org_id or rec.workspace_id != ctx.workspace_id:
            return {"valid": False, "reason": "OUT_OF_SCOPE"}
        now = now_ts()
        if worker_id and rec.worker_id != worker_id:
            return {"valid": False, "reason": "OWNER_MISMATCH", "lease": rec.to_public()}
        if fencing_token is not None and rec.fencing_token != int(fencing_token):
            return {"valid": False, "reason": "FENCING_MISMATCH", "lease": rec.to_public()}
        return {
            "valid": rec.is_active(now),
            "reason": "OK" if rec.is_active(now) else rec.state,
            "lease": rec.to_public(),
        }

    # ── execution contract (M106) — no direct tools ──────────────────────
    def build_execution_request(
        self, ctx: PlatformExecutionContext, lease_id: str
    ) -> dict[str, Any]:
        """Provider-neutral worker execution contract (references only)."""
        self._read(ctx)
        leases = self._leases()
        if lease_id not in leases:
            raise PlatformContextError("LEASE_NOT_FOUND", "unknown lease")
        rec = WorkLease.from_dict(leases[lease_id])
        if rec.org_id != ctx.org_id:
            raise PlatformContextError("LEASE_NOT_FOUND", "out of scope")
        return {
            "protocol_version": limits.PROTOCOL_VERSION,
            "mission_id": rec.mission_id,
            "plan_version": rec.plan_version,
            "work_node_id": rec.work_node_id,
            "lease_id": rec.lease_id,
            "fencing_token": rec.fencing_token,
            "role": rec.role,
            "capability_request": rec.required_capabilities,
            "authorized_context_reference": {
                "org_id": rec.org_id,
                "workspace_id": rec.workspace_id,
                "mission_id": rec.mission_id,
                "orchestration_id": rec.orchestration_id,
            },
            "approval_reference": rec.approval_reference,
            "timeout": rec.resource_budget.get("timeout_sec", limits.PER_TASK_TIMEOUT_SEC),
            "resource_budget": rec.resource_budget,
            "idempotency_key": rec.idempotency_key,
            "evidence_requirements": ["content_hash", "producer", "lease", "attempt"],
            "cancellation_token": f"cancel:{rec.lease_id}",
            "transport": "loopback_only",
            "bind_host": limits.ALLOWED_BIND_HOST,
            "direct_tool_execution": False,
            "execution_authority": "PlatformAgentRuntime→ExecutionGateway",
            "context_transfer_policy": "references_only",
            "forbidden_transfers": [
                "credentials",
                "raw_audio",
                "full_env",
                "unrestricted_repo",
                "hidden_system_prompts",
            ],
        }

    def execute_leased_work(
        self,
        ctx: PlatformExecutionContext,
        *,
        lease_id: str,
        worker_id: str,
        fencing_token: int,
        token: str = "",
        tool_id: str = "m49.echo_readonly",
        arguments: dict[str, Any] | None = None,
        agent_id: str = "",
        binding_id: str = "",
        binding_version: int = 0,
    ) -> dict[str, Any]:
        """Execute work ONLY through PlatformAgentRuntime → ExecutionGateway.

        Workers never call tools directly. Stale/expired/revoked leases fail closed.
        """
        self._operate(ctx)
        with self._lock:
            v = self.verify_lease(
                ctx, lease_id=lease_id, worker_id=worker_id, fencing_token=fencing_token
            )
            if not v.get("valid"):
                raise PlatformContextError(
                    "LEASE_INVALID", v.get("reason") or "lease not valid for execution"
                )
            rec = WorkLease.from_dict(v["lease"])
            if rec.cancellation_state in ("REQUESTED", "CANCELLED"):
                raise PlatformContextError("LEASE_CANCELLED", "lease cancelled")

            # Emit started event
            self._append_event(
                ctx,
                ExecutionEvent(
                    event_type=ExecutionEventType.STARTED.value,
                    worker_id=worker_id,
                    lease_id=lease_id,
                    fencing_token=fencing_token,
                    mission_id=rec.mission_id,
                    work_node_id=rec.work_node_id,
                    attempt=rec.attempt,
                    sequence=rec.last_event_seq + 1,
                    at=now_ts(),
                    org_id=ctx.org_id,
                    workspace_id=ctx.workspace_id,
                    payload={"tool_id": tool_id},
                ),
            )

            # Production / trading prohibition
            args = dict(arguments or {})
            if args.get("production") or args.get("live_trade"):
                raise PlatformContextError(
                    "PRODUCTION_PROHIBITED", "production and live trading forbidden"
                )

            # Route through PlatformAgentRuntime when binding provided;
            # otherwise record a deterministic bounded local result (test path)
            # that still cannot touch tools directly.
            result_payload: dict[str, Any]
            execution_path = "simulated_readonly_worker"
            if token and binding_id and agent_id:
                from saathi.platform.runtime import PlatformAgentRuntime

                runtime = PlatformAgentRuntime(self.platform)
                try:
                    result_payload = runtime.execute_token(
                        token=token,
                        tool_id=tool_id,
                        arguments=args,
                        capability="read",
                        agent_id=agent_id,
                        binding_id=binding_id,
                        binding_version=binding_version,
                        idempotency_key=rec.idempotency_key,
                    )
                    execution_path = "PlatformAgentRuntime→ExecutionGateway"
                except PlatformContextError as e:
                    # Approval-required tools surface as waiting — do not bypass
                    self._append_event(
                        ctx,
                        ExecutionEvent(
                            event_type=ExecutionEventType.WARNING.value,
                            worker_id=worker_id,
                            lease_id=lease_id,
                            fencing_token=fencing_token,
                            mission_id=rec.mission_id,
                            work_node_id=rec.work_node_id,
                            attempt=rec.attempt,
                            sequence=rec.last_event_seq + 2,
                            at=now_ts(),
                            org_id=ctx.org_id,
                            workspace_id=ctx.workspace_id,
                            payload={"error": e.code, "message": str(e)},
                        ),
                    )
                    raise
            else:
                # Deterministic local test worker result — no tool side effects
                result_payload = {
                    "status": "ok",
                    "echo": args.get("text") or args.get("message") or rec.work_node_id,
                    "work_node_id": rec.work_node_id,
                    "worker_id": worker_id,
                    "note": "bounded local worker result; tools only via ExecutionGateway when bound",
                }

            ch = content_hash(result_payload)
            artifact = {
                "class": ArtifactClass.TERMINAL_RESULT.value,
                "content_hash": ch,
                "producer_worker": worker_id,
                "lease_id": lease_id,
                "attempt": rec.attempt,
                "work_node_id": rec.work_node_id,
                "timestamp": now_ts(),
                "sensitivity": "operational",
                "size": len(json.dumps(result_payload, default=str)),
                "validation_status": "pending_reconciliation",
                "payload": result_payload,
                "execution_path": execution_path,
            }
            if artifact["size"] > limits.MAX_RESULT_BYTES:
                raise PlatformContextError("RESULT_TOO_LARGE", "result exceeds size limit")

            return {
                "artifact": artifact,
                "lease_id": lease_id,
                "fencing_token": fencing_token,
                "execution_path": execution_path,
                "direct_tool_execution": False,
            }

    def _append_event(self, ctx, event: ExecutionEvent) -> None:
        raw = json.dumps(event.payload, default=str).encode("utf-8")
        if len(raw) > limits.MAX_EVENT_PAYLOAD_BYTES:
            raise PlatformContextError("EVENT_TOO_LARGE", "event exceeds size limit")
        events = self._events()
        # Reject duplicates / out of order for same lease
        same = [e for e in events if e.get("lease_id") == event.lease_id]
        if same:
            last_seq = max(int(e.get("sequence", 0)) for e in same)
            if event.sequence <= last_seq:
                self._bump_metric("event_replay_rejected")
                raise PlatformContextError(
                    "EVENT_REPLAY", "duplicate or out-of-order event sequence"
                )
        events.append(event.to_public())
        self._save_events(events)
        leases = self._leases()
        if event.lease_id in leases:
            rec = WorkLease.from_dict(leases[event.lease_id])
            rec.last_event_seq = event.sequence
            leases[event.lease_id] = rec.to_public()
            self._save_leases(leases)

    def ingest_event(
        self, ctx: PlatformExecutionContext, event_payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Ingest streamed worker event with validation."""
        self._operate(ctx)
        lease_id = str(event_payload.get("lease_id") or "")
        worker_id = str(event_payload.get("worker_id") or "")
        fencing_token = int(event_payload.get("fencing_token") or 0)
        v = self.verify_lease(
            ctx, lease_id=lease_id, worker_id=worker_id, fencing_token=fencing_token
        )
        if not v.get("valid"):
            self._bump_metric("stale_event_rejections")
            raise PlatformContextError(
                "EVENT_REJECTED", v.get("reason") or "invalid lease for event"
            )
        rec = WorkLease.from_dict(v["lease"])
        if rec.cancellation_state == "CANCELLED":
            self._bump_metric("cancelled_event_rejections")
            raise PlatformContextError("EVENT_REJECTED", "lease cancelled")
        wraw = self._workers().get(worker_id)
        if wraw and WorkerIdentity.from_dict(wraw).trust_state == WorkerTrustState.REVOKED.value:
            raise PlatformContextError("EVENT_REJECTED", "worker revoked")
        event = ExecutionEvent(
            event_type=str(event_payload.get("event_type") or "progress"),
            worker_id=worker_id,
            lease_id=lease_id,
            fencing_token=fencing_token,
            mission_id=rec.mission_id,
            work_node_id=rec.work_node_id,
            attempt=rec.attempt,
            sequence=int(event_payload.get("sequence") or rec.last_event_seq + 1),
            at=now_ts(),
            payload=dict(event_payload.get("payload") or {}),
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
        )
        self._append_event(ctx, event)
        return {"accepted": True, "event": event.to_public()}

    # ── result reconciliation (M107) ─────────────────────────────────────
    def reconcile_result(
        self,
        ctx: PlatformExecutionContext,
        *,
        lease_id: str,
        worker_id: str,
        fencing_token: int,
        result: dict[str, Any],
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        self._operate(ctx)
        with self._lock:
            now = now_ts()
            leases = self._leases()
            if lease_id not in leases:
                rec_out = ReconciliationRecord(
                    outcome=ReconciliationOutcome.REJECTED_UNAUTHORIZED.value,
                    lease_id=lease_id,
                    work_node_id="",
                    worker_id=worker_id,
                    fencing_token=fencing_token,
                    reason="NO_LEASE",
                    at=now,
                    advances_graph=False,
                )
                self._store_reconciliation(rec_out)
                return rec_out.to_public()

            rec = WorkLease.from_dict(leases[lease_id])
            if rec.org_id != ctx.org_id or rec.workspace_id != ctx.workspace_id:
                rec_out = ReconciliationRecord(
                    outcome=ReconciliationOutcome.REJECTED_UNAUTHORIZED.value,
                    lease_id=lease_id,
                    work_node_id=rec.work_node_id,
                    worker_id=worker_id,
                    fencing_token=fencing_token,
                    reason="TENANT_MISMATCH",
                    at=now,
                )
                self._store_reconciliation(rec_out)
                self._bump_metric("rejected_unauthorized")
                return rec_out.to_public()

            if rec.worker_id != worker_id:
                rec_out = ReconciliationRecord(
                    outcome=ReconciliationOutcome.REJECTED_STALE.value,
                    lease_id=lease_id,
                    work_node_id=rec.work_node_id,
                    worker_id=worker_id,
                    fencing_token=fencing_token,
                    reason="WORKER_MISMATCH_REASSIGNED",
                    at=now,
                )
                self._store_reconciliation(rec_out)
                self._bump_metric("rejected_stale")
                return rec_out.to_public()

            if rec.fencing_token != int(fencing_token):
                rec_out = ReconciliationRecord(
                    outcome=ReconciliationOutcome.REJECTED_STALE.value,
                    lease_id=lease_id,
                    work_node_id=rec.work_node_id,
                    worker_id=worker_id,
                    fencing_token=fencing_token,
                    reason="FENCING_MISMATCH",
                    at=now,
                )
                self._store_reconciliation(rec_out)
                self._bump_metric("rejected_stale")
                return rec_out.to_public()

            if rec.cancellation_state == "CANCELLED" or rec.state == LeaseState.CANCELLED.value:
                rec_out = ReconciliationRecord(
                    outcome=ReconciliationOutcome.REJECTED_CANCELLED.value,
                    lease_id=lease_id,
                    work_node_id=rec.work_node_id,
                    worker_id=worker_id,
                    fencing_token=fencing_token,
                    reason="CANCELLED",
                    at=now,
                )
                self._store_reconciliation(rec_out)
                self._bump_metric("rejected_cancelled")
                return rec_out.to_public()

            if rec.completion_state == "COMPLETED" and rec.result_hash:
                # Duplicate result
                ch = content_hash(result)
                if ch == rec.result_hash:
                    rec_out = ReconciliationRecord(
                        outcome=ReconciliationOutcome.REJECTED_DUPLICATE.value,
                        lease_id=lease_id,
                        work_node_id=rec.work_node_id,
                        worker_id=worker_id,
                        fencing_token=fencing_token,
                        reason="DUPLICATE_RESULT",
                        content_hash=ch,
                        at=now,
                    )
                    self._store_reconciliation(rec_out)
                    self._bump_metric("rejected_duplicate")
                    return rec_out.to_public()
                rec_out = ReconciliationRecord(
                    outcome=ReconciliationOutcome.REJECTED_DUPLICATE.value,
                    lease_id=lease_id,
                    work_node_id=rec.work_node_id,
                    worker_id=worker_id,
                    fencing_token=fencing_token,
                    reason="ALREADY_COMPLETED",
                    at=now,
                )
                self._store_reconciliation(rec_out)
                self._bump_metric("rejected_duplicate")
                return rec_out.to_public()

            if not rec.is_active(now) and rec.completion_state == "OPEN":
                # Expired — late result
                rec_out = ReconciliationRecord(
                    outcome=ReconciliationOutcome.REJECTED_STALE.value,
                    lease_id=lease_id,
                    work_node_id=rec.work_node_id,
                    worker_id=worker_id,
                    fencing_token=fencing_token,
                    reason="LEASE_EXPIRED",
                    at=now,
                )
                self._store_reconciliation(rec_out)
                self._bump_metric("rejected_stale")
                return rec_out.to_public()

            if idempotency_key and idempotency_key != rec.idempotency_key:
                rec_out = ReconciliationRecord(
                    outcome=ReconciliationOutcome.REJECTED_UNAUTHORIZED.value,
                    lease_id=lease_id,
                    work_node_id=rec.work_node_id,
                    worker_id=worker_id,
                    fencing_token=fencing_token,
                    reason="IDEMPOTENCY_MISMATCH",
                    at=now,
                )
                self._store_reconciliation(rec_out)
                return rec_out.to_public()

            # Output contract validation
            if not isinstance(result, dict):
                rec_out = ReconciliationRecord(
                    outcome=ReconciliationOutcome.REJECTED_INVALID_OUTPUT.value,
                    lease_id=lease_id,
                    work_node_id=rec.work_node_id,
                    worker_id=worker_id,
                    fencing_token=fencing_token,
                    reason="RESULT_NOT_OBJECT",
                    at=now,
                )
                self._store_reconciliation(rec_out)
                self._bump_metric("rejected_invalid")
                return rec_out.to_public()

            size = len(json.dumps(result, default=str))
            if size > limits.MAX_RESULT_BYTES:
                rec_out = ReconciliationRecord(
                    outcome=ReconciliationOutcome.REJECTED_INVALID_OUTPUT.value,
                    lease_id=lease_id,
                    work_node_id=rec.work_node_id,
                    worker_id=worker_id,
                    fencing_token=fencing_token,
                    reason="RESULT_TOO_LARGE",
                    at=now,
                )
                self._store_reconciliation(rec_out)
                return rec_out.to_public()

            # Unsafe mutation uncertainty
            if result.get("mutation_uncertain") or result.get("requires_review"):
                rec_out = ReconciliationRecord(
                    outcome=ReconciliationOutcome.REQUIRES_REVIEW.value,
                    lease_id=lease_id,
                    work_node_id=rec.work_node_id,
                    worker_id=worker_id,
                    fencing_token=fencing_token,
                    reason="MUTATION_UNCERTAIN",
                    content_hash=content_hash(result),
                    at=now,
                    advances_graph=False,
                )
                self._store_reconciliation(rec_out)
                self._persist_result(rec, result, rec_out)
                return rec_out.to_public()

            ch = content_hash(result)
            warnings = []
            if result.get("warning"):
                warnings.append(str(result.get("warning")))
            outcome = (
                ReconciliationOutcome.ACCEPTED_WITH_WARNINGS.value
                if warnings
                else ReconciliationOutcome.ACCEPTED.value
            )
            rec.completion_state = "COMPLETED"
            rec.state = LeaseState.COMPLETED.value
            rec.result_hash = ch
            leases[lease_id] = rec.to_public()
            self._save_leases(leases)

            # Decrement worker lease count
            workers = self._workers()
            if worker_id in workers:
                ww = WorkerIdentity.from_dict(workers[worker_id])
                ww.active_lease_count = max(0, int(ww.active_lease_count) - 1)
                workers[worker_id] = ww.to_public()
                self._save_workers(workers)

            rec_out = ReconciliationRecord(
                outcome=outcome,
                lease_id=lease_id,
                work_node_id=rec.work_node_id,
                worker_id=worker_id,
                fencing_token=fencing_token,
                reason="OK" if not warnings else ";".join(warnings),
                content_hash=ch,
                at=now,
                advances_graph=True,
            )
            self._store_reconciliation(rec_out)
            self._persist_result(rec, result, rec_out)
            self._audit(
                ctx,
                "fleet.result_accepted",
                detail={
                    "lease_id": lease_id,
                    "work_node_id": rec.work_node_id,
                    "content_hash": ch,
                    "outcome": outcome,
                },
            )
            self._bump_metric("results_accepted")
            try:
                self._append_event(
                    ctx,
                    ExecutionEvent(
                        event_type=ExecutionEventType.COMPLETED.value,
                        worker_id=worker_id,
                        lease_id=lease_id,
                        fencing_token=fencing_token,
                        mission_id=rec.mission_id,
                        work_node_id=rec.work_node_id,
                        attempt=rec.attempt,
                        sequence=rec.last_event_seq + 1,
                        at=now,
                        org_id=ctx.org_id,
                        workspace_id=ctx.workspace_id,
                        payload={"content_hash": ch, "outcome": outcome},
                    ),
                )
            except PlatformContextError:
                pass
            return rec_out.to_public()

    def _store_reconciliation(self, rec: ReconciliationRecord) -> None:
        results = self._results()
        key = f"recon:{rec.lease_id}:{rec.at}:{rec.outcome}"
        results[key] = rec.to_public()
        # Also index latest per lease
        results[f"latest:{rec.lease_id}"] = rec.to_public()
        self._save_results(results)

    def _persist_result(
        self, lease: WorkLease, result: dict, recon: ReconciliationRecord
    ) -> None:
        results = self._results()
        results[f"result:{lease.lease_id}"] = {
            "lease_id": lease.lease_id,
            "work_node_id": lease.work_node_id,
            "worker_id": lease.worker_id,
            "fencing_token": lease.fencing_token,
            "content_hash": recon.content_hash,
            "outcome": recon.outcome,
            "advances_graph": recon.advances_graph,
            "result": result,
            "certified": False,  # not certified until fleet certification
            "at": recon.at,
        }
        self._save_results(results)

    def list_reconciliations(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._read(ctx)
        items = [
            v
            for k, v in self._results().items()
            if k.startswith("recon:") or k.startswith("latest:")
        ]
        # dedupe by keeping recon: keys primarily
        items = [v for k, v in self._results().items() if k.startswith("recon:")]
        items.sort(key=lambda x: x.get("at", 0), reverse=True)
        return {"reconciliations": items[:100], "count": len(items)}

    # ── cancellation (M107) ──────────────────────────────────────────────
    def cancel(
        self,
        ctx: PlatformExecutionContext,
        *,
        scope: str,
        target_id: str,
        reason: str = "operator_cancel",
    ) -> dict[str, Any]:
        """Cancel at mission/work-node/worker/lease level. No orphan work."""
        self._operate(ctx)
        with self._lock:
            now = now_ts()
            leases = self._leases()
            cancelled = []
            for lid, raw in list(leases.items()):
                rec = WorkLease.from_dict(raw)
                if rec.org_id != ctx.org_id or rec.workspace_id != ctx.workspace_id:
                    continue
                match = False
                if scope == "lease" and rec.lease_id == target_id:
                    match = True
                elif scope == "work_node" and rec.work_node_id == target_id:
                    match = True
                elif scope == "worker" and rec.worker_id == target_id:
                    match = True
                elif scope == "mission" and rec.mission_id == target_id:
                    match = True
                elif scope == "orchestration" and rec.orchestration_id == target_id:
                    match = True
                elif scope == "phase" and rec.plan_version == target_id:
                    match = True
                if match and rec.completion_state == "OPEN":
                    rec.cancellation_state = "CANCELLED"
                    rec.state = LeaseState.CANCELLED.value
                    rec.completion_state = "CANCELLED"
                    leases[lid] = rec.to_public()
                    cancelled.append(lid)
            self._save_leases(leases)
            if scope == "worker":
                # Also mark worker
                pass
            self._audit(
                ctx,
                "fleet.cancel",
                detail={"scope": scope, "target_id": target_id, "cancelled": cancelled, "reason": reason},
            )
            self._bump_metric("cancellations")
            return {
                "scope": scope,
                "target_id": target_id,
                "cancelled_leases": cancelled,
                "count": len(cancelled),
                "reason": reason,
                "at": now,
            }

    # ── drain / quarantine / revoke (M108) ───────────────────────────────
    def drain_worker(
        self, ctx: PlatformExecutionContext, worker_id: str, *, reason: str = "operator_drain"
    ) -> dict[str, Any]:
        self._operate(ctx)
        workers = self._workers()
        if worker_id not in workers:
            raise PlatformContextError("WORKER_NOT_FOUND", "unknown worker")
        w = WorkerIdentity.from_dict(workers[worker_id])
        if w.org_id and w.org_id != ctx.org_id:
            raise PlatformContextError("WORKER_NOT_FOUND", "out of scope")
        w.trust_state = WorkerTrustState.DRAINING.value
        w.health_state = WorkerHealthState.DRAINING.value
        w.updated_at = now_ts()
        workers[worker_id] = w.to_public()
        self._save_workers(workers)
        try:
            self.cluster.set_worker_state(ctx, worker_id=worker_id, action="drain")
        except PlatformContextError:
            pass
        self._audit(ctx, "fleet.worker_drain", detail={"worker_id": worker_id, "reason": reason})
        return {"worker": w.to_public()}

    def quarantine_worker(
        self, ctx: PlatformExecutionContext, worker_id: str, *, reason: str
    ) -> dict[str, Any]:
        self._operate(ctx)
        workers = self._workers()
        if worker_id not in workers:
            raise PlatformContextError("WORKER_NOT_FOUND", "unknown worker")
        w = WorkerIdentity.from_dict(workers[worker_id])
        w.trust_state = WorkerTrustState.QUARANTINED.value
        w.health_state = WorkerHealthState.QUARANTINED.value
        w.quarantine_reason = reason
        w.updated_at = now_ts()
        workers[worker_id] = w.to_public()
        self._save_workers(workers)
        # Revoke open leases
        cancel = self.cancel(ctx, scope="worker", target_id=worker_id, reason=f"quarantine:{reason}")
        self._bump_metric("quarantine_events")
        self._audit(
            ctx,
            "fleet.worker_quarantine",
            detail={"worker_id": worker_id, "reason": reason, "leases": cancel["cancelled_leases"]},
        )
        return {"worker": w.to_public(), "cancelled": cancel}

    def revoke_worker(
        self, ctx: PlatformExecutionContext, worker_id: str, *, reason: str = "operator_revoke"
    ) -> dict[str, Any]:
        self._operate(ctx)
        workers = self._workers()
        if worker_id not in workers:
            raise PlatformContextError("WORKER_NOT_FOUND", "unknown worker")
        w = WorkerIdentity.from_dict(workers[worker_id])
        w.trust_state = WorkerTrustState.REVOKED.value
        w.admission_state = AdmissionState.REVOKED.value
        w.health_state = WorkerHealthState.OFFLINE.value
        w.quarantine_reason = reason
        w.updated_at = now_ts()
        workers[worker_id] = w.to_public()
        self._save_workers(workers)
        cancel = self.cancel(ctx, scope="worker", target_id=worker_id, reason=f"revoke:{reason}")
        try:
            self.cluster.set_worker_state(ctx, worker_id=worker_id, action="retire")
        except PlatformContextError:
            pass
        self._audit(ctx, "fleet.worker_revoke", detail={"worker_id": worker_id, "reason": reason})
        return {"worker": w.to_public(), "cancelled": cancel}

    # ── recovery & reassignment (M108) ───────────────────────────────────
    def recover_lost_workers(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        """Detect lost/stale workers, expire leases, prepare reassignment."""
        self._operate(ctx)
        with self._lock:
            now = now_ts()
            workers = self._workers()
            leases = self._leases()
            lost = []
            expired_leases = []
            for wid, raw in list(workers.items()):
                w = WorkerIdentity.from_dict(raw)
                if w.org_id and w.org_id != ctx.org_id:
                    continue
                self._refresh_health(w, now)
                if w.health_state in (
                    WorkerHealthState.STALE.value,
                    WorkerHealthState.OFFLINE.value,
                    WorkerHealthState.UNHEALTHY.value,
                ) and w.trust_state not in (
                    WorkerTrustState.REVOKED.value,
                    WorkerTrustState.QUARANTINED.value,
                ):
                    w.trust_state = WorkerTrustState.UNHEALTHY.value
                    w.quarantine_reason = w.quarantine_reason or "heartbeat_loss"
                    workers[wid] = w.to_public()
                    lost.append(wid)
            for lid, raw in list(leases.items()):
                rec = WorkLease.from_dict(raw)
                if rec.org_id != ctx.org_id:
                    continue
                owner = workers.get(rec.worker_id)
                owner_dead = (
                    owner is None
                    or owner.get("trust_state")
                    in (
                        WorkerTrustState.UNHEALTHY.value,
                        WorkerTrustState.OFFLINE.value,
                        WorkerTrustState.REVOKED.value,
                        WorkerTrustState.QUARANTINED.value,
                    )
                    or owner.get("health_state")
                    in (
                        WorkerHealthState.STALE.value,
                        WorkerHealthState.OFFLINE.value,
                        WorkerHealthState.UNHEALTHY.value,
                    )
                )
                if rec.completion_state == "OPEN" and (
                    not rec.is_active(now) or owner_dead
                ):
                    rec.state = LeaseState.EXPIRED.value
                    rec.completion_state = "OPEN"  # requeue-eligible, not completed
                    # Keep cancellation if already cancelled
                    if rec.cancellation_state != "CANCELLED":
                        leases[lid] = rec.to_public()
                        expired_leases.append(
                            {
                                "lease_id": lid,
                                "work_node_id": rec.work_node_id,
                                "worker_id": rec.worker_id,
                                "retry_safe": True,
                                "prior_fencing_token": rec.fencing_token,
                            }
                        )
            self._save_workers(workers)
            self._save_leases(leases)
            recovery = {
                "lost_workers": lost,
                "expired_leases": expired_leases,
                "at": now,
            }
            prev = list(self.store.get_config(FLEET_RECOVERY_KEY, []) or [])
            prev.append(recovery)
            self.store.set_config(
                FLEET_RECOVERY_KEY, prev[-limits.MAX_RETAINED_EVENTS :], updated_by="m103"
            )
            self._audit(
                ctx,
                "fleet.recovery",
                detail={"lost": len(lost), "expired_leases": len(expired_leases)},
            )
            self._bump_metric("recovery_events")
            # Also run M56 recovery
            try:
                m56 = self.cluster.recover_leases(ctx)
            except PlatformContextError:
                m56 = {}
            recovery["m56_recovery"] = m56
            return recovery

    def reassign_work(
        self,
        ctx: PlatformExecutionContext,
        *,
        work_node: dict[str, Any],
        previous_lease_id: str = "",
        approval_reference: str = "",
    ) -> dict[str, Any]:
        """Reassign retry-safe work with a NEW fencing token. Never resurrects old lease."""
        self._operate(ctx)
        with self._lock:
            if previous_lease_id:
                leases = self._leases()
                if previous_lease_id in leases:
                    old = WorkLease.from_dict(leases[previous_lease_id])
                    if old.org_id != ctx.org_id:
                        raise PlatformContextError("LEASE_NOT_FOUND", "out of scope")
                    # Ensure old lease cannot complete
                    if old.completion_state == "OPEN":
                        old.state = LeaseState.EXPIRED.value
                        leases[previous_lease_id] = old.to_public()
                        self._save_leases(leases)
                    work_node = dict(work_node)
                    work_node.setdefault("work_node_id", old.work_node_id)
                    work_node.setdefault("mission_id", old.mission_id)
                    work_node.setdefault("orchestration_id", old.orchestration_id)
                    work_node["attempt"] = int(old.attempt) + 1
                    work_node.setdefault(
                        "prior_failure_workers", [old.worker_id]
                    )
                    if old.worker_id not in work_node.get("prior_failure_workers", []):
                        work_node["prior_failure_workers"] = list(
                            work_node.get("prior_failure_workers") or []
                        ) + [old.worker_id]
                    approval_reference = approval_reference or old.approval_reference

            # Issue new lease (new fencing token inside acquire_lease)
            issued = self.acquire_lease(
                ctx,
                work_node=work_node,
                approval_reference=approval_reference,
                mission_id=str(work_node.get("mission_id") or ""),
                orchestration_id=str(work_node.get("orchestration_id") or ""),
                plan_version=str(work_node.get("plan_version") or "1"),
            )
            self._audit(
                ctx,
                "fleet.reassign",
                detail={
                    "previous_lease_id": previous_lease_id,
                    "new_lease_id": issued["lease"]["lease_id"],
                    "new_fencing_token": issued["lease"]["fencing_token"],
                },
            )
            self._bump_metric("reassignments")
            return {
                "previous_lease_id": previous_lease_id,
                "new_lease": issued["lease"],
                "scheduling": issued["scheduling"],
                "fencing_token_advanced": True,
            }

    # ── dispatch parallel ready nodes (integration) ──────────────────────
    def dispatch_ready_nodes(
        self,
        ctx: PlatformExecutionContext,
        *,
        nodes: list[dict[str, Any]],
        mission_id: str = "",
        orchestration_id: str = "",
        plan_version: str = "1",
    ) -> dict[str, Any]:
        """Dispatch independent ready nodes in bounded parallel."""
        self._operate(ctx)
        if self._dispatch_state().get("paused"):
            return {"dispatched": [], "blocked": [], "reason": "dispatch_paused"}
        dispatched = []
        blocked = []
        for node in nodes:
            n = dict(node)
            n.setdefault("dependencies_complete", True)
            n.setdefault("mission_id", mission_id)
            n.setdefault("orchestration_id", orchestration_id)
            n.setdefault("plan_version", plan_version)
            try:
                if n.get("approval_required") and not n.get("approval_reference"):
                    if n.get("approval_state") not in ("granted", "approved", "not_required"):
                        blocked.append(
                            {
                                "work_node_id": n.get("work_node_id") or n.get("id"),
                                "reason": "approval_required",
                            }
                        )
                        continue
                result = self.acquire_lease(
                    ctx,
                    work_node=n,
                    approval_reference=str(n.get("approval_reference") or ""),
                    mission_id=mission_id,
                    orchestration_id=orchestration_id,
                    plan_version=plan_version,
                )
                dispatched.append(result)
            except PlatformContextError as e:
                blocked.append(
                    {
                        "work_node_id": n.get("work_node_id") or n.get("id"),
                        "reason": e.code,
                        "message": str(e),
                    }
                )
        return {
            "dispatched": dispatched,
            "blocked": blocked,
            "dispatched_count": len(dispatched),
            "blocked_count": len(blocked),
        }

    def set_dispatch_paused(
        self, ctx: PlatformExecutionContext, *, paused: bool, reason: str = ""
    ) -> dict[str, Any]:
        self._operate(ctx)
        state = self._dispatch_state()
        state["paused"] = bool(paused)
        state["reason"] = reason
        state["at"] = now_ts()
        self._save_dispatch(state)
        # Mirror M56 scheduler pause
        try:
            self.cluster.scheduler_control(ctx, action="pause" if paused else "resume")
        except PlatformContextError:
            pass
        self._audit(
            ctx,
            "fleet.dispatch_control",
            outcome="PAUSED" if paused else "RESUMED",
            detail={"reason": reason},
        )
        return state

    # ── fleet metrics / observability ────────────────────────────────────
    def fleet_metrics(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._read(ctx)
        workers_resp = self.list_workers(ctx)
        workers = workers_resp["workers"]
        now = now_ts()
        leases = [
            WorkLease.from_dict(l)
            for l in self._leases().values()
            if l.get("org_id") == ctx.org_id
        ]
        metrics = self._metrics()
        return {
            "schema_version": FLEET_SCHEMA,
            "registered_workers": len(workers),
            "trusted_workers": sum(
                1 for w in workers if w["trust_state"] == WorkerTrustState.TRUSTED_LOCAL.value
            ),
            "healthy_workers": sum(
                1 for w in workers if w["health_state"] == WorkerHealthState.HEALTHY.value
            ),
            "degraded_workers": sum(
                1 for w in workers if w["health_state"] == WorkerHealthState.DEGRADED.value
            ),
            "offline_workers": sum(
                1 for w in workers if w["health_state"] == WorkerHealthState.OFFLINE.value
            ),
            "quarantined_workers": sum(
                1 for w in workers if w["trust_state"] == WorkerTrustState.QUARANTINED.value
            ),
            "draining_workers": sum(
                1 for w in workers if w["trust_state"] == WorkerTrustState.DRAINING.value
            ),
            "active_leases": sum(1 for l in leases if l.is_active(now)),
            "expired_leases": sum(1 for l in leases if l.state == LeaseState.EXPIRED.value),
            "completed_leases": sum(
                1 for l in leases if l.completion_state == "COMPLETED"
            ),
            "cancelled_leases": sum(
                1 for l in leases if l.cancellation_state == "CANCELLED"
            ),
            "counters": metrics,
            "m56_metrics": self.cluster.distributed_metrics(ctx),
            "production_authorized": False,
        }

    def list_leases(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._read(ctx)
        now = now_ts()
        items = []
        for raw in self._leases().values():
            if raw.get("org_id") and raw.get("org_id") != ctx.org_id:
                continue
            if raw.get("workspace_id") and raw.get("workspace_id") != ctx.workspace_id:
                continue
            rec = WorkLease.from_dict(raw)
            pub = rec.to_public()
            pub["active"] = rec.is_active(now)
            items.append(pub)
        items.sort(key=lambda x: x.get("issued_at", 0), reverse=True)
        return {"leases": items, "count": len(items)}

    def list_events(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._read(ctx)
        events = [
            e
            for e in self._events()
            if not e.get("org_id") or e.get("org_id") == ctx.org_id
        ]
        return {"events": events[-100:], "count": len(events)}

    def recovery_history(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._read(ctx)
        return {
            "recoveries": list(self.store.get_config(FLEET_RECOVERY_KEY, []) or [])[-50:]
        }

    # ── conversational controls ──────────────────────────────────────────
    def command_from_conversation(
        self, ctx: PlatformExecutionContext, message: str, *, worker_id: str = ""
    ) -> dict[str, Any]:
        """Translate chat intent to proposed/controlled fleet actions. RBAC applies."""
        self._read(ctx)
        m = (message or "").lower().strip()
        if not m:
            raise PlatformContextError("VALIDATION_FAILED", "message required")
        intent = "unknown"
        if "healthy" in m or "which workers" in m:
            intent = "list_health"
        elif "why" in m and ("assign" in m or "scheduled" in m or "matched" in m):
            intent = "explain_schedule"
        elif "waiting" in m or "pending work" in m:
            intent = "list_waiting"
        elif "lose" in m and "lease" in m or "lost lease" in m or "expired lease" in m:
            intent = "list_lost_leases"
        elif "rejected" in m or "why was a result" in m:
            intent = "list_rejections"
        elif "drain" in m:
            intent = "drain"
        elif "pause dispatch" in m or "memory pressure" in m:
            intent = "pause_dispatch"
        elif "resume dispatch" in m:
            intent = "resume_dispatch"
        elif "quarantine" in m:
            intent = "quarantine"
        elif "review" in m:
            intent = "list_review"
        elif "recover" in m:
            intent = "recover"

        result: dict[str, Any] = {
            "intent": intent,
            "executed": False,
            "note": "Conversation proposes fleet commands only; RBAC and policy still apply. Voice/chat cannot command worker processes directly.",
            "direct_worker_command": False,
        }
        if intent == "list_health":
            result["result"] = self.list_workers(ctx)
            result["executed"] = True
        elif intent == "explain_schedule":
            result["result"] = self.explain_schedule(ctx)
            result["executed"] = True
        elif intent == "list_waiting":
            result["result"] = {
                "leases": [
                    l
                    for l in self.list_leases(ctx)["leases"]
                    if l.get("completion_state") == "OPEN" and l.get("active")
                ]
            }
            result["executed"] = True
        elif intent == "list_lost_leases":
            result["result"] = {
                "leases": [
                    l
                    for l in self.list_leases(ctx)["leases"]
                    if l.get("state") == LeaseState.EXPIRED.value
                ]
            }
            result["executed"] = True
        elif intent == "list_rejections":
            recons = self.list_reconciliations(ctx)["reconciliations"]
            result["result"] = {
                "rejections": [
                    r
                    for r in recons
                    if str(r.get("outcome", "")).startswith("REJECTED")
                ]
            }
            result["executed"] = True
        elif intent == "list_review":
            recons = self.list_reconciliations(ctx)["reconciliations"]
            result["result"] = {
                "review": [
                    r
                    for r in recons
                    if r.get("outcome") == ReconciliationOutcome.REQUIRES_REVIEW.value
                ]
            }
            result["executed"] = True
        elif intent == "pause_dispatch":
            ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
            result["result"] = self.set_dispatch_paused(
                ctx, paused=True, reason="conversation:memory_pressure"
            )
            result["executed"] = True
        elif intent == "resume_dispatch":
            ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
            result["result"] = self.set_dispatch_paused(ctx, paused=False, reason="conversation")
            result["executed"] = True
        elif intent == "drain" and worker_id:
            ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
            result["result"] = self.drain_worker(ctx, worker_id, reason="conversation")
            result["executed"] = True
        elif intent == "quarantine" and worker_id:
            ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
            result["result"] = self.quarantine_worker(
                ctx, worker_id, reason="conversation"
            )
            result["executed"] = True
        elif intent == "recover":
            ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
            result["result"] = self.recover_lost_workers(ctx)
            result["executed"] = True
        elif intent in ("drain", "quarantine"):
            result["requires_worker_id"] = True
        return result

    # ── certification summary ────────────────────────────────────────────
    def certify_fleet(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._operate(ctx)
        health = self.health(ctx)
        metrics = self.fleet_metrics(ctx)
        return {
            "schema": "m111.fleet_certification.v1",
            "phase": limits.PHASE_A_SINGLE_HOST,
            "verdict": "FLEET_CERTIFIED_PHASE_A_WITH_LIMITATIONS",
            "production_authorized": False,
            "lan_authorized": False,
            "cloud_authorized": False,
            "public_listener": False,
            "extends_m56": True,
            "replaces_m56": False,
            "direct_tool_execution": False,
            "execution_authority": "PlatformAgentRuntime→ExecutionGateway",
            "trading_guardian": "UNCHANGED",
            "health": health,
            "metrics": metrics,
            "limitations": [
                "loopback_only_transport",
                "single_host_multi_process",
                "sqlite_or_config_persistence",
                "no_cryptographic_multi_host_identity",
                "no_lan_workers",
                "no_cloud_workers",
                "no_production_activation",
                "english_primary_interface",
                "deterministic_local_test_workers",
            ],
        }


# Singleton helpers
_DEFAULT: DistributedWorkerRuntime | None = None
_LOCK = threading.Lock()


def default_fleet_runtime(platform_service=None) -> DistributedWorkerRuntime:
    global _DEFAULT
    with _LOCK:
        if platform_service is not None:
            existing = getattr(platform_service, "_fleet_runtime", None)
            if existing is not None:
                return existing
            svc = DistributedWorkerRuntime(platform_service)
            setattr(platform_service, "_fleet_runtime", svc)
            return svc
        if _DEFAULT is None:
            _DEFAULT = DistributedWorkerRuntime()
        return _DEFAULT


def reset_fleet_runtime_for_tests(platform_service=None) -> None:
    global _DEFAULT
    with _LOCK:
        _DEFAULT = None
        if platform_service is not None and hasattr(platform_service, "_fleet_runtime"):
            delattr(platform_service, "_fleet_runtime")
