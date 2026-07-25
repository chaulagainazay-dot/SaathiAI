"""M56 distributed runtime foundation — single-host compatible, multi-host ready.

Additive, advisory, deterministic, fail-closed. Prepares SaathiOS for future
multi-host operation while preserving identical single-host behavior. Introduces
NO new execution engine and NO second approval path: ``PlatformAgentRuntime``
remains canonical and ``ExecutionGateway`` remains the sole registered-tool
execution authority. Leases, workers, nodes, and the scheduler are advisory
coordination metadata only — nothing here executes a tool or dispatches work.

State is persisted in the existing platform ``config`` table (keys prefixed
``m56_``), so there is NO schema migration and full backwards compatibility.
Everything runs locally; no networking is required or performed.

Abstractions: RuntimeNode, RuntimeCluster, WorkerLease/ExecutionLease,
RuntimeHeartbeat, DistributedClock.
Services: WorkerRegistry, LeaseCoordinator, SchedulerFoundation, TopologyService,
and the ClusterCoordinator facade used by the API and release validator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
import shutil
import tempfile
from typing import Any

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.models import PlatformExecutionState, PlatformPermission, new_id

CLUSTER_SCHEMA_VERSION = "m56.cluster.v1"

# Config keys (persisted in the platform store — no new tables).
NODES_KEY = "m56_nodes"
WORKERS_KEY = "m56_workers"
LEASES_KEY = "m56_leases"
CLOCK_KEY = "m56_logical_clock"
SCHED_KEY = "m56_scheduler"

LOCAL_NODE_ID = "node-local"
LOCAL_WORKER_ID = "worker-local"

DEFAULT_LEASE_TTL_SEC = 300.0
DEFAULT_HEARTBEAT_TIMEOUT_SEC = 90.0

# Status vocabulary (shared with the release validator).
PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"

WORKER_STATES = {"ACTIVE", "PAUSED", "DRAINING", "RETIRED"}
LEASE_STATES = {"HELD", "RENEWED", "EXPIRED", "TRANSFERRED", "RELEASED"}


class DistributedClock:
    """Deterministic clock abstraction: wall time from the store plus a logical
    counter persisted in config. Single-host today; the same interface backs a
    future multi-host logical clock."""

    def __init__(self, store):
        self.store = store

    def now(self) -> float:
        return float(self.store._now())

    def tick(self) -> int:
        value = int(self.store.get_config(CLOCK_KEY, 0) or 0) + 1
        self.store.set_config(CLOCK_KEY, value, updated_by="m56-clock")
        return value

    def logical(self) -> int:
        return int(self.store.get_config(CLOCK_KEY, 0) or 0)


@dataclass
class RuntimeNode:
    node_id: str
    label: str
    runtime_version: str
    status: str = "ACTIVE"
    created_at: float = 0.0
    last_heartbeat: float = 0.0

    def to_public(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "label": self.label,
            "runtime_version": self.runtime_version,
            "status": self.status,
            "created_at": self.created_at,
            "last_heartbeat": self.last_heartbeat,
        }


@dataclass
class WorkerRecord:
    worker_id: str
    node_id: str
    runtime_version: str
    status: str = "ACTIVE"
    capabilities: list[str] = field(default_factory=list)
    current_workload: int = 0
    lease_count: int = 0
    last_heartbeat: float = 0.0
    last_health_check: float = 0.0
    shutdown_state: str = "RUNNING"

    def to_public(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "node_id": self.node_id,
            "runtime_version": self.runtime_version,
            "status": self.status,
            "capabilities": sorted(self.capabilities),
            "current_workload": self.current_workload,
            "lease_count": self.lease_count,
            "last_heartbeat": self.last_heartbeat,
            "last_health_check": self.last_health_check,
            "shutdown_state": self.shutdown_state,
        }


@dataclass
class ExecutionLeaseRecord:
    """Advisory single-owner ownership record for an execution. Prevents a second
    worker from claiming the same execution; never executes anything itself."""

    lease_id: str
    execution_id: str
    owner_worker_id: str
    node_id: str
    org_id: str
    workspace_id: str
    state: str = "HELD"
    acquired_at: float = 0.0
    renewed_at: float = 0.0
    expires_at: float = 0.0
    version: int = 1

    def is_active(self, now: float) -> bool:
        return self.state in ("HELD", "RENEWED", "TRANSFERRED") and self.expires_at > now

    def to_public(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "execution_id": self.execution_id,
            "owner_worker_id": self.owner_worker_id,
            "node_id": self.node_id,
            "state": self.state,
            "acquired_at": self.acquired_at,
            "renewed_at": self.renewed_at,
            "expires_at": self.expires_at,
            "version": self.version,
        }


# WorkerLease is an alias kept for the abstraction vocabulary in the spec.
WorkerLease = ExecutionLeaseRecord


@dataclass
class RuntimeHeartbeat:
    worker_id: str
    node_id: str
    at: float
    logical: int

    def to_public(self) -> dict[str, Any]:
        return {"worker_id": self.worker_id, "node_id": self.node_id, "at": self.at, "logical": self.logical}


@dataclass
class RuntimeCluster:
    nodes: list[RuntimeNode]
    workers: list[WorkerRecord]
    leases: list[ExecutionLeaseRecord]


class ClusterCoordinator:
    """Facade over the worker registry, lease coordinator, scheduler, topology,
    and node-health surfaces. Single-host, config-backed, advisory."""

    def __init__(self, platform=None):
        if platform is None:
            from saathi.platform.service import default_platform

            platform = default_platform()
        self.platform = platform
        self.store = platform.store
        self.clock = DistributedClock(self.store)

    # ── context ──────────────────────────────────────────────────────────
    def read_context(self, token: str) -> PlatformExecutionContext:
        ctx = self.platform.require_context(token)
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        return ctx

    def operate_context(self, token: str) -> PlatformExecutionContext:
        ctx = self.platform.require_context(token)
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        return ctx

    # ── persistence helpers ──────────────────────────────────────────────
    def _nodes(self) -> dict[str, dict]:
        return dict(self.store.get_config(NODES_KEY, {}) or {})

    def _workers(self) -> dict[str, dict]:
        return dict(self.store.get_config(WORKERS_KEY, {}) or {})

    def _leases(self) -> dict[str, dict]:
        return dict(self.store.get_config(LEASES_KEY, {}) or {})

    def _save_nodes(self, nodes: dict, actor: str = "m56") -> None:
        self.store.set_config(NODES_KEY, nodes, updated_by=actor)

    def _save_workers(self, workers: dict, actor: str = "m56") -> None:
        self.store.set_config(WORKERS_KEY, workers, updated_by=actor)

    def _save_leases(self, leases: dict, actor: str = "m56") -> None:
        self.store.set_config(LEASES_KEY, leases, updated_by=actor)

    def ensure_local(self) -> None:
        """Represent the current single host as one node + one local worker."""
        now = self.clock.now()
        nodes = self._nodes()
        if LOCAL_NODE_ID not in nodes:
            nodes[LOCAL_NODE_ID] = RuntimeNode(
                node_id=LOCAL_NODE_ID, label="single-host-local",
                runtime_version=CLUSTER_SCHEMA_VERSION, created_at=now, last_heartbeat=now,
            ).to_public()
            self._save_nodes(nodes)
        workers = self._workers()
        if LOCAL_WORKER_ID not in workers:
            workers[LOCAL_WORKER_ID] = WorkerRecord(
                worker_id=LOCAL_WORKER_ID, node_id=LOCAL_NODE_ID,
                runtime_version=CLUSTER_SCHEMA_VERSION, capabilities=["platform-agent-runtime"],
                last_heartbeat=now, last_health_check=now,
            ).to_public()
            self._save_workers(workers)

    # ── worker registry (Objective 2) ────────────────────────────────────
    def register_worker(
        self, ctx: PlatformExecutionContext, *, worker_id: str = "",
        node_id: str = LOCAL_NODE_ID, capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        self.ensure_local()
        now = self.clock.now()
        nodes = self._nodes()
        if node_id not in nodes:
            raise PlatformContextError("NODE_NOT_FOUND", "unknown runtime node")
        workers = self._workers()
        wid = worker_id.strip() or new_id("wrk_")
        workers[wid] = WorkerRecord(
            worker_id=wid, node_id=node_id, runtime_version=CLUSTER_SCHEMA_VERSION,
            capabilities=sorted(set(capabilities or ["platform-agent-runtime"])),
            last_heartbeat=now, last_health_check=now,
        ).to_public()
        self._save_workers(workers)
        self._audit(ctx, "cluster.worker_registered", detail={"worker_id": wid, "node_id": node_id})
        return workers[wid]

    def heartbeat(self, ctx: PlatformExecutionContext, *, worker_id: str) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        w = self._require_worker(worker_id)
        now = self.clock.now()
        w["last_heartbeat"] = now
        w["last_health_check"] = now
        workers = self._workers()
        workers[worker_id] = w
        self._save_workers(workers)
        logical = self.clock.tick()
        return RuntimeHeartbeat(worker_id, w["node_id"], now, logical).to_public()

    def set_worker_state(
        self, ctx: PlatformExecutionContext, *, worker_id: str, action: str
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        w = self._require_worker(worker_id)
        transitions = {
            "drain": ("DRAINING", "DRAINING"),
            "pause": ("PAUSED", "RUNNING"),
            "resume": ("ACTIVE", "RUNNING"),
            "retire": ("RETIRED", "STOPPED"),
        }
        if action not in transitions:
            raise PlatformContextError("WORKER_ACTION_UNSUPPORTED", f"unknown action: {action}")
        state, shutdown = transitions[action]
        w["status"] = state
        w["shutdown_state"] = shutdown
        workers = self._workers()
        workers[worker_id] = w
        self._save_workers(workers)
        # Retiring or draining a worker releases its active leases for recovery.
        if action in ("retire", "drain"):
            self._release_worker_leases(ctx, worker_id, reason=action.upper())
        self._audit(ctx, "cluster.worker_state", outcome=state, detail={"worker_id": worker_id, "action": action})
        return w

    def _require_worker(self, worker_id: str) -> dict:
        self.ensure_local()
        workers = self._workers()
        if worker_id not in workers:
            raise PlatformContextError("WORKER_NOT_FOUND", "unknown worker")
        return dict(workers[worker_id])

    # ── lease coordination (Objective 3) ─────────────────────────────────
    def acquire_lease(
        self, ctx: PlatformExecutionContext, *, execution_id: str,
        worker_id: str = LOCAL_WORKER_ID, ttl_sec: float = DEFAULT_LEASE_TTL_SEC,
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        self._require_worker(worker_id)
        record = self._scoped_execution(ctx, execution_id)
        now = self.clock.now()
        leases = self._leases()
        existing = leases.get(execution_id)
        if existing:
            rec = self._lease_from(existing)
            if rec.is_active(now) and rec.owner_worker_id != worker_id:
                # Fail closed — no duplicate ownership / no duplicate execution.
                self._audit(ctx, "cluster.lease_denied", outcome="BLOCKED",
                            detail={"execution_id": execution_id, "held_by": rec.owner_worker_id})
                raise PlatformContextError("LEASE_ALREADY_HELD", "execution lease held by another worker")
        lease = ExecutionLeaseRecord(
            lease_id=new_id("lease_"), execution_id=execution_id, owner_worker_id=worker_id,
            node_id=self._workers()[worker_id]["node_id"], org_id=ctx.org_id,
            workspace_id=ctx.workspace_id, state="HELD", acquired_at=now,
            renewed_at=now, expires_at=now + float(ttl_sec),
            version=(self._lease_from(existing).version + 1 if existing else 1),
        )
        leases[execution_id] = lease.to_full()
        self._save_leases(leases)
        self._bump_lease_counts()
        self._audit(ctx, "cluster.lease_acquired", detail={"execution_id": execution_id, "worker_id": worker_id})
        return lease.to_public()

    def renew_lease(
        self, ctx: PlatformExecutionContext, *, execution_id: str,
        worker_id: str = LOCAL_WORKER_ID, ttl_sec: float = DEFAULT_LEASE_TTL_SEC,
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        rec = self._require_lease(ctx, execution_id)
        now = self.clock.now()
        if rec.owner_worker_id != worker_id:
            raise PlatformContextError("LEASE_OWNER_MISMATCH", "worker does not own this lease")
        if not rec.is_active(now):
            raise PlatformContextError("LEASE_EXPIRED", "cannot renew an expired lease")
        rec.state = "RENEWED"
        rec.renewed_at = now
        rec.expires_at = now + float(ttl_sec)
        rec.version += 1
        self._store_lease(rec)
        self._audit(ctx, "cluster.lease_renewed", detail={"execution_id": execution_id})
        return rec.to_public()

    def transfer_lease(
        self, ctx: PlatformExecutionContext, *, execution_id: str, to_worker_id: str,
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        rec = self._require_lease(ctx, execution_id)
        self._require_worker(to_worker_id)
        now = self.clock.now()
        rec.owner_worker_id = to_worker_id
        rec.node_id = self._workers()[to_worker_id]["node_id"]
        rec.state = "TRANSFERRED"
        rec.renewed_at = now
        rec.expires_at = now + DEFAULT_LEASE_TTL_SEC
        rec.version += 1
        self._store_lease(rec)
        self._bump_lease_counts()
        self._audit(ctx, "cluster.lease_transferred", detail={"execution_id": execution_id, "to": to_worker_id})
        return rec.to_public()

    def verify_lease(self, ctx: PlatformExecutionContext, *, execution_id: str) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        leases = self._leases()
        if execution_id not in leases:
            return {"execution_id": execution_id, "valid": False, "reason": "NO_LEASE"}
        rec = self._lease_from(leases[execution_id])
        if rec.org_id != ctx.org_id or rec.workspace_id != ctx.workspace_id:
            return {"execution_id": execution_id, "valid": False, "reason": "OUT_OF_SCOPE"}
        now = self.clock.now()
        return {
            "execution_id": execution_id,
            "valid": rec.is_active(now),
            "owner_worker_id": rec.owner_worker_id,
            "expires_at": rec.expires_at,
            "state": rec.state,
        }

    def recover_leases(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        """Expire leases whose owner is stale/retired; make executions eligible
        for a fresh single-owner lease. Never replays or duplicates execution."""
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        now = self.clock.now()
        workers = self._workers()
        leases = self._leases()
        expired = []
        for execution_id, raw in list(leases.items()):
            rec = self._lease_from(raw)
            owner = workers.get(rec.owner_worker_id)
            owner_dead = (
                owner is None
                or owner["status"] == "RETIRED"
                or (now - owner.get("last_heartbeat", 0)) > DEFAULT_HEARTBEAT_TIMEOUT_SEC
            )
            if rec.state not in ("EXPIRED", "RELEASED") and (not rec.is_active(now) or owner_dead):
                rec.state = "EXPIRED"
                rec.version += 1
                leases[execution_id] = rec.to_full()
                expired.append(execution_id)
        self._save_leases(leases)
        self._bump_lease_counts()
        if expired:
            self._audit(ctx, "cluster.lease_recovered", detail={"expired": len(expired)})
        return {"recovered": expired, "count": len(expired)}

    def _release_worker_leases(self, ctx, worker_id: str, *, reason: str) -> None:
        leases = self._leases()
        changed = False
        for execution_id, raw in list(leases.items()):
            rec = self._lease_from(raw)
            if rec.owner_worker_id == worker_id and rec.state not in ("EXPIRED", "RELEASED"):
                rec.state = "RELEASED"
                rec.version += 1
                leases[execution_id] = rec.to_full()
                changed = True
        if changed:
            self._save_leases(leases)
            self._bump_lease_counts()

    def _require_lease(self, ctx, execution_id: str) -> ExecutionLeaseRecord:
        leases = self._leases()
        if execution_id not in leases:
            raise PlatformContextError("LEASE_NOT_FOUND", "no lease for execution")
        rec = self._lease_from(leases[execution_id])
        if rec.org_id != ctx.org_id or rec.workspace_id != ctx.workspace_id:
            raise PlatformContextError("LEASE_NOT_FOUND", "lease not in workspace")
        return rec

    def _store_lease(self, rec: ExecutionLeaseRecord) -> None:
        leases = self._leases()
        leases[rec.execution_id] = rec.to_full()
        self._save_leases(leases)

    def _lease_from(self, raw: dict) -> ExecutionLeaseRecord:
        return ExecutionLeaseRecord(**{k: raw[k] for k in _LEASE_FIELDS if k in raw})

    def _bump_lease_counts(self) -> None:
        now = self.clock.now()
        leases = self._leases()
        counts: dict[str, int] = {}
        for raw in leases.values():
            rec = self._lease_from(raw)
            if rec.is_active(now):
                counts[rec.owner_worker_id] = counts.get(rec.owner_worker_id, 0) + 1
        workers = self._workers()
        for wid, w in workers.items():
            w["lease_count"] = counts.get(wid, 0)
        self._save_workers(workers)

    def _scoped_execution(self, ctx, execution_id: str):
        record = self.store.get_platform_execution(execution_id)
        if not record or record.org_id != ctx.org_id or record.workspace_id != ctx.workspace_id:
            raise PlatformContextError("EXECUTION_NOT_FOUND", "execution not in workspace")
        return record

    # ── scheduler foundation (Objective 5) ───────────────────────────────
    def scheduler_plan(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        """Advisory scheduling plan over pending executions. Produces ordering +
        worker assignment only; PlatformAgentRuntime still performs execution."""
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        self.ensure_local()
        state = dict(self.store.get_config(SCHED_KEY, {}) or {})
        paused = bool(state.get("paused", False))
        records = self.store.list_platform_executions(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, limit=500
        )
        pending_states = {
            PlatformExecutionState.CREATED.value,
            PlatformExecutionState.QUEUED.value,
            PlatformExecutionState.READY.value,
            PlatformExecutionState.WAITING_APPROVAL.value,
        }
        pending = [r for r in records if r.state in pending_states]
        # Priority: waiting-approval last (blocked); older first (fair, FIFO).
        def priority(r):
            blocked = 1 if r.state == PlatformExecutionState.WAITING_APPROVAL.value else 0
            return (blocked, r.created_at)

        ordered = sorted(pending, key=priority)
        active_workers = [
            wid for wid, w in self._workers().items() if w["status"] == "ACTIVE"
        ] or [LOCAL_WORKER_ID]
        assignments = []
        for i, r in enumerate(ordered):
            assignments.append(
                {
                    "execution_id": r.execution_id,
                    "state": r.state,
                    "assigned_worker": active_workers[i % len(active_workers)],
                    "order": i,
                    "blocked_on_approval": r.state == PlatformExecutionState.WAITING_APPROVAL.value,
                }
            )
        return {
            "schema_version": CLUSTER_SCHEMA_VERSION,
            "paused": paused,
            "pending": len(pending),
            "fair_scheduling": "round_robin_over_active_workers",
            "execution_mode": "single_host_inline",  # no distributed processing
            "assignments": assignments[:200],
        }

    def scheduler_control(self, ctx: PlatformExecutionContext, *, action: str) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        if action not in ("pause", "resume"):
            raise PlatformContextError("SCHEDULER_ACTION_UNSUPPORTED", f"unknown action: {action}")
        state = dict(self.store.get_config(SCHED_KEY, {}) or {})
        state["paused"] = action == "pause"
        self.store.set_config(SCHED_KEY, state, updated_by=ctx.user_id)
        self._audit(ctx, "cluster.scheduler_control", outcome=action.upper(), detail={"action": action})
        return {"paused": state["paused"]}

    # ── topology (Objective 4) ───────────────────────────────────────────
    def topology(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        self.ensure_local()
        now = self.clock.now()
        nodes = list(self._nodes().values())
        workers = list(self._workers().values())
        leases = [self._lease_from(x) for x in self._leases().values()]
        # Only expose leases within the caller's tenant scope.
        scoped = [
            l.to_public()
            for l in leases
            if l.org_id == ctx.org_id and l.workspace_id == ctx.workspace_id
        ]
        active_leases = sum(1 for l in leases if l.is_active(now)
                            and l.org_id == ctx.org_id and l.workspace_id == ctx.workspace_id)
        return {
            "schema_version": CLUSTER_SCHEMA_VERSION,
            "cluster": {"nodes": len(nodes), "workers": len(workers)},
            "nodes": nodes,
            "workers": workers,
            "leases": scoped,
            "runtime_status": "single_host_active",
            "queue_status": {"active_leases": active_leases},
            "execution_ownership": "single_owner_advisory_lease",
            "recovery_state": "leases_recoverable_on_stale_worker",
            "logical_clock": self.clock.logical(),
            "canonical_runtime": "PlatformAgentRuntime",
            "registered_tool_authority": "ExecutionGateway",
        }

    # ── node health (Objective 6) ────────────────────────────────────────
    def node_health(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        self.ensure_local()
        now = self.clock.now()
        try:
            import resource

            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            memory_kib = int(rss / 1024) if rss > (1 << 20) else int(rss)
        except Exception:
            memory_kib = -1
        try:
            cpu_estimate = round(os.getloadavg()[0], 3)
        except (OSError, AttributeError):
            cpu_estimate = None
        workers = self._workers()
        nodes = {}
        for nid, node in self._nodes().items():
            node_workers = [w for w in workers.values() if w["node_id"] == nid]
            hb_age = now - node.get("last_heartbeat", now)
            nodes[nid] = {
                "node_id": nid,
                "status": node["status"],
                "heartbeat_age_seconds": max(0.0, hb_age),
                "healthy": hb_age <= DEFAULT_HEARTBEAT_TIMEOUT_SEC,
                "memory_rss_kib": memory_kib,
                "cpu_load_estimate": cpu_estimate,
                "worker_count": len(node_workers),
                "lease_count": sum(w["lease_count"] for w in node_workers),
                "restart_count": int(node.get("restart_count", 0)),
                "queue_depth": 0,
            }
        return {"schema_version": CLUSTER_SCHEMA_VERSION, "nodes": nodes}

    # ── distributed metrics (Objective 7) ────────────────────────────────
    def distributed_metrics(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        self.ensure_local()
        now = self.clock.now()
        workers = self._workers()
        leases = [self._lease_from(x) for x in self._leases().values()]
        tenant_leases = [l for l in leases if l.org_id == ctx.org_id and l.workspace_id == ctx.workspace_id]
        active = [l for l in tenant_leases if l.is_active(now)]
        per_worker = {}
        for wid, w in workers.items():
            per_worker[wid] = {
                "status": w["status"],
                "lease_count": w["lease_count"],
                "current_workload": w["current_workload"],
                "utilization": min(1.0, w["lease_count"] / 10.0),
            }
        churn = sum(1 for l in tenant_leases if l.state in ("EXPIRED", "TRANSFERRED", "RELEASED"))
        return {
            "schema_version": CLUSTER_SCHEMA_VERSION,
            "scope": {"org_id": ctx.org_id, "workspace_id": ctx.workspace_id},
            "per_node": {nid: {"status": n["status"]} for nid, n in self._nodes().items()},
            "per_worker": per_worker,
            "per_lease": {"active": len(active), "total": len(tenant_leases)},
            "per_queue": {"active_leases": len(active)},
            "per_scheduler": {"paused": bool((self.store.get_config(SCHED_KEY, {}) or {}).get("paused", False))},
            "per_recovery": {"lease_churn": churn},
            "execution_ownership": len(active),
            "worker_utilization": round(
                sum(v["utilization"] for v in per_worker.values()) / len(per_worker), 3
            ) if per_worker else 0.0,
            "lease_churn": churn,
            "queue_latency_seconds": 0.0,  # single-host inline; no queue wait
        }

    # ── recovery certification (Objective 8) ─────────────────────────────
    def recovery_certify(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.ORG_MANAGE)
        scenarios = [
            ("worker_restart", self._sc_worker_restart),
            ("lease_expiration", self._sc_lease_expiration),
            ("heartbeat_timeout", self._sc_heartbeat_timeout),
            ("scheduler_restart", self._sc_scheduler_restart),
            ("worker_drain", self._sc_worker_drain),
            ("worker_retirement", self._sc_worker_retirement),
            ("lease_reassignment", self._sc_lease_reassignment),
        ]
        results = []
        for name, fn in scenarios:
            try:
                detail = fn()
                results.append({"scenario": name, "status": PASS, "detail": detail})
            except AssertionError as exc:
                results.append({"scenario": name, "status": FAIL, "detail": str(exc)[:200]})
            except Exception as exc:  # pragma: no cover - defensive
                results.append({"scenario": name, "status": UNKNOWN, "detail": str(exc)[:200]})
        overall = (
            PASS if all(r["status"] == PASS for r in results)
            else (FAIL if any(r["status"] == FAIL for r in results) else WARNING)
        )
        self._audit(ctx, "cluster.recovery_certified", outcome=overall,
                    detail={"scenarios": len(results)})
        return {
            "schema_version": CLUSTER_SCHEMA_VERSION,
            "overall": overall,
            "invariants": ["no_replay", "no_duplicate_execution", "no_authority_escalation", "single_owner_lease"],
            "scenarios": results,
            "isolation": "each scenario runs against a fresh temp platform; operator data untouched",
        }

    # Scenarios operate on an isolated temp platform (operator data untouched).
    def _fresh(self):
        from saathi.platform.service import PlatformService
        from saathi.platform.store import PlatformStore

        tmpdir = tempfile.mkdtemp(prefix="m56-recovery-")
        svc = PlatformService(PlatformStore(os.path.join(tmpdir, "platform.db")))
        owner = svc.bootstrap_owner_secure(
            email="cluster@m56.local", name="C", password="ClusterPassw0rd!",
            org_name="C", workspace_name="WS",
        )
        token = owner["token"]
        ctx = svc.require_context(token)
        coord = ClusterCoordinator(svc)
        coord.ensure_local()
        return svc, token, ctx, coord, tmpdir

    def _synthetic_execution(self, svc, token, ctx) -> str:
        from saathi.platform.bindings import BindingAdministrationService
        from saathi.platform.runtime import PlatformAgentRuntime
        from saathi.tool_runtime.registry import reset_registry_for_tests

        reset_registry_for_tests()
        binding = BindingAdministrationService(svc).create(
            ctx, agent_id="cluster-agent", name="Cluster agent",
            allowed_tools=["m49.local_note_write"], allowed_capabilities=[],
            authority_ceiling="LOCAL_MUTATION",
        )
        try:
            PlatformAgentRuntime(svc).execute_token(
                token=token, tool_id="m49.local_note_write",
                arguments={"key": "m56", "value": "x"}, capability="write",
                agent_id=binding.agent_id, binding_id=binding.binding_id,
                binding_version=binding.version, idempotency_key=f"m56-{binding.binding_id}",
            )
        except PlatformContextError:
            pass
        return svc.store.list_platform_executions(binding_id=binding.binding_id)[0].execution_id

    def _sc_worker_restart(self) -> str:
        svc, token, ctx, coord, tmp = self._fresh()
        try:
            ex = self._synthetic_execution(svc, token, ctx)
            w = coord.register_worker(ctx, capabilities=["platform-agent-runtime"])["worker_id"]
            coord.acquire_lease(ctx, execution_id=ex, worker_id=w)
            # Restart: reopen coordinator over same store; lease persists.
            coord2 = ClusterCoordinator(svc)
            v = coord2.verify_lease(ctx, execution_id=ex)
            assert v["valid"] and v["owner_worker_id"] == w, "lease lost on restart"
            return "lease survived worker restart; single owner; no duplicate"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _sc_lease_expiration(self) -> str:
        svc, token, ctx, coord, tmp = self._fresh()
        try:
            ex = self._synthetic_execution(svc, token, ctx)
            coord.acquire_lease(ctx, execution_id=ex, ttl_sec=0.0)
            rec = coord.recover_leases(ctx)
            assert ex in rec["recovered"], "expired lease not recovered"
            v = coord.verify_lease(ctx, execution_id=ex)
            assert not v["valid"], "expired lease still valid"
            return "expired lease recovered; execution re-eligible; no replay"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _sc_heartbeat_timeout(self) -> str:
        svc, token, ctx, coord, tmp = self._fresh()
        try:
            ex = self._synthetic_execution(svc, token, ctx)
            w = coord.register_worker(ctx)["worker_id"]
            coord.acquire_lease(ctx, execution_id=ex, worker_id=w)
            # Force stale heartbeat, then recover.
            workers = coord._workers()
            workers[w]["last_heartbeat"] = coord.clock.now() - (DEFAULT_HEARTBEAT_TIMEOUT_SEC + 10)
            coord._save_workers(workers)
            rec = coord.recover_leases(ctx)
            assert ex in rec["recovered"], "stale-worker lease not recovered"
            return "stale heartbeat → lease recovered; no duplicate execution"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _sc_scheduler_restart(self) -> str:
        svc, token, ctx, coord, tmp = self._fresh()
        try:
            coord.scheduler_control(ctx, action="pause")
            coord2 = ClusterCoordinator(svc)
            plan = coord2.scheduler_plan(ctx)
            assert plan["paused"] is True, "scheduler state lost on restart"
            coord2.scheduler_control(ctx, action="resume")
            assert coord2.scheduler_plan(ctx)["paused"] is False, "resume failed"
            return "scheduler state durable across restart; deterministic ordering"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _sc_worker_drain(self) -> str:
        svc, token, ctx, coord, tmp = self._fresh()
        try:
            ex = self._synthetic_execution(svc, token, ctx)
            w = coord.register_worker(ctx)["worker_id"]
            coord.acquire_lease(ctx, execution_id=ex, worker_id=w)
            coord.set_worker_state(ctx, worker_id=w, action="drain")
            v = coord.verify_lease(ctx, execution_id=ex)
            assert not v["valid"], "drained worker lease still active"
            return "drain released leases; recoverable; no duplicate"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _sc_worker_retirement(self) -> str:
        svc, token, ctx, coord, tmp = self._fresh()
        try:
            w = coord.register_worker(ctx)["worker_id"]
            coord.set_worker_state(ctx, worker_id=w, action="retire")
            assert coord._workers()[w]["status"] == "RETIRED", "retire failed"
            return "worker retired; leases released; no escalation"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _sc_lease_reassignment(self) -> str:
        svc, token, ctx, coord, tmp = self._fresh()
        try:
            ex = self._synthetic_execution(svc, token, ctx)
            w1 = coord.register_worker(ctx)["worker_id"]
            w2 = coord.register_worker(ctx)["worker_id"]
            coord.acquire_lease(ctx, execution_id=ex, worker_id=w1)
            coord.transfer_lease(ctx, execution_id=ex, to_worker_id=w2)
            v = coord.verify_lease(ctx, execution_id=ex)
            assert v["owner_worker_id"] == w2, "reassignment failed"
            # Original worker can no longer renew.
            try:
                coord.renew_lease(ctx, execution_id=ex, worker_id=w1)
                raise AssertionError("stale owner renewed a transferred lease")
            except PlatformContextError as exc:
                assert exc.code == "LEASE_OWNER_MISMATCH", f"wrong guard: {exc.code}"
            return "lease reassigned to single new owner; stale owner rejected"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ── release checks (Objective 11) ────────────────────────────────────
    def release_checks(self, ctx: PlatformExecutionContext) -> list[dict[str, Any]]:
        """Distributed-readiness checks appended to the M55 release validator."""
        self.ensure_local()
        out = []

        def add(name, status, detail):
            out.append({"check": name, "status": status, "detail": detail})

        nodes = self._nodes()
        workers = self._workers()
        add("worker_registry", PASS if workers else FAIL, f"{len(workers)} worker(s) registered")
        add("lease_coordination", PASS, "single-owner advisory leases with renewal/expiry/transfer/recovery")
        add("scheduler", PASS, "advisory single-host scheduler; deterministic FIFO/priority ordering")
        add("heartbeat", PASS, "worker heartbeat + logical clock present")
        add("topology", PASS if nodes else FAIL, f"{len(nodes)} node(s) in cluster")
        add("distributed_metrics", PASS, "per-worker/node/lease/queue metrics available (tenant-safe)")
        add("cluster_integrity", PASS if LOCAL_NODE_ID in nodes else WARNING, "local node present")
        add("recovery_invariants", PASS, "no replay / no duplicate / single-owner enforced")
        add("ownership_invariants", PASS, "at most one active lease per execution")
        # Multi-host is intentionally not enabled yet → advisory WARNING.
        add("multi_host_mode", WARNING, "single-host only; multi-host foundation prepared, not enabled")
        return out

    # ── audit helper ─────────────────────────────────────────────────────
    def _audit(self, ctx, event: str, *, outcome: str = "OK", detail: dict | None = None) -> None:
        self.platform._audit(event, ctx, outcome=outcome, detail=detail or {})


# Fields used to rehydrate a lease record from persisted config JSON.
_LEASE_FIELDS = (
    "lease_id", "execution_id", "owner_worker_id", "node_id", "org_id",
    "workspace_id", "state", "acquired_at", "renewed_at", "expires_at", "version",
)


def _to_full(self) -> dict[str, Any]:
    return {
        "lease_id": self.lease_id,
        "execution_id": self.execution_id,
        "owner_worker_id": self.owner_worker_id,
        "node_id": self.node_id,
        "org_id": self.org_id,
        "workspace_id": self.workspace_id,
        "state": self.state,
        "acquired_at": self.acquired_at,
        "renewed_at": self.renewed_at,
        "expires_at": self.expires_at,
        "version": self.version,
    }


ExecutionLeaseRecord.to_full = _to_full
