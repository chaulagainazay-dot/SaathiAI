"""M56 distributed runtime foundation — backend certification.

Worker registry, lease coordination, scheduler, topology, node health,
distributed metrics, and recovery certification. Additive, advisory, fail-closed,
single-host. PlatformAgentRuntime remains canonical; ExecutionGateway remains the
sole registered-tool authority; nothing here executes a tool.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from saathi.platform.bindings import BindingAdministrationService
from saathi.platform.cluster import (
    DEFAULT_HEARTBEAT_TIMEOUT_SEC,
    LOCAL_WORKER_ID,
    ClusterCoordinator,
)
from saathi.platform.context import PlatformContextError
from saathi.platform.release import PASS, ReleaseOperationsService
from saathi.platform.runtime import PlatformAgentRuntime
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture()
def alpha(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "m56.db")
    owner = platform.bootstrap_owner_secure(
        email="owner@m56.local", name="Owner", password="OwnerPassw0rd!",
        org_name="M56 Org", workspace_name="M56 Workspace",
    )
    return platform, owner["token"], platform.require_context(owner["token"])


def _execution(alpha):
    platform, token, ctx = alpha
    binding = BindingAdministrationService(platform).create(
        ctx, agent_id="cluster-agent", name="Cluster agent",
        allowed_tools=["m49.local_note_write"], allowed_capabilities=[],
        authority_ceiling="LOCAL_MUTATION",
    )
    with pytest.raises(PlatformContextError):
        PlatformAgentRuntime(platform).execute_token(
            token=token, tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v"}, capability="write",
            agent_id=binding.agent_id, binding_id=binding.binding_id,
            binding_version=binding.version, idempotency_key=f"m56-{binding.binding_id}",
        )
    return platform.store.list_platform_executions(binding_id=binding.binding_id)[0].execution_id


def _viewer(platform, owner_ctx):
    store = platform.store
    user = store.create_user(email="viewer@m56.local", name="Viewer")
    org = store.list_orgs_for_user(owner_ctx.user_id)[0]
    ws = store.list_workspaces(org.org_id)[0]
    store.add_member(org.org_id, user.user_id, "viewer")
    _, tok = store.create_session(
        user.user_id, "viewer-token", org_id=org.org_id,
        workspace_id=ws.workspace_id, role="viewer",
    )
    return platform.require_context(tok)


# ── worker registry ──────────────────────────────────────────────────────────
def test_worker_registry_register_heartbeat_and_states(alpha):
    platform, _, ctx = alpha
    c = ClusterCoordinator(platform)
    w = c.register_worker(ctx, capabilities=["platform-agent-runtime"])["worker_id"]
    hb = c.heartbeat(ctx, worker_id=w)
    assert hb["worker_id"] == w and hb["logical"] >= 1
    for action, state in [("pause", "PAUSED"), ("resume", "ACTIVE"), ("drain", "DRAINING"), ("retire", "RETIRED")]:
        assert c.set_worker_state(ctx, worker_id=w, action=action)["status"] == state


def test_worker_registry_requires_operate_authority(alpha):
    platform, _, ctx = alpha
    vctx = _viewer(platform, ctx)
    with pytest.raises(PlatformContextError) as err:
        ClusterCoordinator(platform).register_worker(vctx)
    assert err.value.code == "PERMISSION_DENIED"


# ── lease coordination ───────────────────────────────────────────────────────
def test_lease_lifecycle_and_single_owner(alpha):
    platform, _, ctx = alpha
    c = ClusterCoordinator(platform)
    ex = _execution(alpha)
    w1 = c.register_worker(ctx)["worker_id"]
    assert c.acquire_lease(ctx, execution_id=ex, worker_id=w1)["state"] == "HELD"
    assert c.renew_lease(ctx, execution_id=ex, worker_id=w1)["state"] == "RENEWED"
    assert c.verify_lease(ctx, execution_id=ex)["valid"] is True
    # A second worker cannot claim the same execution — no duplicate ownership.
    w2 = c.register_worker(ctx)["worker_id"]
    with pytest.raises(PlatformContextError) as err:
        c.acquire_lease(ctx, execution_id=ex, worker_id=w2)
    assert err.value.code == "LEASE_ALREADY_HELD"


def test_lease_transfer_reassigns_single_owner(alpha):
    platform, _, ctx = alpha
    c = ClusterCoordinator(platform)
    ex = _execution(alpha)
    w1 = c.register_worker(ctx)["worker_id"]
    w2 = c.register_worker(ctx)["worker_id"]
    c.acquire_lease(ctx, execution_id=ex, worker_id=w1)
    c.transfer_lease(ctx, execution_id=ex, to_worker_id=w2)
    assert c.verify_lease(ctx, execution_id=ex)["owner_worker_id"] == w2
    with pytest.raises(PlatformContextError) as err:
        c.renew_lease(ctx, execution_id=ex, worker_id=w1)
    assert err.value.code == "LEASE_OWNER_MISMATCH"


def test_lease_recovery_on_stale_worker(alpha):
    platform, _, ctx = alpha
    c = ClusterCoordinator(platform)
    ex = _execution(alpha)
    w = c.register_worker(ctx)["worker_id"]
    c.acquire_lease(ctx, execution_id=ex, worker_id=w)
    workers = c._workers()
    workers[w]["last_heartbeat"] = c.clock.now() - (DEFAULT_HEARTBEAT_TIMEOUT_SEC + 10)
    c._save_workers(workers)
    result = c.recover_leases(ctx)
    assert ex in result["recovered"]
    assert c.verify_lease(ctx, execution_id=ex)["valid"] is False


def test_lease_cross_tenant_isolation(alpha):
    platform, _, ctx = alpha
    c = ClusterCoordinator(platform)
    ex = _execution(alpha)
    c.acquire_lease(ctx, execution_id=ex)
    # Another tenant cannot see or acquire this lease.
    store = platform.store
    user = store.create_user(email="o2@m56.local", name="O2")
    org = store.create_org("Org2", user.user_id)
    ws = store.create_workspace(org.org_id, "WS2", user.user_id)
    store.add_member(org.org_id, user.user_id, "owner")
    _, tok = store.create_session(user.user_id, "t2", org_id=org.org_id, workspace_id=ws.workspace_id, role="owner")
    other = platform.require_context(tok)
    assert c.verify_lease(other, execution_id=ex)["valid"] is False
    with pytest.raises(PlatformContextError):
        c.acquire_lease(other, execution_id=ex)


# ── scheduler ────────────────────────────────────────────────────────────────
def test_scheduler_plan_and_control_persist(alpha):
    platform, _, ctx = alpha
    c = ClusterCoordinator(platform)
    _execution(alpha)
    plan = c.scheduler_plan(ctx)
    assert plan["execution_mode"] == "single_host_inline"
    assert plan["pending"] >= 1
    assert c.scheduler_control(ctx, action="pause")["paused"] is True
    assert ClusterCoordinator(platform).scheduler_plan(ctx)["paused"] is True
    assert c.scheduler_control(ctx, action="resume")["paused"] is False


# ── topology / node health / metrics ─────────────────────────────────────────
def test_topology_is_read_only_and_scoped(alpha):
    platform, _, ctx = alpha
    c = ClusterCoordinator(platform)
    topo = c.topology(ctx)
    assert topo["cluster"]["nodes"] >= 1
    assert topo["canonical_runtime"] == "PlatformAgentRuntime"
    assert topo["registered_tool_authority"] == "ExecutionGateway"


def test_node_health_and_metrics_expose_no_secrets(alpha):
    platform, _, ctx = alpha
    c = ClusterCoordinator(platform)
    blob = (json.dumps(c.node_health(ctx)) + json.dumps(c.distributed_metrics(ctx))).lower()
    for forbidden in ("password", "token", "secret", "db_path", ".db", "/users/", "authorization"):
        assert forbidden not in blob
    nh = c.node_health(ctx)["nodes"]
    assert "node-local" in nh and nh["node-local"]["worker_count"] >= 1


# ── recovery certification ───────────────────────────────────────────────────
def test_recovery_certification_all_scenarios_pass(alpha):
    platform, _, ctx = alpha
    result = ClusterCoordinator(platform).recovery_certify(ctx)
    assert result["overall"] == PASS
    scenarios = {s["scenario"]: s["status"] for s in result["scenarios"]}
    for name in (
        "worker_restart", "lease_expiration", "heartbeat_timeout", "scheduler_restart",
        "worker_drain", "worker_retirement", "lease_reassignment",
    ):
        assert scenarios[name] == PASS, f"{name}: {scenarios[name]}"
    assert "no_replay" in result["invariants"]


def test_recovery_requires_owner_authority(alpha):
    platform, _, ctx = alpha
    vctx = _viewer(platform, ctx)
    with pytest.raises(PlatformContextError) as err:
        ClusterCoordinator(platform).recovery_certify(vctx)
    assert err.value.code == "PERMISSION_DENIED"


# ── release validator integration ────────────────────────────────────────────
def test_release_validator_includes_distributed_checks(alpha):
    platform, _, ctx = alpha
    report = ReleaseOperationsService(platform).release_validate(ctx)
    checks = {c["check"]: c["status"] for c in report["checks"]}
    assert checks.get("worker_registry") == PASS
    assert checks.get("lease_coordination") == PASS
    assert checks.get("ownership_invariants") == PASS
    assert checks.get("multi_host_mode") == "WARNING"
    assert report["production_authorized"] is False


# ── API surface ──────────────────────────────────────────────────────────────
def test_api_cluster_routes(alpha):
    from saathi.server import app

    platform, token, _ = alpha
    ex = _execution(alpha)
    client = TestClient(app)
    h = {"X-Platform-Token": token}

    assert client.get("/api/v1/platform/cluster/topology", headers=h).status_code == 200
    assert client.get("/api/v1/platform/cluster/node-health", headers=h).status_code == 200
    assert client.get("/api/v1/platform/cluster/metrics", headers=h).status_code == 200
    assert client.get("/api/v1/platform/cluster/scheduler", headers=h).status_code == 200

    reg = client.post("/api/v1/platform/cluster/workers/register", json={"capabilities": ["x"]}, headers=h)
    assert reg.status_code == 200
    wid = reg.json()["worker"]["worker_id"]

    acq = client.post(
        "/api/v1/platform/cluster/leases/acquire",
        json={"execution_id": ex, "worker_id": wid}, headers=h,
    )
    assert acq.status_code == 200 and acq.json()["lease"]["state"] == "HELD"

    rec = client.post("/api/v1/platform/cluster/recovery", headers=h)
    assert rec.status_code == 200 and rec.json()["recovery"]["overall"] in (PASS, "WARNING")

    assert client.get("/api/v1/platform/cluster/topology").status_code in (401, 403)
