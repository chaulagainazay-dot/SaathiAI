"""M103–M111 Distributed Worker Execution and Fleet Runtime — focused tests.

Extends M56; never allows direct tool execution or approval bypass.
"""
from __future__ import annotations

import time

import pytest

from saathi.platform.cluster import ClusterCoordinator
from saathi.platform.context import PlatformContextError
from saathi.platform.fleet import (
    DistributedWorkerRuntime,
    WorkerTrustState,
    reset_fleet_runtime_for_tests,
)
from saathi.platform.fleet import limits
from saathi.platform.fleet.models import ReconciliationOutcome
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture()
def env(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "fleet.db")
    boot = platform.bootstrap_owner_secure(
        email="fleet-owner@local",
        name="Fleet Owner",
        password="FleetOwnerPass1!",
    )
    ctx = platform.require_context(boot["token"])
    fleet = DistributedWorkerRuntime(platform)
    yield platform, boot["token"], ctx, fleet
    reset_fleet_runtime_for_tests(platform)
    reset_platform_for_tests()
    reset_registry_for_tests()


def _worker_payload(wid: str, **extra):
    base = {
        "worker_id": wid,
        "protocol_version": limits.PROTOCOL_VERSION,
        "runtime_version": limits.RUNTIME_VERSION,
        "process_instance_id": f"proc-{wid}",
        "capability_set": ["planning", "analysis", "testing", "platform-agent-runtime"],
        "bind_host": "127.0.0.1",
        "resource_limits": {"max_active_leases": 2, "allow_browser": False},
    }
    base.update(extra)
    return base


def _admit_two(fleet, ctx):
    w1 = fleet.register_worker(ctx, _worker_payload("wrk_a"))["worker"]
    w2 = fleet.register_worker(
        ctx,
        _worker_payload(
            "wrk_b",
            capability_set=[
                "planning",
                "analysis",
                "testing",
                "coding",
                "platform-agent-runtime",
            ],
        ),
    )["worker"]
    assert w1["trust_state"] == WorkerTrustState.TRUSTED_LOCAL.value
    assert w2["trust_state"] == WorkerTrustState.TRUSTED_LOCAL.value
    return w1, w2


# ── M103 identity & admission ───────────────────────────────────────────────
def test_register_and_admit_loopback_worker(env):
    _, _, ctx, fleet = env
    res = fleet.register_worker(ctx, _worker_payload("wrk_1"))
    assert res["admission"]["admitted"] is True
    assert res["worker"]["trust_state"] == "TRUSTED_LOCAL"
    assert res["worker"]["admission_state"] == "ADMITTED"
    assert res["worker"]["bind_host"] == "127.0.0.1"


def test_reject_public_listener_and_forbidden_caps(env):
    _, _, ctx, fleet = env
    with pytest.raises(PlatformContextError) as err:
        # quarantine path returns worker but admitted false — register still returns
        res = fleet.register_worker(
            ctx,
            _worker_payload(
                "wrk_pub",
                bind_host="0.0.0.0",
                public_listener=True,
                capability_set=["direct_tool_execution", "planning"],
            ),
        )
        assert res["admission"]["admitted"] is False
        raise PlatformContextError("WORKER_REJECTED", "not admitted")
    # Prefer soft reject:
    res = fleet.register_worker(
        ctx,
        _worker_payload(
            "wrk_pub2",
            bind_host="0.0.0.0",
            capability_set=["planning", "direct_tool_execution"],
        ),
    )
    assert res["admission"]["admitted"] is False
    assert res["worker"]["trust_state"] == "QUARANTINED"
    assert any("forbidden" in r or "non_loopback" in r for r in res["admission"]["reasons"])


def test_protocol_mismatch_rejected(env):
    _, _, ctx, fleet = env
    res = fleet.register_worker(
        ctx, _worker_payload("wrk_proto", protocol_version="fleet.v0")
    )
    assert res["admission"]["admitted"] is False


def test_duplicate_live_identity_quarantined(env):
    _, _, ctx, fleet = env
    fleet.register_worker(ctx, _worker_payload("wrk_dup", process_instance_id="p1"))
    with pytest.raises(PlatformContextError) as err:
        fleet.register_worker(ctx, _worker_payload("wrk_dup", process_instance_id="p2"))
    assert err.value.code == "DUPLICATE_WORKER_IDENTITY"


