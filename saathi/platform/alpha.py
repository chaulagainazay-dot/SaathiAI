"""M51 private-alpha productization methods mixed into PlatformService.

Extends M50 PlatformService without replacing tenancy or gateway paths.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.identity import (
    AuthenticationMethod,
    LocalAlphaIdentityProvider,
    hash_invite_token,
    hash_password_scrypt,
    new_recovery_code,
    password_policy_check,
    verify_password_scrypt,
)
from saathi.platform.models import PlatformPermission, PlatformRole, new_id
from saathi.platform.rate_limit import AuthAbuseControls


# Role rank for invitation grants (cannot grant above self)
_ROLE_RANK = {
    PlatformRole.VIEWER.value: 1,
    PlatformRole.OPERATOR.value: 2,
    PlatformRole.OWNER.value: 3,
    PlatformRole.ADMIN.value: 4,
}


class PrivateAlphaMixin:
    """Mixin methods for PlatformService (M51)."""

    def _abuse(self) -> AuthAbuseControls:
        if not hasattr(self, "_abuse_ctrl"):
            self._abuse_ctrl = AuthAbuseControls(self.store)
        return self._abuse_ctrl

    def _identity_provider(self) -> LocalAlphaIdentityProvider:
        return LocalAlphaIdentityProvider(
            get_credential=self.store.get_credential,
            get_user_by_email=self.store.get_user_by_email,
            magic_code_verifier=self._verify_magic_fixture,
        )

    def _verify_magic_fixture(self, user_id: str, code: str) -> bool:
        """LOCAL_MAGIC_CODE_FIXTURE — codes stored hashed as recovery-style fixtures."""
        th = hash_invite_token(code.strip())
        uid = self.store.consume_recovery_code(th)
        return uid == user_id

    def private_alpha_banner(self) -> dict[str, Any]:
        return {
            "private_alpha": True,
            "labels": [
                "NOT_PRODUCTION",
                "LIVE_CONNECTOR_MUTATIONS_DISABLED",
                "DEPLOYMENT_DISABLED",
                "FINANCIAL_EXECUTION_PROHIBITED",
                "TRADING_GUARDIAN_ADVISORY_ONLY",
                "SINGLE_HOST_LOCAL_DATA",
                "OWNER_MANAGED_BACKUPS",
            ],
            "forbidden_claims": [
                "Production Ready",
                "Fully Autonomous",
                "Live Trading Enabled",
                "Enterprise Secure",
            ],
        }

    # ── password / auth ───────────────────────────────────────────────────
    def set_password(self, user_id: str, password: str, *, actor_id: str = "") -> dict:
        ok, reason = password_policy_check(password)
        if not ok:
            raise PlatformContextError("PASSWORD_POLICY", reason)
        ph = hash_password_scrypt(password)
        self.store.set_password_hash(user_id, ph)
        self.store.revoke_user_sessions(user_id, reason="password_set")
        self._audit(
            "credential.password_set",
            user_id=actor_id or user_id,
            outcome="ok",
            detail={"target_user": user_id},
        )
        return {"ok": True}

    def change_password(
        self, ctx: PlatformExecutionContext, *, current: str, new_password: str
    ) -> dict:
        cred = self.store.get_credential(ctx.user_id)
        if not cred or not verify_password_scrypt(current, cred.get("password_hash") or ""):
            raise PlatformContextError("AUTH_FAILED", "auth_failed")
        ok, reason = password_policy_check(new_password)
        if not ok:
            raise PlatformContextError("PASSWORD_POLICY", reason)
        self.store.set_password_hash(ctx.user_id, hash_password_scrypt(new_password))
        self.store.revoke_user_sessions(
            ctx.user_id, except_session=ctx.session_id, reason="password_change"
        )
        self._audit("credential.password_changed", ctx, outcome="ok")
        return {"ok": True, "other_sessions_revoked": True}

    def issue_recovery_code(self, ctx: PlatformExecutionContext, target_user_id: str) -> dict:
        """PRIVATE_ALPHA_ONLY — owner/admin can mint a local recovery code (not emailed)."""
        ctx.require_permission(PlatformPermission.USER_MANAGE)
        code = new_recovery_code()
        self.store.save_recovery_code(target_user_id, hash_invite_token(code), ttl_sec=86400)
        self._audit(
            "credential.recovery_issued",
            ctx,
            outcome="ok",
            detail={"target_user": target_user_id, "label": "PRIVATE_ALPHA_ONLY"},
        )
        return {
            "recovery_code": code,
            "label": "PRIVATE_ALPHA_ONLY",
            "not_production_recovery": True,
            "note": "Copy now. Not emailed. NOT_PRODUCTION_RECOVERY.",
        }

    def authenticate_login(
        self,
        *,
        email: str,
        password: str = "",
        method: str = AuthenticationMethod.LOCAL_PASSWORD.value,
        org_id: str = "",
        workspace_id: str = "",
        magic_code: str = "",
        client_key: str = "",
        ttl_sec: float | None = None,
    ) -> dict[str, Any]:
        """Secure login with abuse controls + generic failures.

        ``ttl_sec`` overrides the configured session lifetime. It exists so that
        expiry can be exercised on a credentialed account — the passwordless
        ``PlatformService.login`` path is not available to those.
        """
        email_n = (email or "").strip().lower()
        abuse_key = client_key or email_n or "unknown"
        allowed, why = self._abuse().check("login", abuse_key)
        if not allowed:
            self._audit(
                "auth.login_locked",
                outcome="blocked",
                detail={"surface": "login", "reason": why},
            )
            raise PlatformContextError("AUTH_FAILED", "auth_failed")

        provider = self._identity_provider()
        result = provider.authenticate(
            method=method,
            email=email_n,
            password=password,
            code=magic_code,
        )
        if not result.ok:
            self._abuse().record_failure("login", abuse_key)
            self._audit(
                "auth.login_failed",
                outcome="fail",
                detail={"internal": result.internal_reason, "method": method},
            )
            raise PlatformContextError("AUTH_FAILED", "auth_failed")

        assertion = result.assertion
        assert assertion is not None
        user = self.store.get_user(assertion.subject)
        if not user or user.status != "active":
            self._abuse().record_failure("login", abuse_key)
            raise PlatformContextError("AUTH_FAILED", "auth_failed")

        cred = self.store.get_credential(user.user_id)
        if cred and cred.get("force_reset"):
            raise PlatformContextError("PASSWORD_RESET_REQUIRED", "password_reset_required")

        # rate-limit session create
        ok_s, _ = self._abuse().check("session_create", user.user_id)
        if not ok_s:
            raise PlatformContextError("AUTH_FAILED", "auth_failed")

        orgs = self.store.list_orgs_for_user(user.user_id)
        if not orgs:
            raise PlatformContextError("NO_ORG", "user has no organization")
        org = next((o for o in orgs if o.org_id == org_id), orgs[0]) if org_id else orgs[0]
        role = self.store.membership_role(org.org_id, user.user_id)
        if not role:
            raise PlatformContextError("MEMBERSHIP_REVOKED", "membership inactive")
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

        sec = self.store.get_config("security", {}) or {}
        ttl = float(sec.get("session_ttl_sec", 86400) if ttl_sec is None else ttl_sec)
        idle = float(sec.get("idle_ttl_sec", 3600))
        raw = secrets.token_urlsafe(32)
        sess, token = self.store.create_session(
            user.user_id,
            raw,
            org_id=org.org_id,
            workspace_id=ws.workspace_id,
            role=role,
            ttl_sec=ttl,
            idle_sec=idle,
            auth_method=assertion.method,
        )
        if method == AuthenticationMethod.LOCAL_PASSWORD.value:
            self.store.mark_credential_verified(user.user_id)
        self._abuse().record_success("login", abuse_key)
        self._abuse().record_success("session_create", user.user_id)
        self._audit(
            "session.created",
            user_id=user.user_id,
            role=role,
            org_id=org.org_id,
            workspace_id=ws.workspace_id,
            outcome="ok",
            detail={"session_id": sess.session_id, "auth_method": assertion.method},
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
                "auth_method": assertion.method,
                "session_version": sess.session_version,
            },
            "user": user.to_public(),
            "private_alpha": self.private_alpha_banner(),
            "permissions": sorted(
                p.value
                for p in __import__(
                    "saathi.platform.models", fromlist=["permissions_for_role"]
                ).permissions_for_role(role)
            ),
        }

    def bootstrap_owner_secure(
        self,
        *,
        email: str,
        name: str,
        password: str,
        org_name: str = "Default Org",
        workspace_name: str = "Default Workspace",
    ) -> dict[str, Any]:
        """Owner bootstrap with password — DEVELOPMENT_BOOTSTRAP once."""
        users = self.store.list_users()
        if users:
            raise PlatformContextError("BOOTSTRAP_DONE", "already bootstrapped")
        ok, reason = password_policy_check(password)
        if not ok:
            raise PlatformContextError("PASSWORD_POLICY", reason)
        boot = self.bootstrap_owner(
            email=email, name=name, org_name=org_name, workspace_name=workspace_name
        )
        uid = boot["user"]["user_id"]
        self.store.set_password_hash(uid, hash_password_scrypt(password))
        # login with password
        return self.authenticate_login(
            email=email,
            password=password,
            method=AuthenticationMethod.LOCAL_PASSWORD.value,
        )

    def rotate_session(self, token: str) -> dict[str, Any]:
        sess = self.store.session_by_token(token)
        if not sess:
            raise PlatformContextError("SESSION_INVALID", "session invalid")
        new_raw = secrets.token_urlsafe(32)
        ok = self.store.rotate_session_token(sess.session_id, new_raw)
        if not ok:
            raise PlatformContextError("SESSION_INVALID", "rotation failed")
        # old token must not work
        self._audit(
            "session.rotated",
            user_id=sess.user_id,
            org_id=sess.org_id,
            workspace_id=sess.workspace_id,
            outcome="ok",
            detail={"session_id": sess.session_id},
        )
        return {"token": new_raw, "session_id": sess.session_id}

    def select_workspace(
        self, token: str, *, org_id: str, workspace_id: str
    ) -> dict[str, Any]:
        sess = self.store.session_by_token(token)
        if not sess:
            raise PlatformContextError("SESSION_INVALID", "session invalid")
        role = self.store.membership_role(org_id, sess.user_id)
        if not role:
            raise PlatformContextError("MEMBERSHIP_REVOKED", "not a member")
        ws = self.store.get_workspace(workspace_id)
        if not ws or ws.org_id != org_id:
            raise PlatformContextError("WORKSPACE_ISOLATION", "workspace not in org")
        org = self.store.get_org(org_id)
        if not org:
            raise PlatformContextError("ORG_REQUIRED", "org not found")
        self.store.update_session_context(
            sess.session_id, org_id=org_id, workspace_id=workspace_id, role=role
        )
        # rotate token on context switch for safety
        new_raw = secrets.token_urlsafe(32)
        self.store.rotate_session_token(sess.session_id, new_raw)
        self._audit(
            "context.switched",
            user_id=sess.user_id,
            role=role,
            org_id=org_id,
            workspace_id=workspace_id,
            outcome="ok",
        )
        return {
            "token": new_raw,
            "org_id": org_id,
            "workspace_id": workspace_id,
            "role": role,
            "stale_context_cleared": True,
        }

    # ── invitations ───────────────────────────────────────────────────────
    def create_invitation(
        self,
        ctx: PlatformExecutionContext,
        *,
        email: str,
        role: str = PlatformRole.VIEWER.value,
        workspace_id: str = "",
        ttl_sec: float = 604800,
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.USER_MANAGE)
        if role == PlatformRole.SYSTEM.value:
            raise PlatformContextError("ROLE_INVALID", "system role not assignable")
        if _ROLE_RANK.get(role, 0) > _ROLE_RANK.get(ctx.role, 0):
            raise PlatformContextError("ROLE_ESCALATION", "cannot grant higher role")
        if workspace_id:
            ws = self.store.get_workspace(workspace_id)
            if not ws or ws.org_id != ctx.org_id:
                raise PlatformContextError("WORKSPACE_ISOLATION", "workspace not in org")
        raw = secrets.token_urlsafe(24)
        inv = self.store.create_invitation(
            org_id=ctx.org_id,
            email=email,
            role=role,
            inviter_id=ctx.user_id,
            token_hash=hash_invite_token(raw),
            workspace_id=workspace_id or ctx.workspace_id,
            ttl_sec=ttl_sec,
        )
        self._audit(
            "invitation.created",
            ctx,
            outcome="ok",
            detail={"invite_id": inv["invite_id"], "email": email, "role": role},
        )
        return {
            **inv,
            "local_private_alpha_invite": True,
            "invite_code": raw,
            "label": "LOCAL_PRIVATE_ALPHA_INVITE",
            "note": "Not emailed. Copy and share out-of-band.",
        }

    def accept_invitation(
        self,
        *,
        invite_code: str,
        name: str = "",
        password: str = "",
        client_key: str = "",
    ) -> dict[str, Any]:
        abuse_key = client_key or invite_code[:16]
        ok, _ = self._abuse().check("invite_accept", abuse_key)
        if not ok:
            raise PlatformContextError("AUTH_FAILED", "auth_failed")
        th = hash_invite_token(invite_code.strip())
        inv = self.store.get_invitation_by_token_hash(th)
        if not inv:
            self._abuse().record_failure("invite_accept", abuse_key)
            raise PlatformContextError("INVITE_INVALID", "invite invalid")
        now = time.time()
        if inv["status"] != "pending":
            raise PlatformContextError("INVITE_NOT_PENDING", inv["status"])
        if float(inv["expires_at"]) < now:
            self.store.update_invitation_status(inv["invite_id"], "expired")
            raise PlatformContextError("INVITE_EXPIRED", "invite expired")

        email = inv["email"]
        user = self.store.get_user_by_email(email)
        if not user:
            if not password:
                raise PlatformContextError("PASSWORD_REQUIRED", "password required for new user")
            ok_p, reason = password_policy_check(password)
            if not ok_p:
                raise PlatformContextError("PASSWORD_POLICY", reason)
            user = self.store.create_user(email=email, name=name or email.split("@")[0])
            self.store.set_password_hash(user.user_id, hash_password_scrypt(password))
        self.store.add_member(inv["org_id"], user.user_id, inv["role"])
        self.store.update_invitation_status(
            inv["invite_id"], "accepted", accepted_user_id=user.user_id
        )
        # single-use: token hash remains but status accepted
        self._abuse().record_success("invite_accept", abuse_key)
        self._audit(
            "invitation.accepted",
            user_id=user.user_id,
            org_id=inv["org_id"],
            workspace_id=inv.get("workspace_id") or "",
            outcome="ok",
            detail={"invite_id": inv["invite_id"]},
        )
        return self.authenticate_login(
            email=email,
            password=password,
            method=AuthenticationMethod.LOCAL_PASSWORD.value,
            org_id=inv["org_id"],
            workspace_id=inv.get("workspace_id") or "",
        )

    def revoke_invitation(self, ctx: PlatformExecutionContext, invite_id: str) -> dict:
        ctx.require_permission(PlatformPermission.USER_MANAGE)
        inv = self.store.get_invitation(invite_id)
        if not inv or inv["org_id"] != ctx.org_id:
            raise PlatformContextError("INVITE_INVALID", "not found")
        if inv["status"] != "pending":
            raise PlatformContextError("INVITE_NOT_PENDING", inv["status"])
        self.store.update_invitation_status(invite_id, "revoked")
        self._audit("invitation.revoked", ctx, outcome="ok", detail={"invite_id": invite_id})
        return {"ok": True}

    # ── membership admin ──────────────────────────────────────────────────
    def list_members(self, ctx: PlatformExecutionContext) -> list[dict]:
        ctx.require_permission(PlatformPermission.USER_MANAGE)
        return self.store.list_members(ctx.org_id)

    def change_member_role(
        self, ctx: PlatformExecutionContext, user_id: str, role: str
    ) -> dict:
        ctx.require_permission(PlatformPermission.USER_MANAGE)
        if role == PlatformRole.SYSTEM.value:
            raise PlatformContextError("ROLE_INVALID", "system role not assignable")
        if _ROLE_RANK.get(role, 0) > _ROLE_RANK.get(ctx.role, 0):
            raise PlatformContextError("ROLE_ESCALATION", "cannot grant higher role")
        # last owner protection
        current = self.store.membership_role(ctx.org_id, user_id)
        if current == PlatformRole.OWNER.value and role != PlatformRole.OWNER.value:
            if self.store.count_owners(ctx.org_id) <= 1:
                raise PlatformContextError("LAST_OWNER", "cannot demote last owner")
        if user_id == ctx.user_id and ctx.role == PlatformRole.OWNER.value:
            if role != PlatformRole.OWNER.value and self.store.count_owners(ctx.org_id) <= 1:
                raise PlatformContextError("LAST_OWNER", "cannot demote self as last owner")
        self.store.set_member_role(ctx.org_id, user_id, role)
        self.store.revoke_user_sessions(user_id, reason="role_change")
        self._audit(
            "membership.role_changed",
            ctx,
            outcome="ok",
            detail={"target": user_id, "role": role},
        )
        return {"ok": True}

    def remove_member(self, ctx: PlatformExecutionContext, user_id: str) -> dict:
        ctx.require_permission(PlatformPermission.USER_MANAGE)
        role = self.store.membership_role(ctx.org_id, user_id)
        if role == PlatformRole.OWNER.value and self.store.count_owners(ctx.org_id) <= 1:
            raise PlatformContextError("LAST_OWNER", "cannot remove last owner")
        if user_id == ctx.user_id and self.store.count_owners(ctx.org_id) <= 1:
            raise PlatformContextError("LAST_OWNER", "cannot remove self as last owner")
        self.store.remove_member(ctx.org_id, user_id)
        n = self.store.revoke_user_sessions(user_id, reason="membership_removed")
        # projects/missions retain ownership for audit; access is membership-gated
        self._audit(
            "membership.removed",
            ctx,
            outcome="ok",
            detail={
                "target": user_id,
                "sessions_revoked": n,
                "project_ownership": "retained_for_history",
                "mission_ownership": "retained_for_history",
                "approvals": "remain_immutable_audit",
            },
        )
        return {"ok": True, "sessions_revoked": n}

    def suspend_member(self, ctx: PlatformExecutionContext, user_id: str) -> dict:
        ctx.require_permission(PlatformPermission.USER_MANAGE)
        self.store.set_member_status(ctx.org_id, user_id, "suspended")
        n = self.store.revoke_user_sessions(user_id, reason="membership_suspended")
        self._audit(
            "membership.suspended",
            ctx,
            outcome="ok",
            detail={"target": user_id, "sessions_revoked": n},
        )
        return {"ok": True}

    def link_legacy_mission(
        self, ctx: PlatformExecutionContext, mission_id: str, legacy_key: str
    ) -> dict:
        ctx.require_permission(PlatformPermission.MISSION_WRITE)
        mis = self.store.get_mission(mission_id)
        if not mis or mis.org_id != ctx.org_id or mis.workspace_id != ctx.workspace_id:
            raise PlatformContextError("MISSION_ISOLATION", "mission not accessible")
        self.store.link_legacy_mission(
            mission_id, legacy_key, ctx.org_id, ctx.workspace_id
        )
        self._audit(
            "mission.legacy_linked",
            ctx,
            mission_id=mission_id,
            outcome="ok",
            detail={"legacy_key": legacy_key},
        )
        return {"ok": True, "mission_id": mission_id, "legacy_key": legacy_key}

    def owner_safety_flags(self, ctx: PlatformExecutionContext) -> dict:
        ctx.require_permission(PlatformPermission.SETTINGS_READ)
        cfg = self.configuration(ctx)
        return {
            "login_enabled": cfg.get("security", {}).get("login_enabled", True),
            "execution_enabled": cfg.get("security", {}).get("execution_enabled", True),
            "mutations_enabled": False,  # always dry-run connectors
            "approvals_enabled": cfg.get("security", {}).get("approvals_enabled", True),
            "authority_ceiling": cfg.get("security", {}).get(
                "authority_ceiling", "SECURITY_SENSITIVE"
            ),
            "private_alpha": self.private_alpha_banner(),
            "trading_guardian": "ADVISORY_ONLY",
            "connectors": "DRY_RUN_ONLY",
        }

    def owner_set_safety(
        self, ctx: PlatformExecutionContext, updates: dict[str, Any]
    ) -> dict:
        ctx.require_permission(PlatformPermission.SETTINGS_WRITE)
        sec = dict(self.store.get_config("security", {}) or {})
        for k in ("login_enabled", "execution_enabled", "approvals_enabled"):
            if k in updates:
                sec[k] = bool(updates[k])
        if "authority_ceiling" in updates:
            from saathi.platform.bindings import SAFE_AUTHORITY_ORDER

            ceiling = str(updates["authority_ceiling"])
            if ceiling not in SAFE_AUTHORITY_ORDER:
                raise PlatformContextError(
                    "AUTHORITY_CEILING_INVALID",
                    "financial or unknown authority ceiling is prohibited",
                )
            sec["authority_ceiling"] = ceiling
        # never allow enabling live connectors via safety
        self.store.set_config("security", sec, updated_by=ctx.user_id)
        self._audit("owner.safety_updated", ctx, outcome="ok", detail=updates)
        return self.owner_safety_flags(ctx)


def patch_platform_service() -> None:
    """Attach PrivateAlphaMixin methods onto PlatformService class."""
    from saathi.platform.service import PlatformService

    for name, attr in PrivateAlphaMixin.__dict__.items():
        if name.startswith("_") and name not in (
            "_abuse",
            "_identity_provider",
            "_verify_magic_fixture",
        ):
            if callable(attr) and name != "__init__":
                continue
        if callable(attr) and not name.startswith("__"):
            setattr(PlatformService, name, attr)


# Apply on import
patch_platform_service()
