"""M50 PlatformService — identity, tenancy, approvals, and gateway-bound execution.

All tool execution goes through ExecutionGateway.execute_registered_tool.
No parallel execution path.
"""
from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.models import (
    ApprovalRecord,
    ApprovalStatus,
    PlatformPermission,
    PlatformRole,
    new_id,
    permissions_for_role,
)
from saathi.platform.store import PlatformStore

DEFAULT_CONFIG = {
    "models": {"default": "local", "allow_cloud": False},
    "connectors": {"mutations": "DRY_RUN_ONLY", "live": False},
    "runtime": {"gateway": "ExecutionGateway", "anonymous": False},
    "notifications": {"enabled": False},
    "privacy": {"telemetry": False},
    "security": {
        "session_ttl_sec": 86400,
        "approval_ttl_sec": 3600,
        "require_approval_for_mutations": True,
        "authority_ceiling": "SECURITY_SENSITIVE",
    },
    "trading_guardian": "ADVISORY_ONLY",
}


class PlatformService:
    def __init__(self, store: PlatformStore | None = None):
        self.store = store or PlatformStore()
        self._ensure_default_config()

    def _audit(self, event: str, ctx: PlatformExecutionContext | None = None, **extra) -> None:
        """Append audit without kwargs collision with context fields."""
        base = ctx.to_audit_dict() if ctx else {}
        # extras override context (e.g. explicit approval_id / tool_id / outcome)
        payload = {**base, **extra}
        detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else None
        self.store.append_audit(
            event,
            execution_id=str(
                payload.get("execution_id")
                or (detail or {}).get("execution_id")
                or ""
            ),
            user_id=str(payload.get("user_id") or ""),
            role=str(payload.get("role") or ""),
            org_id=str(payload.get("org_id") or ""),
            workspace_id=str(payload.get("workspace_id") or ""),
            project_id=str(payload.get("project_id") or ""),
            mission_id=str(payload.get("mission_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            tool_id=str(payload.get("tool_id") or ""),
            approval_id=str(payload.get("approval_id") or ""),
            authority=str(payload.get("authority") or ""),
            outcome=str(payload.get("outcome") or ""),
            evidence=str(payload.get("evidence") or ""),
            detail=detail,
        )

    def _ensure_default_config(self) -> None:
        existing = self.store.all_config()
        if not existing:
            for k, v in DEFAULT_CONFIG.items():
                self.store.set_config(k, v, updated_by="system:bootstrap")

    # ── bootstrap / onboarding ────────────────────────────────────────────
    def bootstrap_owner(
        self,
        *,
        email: str = "owner@local",
        name: str = "Owner",
        org_name: str = "Default Org",
        workspace_name: str = "Default Workspace",
    ) -> dict[str, Any]:
        """Create owner user + org + workspace if empty. Returns bootstrap info."""
        users = self.store.list_users()
        if users:
            u = users[0]
            orgs = self.store.list_orgs_for_user(u.user_id)
            org = orgs[0] if orgs else None
            ws = self.store.list_workspaces(org.org_id)[0] if org else None
            if org and ws:
                from saathi.platform.bindings import ensure_default_binding

                ensure_default_binding(self, org.org_id, ws.workspace_id, u.user_id)
            return {
                "bootstrapped": False,
                "user": u.to_public(),
                "org": org.to_public() if org else None,
                "workspace": ws.to_public() if ws else None,
            }
        user = self.store.create_user(email=email, name=name)
        org = self.store.create_org(org_name, user.user_id)
        ws = self.store.create_workspace(org.org_id, workspace_name, user.user_id)
        from saathi.platform.bindings import ensure_default_binding

        ensure_default_binding(self, org.org_id, ws.workspace_id, user.user_id)
        self._audit(
            "platform.bootstrap",
            user_id=user.user_id,
            role=PlatformRole.OWNER.value,
            org_id=org.org_id,
            workspace_id=ws.workspace_id,
            outcome="ok",
        )
        return {
            "bootstrapped": True,
            "user": user.to_public(),
            "org": org.to_public(),
            "workspace": ws.to_public(),
        }

    def login(
        self,
        *,
        email: str,
        org_id: str = "",
        workspace_id: str = "",
        ttl_sec: float | None = None,
    ) -> dict[str, Any]:
        """Issue a platform session for an existing user (local alpha auth).

        M50 compatibility path for accounts provisioned before local credentials
        existed. It performs no credential check, so it must never serve an
        account that HAS a credential — otherwise supplying an email alone
        would issue that user's session and defeat the login gate entirely.
        Credentialed accounts must go through ``authenticate_login``, which
        applies password verification, abuse controls and generic failures.
        """
        user = self.store.get_user_by_email(email)
        if not user or user.status != "active":
            raise PlatformContextError("AUTH_FAILED", "user not found or inactive")
        credential = self.store.get_credential(user.user_id)
        if credential and credential.get("password_hash"):
            self._audit(
                "auth.login_failed",
                outcome="fail",
                detail={
                    "internal": "passwordless_path_refused_for_credentialed_user",
                    "method": "LOCAL_PASSWORDLESS",
                },
            )
            raise PlatformContextError("AUTH_FAILED", "auth_failed")
        orgs = self.store.list_orgs_for_user(user.user_id)
        if not orgs:
            raise PlatformContextError("NO_ORG", "user has no organization")
        org = next((o for o in orgs if o.org_id == org_id), orgs[0]) if org_id else orgs[0]
        role = self.store.membership_role(org.org_id, user.user_id) or PlatformRole.VIEWER.value
        workspaces = self.store.list_workspaces(org.org_id)
        if not workspaces:
            raise PlatformContextError("NO_WORKSPACE", "organization has no workspace")
        ws = (
            next((w for w in workspaces if w.workspace_id == workspace_id), workspaces[0])
            if workspace_id
            else workspaces[0]
        )
        if ws.org_id != org.org_id:
            raise PlatformContextError("WORKSPACE_ISOLATION", "workspace not in organization")
        ttl = ttl_sec
        if ttl is None:
            sec = self.store.get_config("security", DEFAULT_CONFIG["security"])
            ttl = float(sec.get("session_ttl_sec", 86400))
        raw = secrets.token_urlsafe(32)
        sess, token = self.store.create_session(
            user.user_id,
            raw,
            org_id=org.org_id,
            workspace_id=ws.workspace_id,
            role=role,
            ttl_sec=ttl,
        )
        self._audit(
            "session.created",
            user_id=user.user_id,
            role=role,
            org_id=org.org_id,
            workspace_id=ws.workspace_id,
            outcome="ok",
            detail={"session_id": sess.session_id},
        )
        return {
            "token": token,
            "session": {
                "session_id": sess.session_id,
                "user_id": user.user_id,
                "org_id": org.org_id,
                "workspace_id": ws.workspace_id,
                "role": role,
                "expires_at": sess.expires_at,
            },
            "user": user.to_public(),
            "permissions": sorted(p.value for p in permissions_for_role(role)),
        }

    def logout(self, token: str) -> bool:
        sess = self.store.session_by_token(token)
        if not sess:
            return False
        ok = self.store.revoke_session(sess.session_id)
        self._audit(
            "session.revoked",
            user_id=sess.user_id,
            role=sess.role,
            org_id=sess.org_id,
            workspace_id=sess.workspace_id,
            outcome="ok" if ok else "miss",
            detail={"session_id": sess.session_id},
        )
        return ok

    def revoke_session(self, *, actor_user_id: str, session_id: str) -> bool:
        ok = self.store.revoke_session(session_id)
        self._audit(
            "session.revoked",
            user_id=actor_user_id,
            outcome="ok" if ok else "miss",
            detail={"session_id": session_id},
        )
        return ok

    # ── context ───────────────────────────────────────────────────────────
    def context_from_token(
        self,
        token: str,
        *,
        project_id: str = "",
        mission_id: str = "",
        run_id: str = "",
    ) -> PlatformExecutionContext:
        if not token:
            raise PlatformContextError("ANONYMOUS_PROHIBITED", "session token required")
        sess = self.store.session_by_token(token)
        if not sess:
            raise PlatformContextError("SESSION_INVALID", "session expired, revoked, or unknown")
        sec = self.store.get_config("security", {}) or {}
        idle = float(sec.get("idle_ttl_sec", 3600))
        self.store.touch_session(sess.session_id, idle_sec=idle)
        if sec.get("login_enabled") is False:
            raise PlatformContextError("LOGIN_DISABLED", "owner disabled login")
        # membership still valid?
        role = self.store.membership_role(sess.org_id, sess.user_id)
        if not role:
            raise PlatformContextError("MEMBERSHIP_REVOKED", "user not in organization")
        # workspace isolation
        ws = self.store.get_workspace(sess.workspace_id)
        if not ws or ws.org_id != sess.org_id:
            raise PlatformContextError("WORKSPACE_ISOLATION", "workspace not in session org")
        if project_id:
            proj = self.store.get_project(project_id)
            if not proj or proj.org_id != sess.org_id or proj.workspace_id != sess.workspace_id:
                raise PlatformContextError(
                    "PROJECT_ISOLATION", "project not in session workspace/org"
                )
        if mission_id:
            mis = self.store.get_mission(mission_id)
            if not mis or mis.org_id != sess.org_id:
                raise PlatformContextError("MISSION_ISOLATION", "mission not in session org")
            if project_id and mis.project_id != project_id:
                raise PlatformContextError("MISSION_PROJECT_MISMATCH", "mission not in project")
        ctx = PlatformExecutionContext(
            user_id=sess.user_id,
            role=role,
            org_id=sess.org_id,
            workspace_id=sess.workspace_id,
            project_id=project_id,
            mission_id=mission_id,
            run_id=run_id or new_id("run_"),
            session_id=sess.session_id,
        )
        ctx.validate()
        return ctx

    def require_context(self, token: str | None, **kwargs) -> PlatformExecutionContext:
        if not token:
            raise PlatformContextError("ANONYMOUS_PROHIBITED", "anonymous execution prohibited")
        return self.context_from_token(token, **kwargs)

    # ── tenancy CRUD (permission gated) ───────────────────────────────────
    def create_project(
        self, ctx: PlatformExecutionContext, name: str, *, mission_key: str = ""
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.PROJECT_CREATE)
        proj = self.store.create_project(
            workspace_id=ctx.workspace_id,
            org_id=ctx.org_id,
            name=name,
            owner_id=ctx.user_id,
            mission_key=mission_key,
        )
        self._audit(
            "project.created",
            ctx,
            project_id=proj.project_id,
            outcome="ok",
            detail={"name": name},
        )
        return proj.to_public()

    def create_mission(
        self, ctx: PlatformExecutionContext, project_id: str, key: str, name: str
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_WRITE)
        proj = self.store.get_project(project_id)
        if not proj or proj.org_id != ctx.org_id or proj.workspace_id != ctx.workspace_id:
            raise PlatformContextError("PROJECT_ISOLATION", "project not accessible")
        try:
            mis = self.store.create_mission(
                project_id=project_id,
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                key=key,
                name=name,
                owner_id=ctx.user_id,
            )
        except ValueError as exc:
            # Duplicate submission: the (org_id, key) uniqueness constraint fired.
            # Fail closed with a conflict the UI can render, not a 500 stack trace.
            self._audit(
                "mission.created",
                ctx,
                project_id=project_id,
                outcome="denied",
                detail={"key": key, "reason": "MISSION_KEY_EXISTS"},
            )
            raise PlatformContextError(
                "MISSION_KEY_EXISTS", "mission key already exists in this organization"
            ) from exc
        self._audit(
            "mission.created",
            ctx,
            project_id=project_id,
            mission_id=mis.mission_id,
            outcome="ok",
            detail={"key": key, "name": name},
        )
        return mis.to_public()

    def add_member(
        self, ctx: PlatformExecutionContext, user_id: str, role: str
    ) -> None:
        ctx.require_permission(PlatformPermission.USER_MANAGE)
        try:
            PlatformRole(role)
        except ValueError as exc:
            raise PlatformContextError("ROLE_INVALID", str(role)) from exc
        if role == PlatformRole.SYSTEM.value:
            raise PlatformContextError("ROLE_INVALID", "cannot assign system role")
        self.store.add_member(ctx.org_id, user_id, role)
        self._audit(
            "membership.updated",
            ctx,
            outcome="ok",
            detail={"target_user": user_id, "role": role},
        )

    # ── approval center ───────────────────────────────────────────────────
    def _reject_unsatisfiable_approval_scope(
        self,
        ctx: PlatformExecutionContext,
        *,
        tool_id: str,
        authority: str,
        side_effect_class: str,
        capability: str,
    ) -> None:
        """Refuse an approval whose declared scope the tool can never satisfy.

        The execution gateway matches an approval's authority, side-effect class
        and capability against the tool manifest exactly. Without this check a
        contradictory request is stored, routed to a human, approved, and only
        then rejected at dispatch as an unattributed "approval invalid" — a
        dead-end for the operator. Catch it at request time with a message that
        names the field. Unregistered tool ids (dynamic connector grants) keep
        the previous permissive behaviour and are still validated at dispatch.
        """
        from saathi.tool_runtime.registry import default_registry

        manifest = default_registry().get_manifest(tool_id)
        if manifest is None:
            return
        mismatches: list[str] = []
        if authority and authority != manifest.authority_class.value:
            mismatches.append(
                f"authority {authority!r} (tool declares {manifest.authority_class.value!r})"
            )
        if side_effect_class and side_effect_class != manifest.side_effect_class.value:
            mismatches.append(
                f"side_effect_class {side_effect_class!r} "
                f"(tool declares {manifest.side_effect_class.value!r})"
            )
        allowed_caps = tuple(manifest.capabilities or ())
        if capability and allowed_caps and capability not in allowed_caps:
            mismatches.append(
                f"capability {capability!r} (tool declares {list(allowed_caps)})"
            )
        if not mismatches:
            return
        self._audit(
            "approval.requested",
            ctx,
            tool_id=tool_id,
            outcome="denied",
            detail={"reason": "APPROVAL_SCOPE_UNSATISFIABLE", "mismatches": mismatches},
        )
        raise PlatformContextError(
            "VALIDATION_FAILED",
            "approval scope does not match the tool contract: " + "; ".join(mismatches),
        )

    def request_approval(
        self,
        ctx: PlatformExecutionContext,
        *,
        tool_id: str,
        action: str = "",
        target_resource: str = "",
        authority: str = "",
        side_effect_class: str = "",
        capability: str = "",
        ttl_sec: float | None = None,
        connector: str = "",
        tool_version: str = "",
    ) -> ApprovalRecord:
        ctx.require_permission(PlatformPermission.APPROVAL_REQUEST)
        self._reject_unsatisfiable_approval_scope(
            ctx,
            tool_id=tool_id,
            authority=authority,
            side_effect_class=side_effect_class,
            capability=capability,
        )
        sec = self.store.get_config("security", DEFAULT_CONFIG["security"])
        ttl = float(ttl_sec if ttl_sec is not None else sec.get("approval_ttl_sec", 3600))
        now = time.time()
        rec = ApprovalRecord(
            approval_id=new_id("apr_"),
            user_id=ctx.user_id,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=ctx.project_id,
            mission_id=ctx.mission_id,
            tool_id=tool_id,
            action=action,
            target_resource=target_resource,
            authority=authority,
            side_effect_class=side_effect_class,
            capability=capability,
            status=ApprovalStatus.PENDING.value,
            requested_by=ctx.user_id,
            created_at=now,
            expires_at=now + ttl,
            # Leave run_id unbound at request time so the same approved
            # grant can be used for one execution run (run binds at consume).
            run_id="",
            tool_version=tool_version,
            connector=connector,
        )
        self.store.save_approval(rec)
        self._audit(
            "approval.requested",
            ctx,
            tool_id=tool_id,
            approval_id=rec.approval_id,
            authority=authority,
            outcome="pending",
        )
        return rec

    def decide_approval(
        self,
        ctx: PlatformExecutionContext,
        approval_id: str,
        *,
        approve: bool,
        reason: str = "",
    ) -> ApprovalRecord:
        ctx.require_permission(PlatformPermission.APPROVAL_DECIDE)
        self.store.expire_stale_approvals()
        rec = self.store.get_approval(approval_id)
        if not rec:
            raise PlatformContextError("APPROVAL_NOT_FOUND", approval_id)
        if rec.org_id != ctx.org_id:
            raise PlatformContextError("APPROVAL_ISOLATION", "cross-org approval denied")
        if rec.status != ApprovalStatus.PENDING.value:
            raise PlatformContextError(
                "APPROVAL_NOT_PENDING", f"status={rec.status}"
            )
        now = time.time()
        if rec.expires_at and rec.expires_at < now:
            rec.status = ApprovalStatus.EXPIRED.value
            self.store.save_approval(rec)
            raise PlatformContextError("APPROVAL_EXPIRED", approval_id)
        decided_status = (
            ApprovalStatus.APPROVED.value if approve else ApprovalStatus.REJECTED.value
        )
        # M341: the decision is applied by a conditional UPDATE, so concurrent
        # deciders cannot each observe `pending` and each write a decision. The
        # loser is refused exactly as a sequential second decider would be.
        if not self.store.decide_approval_if_pending(
            approval_id,
            status=decided_status,
            decided_by=ctx.user_id,
            decided_at=now,
            reason=reason,
        ):
            current = self.store.get_approval(approval_id)
            raise PlatformContextError(
                "APPROVAL_NOT_PENDING",
                f"status={current.status if current else 'missing'}",
            )
        rec = self.store.get_approval(approval_id) or rec
        self._audit(
            "approval.decided",
            ctx,
            tool_id=rec.tool_id,
            approval_id=rec.approval_id,
            authority=rec.authority,
            outcome=rec.status,
            detail={"approve": approve, "reason": reason[:200]},
        )
        return rec

    def revoke_approval(self, ctx: PlatformExecutionContext, approval_id: str) -> ApprovalRecord:
        ctx.require_permission(PlatformPermission.APPROVAL_DECIDE)
        rec = self.store.get_approval(approval_id)
        if not rec:
            raise PlatformContextError("APPROVAL_NOT_FOUND", approval_id)
        if rec.org_id != ctx.org_id:
            raise PlatformContextError("APPROVAL_ISOLATION", "cross-org approval denied")
        if rec.status not in (
            ApprovalStatus.PENDING.value,
            ApprovalStatus.APPROVED.value,
        ):
            raise PlatformContextError("APPROVAL_NOT_REVOCABLE", rec.status)
        # M341: same conditional-UPDATE guarantee as decide_approval, so a
        # revocation racing a decision or a second revocation cannot both win.
        if not self.store.revoke_approval_if_revocable(
            approval_id, decided_by=ctx.user_id, decided_at=time.time()
        ):
            current = self.store.get_approval(approval_id)
            raise PlatformContextError(
                "APPROVAL_NOT_REVOCABLE", current.status if current else "missing"
            )
        rec = self.store.get_approval(approval_id) or rec
        self._audit(
            "approval.revoked",
            ctx,
            approval_id=approval_id,
            tool_id=rec.tool_id,
            outcome="revoked",
        )
        return rec

    def inbox(
        self, ctx: PlatformExecutionContext, *, status: str = "pending", limit: int = 50
    ) -> list[dict[str, Any]]:
        ctx.require_permission(PlatformPermission.APPROVAL_READ)
        self.store.expire_stale_approvals()
        return [
            a.to_public()
            for a in self.store.list_approvals(
                org_id=ctx.org_id, status=status, limit=limit
            )
        ]

    # ── execute via M49 gateway ───────────────────────────────────────────
    def execute_tool(
        self,
        ctx: PlatformExecutionContext,
        *,
        tool_id: str,
        arguments: dict | None = None,
        approval_id: str = "",
        idempotency_key: str = "",
        capability: str = "",
    ):
        """M50 compatibility wrapper; M52 runtime is the sole platform entry."""
        from saathi.platform.runtime import PlatformAgentRuntime

        return PlatformAgentRuntime(self).execute_context(
            ctx,
            tool_id=tool_id,
            arguments=arguments,
            approval_id=approval_id,
            idempotency_key=idempotency_key,
            capability=capability,
        )

    def configuration(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.SETTINGS_READ)
        cfg = {**DEFAULT_CONFIG, **self.store.all_config()}
        # never claim live trading
        cfg["trading_guardian"] = "ADVISORY_ONLY"
        cfg["connectors"] = {
            **DEFAULT_CONFIG["connectors"],
            **(cfg.get("connectors") or {}),
            "mutations": "DRY_RUN_ONLY",
            "live": False,
        }
        return cfg

    def update_configuration(
        self, ctx: PlatformExecutionContext, updates: dict[str, Any]
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.SETTINGS_WRITE)
        # fail closed: cannot enable live connectors or trading via config
        blocked_keys = []
        for k, v in (updates or {}).items():
            if k in ("trading_guardian",) and v not in ("ADVISORY_ONLY", "ADVISORY"):
                blocked_keys.append(k)
                continue
            if k == "connectors" and isinstance(v, dict):
                if v.get("live") is True or str(v.get("mutations", "")).upper() not in (
                    "",
                    "DRY_RUN_ONLY",
                    "DRY_RUN",
                ):
                    blocked_keys.append(k)
                    continue
            self.store.set_config(k, v, updated_by=ctx.user_id)
        self._audit(
            "settings.updated",
            ctx,
            outcome="ok" if not blocked_keys else "partial",
            detail={"keys": list((updates or {}).keys()), "blocked": blocked_keys},
        )
        return self.configuration(ctx)

    def health(self) -> dict[str, Any]:
        return {
            "platform": "M51",
            "identity": "ACTIVE",
            "rbac": "ACTIVE",
            "approval_center": "ACTIVE",
            "workspace_model": "ACTIVE",
            "project_model": "ACTIVE",
            "mission_model": "ACTIVE",
            "private_alpha": "PRODUCTIZED",
            "authentication": "LOCAL_PASSWORD_AND_FIXTURE",
            "session_security": "HARDENED",
            "invitations": "ACTIVE",
            "runtime": {
                "framework": "CANONICAL_TOOL_FRAMEWORK_ACTIVE",
                "gateway": "TOOL_GATEWAY_ENFORCED",
                "authority": "AUTHORITY_FAIL_CLOSED",
                "connectors": "CONNECTOR_MUTATIONS_DRY_RUN_ONLY",
                "trading_guardian": "TRADING_GUARDIAN_UNENGAGED_ADVISORY_ONLY",
                "production": "PRODUCTION_NOT_AUTHORIZED",
            },
            "users": len(self.store.list_users()),
            "db": str(self.store.db_path),
        }


_DEFAULT: PlatformService | None = None


def default_platform() -> PlatformService:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = PlatformService()
    return _DEFAULT


def reset_platform_for_tests(db_path: Path | str | None = None) -> PlatformService:
    global _DEFAULT
    import tempfile

    if _DEFAULT is not None:
        speech_service = getattr(_DEFAULT, "_speech_service", None)
        if speech_service is not None:
            speech_service.shutdown()
    path = db_path or (Path(tempfile.mkdtemp()) / "platform-test.db")
    _DEFAULT = PlatformService(PlatformStore(path))
    return _DEFAULT
