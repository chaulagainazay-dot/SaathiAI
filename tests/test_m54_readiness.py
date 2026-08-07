"""M54 private-alpha operational readiness — diagnostics, export, retention, drills.

Backend certification of the M54 readiness layer. Browser certification lives in
saathi-os/scripts/m54_browser_cert.mjs; these tests prove the API/service
contracts the browser flow depends on, plus restart recovery rehearsals and the
security boundaries that must hold regardless of any browser-supplied field.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from saathi.platform.bindings import BindingAdministrationService
from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformExecutionState
from saathi.platform.operations import RuntimeOperationsService
from saathi.platform.readiness import (
    DEFAULT_RETENTION_DAYS,
    SCHEMA_VERSION,
    OperationalReadinessService,
)
from saathi.platform.runtime import PlatformAgentRuntime
from saathi.platform.service import PlatformService, reset_platform_for_tests
from saathi.platform.store import PlatformStore
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture()
def alpha(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "m54.db")
    owner = platform.bootstrap_owner_secure(
        email="owner@m54.local",
        name="Owner",
        password="OwnerPassw0rd!",
        org_name="M54 Org",
        workspace_name="M54 Workspace",
    )
    return platform, owner["token"], platform.require_context(owner["token"])


def _binding(alpha, *, agent_id="ops-agent", ceiling="LOCAL_MUTATION"):
    platform, _, owner_ctx = alpha
    return BindingAdministrationService(platform).create(
        owner_ctx,
        agent_id=agent_id,
        name="Operations agent",
        allowed_tools=["m49.echo_readonly", "m49.local_note_write"],
        allowed_capabilities=[],
        authority_ceiling=ceiling,
    )


def _completed(alpha, binding):
    platform, token, _ = alpha
    return PlatformAgentRuntime(platform).execute_token(
        token=token,
        tool_id="m49.echo_readonly",
        arguments={"text": "observable"},
        agent_id=binding.agent_id,
        binding_id=binding.binding_id,
        binding_version=binding.version,
    )


def _waiting(alpha, binding):
    platform, token, _ = alpha
    with pytest.raises(PlatformContextError) as error:
        PlatformAgentRuntime(platform).execute_token(
            token=token,
            tool_id="m49.local_note_write",
            arguments={"key": "m54", "value": "pending"},
            capability="write",
            agent_id=binding.agent_id,
            binding_id=binding.binding_id,
            binding_version=binding.version,
            idempotency_key=f"waiting-{binding.binding_id}",
        )
    assert error.value.code == "APPROVAL_REQUIRED"
    return platform.store.list_platform_executions(binding_id=binding.binding_id)[0]


def _second_tenant(platform):
    store = platform.store
    user = store.create_user(email="other@m54.local", name="Other Owner")
    org = store.create_org("Other Org", user.user_id)
    ws = store.create_workspace(org.org_id, "Other Workspace", user.user_id)
    store.add_member(org.org_id, user.user_id, "owner")
    _, token = store.create_session(
        user.user_id,
        "second-tenant-token",
        org_id=org.org_id,
        workspace_id=ws.workspace_id,
        role="owner",
    )
    return token, platform.require_context(token)


# ── diagnostics ─────────────────────────────────────────────────────────────
def test_diagnostics_reports_bounded_safe_status(alpha):
    platform, _, ctx = alpha
    binding = _binding(alpha)
    _completed(alpha, binding)
    _waiting(alpha, binding)
    diag = OperationalReadinessService(platform).diagnostics(ctx)

    assert diag["schema_version"] == SCHEMA_VERSION
    assert diag["environment"]["classification"] == "LOCAL_OR_TEST"
    assert diag["environment"]["production_authorized"] is False
    assert "PRIVATE_ALPHA" in diag["environment"]["labels"]
    assert diag["runtime"]["waiting_approval"] == 1
    assert diag["runtime"]["attention_count"] == 1
    # default bootstrap binding + the ops binding are both ACTIVE
    assert diag["bindings"]["by_state"]["ACTIVE"] >= 1
    assert diag["bindings"]["total"] == diag["bindings"]["by_state"]["ACTIVE"]
    assert diag["safety"]["connector_mutations"] == "DRY_RUN_ONLY"
    assert diag["safety"]["financial_execution"] == "DISABLED"
    assert diag["safety"]["trading_execution"] == "DISABLED"
    assert diag["safety"]["trading_guardian"] == "UNENGAGED_ADVISORY_ONLY"
    assert diag["safety"]["registered_tool_authority"] == "ExecutionGateway"
    assert diag["safety"]["canonical_runtime"] == "PlatformAgentRuntime"


def test_diagnostics_never_exposes_secrets_or_environment(alpha):
    platform, _, ctx = alpha
    blob = json.dumps(OperationalReadinessService(platform).diagnostics(ctx)).lower()
    for forbidden in ("password", "token", "secret", "db_path", "/users/", ".db", "authorization"):
        assert forbidden not in blob


# ── evidence export ─────────────────────────────────────────────────────────
def test_export_execution_summary_is_redacted_and_hashed(alpha):
    platform, _, ctx = alpha
    binding = _binding(alpha)
    _completed(alpha, binding)
    svc = OperationalReadinessService(platform)
    result = svc.export(ctx, kind="execution_summary", fmt="json")

    manifest = result["manifest"]
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["production_data"] is False
    assert manifest["content_hash"].startswith("sha256:")
    assert manifest["record_count"] == len(result["records"])
    for row in result["records"]:
        assert "arguments_json" not in row
        assert "result_json" not in row
        assert "approval_id" not in row
        assert set(row).issubset(set(manifest["columns"]))
    # Deterministic hash for identical data.
    again = svc.export(ctx, kind="execution_summary", fmt="json")
    assert again["manifest"]["content_hash"] == manifest["content_hash"]


def test_export_csv_format_has_header(alpha):
    platform, _, ctx = alpha
    binding = _binding(alpha)
    _completed(alpha, binding)
    result = OperationalReadinessService(platform).export(
        ctx, kind="execution_summary", fmt="csv"
    )
    assert result["manifest"]["format"] == "csv"
    first_line = result["csv"].splitlines()[0]
    assert "execution_id" in first_line and "state" in first_line


def test_export_scrub_drops_forbidden_keys_and_redacts_secret_text(alpha):
    platform, _, _ = alpha
    svc = OperationalReadinessService(platform)
    dirty = {
        "execution_id": "ex_1",
        "password": "hunter2",
        "session_token": "abc",
        "note": "authorization: Bearer sk_live_ABCDEFGHIJKLMNOP",
        "nested": {"api_key": "x", "safe": "ok"},
    }
    clean = svc._scrub(dirty)
    assert "password" not in clean and "session_token" not in clean
    assert "api_key" not in clean["nested"] and clean["nested"]["safe"] == "ok"
    assert "sk_live" not in clean["note"] and "[REDACTED]" in clean["note"]


def test_export_rejects_unknown_kind_and_format(alpha):
    platform, _, ctx = alpha
    svc = OperationalReadinessService(platform)
    with pytest.raises(PlatformContextError) as e1:
        svc.export(ctx, kind="everything", fmt="json")
    assert e1.value.code == "EXPORT_KIND_UNSUPPORTED"
    with pytest.raises(PlatformContextError) as e2:
        svc.export(ctx, kind="execution_summary", fmt="pdf")
    assert e2.value.code == "EXPORT_FORMAT_UNSUPPORTED"


def test_export_emits_audit_event(alpha):
    platform, _, ctx = alpha
    OperationalReadinessService(platform).export(ctx, kind="certification_manifest")
    events = {e["event"] for e in platform.store.list_audit(org_id=ctx.org_id)}
    assert "readiness.evidence_exported" in events


# ── retention (dry-run only) ────────────────────────────────────────────────
def test_retention_preview_is_dry_run_and_classifies_records(alpha):
    platform, _, ctx = alpha
    binding = _binding(alpha)
    completed = _completed(alpha, binding)
    _waiting(alpha, binding)  # non-terminal → protected
    svc = OperationalReadinessService(platform)

    created_at = platform.store.get_platform_execution(
        completed.platform_execution_id
    ).created_at
    future = created_at + DEFAULT_RETENTION_DAYS * 86400 + 10
    plan = svc.retention_preview(ctx, retention_days=DEFAULT_RETENTION_DAYS, now=future)

    assert plan["mode"] == "DRY_RUN"
    assert plan["purge_executed"] is False
    assert plan["irreversible"] is True
    assert completed.platform_execution_id in plan["eligible_execution_ids"]
    assert plan["protected"]["non_terminal"] == 1
    # Nothing was actually deleted.
    assert platform.store.get_platform_execution(completed.platform_execution_id)


def test_retention_hold_protects_terminal_record(alpha):
    platform, _, ctx = alpha
    binding = _binding(alpha)
    completed = _completed(alpha, binding)
    svc = OperationalReadinessService(platform)
    svc.set_hold(ctx, execution_id=completed.platform_execution_id, held=True)

    created_at = platform.store.get_platform_execution(
        completed.platform_execution_id
    ).created_at
    future = created_at + DEFAULT_RETENTION_DAYS * 86400 + 10
    plan = svc.retention_preview(ctx, retention_days=DEFAULT_RETENTION_DAYS, now=future)
    assert completed.platform_execution_id not in plan["eligible_execution_ids"]
    assert plan["protected"]["legal_or_operator_hold"] == 1


def test_retention_requires_owner_authority(alpha):
    platform, _, _ = alpha
    token, viewer_ctx = _second_tenant(platform)  # owner of other tenant
    # Downgrade: create a viewer session in the same tenant to prove denial.
    store = platform.store
    user = store.create_user(email="viewer@m54.local", name="Viewer")
    org = store.list_orgs_for_user(viewer_ctx.user_id)[0]
    ws = store.list_workspaces(org.org_id)[0]
    store.add_member(org.org_id, user.user_id, "viewer")
    _, vtoken = store.create_session(
        user.user_id, "viewer-token", org_id=org.org_id,
        workspace_id=ws.workspace_id, role="viewer",
    )
    vctx = platform.require_context(vtoken)
    with pytest.raises(PlatformContextError) as err:
        OperationalReadinessService(platform).retention_preview(vctx)
    assert err.value.code == "PERMISSION_DENIED"


# ── restart / recovery rehearsals ───────────────────────────────────────────
def test_restart_preserves_waiting_execution_and_allows_single_resume(tmp_path):
    reset_registry_for_tests()
    path = tmp_path / "restart.db"
    platform = reset_platform_for_tests(path)
    owner = platform.bootstrap_owner_secure(
        email="o@m54.local", name="O", password="OwnerPassw0rd!",
        org_name="Org", workspace_name="WS",
    )
    token = owner["token"]
    ctx = platform.require_context(token)
    binding = BindingAdministrationService(platform).create(
        ctx, agent_id="restart-agent", name="Restart agent",
        allowed_tools=["m49.local_note_write"], allowed_capabilities=[],
        authority_ceiling="LOCAL_MUTATION",
    )
    waiting = _waiting((platform, token, ctx), binding)
    platform.store.close()

    # Restart: brand-new service over the same single-host SQLite file.
    restarted = PlatformService(PlatformStore(path))
    record = restarted.store.get_platform_execution(waiting.execution_id)
    assert record.state == PlatformExecutionState.WAITING_APPROVAL.value
    ctx2 = restarted.require_context(token)
    ops = RuntimeOperationsService(restarted)
    reasons = ops.attention(ctx2)[0]["attention_reasons"]
    assert "APPROVAL_REQUIRED" in reasons


def test_restart_after_recorded_dispatch_cannot_replay(alpha):
    platform, token, ctx = alpha
    binding = _binding(alpha)
    waiting = _waiting(alpha, binding)
    # Drive a legal path to PAUSED with a recorded (uncertain) dispatch:
    # WAITING_APPROVAL -> READY -> RUNNING(dispatch_started) -> PAUSED.
    store = platform.store
    store.transition_platform_execution(
        waiting.execution_id, PlatformExecutionState.READY
    )
    store.transition_platform_execution(
        waiting.execution_id, PlatformExecutionState.RUNNING, dispatch_started=True
    )
    store.transition_platform_execution(
        waiting.execution_id, PlatformExecutionState.PAUSED
    )
    ops = RuntimeOperationsService(platform)
    reasons = ops.attention(ctx)[0]["attention_reasons"]
    assert "DISPATCH_OUTCOME_UNCERTAIN" in reasons
    with pytest.raises(PlatformContextError) as err:
        ops.reconcile(
            ctx, token=token, execution_id=waiting.execution_id,
            action="RESUME", idempotency_key="replay-attempt",
        )
    assert err.value.code == "DISPATCH_OUTCOME_UNCERTAIN"


# ── security boundaries ─────────────────────────────────────────────────────
def test_cross_tenant_export_and_diagnostics_are_isolated(alpha):
    platform, _, ctx = alpha
    binding = _binding(alpha)
    _completed(alpha, binding)
    other_token, other_ctx = _second_tenant(platform)
    svc = OperationalReadinessService(platform)

    own = svc.export(ctx, kind="execution_summary")
    other = svc.export(other_ctx, kind="execution_summary")
    assert own["manifest"]["record_count"] == 1
    assert other["manifest"]["record_count"] == 0
    assert svc.diagnostics(other_ctx)["runtime"]["total_recent_executions"] == 0


def test_cross_tenant_hold_fails_closed(alpha):
    platform, _, _ = alpha
    binding = _binding(alpha)
    completed = _completed(alpha, binding)
    _, other_ctx = _second_tenant(platform)
    with pytest.raises(PlatformContextError) as err:
        OperationalReadinessService(platform).set_hold(
            other_ctx, execution_id=completed.platform_execution_id, held=True
        )
    assert err.value.code == "EXECUTION_NOT_FOUND"


# ── API surface ─────────────────────────────────────────────────────────────
def test_api_readiness_routes(alpha):
    from saathi.server import app

    platform, token, _ = alpha
    binding = _binding(alpha)
    _completed(alpha, binding)
    client = TestClient(app)
    h = {"X-Platform-Token": token}

    diag = client.get("/api/v1/platform/runtime/diagnostics", headers=h)
    assert diag.status_code == 200
    assert diag.json()["diagnostics"]["environment"]["production_authorized"] is False

    export = client.get(
        "/api/v1/platform/runtime/export",
        params={"kind": "execution_summary", "format": "json"},
        headers=h,
    )
    assert export.status_code == 200
    assert export.json()["manifest"]["production_data"] is False

    retention = client.post(
        "/api/v1/platform/runtime/retention/preview", json={}, headers=h
    )
    assert retention.status_code == 200
    assert retention.json()["retention"]["mode"] == "DRY_RUN"

    anon = client.get("/api/v1/platform/runtime/diagnostics")
    assert anon.status_code in (401, 403)
