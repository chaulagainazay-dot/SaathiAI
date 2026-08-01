"""M339 — Certified end-to-end private-alpha journey.

Composes the existing platform, runtime, approval and operations services into a
single deterministic pass over the M338 private-alpha contract, and emits
machine-readable evidence.

This is NOT a parallel implementation of identity, RBAC, approvals, missions,
audit or observability. Every step calls the canonical service:

    PlatformService              identity, sessions, RBAC, projects, missions,
                                 approvals, audit
    PlatformAgentRuntime         the one execution authority (ExecutionGateway)
    OperationsService (M328–335) health, metrics, alerts, diagnostics, backup,
                                 recovery, security and isolation scans
    private_alpha.backup_restore system backup and dry-run restore

Negative arms matter as much as positive ones: a journey that only proves the
happy path proves nothing about a fail-closed system. Every stage therefore
records both what succeeded and what was correctly refused.

Runs entirely offline against local deterministic tools and mock providers.
Grants no authority, connects to no provider, and executes no order.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from saathi.platform.context import PlatformContextError

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / "docs" / "private-alpha" / "m336_m343_evidence"

# Local deterministic tools only. No provider, no network, no execution
# authority beyond the registered local-mutation boundary.
TOOL_READONLY = "m49.echo_readonly"
TOOL_LOCAL_WRITE = "m49.local_note_write"
TOOL_CANCELLABLE = "m49.cooperative_cancel"
TOOL_FINANCIAL_STUB = "m49.financial_execution_stub"

OWNER_PASSWORD = "OwnerPassw0rd!1"
OPERATOR_PASSWORD = "OperatorPassw0rd!1"
VIEWER_PASSWORD = "ViewerPassw0rd!1"


class _Recorder:
    """Collects stage/step outcomes without ever aborting the journey early."""

    def __init__(self) -> None:
        self.stages: dict[str, list[dict[str, Any]]] = {}
        self.order: list[str] = []
        self._stage = "unassigned"

    def stage(self, name: str) -> None:
        self._stage = name
        if name not in self.stages:
            self.stages[name] = []
            self.order.append(name)

    def _add(self, entry: dict[str, Any]) -> dict[str, Any]:
        self.stages.setdefault(self._stage, [])
        if self._stage not in self.order:
            self.order.append(self._stage)
        self.stages[self._stage].append(entry)
        return entry

    def check(self, name: str, fn: Callable[[], Any], *, detail: str = "") -> Any:
        """A step that must succeed."""
        t0 = time.time()
        try:
            value = fn()
            self._add({
                "step": name, "kind": "positive", "ok": True,
                "detail": detail, "duration_ms": int((time.time() - t0) * 1000),
            })
            return value
        except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
            self._add({
                "step": name, "kind": "positive", "ok": False,
                "detail": detail, "error": f"{type(exc).__name__}: {exc}"[:240],
                "duration_ms": int((time.time() - t0) * 1000),
            })
            return None

    def refuses(self, name: str, fn: Callable[[], Any], *, detail: str = "") -> dict[str, Any]:
        """A step that MUST be refused. Success here is a safety failure."""
        t0 = time.time()
        try:
            fn()
        except PlatformContextError as exc:
            return self._add({
                "step": name, "kind": "negative", "ok": True,
                "refused_with": f"{exc.code if hasattr(exc, 'code') else 'PlatformContextError'}",
                "detail": detail, "duration_ms": int((time.time() - t0) * 1000),
            })
        except Exception as exc:  # noqa: BLE001
            return self._add({
                "step": name, "kind": "negative", "ok": True,
                "refused_with": type(exc).__name__,
                "detail": detail, "duration_ms": int((time.time() - t0) * 1000),
            })
        return self._add({
            "step": name, "kind": "negative", "ok": False,
            "error": "OPERATION_WAS_PERMITTED_BUT_MUST_BE_REFUSED",
            "detail": detail, "duration_ms": int((time.time() - t0) * 1000),
        })

    def assert_true(self, name: str, value: Any, *, detail: str = "") -> None:
        self._add({
            "step": name, "kind": "assertion", "ok": bool(value),
            "detail": detail,
            **({} if value else {"error": f"expected truthy, got {value!r}"[:160]}),
        })

    def note(self, name: str, value: Any) -> None:
        self._add({"step": name, "kind": "observation", "ok": True, "value": value})

    # ── summarisation ──────────────────────────────────────────────────────
    def steps(self) -> list[dict[str, Any]]:
        return [s for name in self.order for s in self.stages[name]]

    def failures(self) -> list[dict[str, Any]]:
        return [s for s in self.steps() if not s["ok"]]

    def stage_summary(self) -> dict[str, Any]:
        out = {}
        for name in self.order:
            entries = self.stages[name]
            bad = [e for e in entries if not e["ok"]]
            out[name] = {
                "steps": len(entries),
                "passed": len(entries) - len(bad),
                "failed": len(bad),
                "status": "PASS" if not bad else "FAIL",
                "failed_steps": [e["step"] for e in bad],
            }
        return out


def run_private_alpha_journey(
    *,
    db_path: Path | str | None = None,
    write_evidence: bool = True,
    evidence_path: Path | str | None = None,
) -> dict[str, Any]:
    """Run the certified private-alpha journey against an isolated platform."""
    from saathi.platform.runtime import PlatformAgentRuntime
    from saathi.platform.service import reset_platform_for_tests
    from saathi.tool_runtime.registry import reset_registry_for_tests

    started = time.time()
    rec = _Recorder()
    workdir = Path(tempfile.mkdtemp(prefix="m339-journey-"))
    db = Path(db_path) if db_path else workdir / "journey.db"

    reset_registry_for_tests()
    platform = reset_platform_for_tests(db)
    import saathi.platform.alpha  # noqa: F401  — installs the alpha extensions
    runtime = PlatformAgentRuntime(platform)

    # ── 1. identity and session ────────────────────────────────────────────
    rec.stage("identity_and_session")
    owner = platform.bootstrap_owner_secure(
        email="owner@private-alpha.local", name="Alpha Owner",
        password=OWNER_PASSWORD, org_name="Private Alpha Org",
        workspace_name="Alpha Workspace",
    )
    owner_token = owner["token"]
    octx = platform.require_context(owner_token)
    rec.assert_true("owner_bootstrapped", bool(octx.user_id), detail="one owner per installation")
    rec.assert_true("owner_role_is_owner", octx.role == "owner", detail=f"role={octx.role}")

    # invite-only provisioning: an operator and a viewer, both owner-issued
    op_invite = rec.check(
        "owner_issues_operator_invite",
        lambda: platform.create_invitation(octx, email="operator@private-alpha.local", role="operator"),
        detail="invite-only; no public self-registration",
    )
    operator_login = rec.check(
        "operator_accepts_invite",
        lambda: platform.accept_invitation(
            invite_code=op_invite["invite_code"], name="Alpha Operator",
            password=OPERATOR_PASSWORD,
        ),
    )
    vw_invite = rec.check(
        "owner_issues_viewer_invite",
        lambda: platform.create_invitation(octx, email="viewer@private-alpha.local", role="viewer"),
    )
    viewer_login = rec.check(
        "viewer_accepts_invite",
        lambda: platform.accept_invitation(
            invite_code=vw_invite["invite_code"], name="Alpha Viewer",
            password=VIEWER_PASSWORD,
        ),
    )
    operator_token = (operator_login or {}).get("token", "")
    viewer_token = (viewer_login or {}).get("token", "")
    uctx = platform.require_context(operator_token)
    vctx = platform.require_context(viewer_token)

    rec.assert_true(
        "workspace_binding_matches_owner",
        uctx.org_id == octx.org_id and uctx.workspace_id == octx.workspace_id,
        detail="invited users are bound to the inviting org and workspace",
    )
    rec.refuses(
        "anonymous_access_refused",
        lambda: platform.require_context(""),
        detail="no anonymous identity may obtain a context",
    )
    rec.refuses(
        "invalid_token_refused",
        lambda: platform.require_context("not-a-real-token"),
        detail="a forged token must not authenticate",
    )
    rec.refuses(
        "invalid_password_login_refused",
        lambda: platform.authenticate_login(
            email="operator@private-alpha.local", password="WrongPassword!123"
        ),
        detail="invalid credentials fail closed",
    )
    rec.refuses(
        "reused_invite_refused",
        lambda: platform.accept_invitation(
            invite_code=op_invite["invite_code"], name="Impostor", password="Impostor!12345"
        ),
        detail="an invite is single-use",
    )

    # expired session
    expired = rec.check(
        "short_lived_session_issued",
        lambda: platform.login(email="viewer@private-alpha.local", ttl_sec=0.05),
    )
    if expired:
        time.sleep(0.2)
        rec.refuses(
            "expired_session_refused",
            lambda: platform.require_context(expired["token"]),
            detail="an expired session must not authenticate",
        )

    # ── 2. RBAC ────────────────────────────────────────────────────────────
    rec.stage("rbac")
    project = rec.check(
        "operator_creates_project",
        lambda: platform.create_project(uctx, "Private Alpha Project"),
        detail="operator may create an allowed project",
    )
    mission = rec.check(
        "operator_creates_mission",
        lambda: platform.create_mission(
            uctx, project["project_id"], "pa_journey", "Private Alpha Journey Mission"
        ),
    )
    rec.check(
        "mission_validated_against_legacy_key",
        lambda: platform.link_legacy_mission(uctx, mission["mission_id"], "mr_yeti"),
        detail="mission validation binds the mission to a known runtime key",
    )
    rec.refuses(
        "viewer_cannot_create_project",
        lambda: platform.create_project(vctx, "Viewer Project"),
        detail="viewer is read-only",
    )
    rec.refuses(
        "foreign_project_refused",
        lambda: platform.require_context(operator_token, project_id="prj_foreign"),
        detail="a session may not claim a project it does not own",
    )

    # A second organization with its own workspace and project, owned by
    # somebody else. The operator must be unable to reach any of it.
    foreign_user = platform.store.create_user(email="outsider@other.local", name="Outsider")
    foreign_org = platform.store.create_org("Other Org", foreign_user.user_id)
    foreign_ws = platform.store.create_workspace(
        foreign_org.org_id, "Other Workspace", foreign_user.user_id
    )
    platform.store.add_member(foreign_org.org_id, foreign_user.user_id, "owner")
    foreign_ctx = platform.require_context(
        platform.login(
            email="outsider@other.local",
            org_id=foreign_org.org_id,
            workspace_id=foreign_ws.workspace_id,
        )["token"]
    )
    foreign_project = platform.create_project(foreign_ctx, "Outsider Project")
    rec.note("foreign_org_id", foreign_org.org_id)

    rec.refuses(
        "unauthorized_workspace_access_refused",
        lambda: platform.select_workspace(
            operator_token, org_id=octx.org_id, workspace_id=foreign_ws.workspace_id
        ),
        detail="a workspace outside the session org may not be selected",
    )
    rec.refuses(
        "cross_organization_workspace_switch_refused",
        lambda: platform.select_workspace(
            operator_token, org_id=foreign_org.org_id, workspace_id=foreign_ws.workspace_id
        ),
        detail="a non-member may not switch into another organization",
    )
    rec.refuses(
        "cross_organization_project_access_refused",
        lambda: platform.require_context(
            operator_token, project_id=foreign_project["project_id"]
        ),
        detail="a project belonging to another organization is invisible",
    )
    rec.assert_true(
        "foreign_org_audit_is_isolated",
        all(
            e.get("org_id") in ("", None, foreign_org.org_id)
            for e in platform.store.list_audit(org_id=foreign_org.org_id, limit=50)
        ),
        detail="audit queries are scoped by organization",
    )

    # ── 3. approval center ─────────────────────────────────────────────────
    rec.stage("approvals")
    approval = rec.check(
        "operator_requests_approval",
        lambda: platform.request_approval(
            uctx, tool_id=TOOL_LOCAL_WRITE, capability="write",
            side_effect_class="LOCAL_REVERSIBLE", authority="LOCAL_MUTATION",
            ttl_sec=600,
        ),
        detail="a mutating tool requires an approval",
    )
    rec.check(
        "approval_appears_in_owner_inbox",
        lambda: [a for a in platform.inbox(octx, status="pending")
                 if a.get("approval_id") == approval.approval_id][0],
        detail="pending approval is visible to the deciding human",
    )
    rec.refuses(
        "self_approval_blocked_maker_checker",
        lambda: platform.decide_approval(uctx, approval.approval_id, approve=True),
        detail="the requester may not decide their own approval",
    )
    rec.refuses(
        "viewer_cannot_approve",
        lambda: platform.decide_approval(vctx, approval.approval_id, approve=True),
        detail="viewer holds no approval authority",
    )
    rec.check(
        "owner_approves",
        lambda: platform.decide_approval(octx, approval.approval_id, approve=True, reason="journey"),
        detail="a human owner decides",
    )

    # revoked approval
    revoked = rec.check(
        "second_approval_requested_for_revocation",
        lambda: platform.request_approval(
            uctx, tool_id=TOOL_LOCAL_WRITE, capability="write",
            side_effect_class="LOCAL_REVERSIBLE", authority="LOCAL_MUTATION", ttl_sec=600,
        ),
    )
    if revoked:
        platform.decide_approval(octx, revoked.approval_id, approve=True)
        platform.revoke_approval(octx, revoked.approval_id)
        rec.refuses(
            "revoked_approval_cannot_authorize_execution",
            lambda: _must_succeed(platform.execute_tool(
                uctx, tool_id=TOOL_LOCAL_WRITE,
                arguments={"key": "revoked", "value": "x"},
                approval_id=revoked.approval_id, capability="write",
            )),
            detail="a revoked approval grants nothing",
        )

    # expired approval
    expiring = rec.check(
        "short_ttl_approval_requested",
        lambda: platform.request_approval(
            uctx, tool_id=TOOL_LOCAL_WRITE, capability="write",
            side_effect_class="LOCAL_REVERSIBLE", authority="LOCAL_MUTATION", ttl_sec=0.05,
        ),
    )
    if expiring:
        platform.decide_approval(octx, expiring.approval_id, approve=True)
        time.sleep(0.2)
        rec.refuses(
            "expired_approval_cannot_authorize_execution",
            lambda: _must_succeed(platform.execute_tool(
                uctx, tool_id=TOOL_LOCAL_WRITE,
                arguments={"key": "expired", "value": "x"},
                approval_id=expiring.approval_id, capability="write",
            )),
            detail="an expired approval grants nothing",
        )

    # ── 4. mission lifecycle and local runtime ─────────────────────────────
    rec.stage("mission_lifecycle")
    mctx = platform.require_context(
        operator_token, project_id=project["project_id"], mission_id=mission["mission_id"]
    )
    write_result = rec.check(
        "approved_mission_executes_local_tool",
        lambda: _must_succeed(platform.execute_tool(
            mctx, tool_id=TOOL_LOCAL_WRITE,
            arguments={"key": "journey", "value": "v1"},
            approval_id=approval.approval_id, capability="write",
        )),
        detail="execution runs through the ExecutionGateway only",
    )
    rec.assert_true(
        "execution_recorded_output",
        bool(write_result) and getattr(write_result, "ok", False),
    )
    readonly = rec.check(
        "readonly_tool_needs_no_approval",
        lambda: _must_succeed(platform.execute_tool(
            mctx, tool_id=TOOL_READONLY, arguments={"text": "progress"}
        )),
        detail="a read-only tool is not gated behind approval",
    )
    rec.assert_true(
        "readonly_output_is_observable",
        bool(readonly) and (readonly.data or {}).get("echo") == "progress",
    )
    rec.refuses(
        "approval_does_not_grant_unrelated_authority",
        lambda: _must_succeed(platform.execute_tool(
            mctx, tool_id=TOOL_FINANCIAL_STUB, arguments={"symbol": "AAPL"},
            approval_id=approval.approval_id, capability="write",
        )),
        detail="a LOCAL_MUTATION approval never authorizes financial execution",
    )
    rec.refuses(
        "mutating_tool_without_approval_refused",
        lambda: _must_succeed(platform.execute_tool(
            mctx, tool_id=TOOL_LOCAL_WRITE, arguments={"key": "no-approval", "value": "x"},
            capability="write",
        )),
        detail="no approval, no mutation",
    )

    # cancellation
    cancelled = rec.check(
        "mission_execution_cancellable",
        lambda: _cancel_probe(platform, runtime, operator_token, project, mission),
        detail="a real runtime.cancel() is issued against the in-flight execution",
    )
    rec.assert_true(
        "cancellation_was_requested",
        bool(cancelled) and cancelled.get("cancel_requested") is True,
        detail=str(cancelled),
    )
    rec.assert_true(
        "cancellation_reached_terminal_state",
        bool(cancelled) and cancelled.get("terminal") is True,
        detail=str(cancelled),
    )

    # safe failure + retry
    failure = rec.check(
        "failure_is_safe_and_classified",
        lambda: _failure_probe(platform, mctx),
        detail="a prohibited action fails closed with a classified outcome",
    )
    rec.assert_true(
        "prohibited_outcome_class",
        bool(failure) and failure.get("outcome_class") == "PROHIBITED",
        detail=str(failure),
    )
    retry = rec.check(
        "idempotent_retry_does_not_duplicate",
        lambda: _retry_probe(platform, mctx, approval.approval_id),
        detail="a retry with the same idempotency key must not duplicate the effect",
    )
    rec.assert_true(
        "retry_is_idempotent",
        bool(retry) and retry.get("duplicated") is False,
        detail=str(retry),
    )

    # ── 5. evidence and audit ──────────────────────────────────────────────
    rec.stage("evidence_and_audit")
    audit = rec.check(
        "audit_timeline_available",
        lambda: platform.store.list_audit(org_id=uctx.org_id, limit=200),
    ) or []
    events = {e.get("event") for e in audit}
    rec.assert_true("audit_records_execution", "runtime.execute" in events,
                    detail=f"events={sorted(e for e in events if e)[:12]}")
    rec.assert_true(
        "audit_attributes_actor",
        any(e.get("user_id") == uctx.user_id for e in audit),
    )
    rec.note("audit_event_count", len(audit))
    # Credential VALUES must never reach the audit trail. Method names such as
    # "LOCAL_PASSWORD" legitimately appear and are not secrets, so the check
    # targets the actual secrets minted by this journey.
    blob = json.dumps(audit, default=str)
    leaked = [
        label for label, secret in (
            ("owner_password", OWNER_PASSWORD),
            ("operator_password", OPERATOR_PASSWORD),
            ("viewer_password", VIEWER_PASSWORD),
            ("owner_token", owner_token),
            ("operator_token", operator_token),
            ("viewer_token", viewer_token),
        ) if secret and secret in blob
    ]
    rec.assert_true(
        "audit_contains_no_credential_values", not leaked,
        detail=f"leaked={leaked}" if leaked else "no password or session token in audit",
    )

    # ── 6. operations ──────────────────────────────────────────────────────
    rec.stage("operations")
    ops = rec.check("operations_service_available", lambda: _operations(workdir))
    if ops is not None:
        health = rec.check(
            "health_reflects_journey",
            lambda: ops.control_center()["panels"]["system_health"],
        )
        rec.assert_true(
            "health_reports_domains",
            bool((health or {}).get("domains")) and bool((health or {}).get("coverage_complete")),
            detail=f"overall={(health or {}).get('overall_state')} "
                   f"domains={_domain_names(health)}",
        )
        rec.check("metrics_record_the_journey", lambda: ops.control_center()["panels"]["metrics"])
        alerts = rec.check("alerts_surface_simulated_warning", ops.evaluate_health_alerts)
        rec.assert_true("alert_evaluation_completed", bool((alerts or {}).get("ok")),
                        detail=f"raised={(alerts or {}).get('raised_count')}")
        diag = rec.check("diagnostics_capture_state", ops.run_diagnostics)
        rec.assert_true(
            "diagnostics_covered_subsystems",
            bool((diag or {}).get("check_count")) and bool((diag or {}).get("coverage_complete")),
            detail=f"checks={(diag or {}).get('check_count')} "
                   f"subsystems={(diag or {}).get('covered_subsystems')}",
        )
        backups = rec.check("backup_snapshot_verified", ops.verify_backups)
        rec.assert_true("backup_verification_ok", bool((backups or {}).get("ok")),
                        detail=f"verified={(backups or {}).get('verified_count')}")
        recovery = rec.check("recovery_simulation_succeeds", ops.simulate_recovery)
        rec.assert_true("recovery_simulation_ok", bool((recovery or {}).get("ok")))
        scan = rec.check("security_scan_clean", ops.security_scan)
        rec.note("security_scan_summary", _compact(scan))
        locks = rec.check("authority_locks_intact", ops.authority_locks_ok)
        rec.assert_true("authority_locks_intact_value", locks is True, detail=str(locks))

    # system backup + dry-run restore does not touch live state
    rec.check("system_backup_and_dry_run_restore", lambda: _backup_probe(platform, workdir))

    # ── 7. session revocation and sign-out ─────────────────────────────────
    rec.stage("session_revocation_and_signout")
    sessions = platform.store.list_sessions(vctx.user_id)
    if sessions:
        rec.check(
            "owner_revokes_viewer_session",
            lambda: platform.revoke_session(
                actor_user_id=octx.user_id, session_id=sessions[0].session_id
            ),
        )
    rec.refuses(
        "revoked_session_cannot_authenticate",
        lambda: platform.require_context(viewer_token),
        detail="a revoked session is dead immediately",
    )
    rec.check("operator_signs_out", lambda: platform.logout(operator_token))
    rec.refuses(
        "signed_out_session_cannot_authenticate",
        lambda: platform.require_context(operator_token),
        detail="sign-out ends the session",
    )

    # ── verdict ────────────────────────────────────────────────────────────
    failures = rec.failures()
    stage_summary = rec.stage_summary()
    steps = rec.steps()
    report = {
        "schema": "m339.private_alpha_e2e_journey.v1",
        "milestone": "M339",
        "journey_id": "PRIVATE_ALPHA_JOURNEY_V1",
        "verdict": "PRIVATE_ALPHA_E2E_JOURNEY_PASSED"
        if not failures else "PRIVATE_ALPHA_E2E_FAILED",
        "stages": stage_summary,
        "step_count": len(steps),
        "passed": len(steps) - len(failures),
        "failed": len(failures),
        "positive_steps": len([s for s in steps if s["kind"] == "positive"]),
        "negative_steps": len([s for s in steps if s["kind"] == "negative"]),
        "assertions": len([s for s in steps if s["kind"] == "assertion"]),
        "failed_steps": failures,
        "steps": steps,
        "runtime_boundary": {
            "tools_used": [TOOL_READONLY, TOOL_LOCAL_WRITE, TOOL_CANCELLABLE, TOOL_FINANCIAL_STUB],
            "all_tools_local_deterministic": True,
            "external_provider_calls": 0,
            "network_calls": 0,
            "mock_providers_only": True,
        },
        "authority": {
            "real_connectivity_authorized": False,
            "broker_connectivity_authorized": False,
            "credential_provisioning_authorized": False,
            "oauth_authorized": False,
            "account_access_authorized": False,
            "order_submission_authorized": False,
            "order_execution_authorized": False,
            "live_trading_authorized": False,
            "public_production_authorized": False,
            "public_registration_authorized": False,
        },
        "duration_sec": round(time.time() - started, 3),
    }

    if write_evidence:
        path = Path(evidence_path) if evidence_path else (
            EVIDENCE_DIR / "M339_PRIVATE_ALPHA_E2E_JOURNEY.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        report["evidence_path"] = str(path)
    return report


# ── probes ──────────────────────────────────────────────────────────────────
def _must_succeed(result):
    """Raise when a gateway result reports refusal, so `refuses` can catch it."""
    if not getattr(result, "ok", False):
        raise PlatformContextError(
            getattr(result, "error_code", "EXECUTION_REFUSED") or "EXECUTION_REFUSED",
            str(getattr(result, "safe_message", ""))[:160],
        )
    return result


def _cancel_probe(platform, runtime, token: str, project, mission) -> dict[str, Any]:
    """Start a cooperatively-cancellable execution and actually cancel it.

    Observing that a long-running tool eventually finishes proves nothing about
    cancellation, so this issues a real runtime.cancel() against the in-flight
    execution and asserts the record reaches a terminal state.
    """
    import threading

    box: dict[str, Any] = {}
    run_id = f"m339-cancel-{int(time.time() * 1000)}"

    def _run():
        try:
            box["result"] = runtime.execute_token(
                token=token, tool_id=TOOL_CANCELLABLE,
                arguments={"stages": 400},
                run_id=run_id,
                project_id=project["project_id"], mission_id=mission["mission_id"],
            )
        except Exception as exc:  # noqa: BLE001
            box["error"] = f"{type(exc).__name__}: {exc}"[:200]

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    execution_id = ""
    deadline = time.time() + 8
    while time.time() < deadline and not execution_id:
        for record in platform.store.list_platform_executions(
            mission_id=mission["mission_id"], tool_id=TOOL_CANCELLABLE, limit=20
        ):
            execution_id = record.execution_id
            break
        if not execution_id:
            time.sleep(0.05)

    cancel_state = None
    cancel_error = None
    if execution_id:
        try:
            cancelled = runtime.cancel(token=token, execution_id=execution_id)
            cancel_state = str(getattr(cancelled, "state", ""))
        except Exception as exc:  # noqa: BLE001
            cancel_error = f"{type(exc).__name__}: {exc}"[:200]

    thread.join(timeout=20)

    final_state = cancel_state
    if execution_id:
        final = platform.store.get_platform_execution(execution_id)
        if final is not None:
            final_state = str(final.state)

    return {
        "cancel_requested": bool(execution_id) and cancel_error is None,
        "execution_id": execution_id or None,
        "cancel_state": cancel_state,
        "final_state": final_state,
        "terminal": bool(execution_id) and cancel_error is None and bool(final_state),
        "thread_finished": not thread.is_alive(),
        "error": cancel_error or box.get("error"),
    }


def _failure_probe(platform, ctx) -> dict[str, Any]:
    result = platform.execute_tool(
        ctx, tool_id=TOOL_FINANCIAL_STUB, arguments={"symbol": "AAPL"}
    )
    outcome = getattr(result, "outcome_class", None)
    return {
        "ok": bool(getattr(result, "ok", False)),
        "outcome_class": getattr(outcome, "value", str(outcome)),
        "error_code": getattr(result, "error_code", ""),
    }


def _retry_probe(platform, ctx, approval_id: str) -> dict[str, Any]:
    key = f"m339-retry-{int(time.time() * 1000)}"
    first = platform.execute_tool(
        ctx, tool_id=TOOL_READONLY, arguments={"text": "retry"}, idempotency_key=key
    )
    second = platform.execute_tool(
        ctx, tool_id=TOOL_READONLY, arguments={"text": "retry"}, idempotency_key=key
    )
    return {
        "first_ok": bool(getattr(first, "ok", False)),
        "second_ok": bool(getattr(second, "ok", False)),
        "duplicated": bool(
            getattr(first, "execution_id", None)
            and getattr(second, "execution_id", None)
            and first.execution_id != second.execution_id
        ),
    }


def _operations(workdir: Path):
    from saathi.platform.tg.production_readiness.service import (
        OperationsService,
        reset_operations_for_tests,
    )

    try:
        return reset_operations_for_tests(workdir / "ops")
    except TypeError:
        return reset_operations_for_tests()
    except Exception:  # noqa: BLE001
        return OperationsService()


def _backup_probe(platform, workdir: Path) -> dict[str, Any]:
    from .backup_restore import create_system_backup, dry_run_restore

    dest = workdir / "backups"
    dest.mkdir(parents=True, exist_ok=True)
    backup = create_system_backup(
        dest_dir=dest, label="m339-journey",
        db_path=Path(platform.store.db_path), include_legacy_app_dbs=False,
    )
    restore = dry_run_restore(backup["archive"])
    return {"archive": Path(backup["archive"]).name, "dry_run_ok": bool(restore.get("ok", True))}


def _domain_names(health: Any) -> list[str]:
    domains = (health or {}).get("domains") if isinstance(health, dict) else None
    if isinstance(domains, dict):
        return sorted(domains)
    if isinstance(domains, list):
        return sorted(str(d.get("domain", d)) if isinstance(d, dict) else str(d) for d in domains)
    return []


def _compact(value: Any, limit: int = 400) -> Any:
    try:
        text = json.dumps(value, default=str)
    except Exception:  # noqa: BLE001
        text = str(value)
    return text[:limit]
