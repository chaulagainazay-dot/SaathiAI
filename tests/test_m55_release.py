"""M55 release-candidate operational excellence — backend certification.

Health, metrics, backup validation, recovery certification, and the release
validator/gate. All advisory, tenant-scoped, fail-closed, additive. Nothing here
enables production, connectors, financial, or trading execution.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from saathi.platform.bindings import BindingAdministrationService
from saathi.platform.context import PlatformContextError
from saathi.platform.release import (
    FAIL,
    PASS,
    READY_WITH_LIMITATIONS,
    ReleaseOperationsService,
)
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture()
def alpha(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "m55.db")
    owner = platform.bootstrap_owner_secure(
        email="owner@m55.local", name="Owner", password="OwnerPassw0rd!",
        org_name="M55 Org", workspace_name="M55 Workspace",
    )
    return platform, owner["token"], platform.require_context(owner["token"])


def _viewer(platform, owner_ctx):
    store = platform.store
    user = store.create_user(email="viewer@m55.local", name="Viewer")
    org = store.list_orgs_for_user(owner_ctx.user_id)[0]
    ws = store.list_workspaces(org.org_id)[0]
    store.add_member(org.org_id, user.user_id, "viewer")
    _, tok = store.create_session(
        user.user_id, "viewer-token", org_id=org.org_id,
        workspace_id=ws.workspace_id, role="viewer",
    )
    return platform.require_context(tok)


# ── health & metrics ─────────────────────────────────────────────────────────
def test_health_reports_bounded_tenant_safe_status(alpha):
    platform, _, ctx = alpha
    health = ReleaseOperationsService(platform).health(ctx)
    for key in (
        "uptime_seconds", "memory_rss_kib", "queue_depth", "pending_approvals",
        "storage_bytes", "database_status", "api_latency_ms", "tenant_counts",
        "workspace_counts", "active_sessions",
    ):
        assert key in health, f"missing {key}"
    assert health["production_authorized"] is False
    assert health["database_status"] == "available"
    assert health["active_sessions"] >= 1


def test_health_and_metrics_expose_no_secrets(alpha):
    platform, _, ctx = alpha
    svc = ReleaseOperationsService(platform)
    blob = (json.dumps(svc.health(ctx)) + json.dumps(svc.metrics(ctx))).lower()
    for forbidden in ("password", "token", "secret", "db_path", ".db", "/users/", "authorization"):
        assert forbidden not in blob


def test_metrics_shape(alpha):
    platform, _, ctx = alpha
    metrics = ReleaseOperationsService(platform).metrics(ctx)
    assert metrics["execution_totals"] == 0
    assert metrics["restart_count"] == "UNKNOWN"
    assert "runtime_attention_reasons" in metrics


# ── backup validation ────────────────────────────────────────────────────────
def test_backup_validation_is_simulation_only(alpha):
    platform, _, ctx = alpha
    manifest = ReleaseOperationsService(platform).backup_validate(ctx)
    assert manifest["destructive_restore"] is False
    assert manifest["mode"] == "SIMULATION_ONLY"
    assert manifest["integrity_check"] == "ok"
    assert manifest["restore_simulation"] == "PASS"
    assert manifest["checksum"].startswith("sha256:")
    assert "/" not in manifest["database_name"]  # basename only, no path


def test_backup_requires_owner_authority(alpha):
    platform, _, ctx = alpha
    vctx = _viewer(platform, ctx)
    with pytest.raises(PlatformContextError) as err:
        ReleaseOperationsService(platform).backup_validate(vctx)
    assert err.value.code == "PERMISSION_DENIED"


# ── recovery certification ───────────────────────────────────────────────────
def test_recovery_certification_all_scenarios_pass(alpha):
    platform, _, ctx = alpha
    result = ReleaseOperationsService(platform).recovery_certify(ctx)
    assert result["overall"] == PASS
    scenarios = {s["scenario"]: s["status"] for s in result["scenarios"]}
    assert scenarios["process_restart"] == PASS
    assert scenarios["restart_after_dispatch_recorded"] == PASS
    assert scenarios["binding_interruption"] == PASS
    assert "no_replay" in result["invariants"]


def test_recovery_requires_owner_authority(alpha):
    platform, _, ctx = alpha
    vctx = _viewer(platform, ctx)
    with pytest.raises(PlatformContextError) as err:
        ReleaseOperationsService(platform).recovery_certify(vctx)
    assert err.value.code == "PERMISSION_DENIED"


# ── release validator ────────────────────────────────────────────────────────
def test_release_validator_ready_with_limitations_and_no_fail(alpha):
    platform, _, ctx = alpha
    report = ReleaseOperationsService(platform).release_validate(ctx)
    assert report["overall"] == READY_WITH_LIMITATIONS
    assert report["production_authorized"] is False
    statuses = {c["check"]: c["status"] for c in report["checks"]}
    assert statuses["runtime"] == PASS
    assert statuses["tenant_isolation"] == PASS
    assert statuses["evidence_export"] == PASS
    assert statuses["production_mode"] == "WARNING"
    assert report["summary"].get(FAIL, 0) == 0
    assert 0 <= report["readiness_score"] <= 100


def test_release_validator_requires_owner_authority(alpha):
    platform, _, ctx = alpha
    vctx = _viewer(platform, ctx)
    with pytest.raises(PlatformContextError) as err:
        ReleaseOperationsService(platform).release_validate(vctx)
    assert err.value.code == "PERMISSION_DENIED"


# ── release-check CLI ────────────────────────────────────────────────────────
def test_release_check_cli_builds_deterministic_report():
    from saathi.platform.release_check import build_report

    report = build_report()
    assert report["overall_status"] in ("READY", "READY_WITH_LIMITATIONS")
    assert report["production_authorized"] is False
    assert report["authority"]["registered_tool_authority"] == "ExecutionGateway"
    sections = {s["section"] for s in report["sections"]}
    for required in ("architecture", "runtime", "recovery", "health", "backup", "documentation"):
        assert required in sections


# ── API surface ──────────────────────────────────────────────────────────────
def test_api_release_routes(alpha):
    from saathi.server import app

    platform, token, _ = alpha
    client = TestClient(app)
    h = {"X-Platform-Token": token}

    assert client.get("/api/v1/platform/release/health", headers=h).status_code == 200
    assert client.get("/api/v1/platform/release/metrics", headers=h).status_code == 200

    val = client.post("/api/v1/platform/release/validate", headers=h)
    assert val.status_code == 200
    assert val.json()["release"]["production_authorized"] is False

    backup = client.post("/api/v1/platform/release/backup", headers=h)
    assert backup.status_code == 200
    assert backup.json()["backup"]["destructive_restore"] is False

    recovery = client.post("/api/v1/platform/release/recovery", headers=h)
    assert recovery.status_code == 200
    assert recovery.json()["recovery"]["overall"] in (PASS, "WARNING")

    assert client.get("/api/v1/platform/release/health").status_code in (401, 403)
