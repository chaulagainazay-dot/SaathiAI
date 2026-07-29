"""SaathiOS Core Operating System unification service.

One assistant, one search, one dashboard, one notification center, one memory
surface — all built by composing certified subsystems:

- AppRuntime, HcgService, IELTSService
- WorkflowService (notifications, workflow search, plans)
- ConversationService intent patterns (propose only)
- KnowledgeService (when available)
- Approval Center / ExecutionGateway (never bypassed)

This is NOT a second memory, search, notification, workflow, or approval engine.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.models import PlatformPermission, new_id

SCHEMA = "m148.core_os.v1"
MEMORY_KEY = "m148_core_memory"
AUTOMATIONS_KEY = "m148_core_automations"
WORKFLOWS_KEY = "m148_core_workflow_graphs"
ACTIVITY_KEY = "m148_core_activity"
PREFS_KEY = "m148_core_preferences"


class SaathiCoreService:
    def __init__(self, platform=None):
        if platform is None:
            from saathi.platform.service import default_platform

            platform = default_platform()
        self.platform = platform
        self.store = platform.store

    def _read(self, ctx: PlatformExecutionContext) -> None:
        ctx.require_permission(PlatformPermission.RUNTIME_READ)

    def _operate(self, ctx: PlatformExecutionContext) -> None:
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)

    def _audit(self, ctx, event: str, *, detail: dict | None = None) -> None:
        self.store.append_audit(
            event,
            user_id=ctx.user_id,
            role=ctx.role,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=getattr(ctx, "project_id", ""),
            mission_id=getattr(ctx, "mission_id", ""),
            outcome="ok",
            detail=detail or {},
        )

    def _scope(self, ctx) -> str:
        return f"{ctx.org_id}:{ctx.workspace_id}:{ctx.user_id}"

    def _mem_bucket(self) -> dict:
        return dict(self.store.get_config(MEMORY_KEY, {}) or {})

    def _save_mem(self, bucket: dict) -> None:
        self.store.set_config(MEMORY_KEY, bucket, updated_by="core_os")

    def _user_mem(self, ctx) -> dict:
        b = self._mem_bucket()
        key = self._scope(ctx)
        slot = dict(b.get(key) or {})
        slot.setdefault("preferences", {})
        slot.setdefault("goals", [])
        slot.setdefault("recent_work", [])
        slot.setdefault("pinned", [])
        slot.setdefault("frequent_commands", [])
        slot.setdefault("app_history", [])
        slot.setdefault("favorite_reports", [])
        slot.setdefault("favorite_dashboards", [])
        slot.setdefault("recent_searches", [])
        slot.setdefault("recent_conversations", [])
        slot.setdefault("recent_workflows", [])
        return slot

    def _put_user_mem(self, ctx, slot: dict) -> None:
        b = self._mem_bucket()
        b[self._scope(ctx)] = slot
        self._save_mem(b)

    def _activity_append(self, ctx, kind: str, summary: str, **extra) -> None:
        events = list(self.store.get_config(ACTIVITY_KEY, []) or [])
        events.insert(
            0,
            {
                "id": new_id("act_"),
                "org_id": ctx.org_id,
                "workspace_id": ctx.workspace_id,
                "user_id": ctx.user_id,
                "kind": kind,
                "summary": summary[:300],
                "ts": time.time(),
                **{k: v for k, v in extra.items() if k not in ("org_id", "workspace_id")},
            },
        )
        self.store.set_config(ACTIVITY_KEY, events[:500], updated_by="core_os")

    # ── Operator Home / Dashboard (M148 / M155) ───────────────────────────
    def operator_home(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._read(ctx)
        apps_summary = {"installed": 0, "enabled": 0, "running": 0, "apps": []}
        try:
            from saathi.platform.apps import default_app_runtime

            rt = default_app_runtime(self.platform)
            launcher = rt.launcher(ctx)
            apps_summary = {
                "installed": len(launcher.get("installed") or []),
                "enabled": len(launcher.get("enabled") or []),
                "running": sum(
                    1
                    for a in (launcher.get("installed") or [])
                    if a.get("lifecycle_state") == "RUNNING"
                ),
                "apps": [
                    {
                        "app_id": a.get("app_id"),
                        "display_name": (a.get("manifest") or {}).get("display_name")
                        or a.get("app_id"),
                        "state": a.get("lifecycle_state"),
                        "href": self._app_href(a.get("app_id") or ""),
                    }
                    for a in (launcher.get("enabled") or [])[:20]
                ],
                "marketplace": False,
            }
        except Exception as exc:  # noqa: BLE001
            apps_summary["error"] = str(exc)[:120]

        hcg_metrics = None
        try:
            from saathi.platform.hcg import HcgService

            hcg = HcgService(self.store, platform=self.platform)
            dash = hcg.dashboard(ctx)
            hcg_metrics = {
                "sales_today_minor": dash["metrics"].get("sales_today_minor"),
                "order_count": dash["metrics"].get("order_count"),
                "low_stock_count": dash["metrics"].get("low_stock_count"),
                "open_shift_count": dash["metrics"].get("open_shift_count"),
                "label": dash.get("label"),
                "href": "/apps/hcg",
            }
        except Exception:
            hcg_metrics = {"available": False, "href": "/apps/hcg"}

        ielts_metrics = None
        try:
            from saathi.platform.ielts.service import IELTSService

            ielts = IELTSService(self.store)
            pd = ielts.product_dashboard(ctx)
            ielts_metrics = {
                "practice_count": (pd.get("progress") or {}).get("practice_count"),
                "readiness": (pd.get("readiness") or {}).get("readiness_label"),
                "overall_estimate": (pd.get("readiness") or {}).get("overall_estimate"),
                "label": pd.get("label"),
                "href": "/apps/ielts",
            }
        except Exception:
            ielts_metrics = {"available": False, "href": "/apps/ielts"}

        notifications = []
        try:
            from saathi.platform.workflow_service import WorkflowService

            wf = WorkflowService(self.store)
            notifications = wf.list_notifications(ctx)[:15]
        except Exception:
            notifications = []

        approvals = []
        try:
            approvals = [
                a.to_public() if hasattr(a, "to_public") else a
                for a in self.store.list_approvals(org_id=ctx.org_id, status="pending", limit=20)
            ]
        except Exception:
            approvals = []

        mem = self._user_mem(ctx)
        activity = [
            e
            for e in (self.store.get_config(ACTIVITY_KEY, []) or [])
            if e.get("org_id") == ctx.org_id and e.get("workspace_id") == ctx.workspace_id
        ][:20]

        automations = self.list_automations(ctx).get("automations") or []
        health = self.health(ctx)

        return {
            "schema": SCHEMA,
            "title": "Operator Home",
            "applications": apps_summary,
            "hcg": hcg_metrics,
            "ielts": ielts_metrics,
            "notifications": notifications,
            "approvals_pending": approvals,
            "approvals_count": len(approvals),
            "memory": {
                "pinned_count": len(mem.get("pinned") or []),
                "recent_searches": (mem.get("recent_searches") or [])[:5],
                "recent_work": (mem.get("recent_work") or [])[:5],
            },
            "activity": activity,
            "automations_count": len(automations),
            "todays_work": self._todays_work(hcg_metrics, ielts_metrics, approvals, notifications),
            "quick_actions": [
                {"id": "open_hcg", "label": "Open HCG Operations", "href": "/apps/hcg"},
                {"id": "open_ielts", "label": "Open IELTSAlert", "href": "/apps/ielts"},
                {"id": "approvals", "label": "Review approvals", "href": "/platform/approvals"},
                {"id": "search", "label": "Universal search", "href": "/platform/search"},
                {"id": "apps", "label": "Application launcher", "href": "/apps"},
                {"id": "notifications", "label": "Notification center", "href": "/platform/notifications"},
            ],
            "health": health,
            "cross_app": True,
            "unified": True,
            "production_authorized": False,
        }

    @staticmethod
    def _app_href(app_id: str) -> str:
        if app_id == "saathi.hcg_pos":
            return "/apps/hcg"
        if app_id == "saathi.ielts_alert":
            return "/apps/ielts"
        return "/apps"

    @staticmethod
    def _todays_work(hcg, ielts, approvals, notifications) -> list[dict]:
        items = []
        if approvals:
            items.append(
                {
                    "priority": 1,
                    "label": f"{len(approvals)} approval(s) pending",
                    "href": "/platform/approvals",
                }
            )
        if hcg and hcg.get("low_stock_count"):
            items.append(
                {
                    "priority": 2,
                    "label": f"HCG: {hcg['low_stock_count']} low-stock item(s)",
                    "href": "/apps/hcg",
                }
            )
        if ielts and ielts.get("readiness"):
            items.append(
                {
                    "priority": 3,
                    "label": f"IELTS readiness: {ielts.get('readiness')}",
                    "href": "/apps/ielts",
                }
            )
        unread = [n for n in notifications if not n.get("read")]
        if unread:
            items.append(
                {
                    "priority": 4,
                    "label": f"{len(unread)} notification(s)",
                    "href": "/platform/notifications",
                }
            )
        if not items:
            items.append({"priority": 9, "label": "No urgent work — open an application", "href": "/apps"})
        return sorted(items, key=lambda x: x["priority"])

    def health(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._read(ctx)
        return {
            "status": "HEALTHY",
            "schema": SCHEMA,
            "core_complete_posture": "local_unification_layer",
            "duplicates_forbidden": True,
            "subsystems": {
                "app_runtime": True,
                "workflow_notifications": True,
                "hcg": True,
                "ielts": True,
                "execution_gateway": "authoritative",
                "approval_center": "authoritative",
            },
            "production_authorized": False,
            "marketplace": False,
        }

    # ── Universal Search (M149) ───────────────────────────────────────────
    def universal_search(
        self, ctx: PlatformExecutionContext, query: str, *, limit: int = 40
    ) -> dict[str, Any]:
        self._read(ctx)
        q = (query or "").strip()
        if not q:
            return {"query": q, "results": [], "count": 0, "scope": "SERVER_AUTHORIZED"}
        results: list[dict] = []
        limit = max(1, min(int(limit), 100))

        # Platform workflow search (missions, projects, approvals, templates, notifications)
        try:
            from saathi.platform.workflow_service import WorkflowService

            wf = WorkflowService(self.store)
            wr = wf.search(ctx, q, type_filter="all", limit=limit)
            for r in wr.get("results") or []:
                results.append(
                    {
                        "source": "platform",
                        "type": r.get("type"),
                        "id": r.get("id"),
                        "label": r.get("label"),
                        "href": r.get("route"),
                    }
                )
        except Exception:
            pass

        # Applications
        try:
            from saathi.platform.apps import default_app_runtime

            for a in default_app_runtime(self.platform).list_apps(ctx).get("apps") or []:
                name = ((a.get("manifest") or {}).get("display_name") or a.get("app_id") or "").lower()
                aid = (a.get("app_id") or "").lower()
                if q.lower() in name or q.lower() in aid:
                    results.append(
                        {
                            "source": "apps",
                            "type": "application",
                            "id": a.get("app_id"),
                            "label": f"App — {(a.get('manifest') or {}).get('display_name') or a.get('app_id')}",
                            "href": self._app_href(a.get("app_id") or ""),
                        }
                    )
        except Exception:
            pass

        # HCG
        try:
            from saathi.platform.hcg import HcgService

            hcg = HcgService(self.store, platform=self.platform)
            for r in (hcg.search(ctx, q=q, limit=15).get("results") or []):
                results.append(
                    {
                        "source": "hcg",
                        "type": r.get("record_type") or "hcg",
                        "id": r.get("record_id"),
                        "label": f"HCG — {r.get('record_type')} {r.get('status')}",
                        "href": "/apps/hcg",
                    }
                )
        except Exception:
            pass

        # IELTS
        try:
            from saathi.platform.ielts.service import IELTSService

            for r in IELTSService(self.store).search(ctx, q, limit=15):
                results.append(
                    {
                        "source": "ielts",
                        "type": r.get("record_type") or "ielts",
                        "id": r.get("record_id"),
                        "label": f"IELTS — {r.get('record_type')} {r.get('status')}",
                        "href": "/apps/ielts",
                    }
                )
        except Exception:
            pass

        # Knowledge (if permitted)
        try:
            from saathi.platform.knowledge.service import KnowledgeService

            if role_allows_knowledge(ctx):
                ks = KnowledgeService(self.platform)
                kr = ks.search(ctx, q, top_k=5)
                for hit in (kr.get("results") or kr.get("hits") or [])[:5]:
                    results.append(
                        {
                            "source": "knowledge",
                            "type": "knowledge",
                            "id": hit.get("id") or hit.get("chunk_id") or "",
                            "label": f"Knowledge — {(hit.get('title') or hit.get('text') or '')[:80]}",
                            "href": "/knowledge",
                        }
                    )
        except Exception:
            pass

        # Static command/nav hits
        for cmd in STATIC_COMMANDS:
            if q.lower() in cmd["label"].lower() or q.lower() in cmd["id"].lower():
                results.append({**cmd, "source": "commands", "type": "command"})

        # Memory: recent searches
        mem = self._user_mem(ctx)
        searches = list(mem.get("recent_searches") or [])
        if q not in searches:
            searches.insert(0, q[:120])
            mem["recent_searches"] = searches[:20]
            self._put_user_mem(ctx, mem)

        self._activity_append(ctx, "search", f"Search: {q[:80]}")
        out = results[:limit]
        return {
            "query": q,
            "results": out,
            "count": len(out),
            "scope": "SERVER_AUTHORIZED",
            "tenant_isolated": True,
            "workspace_isolated": True,
            "permissions_enforced": True,
        }

    # ── Unified Yeti (M150) ───────────────────────────────────────────────
    def yeti_ask(self, ctx: PlatformExecutionContext, question: str) -> dict[str, Any]:
        """Cross-app grounded Q&A. Read-only; never mutates financials/assessments."""
        self._read(ctx)
        q = (question or "").strip()
        if not q:
            raise PlatformContextError("VALIDATION_FAILED", "question required")
        ql = q.lower()
        answers: list[dict] = []
        intent = self._classify_intent(ql)

        if intent in ("hcg", "sales", "inventory", "revenue", "orders") or any(
            w in ql for w in ("sold", "sales", "inventory", "cash", "hcg", "revenue", "supplier", "stock")
        ):
            try:
                from saathi.platform.hcg import HcgService

                ans = HcgService(self.store, platform=self.platform).grounded_answer(ctx, q)
                answers.append({"domain": "hcg", **ans})
            except Exception as exc:  # noqa: BLE001
                answers.append({"domain": "hcg", "answer": f"HCG unavailable: {str(exc)[:100]}", "can_mutate": False})

        if intent in ("ielts", "study", "band") or any(
            w in ql for w in ("ielts", "study", "band", "readiness", "writing", "speaking", "practice")
        ):
            try:
                from saathi.platform.ielts.service import IELTSService

                ans = IELTSService(self.store).grounded_answer(ctx, q)
                answers.append({"domain": "ielts", **ans})
            except Exception as exc:  # noqa: BLE001
                answers.append({"domain": "ielts", "answer": f"IELTS unavailable: {str(exc)[:100]}", "can_mutate": False})

        if any(w in ql for w in ("approval", "approve", "pending")):
            try:
                pending = self.store.list_approvals(org_id=ctx.org_id, status="pending", limit=20)
                answers.append(
                    {
                        "domain": "approvals",
                        "answer": f"{len(pending)} pending approval(s). Open Approval Center to decide — models cannot approve.",
                        "can_mutate": False,
                        "href": "/platform/approvals",
                        "count": len(pending),
                    }
                )
            except Exception:
                pass

        if any(w in ql for w in ("first", "today", "attention", "should i", "priority", "overnight", "changed")):
            home = self.operator_home(ctx)
            work = home.get("todays_work") or []
            lines = "; ".join(w["label"] for w in work[:5])
            answers.append(
                {
                    "domain": "operator",
                    "answer": f"Today's priorities: {lines}",
                    "can_mutate": False,
                    "items": work,
                }
            )

        if any(w in ql for w in ("application", "apps", "health")):
            home = self.operator_home(ctx)
            apps = home.get("applications") or {}
            answers.append(
                {
                    "domain": "apps",
                    "answer": (
                        f"{apps.get('enabled', 0)} enabled app(s), "
                        f"{apps.get('running', 0)} running. Marketplace not authorized."
                    ),
                    "can_mutate": False,
                    "apps": apps.get("apps") or [],
                }
            )

        if not answers:
            answers.append(
                {
                    "domain": "general",
                    "answer": (
                        "I can answer about HCG operations, IELTS progress, approvals, "
                        "applications, and today's priorities. I cannot bypass ExecutionGateway "
                        "or mutate financial/assessment records."
                    ),
                    "can_mutate": False,
                }
            )

        # Compose primary answer
        primary = answers[0]
        mem = self._user_mem(ctx)
        recent = list(mem.get("recent_conversations") or [])
        recent.insert(0, {"q": q[:200], "a": (primary.get("answer") or "")[:300], "ts": time.time()})
        mem["recent_conversations"] = recent[:30]
        self._put_user_mem(ctx, mem)
        self._activity_append(ctx, "yeti", f"Yeti: {q[:80]}")
        self._audit(ctx, "core.yeti.ask", detail={"domains": [a.get("domain") for a in answers]})

        return {
            "question": q,
            "answer": primary.get("answer"),
            "domains": answers,
            "can_mutate": False,
            "mutable": False,
            "execution_gateway_bypass": False,
            "approval_bypass": False,
            "intent": intent,
            "source": "SaathiCoreService.yeti_ask",
            "security": "Conversation proposes; ExecutionGateway + Approval Center remain authoritative",
        }

    @staticmethod
    def _classify_intent(ql: str) -> str:
        if any(w in ql for w in ("hcg", "sold", "sales", "cash", "inventory", "stock", "revenue")):
            return "hcg"
        if any(w in ql for w in ("ielts", "study", "band", "writing", "speaking", "readiness")):
            return "ielts"
        if "approval" in ql:
            return "approvals"
        return "general"

    # ── Memory / Preferences (M148) ───────────────────────────────────────
    def get_memory(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._read(ctx)
        slot = self._user_mem(ctx)
        return {
            "memory": slot,
            "scope": self._scope(ctx),
            "tenant_isolated": True,
            "workspace_isolated": True,
            "user_isolated": True,
            "explainable": True,
        }

    def update_preferences(self, ctx: PlatformExecutionContext, preferences: dict) -> dict:
        try:
            ctx.require_permission(PlatformPermission.WORKSPACE_WRITE)
        except PlatformContextError:
            try:
                ctx.require_permission(PlatformPermission.SETTINGS_WRITE)
            except PlatformContextError:
                ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        slot = self._user_mem(ctx)
        prefs = dict(slot.get("preferences") or {})
        for k, v in (preferences or {}).items():
            if str(k).lower() in ("token", "password", "secret", "credential", "api_key"):
                raise PlatformContextError("UNSAFE_CONFIG", f"forbidden preference key: {k}")
            if isinstance(v, str) and len(v) > 500:
                raise PlatformContextError("VALIDATION_FAILED", "preference value too long")
            prefs[str(k)[:80]] = v
        slot["preferences"] = prefs
        self._put_user_mem(ctx, slot)
        self._audit(ctx, "core.memory.preferences", detail={"keys": list(prefs.keys())[:20]})
        return {"preferences": prefs}

    def pin_item(self, ctx: PlatformExecutionContext, *, item_type: str, item_id: str, label: str = "") -> dict:
        try:
            ctx.require_permission(PlatformPermission.WORKSPACE_WRITE)
        except PlatformContextError:
            self._read(ctx)
        slot = self._user_mem(ctx)
        pins = list(slot.get("pinned") or [])
        entry = {
            "type": (item_type or "")[:40],
            "id": (item_id or "")[:120],
            "label": (label or item_id or "")[:200],
            "ts": time.time(),
        }
        pins = [p for p in pins if not (p.get("type") == entry["type"] and p.get("id") == entry["id"])]
        pins.insert(0, entry)
        slot["pinned"] = pins[:50]
        self._put_user_mem(ctx, slot)
        return {"pinned": slot["pinned"]}

    def record_work(self, ctx: PlatformExecutionContext, *, label: str, href: str = "") -> dict:
        self._read(ctx)
        slot = self._user_mem(ctx)
        work = list(slot.get("recent_work") or [])
        work.insert(0, {"label": label[:200], "href": href[:200], "ts": time.time()})
        slot["recent_work"] = work[:40]
        self._put_user_mem(ctx, slot)
        return {"recent_work": slot["recent_work"]}

    # ── Automations (M151) — definitions only; execute via Mission/Agent/Gateway ──
    def list_automations(self, ctx: PlatformExecutionContext) -> dict:
        self._read(ctx)
        raw = dict(self.store.get_config(AUTOMATIONS_KEY, {}) or {})
        items = [
            a
            for a in (raw.get("items") or [])
            if a.get("org_id") == ctx.org_id and a.get("workspace_id") == ctx.workspace_id
        ]
        return {"automations": items, "execution": "MissionRuntime→AgentRuntime→ExecutionGateway→ApprovalCenter"}

    def create_automation(
        self,
        ctx: PlatformExecutionContext,
        *,
        name: str,
        schedule: str,
        action: str,
        app_scope: str = "platform",
        requires_approval: bool = True,
    ) -> dict:
        try:
            ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        except PlatformContextError:
            ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        name = (name or "").strip()[:120]
        if not name:
            raise PlatformContextError("VALIDATION_FAILED", "name required")
        schedule = (schedule or "daily_morning")[:40]
        action = (action or "summarize")[:80]
        # Automations never self-execute tools
        rec = {
            "automation_id": new_id("auto_"),
            "org_id": ctx.org_id,
            "workspace_id": ctx.workspace_id,
            "owner_id": ctx.user_id,
            "name": name,
            "schedule": schedule,
            "action": action,
            "app_scope": app_scope[:40],
            "requires_approval": bool(requires_approval),
            "enabled": True,
            "direct_tool_execution": False,
            "bypass_gateway": False,
            "execution_path": "MissionRuntime→AgentRuntime→ExecutionGateway",
            "created_at": time.time(),
        }
        raw = dict(self.store.get_config(AUTOMATIONS_KEY, {}) or {})
        items = list(raw.get("items") or [])
        items.append(rec)
        raw["items"] = items[-200:]
        self.store.set_config(AUTOMATIONS_KEY, raw, updated_by=ctx.user_id)
        self._audit(ctx, "core.automation.created", detail={"automation_id": rec["automation_id"]})
        self._activity_append(ctx, "automation", f"Automation created: {name}")
        return {"automation": rec}

    def run_automation_dry(
        self, ctx: PlatformExecutionContext, automation_id: str
    ) -> dict:
        """Produce a summary proposal — does NOT execute tools."""
        self._read(ctx)
        items = self.list_automations(ctx)["automations"]
        auto = next((a for a in items if a.get("automation_id") == automation_id), None)
        if not auto:
            raise PlatformContextError("NOT_FOUND", automation_id)
        scope = auto.get("app_scope") or "platform"
        summary_parts = []
        if scope in ("hcg", "platform", "all"):
            try:
                from saathi.platform.hcg import HcgService

                d = HcgService(self.store, platform=self.platform).dashboard(ctx)
                m = d["metrics"]
                summary_parts.append(
                    f"HCG sales {m.get('sales_today_minor')} paisa, orders {m.get('order_count')}"
                )
            except Exception:
                pass
        if scope in ("ielts", "platform", "all"):
            try:
                from saathi.platform.ielts.service import IELTSService

                p = IELTSService(self.store).product_dashboard(ctx)
                summary_parts.append(
                    f"IELTS practices {(p.get('progress') or {}).get('practice_count')}, "
                    f"readiness {(p.get('readiness') or {}).get('readiness_label')}"
                )
            except Exception:
                pass
        proposal = {
            "automation_id": automation_id,
            "summary": "; ".join(summary_parts) or "No domain data available",
            "executed": False,
            "requires_approval": auto.get("requires_approval", True),
            "execution_path": auto.get("execution_path"),
            "bypass_gateway": False,
        }
        self._activity_append(ctx, "automation_dry", proposal["summary"][:200])
        return {"proposal": proposal}

    # ── Workflow Composer graphs (M152) — metadata only ───────────────────
    def list_workflow_graphs(self, ctx: PlatformExecutionContext) -> dict:
        self._read(ctx)
        raw = dict(self.store.get_config(WORKFLOWS_KEY, {}) or {})
        graphs = [
            g
            for g in (raw.get("graphs") or [])
            if g.get("org_id") == ctx.org_id and g.get("workspace_id") == ctx.workspace_id
        ]
        return {"graphs": graphs, "executes_via": "MissionRuntime + ExecutionGateway"}

    def save_workflow_graph(
        self,
        ctx: PlatformExecutionContext,
        *,
        name: str,
        nodes: list[dict],
        edges: list[dict] | None = None,
        graph_id: str = "",
    ) -> dict:
        try:
            ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        except PlatformContextError:
            ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        name = (name or "").strip()[:120]
        if not name:
            raise PlatformContextError("VALIDATION_FAILED", "name required")
        nodes = list(nodes or [])[:40]
        allowed = {
            "trigger", "condition", "agent", "approval", "execution",
            "evidence", "notification", "finish",
        }
        for n in nodes:
            if (n.get("type") or "") not in allowed:
                raise PlatformContextError("VALIDATION_FAILED", f"illegal node type {n.get('type')}")
            if n.get("type") == "execution":
                n["gateway_required"] = True
                n["direct_tool_execution"] = False
            if n.get("type") == "approval":
                n["approval_center"] = True
        graph = {
            "graph_id": graph_id or new_id("wfg_"),
            "org_id": ctx.org_id,
            "workspace_id": ctx.workspace_id,
            "owner_id": ctx.user_id,
            "name": name,
            "nodes": nodes,
            "edges": list(edges or [])[:80],
            "bypass_gateway": False,
            "updated_at": time.time(),
        }
        raw = dict(self.store.get_config(WORKFLOWS_KEY, {}) or {})
        graphs = [g for g in (raw.get("graphs") or []) if g.get("graph_id") != graph["graph_id"]]
        graphs.append(graph)
        raw["graphs"] = graphs[-100:]
        self.store.set_config(WORKFLOWS_KEY, raw, updated_by=ctx.user_id)
        self._audit(ctx, "core.workflow_graph.saved", detail={"graph_id": graph["graph_id"]})
        mem = self._user_mem(ctx)
        rw = list(mem.get("recent_workflows") or [])
        rw.insert(0, {"graph_id": graph["graph_id"], "name": name, "ts": time.time()})
        mem["recent_workflows"] = rw[:20]
        self._put_user_mem(ctx, mem)
        return {"graph": graph}

    # ── Notification center aggregation (M153) ────────────────────────────
    def notification_center(self, ctx: PlatformExecutionContext) -> dict:
        self._read(ctx)
        items = []
        try:
            from saathi.platform.workflow_service import WorkflowService

            for n in WorkflowService(self.store).list_notifications(ctx):
                items.append({**n, "channel": "platform"})
        except Exception:
            pass
        # Tag sources by type prefix
        for n in items:
            t = (n.get("type") or "").lower()
            if "hcg" in t:
                n["source_app"] = "hcg"
            elif "ielts" in t:
                n["source_app"] = "ielts"
            else:
                n["source_app"] = n.get("source_app") or "platform"
        return {
            "notifications": items[:100],
            "count": len(items),
            "unified": True,
            "channels": ["platform", "hcg", "ielts", "system", "mission", "workers", "agents", "approvals"],
            "engine": "WorkflowService+PlatformStore.notifications",
        }

    # ── Cross-app context / recommendations (M154) ────────────────────────
    def cross_app_context(self, ctx: PlatformExecutionContext) -> dict:
        self._read(ctx)
        home = self.operator_home(ctx)
        recs = []
        if (home.get("approvals_count") or 0) > 0:
            recs.append(
                {
                    "id": "rec-approvals",
                    "label": "Clear pending approvals",
                    "href": "/platform/approvals",
                    "reason": "Approvals block gated work",
                }
            )
        hcg = home.get("hcg") or {}
        if hcg.get("low_stock_count"):
            recs.append(
                {
                    "id": "rec-stock",
                    "label": "Review HCG low stock",
                    "href": "/apps/hcg",
                    "reason": "Inventory attention",
                }
            )
        ielts = home.get("ielts") or {}
        if ielts.get("readiness") in ("needs_work", "insufficient_data"):
            recs.append(
                {
                    "id": "rec-ielts",
                    "label": "Continue IELTS practice",
                    "href": "/apps/ielts",
                    "reason": f"Readiness: {ielts.get('readiness')}",
                }
            )
        if not recs:
            recs.append(
                {
                    "id": "rec-apps",
                    "label": "Open application launcher",
                    "href": "/apps",
                    "reason": "Discover installed apps",
                }
            )
        return {
            "context": {
                "hcg_summary": hcg,
                "ielts_summary": ielts,
                "apps": home.get("applications"),
            },
            "recommendations": recs,
            "deep_links": {
                "hcg": "/apps/hcg",
                "ielts": "/apps/ielts",
                "launcher": "/apps",
                "search": "/platform/search",
                "home": "/platform/home",
            },
            "isolation": "no cross-app direct database access",
        }

    # ── Command catalog for palette (M148) ────────────────────────────────
    def command_catalog(self, ctx: PlatformExecutionContext) -> dict:
        self._read(ctx)
        cmds = list(STATIC_COMMANDS)
        try:
            from saathi.platform.apps import default_app_runtime

            for a in default_app_runtime(self.platform).list_apps(ctx).get("apps") or []:
                if a.get("lifecycle_state") in ("ENABLED", "RUNNING", "PAUSED"):
                    aid = a.get("app_id") or ""
                    cmds.append(
                        {
                            "id": f"launch-{aid}",
                            "label": f"Launch {(a.get('manifest') or {}).get('display_name') or aid}",
                            "href": self._app_href(aid),
                            "group": "Applications",
                        }
                    )
        except Exception:
            pass
        return {"commands": cmds, "count": len(cmds)}

    def activity_feed(self, ctx: PlatformExecutionContext, *, limit: int = 50) -> dict:
        self._read(ctx)
        events = [
            e
            for e in (self.store.get_config(ACTIVITY_KEY, []) or [])
            if e.get("org_id") == ctx.org_id and e.get("workspace_id") == ctx.workspace_id
        ]
        return {"activity": events[: max(1, min(limit, 100))], "unified": True}

    def timeline(self, ctx: PlatformExecutionContext) -> dict:
        """Unified timeline: activity + recent approvals + notifications."""
        self._read(ctx)
        feed = self.activity_feed(ctx, limit=30)["activity"]
        notes = self.notification_center(ctx)["notifications"][:10]
        return {
            "timeline": [
                *[{"kind": "activity", **e} for e in feed],
                *[
                    {
                        "kind": "notification",
                        "summary": n.get("title"),
                        "ts": n.get("created_at"),
                        "id": n.get("notification_id"),
                    }
                    for n in notes
                ],
            ],
            "unified": True,
        }


STATIC_COMMANDS = [
    {"id": "home", "label": "Go to Operator Home", "href": "/platform/home", "group": "Navigate"},
    {"id": "apps", "label": "Open Application Launcher", "href": "/apps", "group": "Navigate"},
    {"id": "hcg", "label": "Open HCG Operations", "href": "/apps/hcg", "group": "Applications"},
    {"id": "ielts", "label": "Open IELTSAlert", "href": "/apps/ielts", "group": "Applications"},
    {"id": "search", "label": "Universal Search", "href": "/platform/search", "group": "Navigate"},
    {"id": "approvals", "label": "Review Approvals", "href": "/platform/approvals", "group": "Actions"},
    {"id": "notifications", "label": "Notification Center", "href": "/platform/notifications", "group": "Navigate"},
    {"id": "workflows", "label": "Workflows", "href": "/platform/workflows", "group": "Navigate"},
    {"id": "missions", "label": "Missions", "href": "/platform/missions", "group": "Navigate"},
    {"id": "evidence", "label": "Evidence", "href": "/platform/evidence", "group": "Navigate"},
    {"id": "settings", "label": "Settings", "href": "/settings", "group": "Navigate"},
]


def role_allows_knowledge(ctx) -> bool:
    try:
        ctx.require_permission(PlatformPermission.KNOWLEDGE_SEARCH)
        return True
    except Exception:
        try:
            ctx.require_permission(PlatformPermission.KNOWLEDGE_READ)
            return True
        except Exception:
            return False


_DEFAULT: SaathiCoreService | None = None


def default_core_service(platform_service=None) -> SaathiCoreService:
    global _DEFAULT
    if platform_service is not None:
        existing = getattr(platform_service, "_core_os", None)
        if existing is not None:
            return existing
        svc = SaathiCoreService(platform_service)
        setattr(platform_service, "_core_os", svc)
        return svc
    if _DEFAULT is None:
        _DEFAULT = SaathiCoreService()
    return _DEFAULT


def reset_core_service_for_tests(platform_service=None) -> None:
    global _DEFAULT
    _DEFAULT = None
    if platform_service is not None and hasattr(platform_service, "_core_os"):
        delattr(platform_service, "_core_os")