def test_revoked_worker_denied(env):
    _, _, ctx, fleet = env
    fleet.register_worker(ctx, _worker_payload("wrk_rev"))
    fleet.revoke_worker(ctx, "wrk_rev", reason="test")
    with pytest.raises(PlatformContextError) as err:
        fleet.register_worker(ctx, _worker_payload("wrk_rev", process_instance_id="p-new"))
    assert err.value.code == "WORKER_REVOKED"


def test_viewer_cannot_register(env):
    platform, _, ctx, fleet = env
    store = platform.store
    user = store.create_user(email="viewer@fleet.local", name="Viewer")
    org = store.list_orgs_for_user(ctx.user_id)[0]
    ws = store.list_workspaces(org.org_id)[0]
    store.add_member(org.org_id, user.user_id, "viewer")
    _, tok = store.create_session(
        user.user_id, "viewer-tok", org_id=org.org_id, workspace_id=ws.workspace_id, role="viewer"
    )
    vctx = platform.require_context(tok)
    with pytest.raises(PlatformContextError) as err:
        fleet.register_worker(vctx, _worker_payload("wrk_v"))
    assert err.value.code == "PERMISSION_DENIED"


# ── M104 matching & scheduling ──────────────────────────────────────────────
def test_deterministic_matching_and_tiebreak(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    node = {
        "work_node_id": "node-1",
        "required_capabilities": ["planning"],
        "dependencies_complete": True,
        "approval_state": "not_required",
    }
    d1 = fleet.match_worker(ctx, node, seed="s1")
    d2 = fleet.match_worker(ctx, node, seed="s1")
    assert d1.selected_worker_id == d2.selected_worker_id
    assert d1.selected_worker_id in ("wrk_a", "wrk_b")
    assert d1.tie_breaking_rule
    assert d1.candidates


def test_separation_of_duties(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    node = {
        "work_node_id": "node-sod",
        "required_capabilities": ["planning"],
        "dependencies_complete": True,
        "sod_exclude_workers": ["wrk_a"],
    }
    d = fleet.match_worker(ctx, node)
    assert d.selected_worker_id == "wrk_b"
    assert any(r["reason"] == "separation_of_duties" for r in d.rejected)


def test_approval_blocks_match_and_lease(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    node = {
        "work_node_id": "node-appr",
        "required_capabilities": ["planning"],
        "dependencies_complete": True,
        "approval_state": "pending",
        "approval_required": True,
    }
    d = fleet.match_worker(ctx, node)
    assert d.lease_result == "BLOCKED_APPROVAL"
    with pytest.raises(PlatformContextError) as err:
        fleet.acquire_lease(ctx, work_node=node)
    assert err.value.code == "APPROVAL_REQUIRED"


def test_resource_aware_prefers_lower_load(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    # Give wrk_a a lease so wrk_b is preferred
    fleet.acquire_lease(
        ctx,
        work_node={
            "work_node_id": "n-load-1",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
        },
        worker_id="wrk_a",
    )
    d = fleet.match_worker(
        ctx,
        {
            "work_node_id": "n-load-2",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
        },
    )
    assert d.selected_worker_id == "wrk_b"


# ── M105 leases, fencing, heartbeats ────────────────────────────────────────
def test_atomic_lease_and_fencing_monotonic(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    a = fleet.acquire_lease(
        ctx,
        work_node={
            "work_node_id": "n1",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
        },
    )
    b = fleet.acquire_lease(
        ctx,
        work_node={
            "work_node_id": "n2",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
        },
    )
    assert a["lease"]["fencing_token"] < b["lease"]["fencing_token"]
    with pytest.raises(PlatformContextError) as err:
        fleet.acquire_lease(
            ctx,
            work_node={
                "work_node_id": "n1",
                "required_capabilities": ["planning"],
                "dependencies_complete": True,
            },
        )
    assert err.value.code == "LEASE_ALREADY_HELD"


def test_renew_requires_fence_and_health(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    issued = fleet.acquire_lease(
        ctx,
        work_node={
            "work_node_id": "n-ren",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
        },
        worker_id="wrk_a",
    )
    lease = issued["lease"]
    fleet.heartbeat(ctx, "wrk_a", {"cpu_pressure": 10, "memory_pressure": 10})
    renewed = fleet.renew_lease(
        ctx,
        lease_id=lease["lease_id"],
        worker_id="wrk_a",
        fencing_token=lease["fencing_token"],
    )
    assert renewed["lease"]["state"] == "RENEWED"
    with pytest.raises(PlatformContextError) as err:
        fleet.renew_lease(
            ctx,
            lease_id=lease["lease_id"],
            worker_id="wrk_a",
            fencing_token=lease["fencing_token"] - 1,
        )
    assert err.value.code == "FENCING_MISMATCH"


def test_heartbeat_strips_secrets_and_bounds_size(env):
    _, _, ctx, fleet = env
    fleet.register_worker(ctx, _worker_payload("wrk_hb"))
    with pytest.raises(PlatformContextError) as err:
        fleet.heartbeat(ctx, "wrk_hb", {"secrets": {"x": 1}})
    assert err.value.code == "HEARTBEAT_FORBIDDEN_FIELD"
    ok = fleet.heartbeat(ctx, "wrk_hb", {"cpu_pressure": 5, "queue_depth": 1})
    assert ok["heartbeat"]["worker_id"] == "wrk_hb"


# ── M106/M107 execution contract & reconciliation ───────────────────────────
def test_execution_never_direct_tools(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    issued = fleet.acquire_lease(
        ctx,
        work_node={
            "work_node_id": "n-exec",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
        },
        worker_id="wrk_a",
    )
    lease = issued["lease"]
    out = fleet.execute_leased_work(
        ctx,
        lease_id=lease["lease_id"],
        worker_id="wrk_a",
        fencing_token=lease["fencing_token"],
        arguments={"text": "hello"},
    )
    assert out["direct_tool_execution"] is False
    assert out["execution_path"] in (
        "simulated_readonly_worker",
        "PlatformAgentRuntime→ExecutionGateway",
    )
    req = fleet.build_execution_request(ctx, lease["lease_id"])
    assert req["direct_tool_execution"] is False
    assert req["execution_authority"] == "PlatformAgentRuntime→ExecutionGateway"
    assert req["transport"] == "loopback_only"
    assert req["bind_host"] == "127.0.0.1"


def test_stale_and_duplicate_results_rejected(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    issued = fleet.acquire_lease(
        ctx,
        work_node={
            "work_node_id": "n-res",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
        },
        worker_id="wrk_a",
    )
    lease = issued["lease"]
    accepted = fleet.reconcile_result(
        ctx,
        lease_id=lease["lease_id"],
        worker_id="wrk_a",
        fencing_token=lease["fencing_token"],
        result={"status": "ok", "value": 1},
    )
    assert accepted["outcome"] == ReconciliationOutcome.ACCEPTED.value
    assert accepted["advances_graph"] is True

    dup = fleet.reconcile_result(
        ctx,
        lease_id=lease["lease_id"],
        worker_id="wrk_a",
        fencing_token=lease["fencing_token"],
        result={"status": "ok", "value": 1},
    )
    assert dup["outcome"] == ReconciliationOutcome.REJECTED_DUPLICATE.value
    assert dup["advances_graph"] is False

    stale = fleet.reconcile_result(
        ctx,
        lease_id=lease["lease_id"],
        worker_id="wrk_a",
        fencing_token=lease["fencing_token"] + 99,
        result={"status": "ok", "value": 2},
    )
    assert stale["outcome"] == ReconciliationOutcome.REJECTED_STALE.value
    assert stale["advances_graph"] is False


def test_late_result_after_expiry_rejected(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    issued = fleet.acquire_lease(
        ctx,
        work_node={
            "work_node_id": "n-late",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
        },
        worker_id="wrk_a",
        ttl_sec=1.0,
    )
    lease = issued["lease"]
    # Force expiry
    leases = fleet._leases()
    rec = leases[lease["lease_id"]]
    rec["expires_at"] = time.time() - 10
    fleet._save_leases(leases)
    late = fleet.reconcile_result(
        ctx,
        lease_id=lease["lease_id"],
        worker_id="wrk_a",
        fencing_token=lease["fencing_token"],
        result={"status": "late"},
    )
    assert late["outcome"] == ReconciliationOutcome.REJECTED_STALE.value


def test_cancel_rejects_results_and_no_orphan(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    issued = fleet.acquire_lease(
        ctx,
        work_node={
            "work_node_id": "n-can",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
            "mission_id": "m-1",
        },
        worker_id="wrk_a",
    )
    lease = issued["lease"]
    cancel = fleet.cancel(ctx, scope="lease", target_id=lease["lease_id"])
    assert lease["lease_id"] in cancel["cancelled_leases"]
    rejected = fleet.reconcile_result(
        ctx,
        lease_id=lease["lease_id"],
        worker_id="wrk_a",
        fencing_token=lease["fencing_token"],
        result={"status": "done"},
    )
    assert rejected["outcome"] == ReconciliationOutcome.REJECTED_CANCELLED.value
    # No open active leases for node
    open_active = [
        l
        for l in fleet.list_leases(ctx)["leases"]
        if l["work_node_id"] == "n-can" and l.get("active")
    ]
    assert open_active == []


def test_event_replay_rejected(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    issued = fleet.acquire_lease(
        ctx,
        work_node={
            "work_node_id": "n-ev",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
        },
        worker_id="wrk_a",
    )
    lease = issued["lease"]
    fleet.ingest_event(
        ctx,
        {
            "lease_id": lease["lease_id"],
            "worker_id": "wrk_a",
            "fencing_token": lease["fencing_token"],
            "event_type": "progress",
            "sequence": 1,
            "payload": {"pct": 10},
        },
    )
    with pytest.raises(PlatformContextError) as err:
        fleet.ingest_event(
            ctx,
            {
                "lease_id": lease["lease_id"],
                "worker_id": "wrk_a",
                "fencing_token": lease["fencing_token"],
                "event_type": "progress",
                "sequence": 1,
                "payload": {"pct": 10},
            },
        )
    assert err.value.code == "EVENT_REPLAY"


# ── M108 recovery, reassignment, drain ──────────────────────────────────────
def test_worker_loss_recovery_and_reassign_new_fence(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    issued = fleet.acquire_lease(
        ctx,
        work_node={
            "work_node_id": "n-loss",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
        },
        worker_id="wrk_a",
    )
    old = issued["lease"]
    # Simulate heartbeat loss
    workers = fleet._workers()
    workers["wrk_a"]["last_heartbeat"] = time.time() - 1000
    fleet._save_workers(workers)
    recovery = fleet.recover_lost_workers(ctx)
    assert "wrk_a" in recovery["lost_workers"] or any(
        e["work_node_id"] == "n-loss" for e in recovery["expired_leases"]
    )
    reassigned = fleet.reassign_work(
        ctx,
        work_node={
            "work_node_id": "n-loss",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
        },
        previous_lease_id=old["lease_id"],
    )
    new_lease = reassigned["new_lease"]
    assert new_lease["fencing_token"] > old["fencing_token"]
    assert new_lease["worker_id"] in ("wrk_a", "wrk_b")
    # Stale result from old fence rejected
    stale = fleet.reconcile_result(
        ctx,
        lease_id=old["lease_id"],
        worker_id="wrk_a",
        fencing_token=old["fencing_token"],
        result={"status": "stale-late"},
    )
    assert stale["outcome"] in (
        ReconciliationOutcome.REJECTED_STALE.value,
        ReconciliationOutcome.REJECTED_CANCELLED.value,
    ) or stale["advances_graph"] is False
    # New lease accepts
    ok = fleet.reconcile_result(
        ctx,
        lease_id=new_lease["lease_id"],
        worker_id=new_lease["worker_id"],
        fencing_token=new_lease["fencing_token"],
        result={"status": "recovered"},
    )
    assert ok["outcome"] == ReconciliationOutcome.ACCEPTED.value


def test_drain_blocks_new_leases(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    fleet.drain_worker(ctx, "wrk_a")
    d = fleet.match_worker(
        ctx,
        {
            "work_node_id": "n-drain",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
        },
    )
    assert d.selected_worker_id != "wrk_a"
    assert d.selected_worker_id == "wrk_b"


def test_quarantine_revokes_leases(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    issued = fleet.acquire_lease(
        ctx,
        work_node={
            "work_node_id": "n-q",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
        },
        worker_id="wrk_a",
    )
    q = fleet.quarantine_worker(ctx, "wrk_a", reason="suspicious")
    assert q["worker"]["trust_state"] == "QUARANTINED"
    assert issued["lease"]["lease_id"] in q["cancelled"]["cancelled_leases"]


# ── Integration: parallel dispatch, M56 extension, tenant isolation ─────────
def test_bounded_parallel_dispatch_two_nodes(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    out = fleet.dispatch_ready_nodes(
        ctx,
        nodes=[
            {
                "work_node_id": "p1",
                "required_capabilities": ["planning"],
                "dependencies_complete": True,
            },
            {
                "work_node_id": "p2",
                "required_capabilities": ["analysis"],
                "dependencies_complete": True,
            },
            {
                "work_node_id": "p3",
                "required_capabilities": ["planning"],
                "dependencies_complete": True,
                "approval_required": True,
                "approval_state": "pending",
            },
        ],
        mission_id="mission-parallel",
    )
    assert out["dispatched_count"] == 2
    assert out["blocked_count"] == 1
    assert out["blocked"][0]["reason"] == "approval_required"
    workers_used = {d["lease"]["worker_id"] for d in out["dispatched"]}
    assert len(workers_used) >= 1


def test_extends_m56_not_replace(env):
    platform, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    cluster = ClusterCoordinator(platform)
    topo = cluster.topology(ctx)
    assert "nodes" in topo or "workers" in topo or "schema_version" in topo
    h = fleet.health(ctx)
    assert h["extends"] == "M56_ClusterCoordinator"
    assert h["production_authorized"] is False
    assert h["public_listener"] is False
    cert = fleet.certify_fleet(ctx)
    assert cert["extends_m56"] is True
    assert cert["replaces_m56"] is False
    assert cert["direct_tool_execution"] is False


def test_tenant_workspace_isolation(env):
    platform, _, ctx, fleet = env
    fleet.register_worker(ctx, _worker_payload("wrk_t1"))
    other_user = platform.store.create_user(email="other-fleet@local", name="Other")
    other_org = platform.store.create_org("Other Org", other_user.user_id)
    other_ws = platform.store.create_workspace(
        other_org.org_id, "Other WS", other_user.user_id
    )
    platform.store.add_member(other_org.org_id, other_user.user_id, "owner")
    _, other_tok = platform.store.create_session(
        other_user.user_id,
        "other-fleet-tok",
        org_id=other_org.org_id,
        workspace_id=other_ws.workspace_id,
        role="owner",
    )
    octx = platform.require_context(other_tok)
    with pytest.raises(PlatformContextError):
        fleet.get_worker(octx, "wrk_t1")


def test_conversation_controls_no_direct_command(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    r = fleet.command_from_conversation(ctx, "Which workers are healthy?")
    assert r["intent"] == "list_health"
    assert r["direct_worker_command"] is False
    assert r["executed"] is True
    r2 = fleet.command_from_conversation(ctx, "Pause dispatch because memory pressure is high")
    assert r2["intent"] == "pause_dispatch"
    assert fleet.health(ctx)["dispatch_paused"] is True


def test_stale_lease_cannot_execute(env):
    _, _, ctx, fleet = env
    _admit_two(fleet, ctx)
    issued = fleet.acquire_lease(
        ctx,
        work_node={
            "work_node_id": "n-stale-exec",
            "required_capabilities": ["planning"],
            "dependencies_complete": True,
        },
        worker_id="wrk_a",
        ttl_sec=1.0,
    )
    lease = issued["lease"]
    leases = fleet._leases()
    leases[lease["lease_id"]]["expires_at"] = time.time() - 5
    fleet._save_leases(leases)
    with pytest.raises(PlatformContextError) as err:
        fleet.execute_leased_work(
            ctx,
            lease_id=lease["lease_id"],
            worker_id="wrk_a",
            fencing_token=lease["fencing_token"],
        )
    assert err.value.code == "LEASE_INVALID"


def test_m56_regression_still_passes_coordinator(env):
    """Smoke: M56 ClusterCoordinator still works alongside fleet."""
    platform, _, ctx, fleet = env
    c = ClusterCoordinator(platform)
    w = c.register_worker(ctx, capabilities=["platform-agent-runtime"])
    hb = c.heartbeat(ctx, worker_id=w["worker_id"])
    assert hb["worker_id"] == w["worker_id"]
    plan = c.scheduler_plan(ctx)
    assert plan["execution_mode"] == "single_host_inline"
