"""M61 WorkflowService — server-authoritative persistence for operator workflows.

Replaces the M60 frontend-only / draft-only / derived / local-only states with
durable, tenant-scoped, versioned records. Every mutation is permission-gated
(via PlatformExecutionContext), audited (append_audit), and optimistic-concurrency
checked. This service NEVER executes tools, grants execution authority, or bypasses
PlatformAgentRuntime / ExecutionGateway. It only persists operator-facing metadata.
"""
from __future__ import annotations

from typing import Any

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.models import PlatformPermission
from saathi.platform.store import PlatformStore


def _conflict(kind: str, record: dict | None) -> None:
    if kind == "not_found":
        raise PlatformContextError("NOT_FOUND", "object not found or outside scope")
    if kind == "conflict":
        raise PlatformContextError("STALE_STATE", "version conflict — reload authoritative state")


class WorkflowService:
    def __init__(self, store: PlatformStore):
        self.store = store

    def _audit(self, ctx: PlatformExecutionContext, event: str, **extra) -> None:
        base = ctx.to_audit_dict()
        detail = extra.pop("detail", None)
        self.store.append_audit(
            event,
            user_id=str(base.get("user_id") or ""),
            role=str(base.get("role") or ""),
            org_id=str(base.get("org_id") or ""),
            workspace_id=str(base.get("workspace_id") or ""),
            project_id=str(extra.get("project_id") or base.get("project_id") or ""),
            mission_id=str(extra.get("mission_id") or ""),
            execution_id=str(extra.get("execution_id") or ""),
            outcome=str(extra.get("outcome") or "ok"),
            detail=detail if isinstance(detail, dict) else {k: v for k, v in extra.items()},
        )

    # ── mission plans ─────────────────────────────────────────────────────
    def upsert_plan(self, ctx, *, mission_id, body, state=None, expected_version=None) -> dict:
        ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        existing = self.store.get_plan_for_mission(mission_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id)
        if existing is None:
            plan = self.store.create_plan(
                mission_id=mission_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id,
                project_id=ctx.project_id, owner_id=ctx.user_id, body=body, state=state or "draft",
            )
            self._audit(ctx, "workflow.plan.created", mission_id=mission_id, detail={"plan_id": plan["plan_id"]})
            return plan
        ev = expected_version if expected_version is not None else existing["version"]
        kind, rec = self.store.update_plan(
            existing["plan_id"], org_id=ctx.org_id, workspace_id=ctx.workspace_id,
            expected_version=ev, body=body, state=state, updated_by=ctx.user_id,
        )
        _conflict(kind, rec)
        self._audit(ctx, "workflow.plan.updated", mission_id=mission_id, detail={"plan_id": existing["plan_id"], "version": rec["version"]})
        return rec

    def get_plan(self, ctx, *, mission_id) -> dict | None:
        ctx.require_permission(PlatformPermission.WORKFLOW_READ)
        return self.store.get_plan_for_mission(mission_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id)

    def plan_revisions(self, ctx, *, plan_id) -> list[dict]:
        ctx.require_permission(PlatformPermission.WORKFLOW_READ)
        return self.store.list_plan_revisions(plan_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id)

    def publish_plan(self, ctx, *, mission_id, expected_version) -> dict:
        ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        existing = self.store.get_plan_for_mission(mission_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id)
        if not existing:
            raise PlatformContextError("NOT_FOUND", "no plan for mission")
        kind, rec = self.store.update_plan(existing["plan_id"], org_id=ctx.org_id, workspace_id=ctx.workspace_id, expected_version=expected_version, state="published", updated_by=ctx.user_id)
        _conflict(kind, rec)
        self._audit(ctx, "workflow.plan.published", mission_id=mission_id, detail={"plan_id": existing["plan_id"]})
        return rec

    # ── notifications ─────────────────────────────────────────────────────
    def create_notification(self, ctx, *, type, title, summary="", severity="info", related_object="", related_type="", evidence="", dedupe_key="") -> dict:
        ctx.require_permission(PlatformPermission.NOTIFICATION_WRITE)
        n = self.store.create_notification(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, user_id="", type=type, title=title,
            summary=summary, severity=severity, actor=f"user:{ctx.user_id}", related_object=related_object,
            related_type=related_type, evidence=evidence, dedupe_key=dedupe_key,
        )
        self._audit(ctx, "notification.created", detail={"notification_id": n["notification_id"], "type": type})
        return n

    def list_notifications(self, ctx, *, include_archived=False) -> list[dict]:
        ctx.require_permission(PlatformPermission.NOTIFICATION_READ)
        return self.store.list_notifications(org_id=ctx.org_id, workspace_id=ctx.workspace_id, include_archived=include_archived)

    def set_notification(self, ctx, notification_id, *, read=None, archived=None) -> dict:
        ctx.require_permission(PlatformPermission.NOTIFICATION_WRITE)
        rec = self.store.set_notification_flags(notification_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, read=read, archived=archived)
        if not rec:
            raise PlatformContextError("NOT_FOUND", "notification not found")
        self._audit(ctx, "notification.updated", detail={"notification_id": notification_id, "read": read, "archived": archived})
        return rec

    # ── saved views ───────────────────────────────────────────────────────
    def create_view(self, ctx, *, name, route, config, is_default=False) -> dict:
        ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        _reject_secrets(config)
        v = self.store.create_saved_view(org_id=ctx.org_id, workspace_id=ctx.workspace_id, user_id=ctx.user_id, name=name, route=route, config=config, is_default=is_default)
        self._audit(ctx, "saved_view.created", detail={"view_id": v["view_id"]})
        return v

    def list_views(self, ctx) -> list[dict]:
        ctx.require_permission(PlatformPermission.WORKFLOW_READ)
        return self.store.list_saved_views(org_id=ctx.org_id, workspace_id=ctx.workspace_id, user_id=ctx.user_id)

    def update_view(self, ctx, view_id, *, expected_version, name=None, route=None, config=None, is_default=None) -> dict:
        ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        if config is not None:
            _reject_secrets(config)
        kind, rec = self.store.update_saved_view(view_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, user_id=ctx.user_id, expected_version=expected_version, name=name, route=route, config=config, is_default=is_default)
        _conflict(kind, rec)
        self._audit(ctx, "saved_view.updated", detail={"view_id": view_id})
        return rec

    def delete_view(self, ctx, view_id) -> None:
        ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        if not self.store.delete_saved_view(view_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, user_id=ctx.user_id):
            raise PlatformContextError("NOT_FOUND", "saved view not found")
        self._audit(ctx, "saved_view.deleted", detail={"view_id": view_id})

    # ── templates ─────────────────────────────────────────────────────────
    def create_template(self, ctx, *, name, body) -> dict:
        ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        t = self.store.create_template(org_id=ctx.org_id, workspace_id=ctx.workspace_id, owner_id=ctx.user_id, name=name, body=body)
        self._audit(ctx, "template.created", detail={"template_id": t["template_id"]})
        return t

    def list_templates(self, ctx) -> list[dict]:
        ctx.require_permission(PlatformPermission.WORKFLOW_READ)
        return self.store.list_templates(org_id=ctx.org_id, workspace_id=ctx.workspace_id)

    def update_template(self, ctx, template_id, *, expected_version, name=None, body=None, state=None) -> dict:
        ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        kind, rec = self.store.update_template(template_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, expected_version=expected_version, name=name, body=body, state=state)
        _conflict(kind, rec)
        self._audit(ctx, "template.updated", detail={"template_id": template_id})
        return rec

    # ── drafts ────────────────────────────────────────────────────────────
    def save_draft(self, ctx, *, kind, body) -> dict:
        ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        _reject_secrets(body)
        d = self.store.upsert_draft(org_id=ctx.org_id, workspace_id=ctx.workspace_id, user_id=ctx.user_id, kind=kind, body=body)
        return d

    def get_draft(self, ctx, *, kind) -> dict | None:
        ctx.require_permission(PlatformPermission.WORKFLOW_READ)
        return self.store.get_draft(org_id=ctx.org_id, workspace_id=ctx.workspace_id, user_id=ctx.user_id, kind=kind)

    def discard_draft(self, ctx, *, kind) -> None:
        ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        self.store.delete_draft(org_id=ctx.org_id, workspace_id=ctx.workspace_id, user_id=ctx.user_id, kind=kind)

    # ── attention mutations ───────────────────────────────────────────────
    def attention_transition(self, ctx, execution_id, *, action, note="", expected_version=None) -> dict:
        ctx.require_permission(PlatformPermission.ATTENTION_WRITE)
        target = {"acknowledge": "acknowledged", "resolve": "resolved", "reopen": "open"}.get(action)
        if not target:
            raise PlatformContextError("VALIDATION_FAILED", f"unknown attention action: {action}")
        kind, rec = self.store.set_attention_state(execution_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, state=target, actor=f"user:{ctx.user_id}", note=note, expected_version=expected_version)
        _conflict(kind, rec)
        self._audit(ctx, f"attention.{action}", execution_id=execution_id, detail={"state": target, "note": note[:200]})
        return rec

    def attention_state(self, ctx, execution_id) -> dict:
        ctx.require_permission(PlatformPermission.WORKFLOW_READ)
        return self.store.get_attention_state(execution_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id)

    # ── server search (authorized, tenant-scoped, read-only) ──────────────
    def search(self, ctx, query: str, *, type_filter="all", limit=50) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.WORKFLOW_READ)
        q = (query or "").strip().lower()
        results: list[dict] = []
        if not q:
            return {"scope": "SERVER_AUTHORIZED", "results": [], "query": query}
        st = self.store

        def add(t, cond, oid, label, route):
            if (type_filter in ("all", t)) and cond and len(results) < limit:
                results.append({"type": t, "id": oid, "label": label, "route": route})

        for m in st.list_missions(org_id=ctx.org_id):
            add("mission", q in (m.name or "").lower() or q in (m.key or "").lower() or q in m.mission_id.lower(), m.mission_id, f"Mission — {m.name}", f"/platform/missions/{m.mission_id}")
        for p in st.list_projects(org_id=ctx.org_id, workspace_id=ctx.workspace_id):
            add("project", q in (p.name or "").lower() or q in p.project_id.lower(), p.project_id, f"Project — {p.name}", "/platform/missions")
        for a in st.list_approvals(org_id=ctx.org_id, status="", limit=500):
            add("approval", q in (a.tool_id or "").lower() or q in a.approval_id.lower(), a.approval_id, f"Approval — {a.tool_id}", f"/platform/approvals/{a.approval_id}")
        for t in st.list_templates(org_id=ctx.org_id, workspace_id=ctx.workspace_id):
            add("template", q in (t["name"] or "").lower(), t["template_id"], f"Template — {t['name']}", "/platform/templates")
        for n in st.list_notifications(org_id=ctx.org_id, workspace_id=ctx.workspace_id):
            add("notification", q in (n["title"] or "").lower(), n["notification_id"], f"Notification — {n['title']}", n.get("related_object") and f"/platform/attention/{n['related_object']}" or "/platform/notifications")
        return {"scope": "SERVER_AUTHORIZED", "results": results, "query": query, "count": len(results)}


_SECRET_KEYS = ("token", "credential", "secret", "authority", "permission", "password", "apikey", "api_key")


def _reject_secrets(obj: Any) -> None:
    """Fail closed if a persisted blob carries a secret-shaped key."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(s in str(k).lower() for s in _SECRET_KEYS):
                raise PlatformContextError("UNSAFE_CONFIG", f"forbidden field in persisted payload: {k}")
            _reject_secrets(v)
    elif isinstance(obj, list):
        for v in obj:
            _reject_secrets(v)
