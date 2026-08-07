"""M208 — Multi-Campaign Manager over durable pg_campaigns.

Compose-only. Does not redesign durable campaigns.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from saathi.platform.tg.paper_activation.durable.events import make_event, fingerprint
from saathi.platform.tg.paper_activation.durable.service import DurableGovError
from saathi.platform.tg.paper_activation.ops.models import CampaignStatusExt


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, sort_keys=True, default=str)


def _loads(s: str | None, default: Any = None) -> Any:
    import json
    if not s:
        return default if default is not None else {}
    return json.loads(s)


class MultiCampaignManager:
    """Extended campaign operations: groups, templates, clone, archive, schedule."""

    def __init__(self, gov: Any):
        self.gov = gov
        self.store = gov.store

    def ensure_schema(self) -> None:
        from saathi.platform.tg.paper_activation.ops.schema import OPS_SCHEMA_SQL, SCHEMA_VERSION, ENGINE_VERSION
        with self.store._lock:
            self.store._conn.executescript(OPS_SCHEMA_SQL)
            now = time.time()
            self.store._conn.execute(
                "INSERT INTO pg_ops_meta(key, value, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                ("schema_version", SCHEMA_VERSION, now),
            )
            self.store._conn.execute(
                "INSERT INTO pg_ops_meta(key, value, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                ("engine_version", ENGINE_VERSION, now),
            )
            self.store._conn.commit()

    # ── groups / templates ───────────────────────────────────────────────────
    def create_group(
        self, *, name: str, description: str = "", tags: list | None = None,
        owner: str = "", org_id: str = "local", workspace_id: str = "local",
    ) -> dict[str, Any]:
        gid = _id("cgrp")
        now = time.time()
        tags = tags or []

        def _do(store):
            store.execute(
                """INSERT INTO pg_campaign_groups(id, org_id, workspace_id, name, description, tags_json, owner, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (gid, org_id, workspace_id, name, description, _dumps(tags), owner, now, now),
            )
            return {"id": gid, "name": name, "tags": tags, "owner": owner, "paper_only": True}

        return self.store.with_tx(_do)

    def list_groups(self, *, org_id: str = "") -> list[dict[str, Any]]:
        with self.store._lock:
            sql = "SELECT * FROM pg_campaign_groups WHERE 1=1"
            params: list[Any] = []
            if org_id:
                sql += " AND org_id=?"
                params.append(org_id)
            rows = self.store.execute(sql, params).fetchall()
            return [
                {
                    "id": r["id"], "name": r["name"], "description": r["description"],
                    "tags": _loads(r["tags_json"], []), "owner": r["owner"],
                    "org_id": r["org_id"], "paper_only": True,
                }
                for r in rows
            ]

    def create_template(
        self, *, name: str, strategy_slug: str = "", body: dict | None = None, org_id: str = "local",
    ) -> dict[str, Any]:
        tid = _id("ctpl")
        now = time.time()
        body = body or {}

        def _do(store):
            store.execute(
                """INSERT INTO pg_campaign_templates(id, org_id, name, strategy_slug, body_json, version, created_at, updated_at)
                VALUES (?,?,?,?,?,1,?,?)""",
                (tid, org_id, name, strategy_slug, _dumps(body), now, now),
            )
            return {"id": tid, "name": name, "strategy_slug": strategy_slug, "body": body, "paper_only": True}

        return self.store.with_tx(_do)

    def list_templates(self, *, org_id: str = "") -> list[dict[str, Any]]:
        with self.store._lock:
            sql = "SELECT * FROM pg_campaign_templates WHERE 1=1"
            params: list[Any] = []
            if org_id:
                sql += " AND org_id=?"
                params.append(org_id)
            return [
                {
                    "id": r["id"], "name": r["name"], "strategy_slug": r["strategy_slug"],
                    "body": _loads(r["body_json"], {}), "version": r["version"], "paper_only": True,
                }
                for r in self.store.execute(sql, params).fetchall()
            ]

    def _save_ext(self, campaign_id: str, ext: dict[str, Any]) -> dict[str, Any]:
        now = time.time()

        def _do(store):
            store.execute(
                """INSERT INTO pg_campaign_ext(
                    campaign_id, group_id, template_id, owner, tags_json, metadata_json,
                    objectives_text, notes, schedule_json, depends_on_json, cloned_from,
                    archived_at, version_history_json, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(campaign_id) DO UPDATE SET
                    group_id=excluded.group_id, template_id=excluded.template_id,
                    owner=excluded.owner, tags_json=excluded.tags_json,
                    metadata_json=excluded.metadata_json, objectives_text=excluded.objectives_text,
                    notes=excluded.notes, schedule_json=excluded.schedule_json,
                    depends_on_json=excluded.depends_on_json, cloned_from=excluded.cloned_from,
                    archived_at=excluded.archived_at, version_history_json=excluded.version_history_json,
                    updated_at=excluded.updated_at
                """,
                (
                    campaign_id,
                    ext.get("group_id", ""),
                    ext.get("template_id", ""),
                    ext.get("owner", ""),
                    _dumps(ext.get("tags", [])),
                    _dumps(ext.get("metadata", {})),
                    ext.get("objectives_text", ""),
                    ext.get("notes", ""),
                    _dumps(ext.get("schedule", {})),
                    _dumps(ext.get("depends_on", [])),
                    ext.get("cloned_from", ""),
                    ext.get("archived_at"),
                    _dumps(ext.get("version_history", [])),
                    now,
                ),
            )
            return ext

        return self.store.with_tx(_do)

    def get_ext(self, campaign_id: str) -> dict[str, Any]:
        with self.store._lock:
            r = self.store.execute(
                "SELECT * FROM pg_campaign_ext WHERE campaign_id=?", (campaign_id,)
            ).fetchone()
            if not r:
                return {}
            return {
                "group_id": r["group_id"], "template_id": r["template_id"], "owner": r["owner"],
                "tags": _loads(r["tags_json"], []), "metadata": _loads(r["metadata_json"], {}),
                "objectives_text": r["objectives_text"], "notes": r["notes"],
                "schedule": _loads(r["schedule_json"], {}),
                "depends_on": _loads(r["depends_on_json"], []),
                "cloned_from": r["cloned_from"], "archived_at": r["archived_at"],
                "version_history": _loads(r["version_history_json"], []),
            }

    def create_campaign(
        self,
        *,
        strategy_slug: str,
        initial_cash: str = "100000",
        operator_notes: str = "",
        org_id: str = "local",
        workspace_id: str = "local",
        group_id: str = "",
        template_id: str = "",
        owner: str = "",
        tags: list | None = None,
        metadata: dict | None = None,
        objectives: dict | None = None,
        objectives_text: str = "",
        schedule: dict | None = None,
        depends_on: list | None = None,
        min_trade_count: int = 0,
        min_duration_sec: float = 0,
        planned_end_date: float | None = None,
    ) -> dict[str, Any]:
        if template_id:
            with self.store._lock:
                t = self.store.execute(
                    "SELECT * FROM pg_campaign_templates WHERE id=?", (template_id,)
                ).fetchone()
            if t:
                body = _loads(t["body_json"], {})
                strategy_slug = strategy_slug or t["strategy_slug"] or body.get("strategy_slug", strategy_slug)
                initial_cash = body.get("initial_cash", initial_cash)
                min_trade_count = int(body.get("min_trade_count", min_trade_count))
                min_duration_sec = float(body.get("min_duration_sec", min_duration_sec))
                tags = tags or body.get("tags")
                objectives = objectives or body.get("objectives")
                schedule = schedule or body.get("schedule")

        out = self.gov.campaign_create(
            strategy_slug=strategy_slug,
            initial_cash=initial_cash,
            operator_notes=operator_notes,
            org_id=org_id,
            workspace_id=workspace_id,
            planned_end_date=planned_end_date,
            min_trade_count=min_trade_count,
        )
        c = out["campaign"]
        # patch min_duration if provided
        if min_duration_sec:
            c["min_duration_sec"] = min_duration_sec
            if objectives:
                c["objectives"] = objectives
            self.store.save_campaign(c)
            c = self.store.get_campaign(c["id"])

        if schedule and schedule.get("start_at") and schedule["start_at"] > time.time():
            c["status"] = CampaignStatusExt.SCHEDULED.value
            self.store.save_campaign(c)
            c = self.store.get_campaign(c["id"])

        hist = [{
            "event": "created", "ts": time.time(), "version": 1,
            "snapshot": {"status": c["status"], "strategy_slug": strategy_slug},
        }]
        self._save_ext(c["id"], {
            "group_id": group_id, "template_id": template_id, "owner": owner,
            "tags": tags or [], "metadata": metadata or {},
            "objectives_text": objectives_text,
            "notes": operator_notes, "schedule": schedule or {},
            "depends_on": depends_on or [], "version_history": hist,
        })
        full = self.get_campaign_full(c["id"])
        return {"campaign": full, "paper_only": True, "live_authorized": False}

    def get_campaign_full(self, campaign_id: str) -> dict[str, Any]:
        c = self.store.get_campaign(campaign_id)
        if not c:
            raise DurableGovError("NOT_FOUND", "campaign not found")
        ext = self.get_ext(campaign_id)
        return {**c, **ext, "paper_only": True, "live_authorized": False}

    def list_campaigns_full(
        self, *, org_id: str = "", status: str = "", group_id: str = "", tag: str = "",
    ) -> list[dict[str, Any]]:
        camps = self.store.list_campaigns(org_id=org_id, status=status)
        out = []
        for c in camps:
            full = {**c, **self.get_ext(c["id"]), "paper_only": True}
            if group_id and full.get("group_id") != group_id:
                continue
            if tag and tag not in (full.get("tags") or []):
                continue
            out.append(full)
        return out

    def clone_campaign(self, campaign_id: str, *, owner: str = "", operator_notes: str = "") -> dict[str, Any]:
        src = self.get_campaign_full(campaign_id)
        out = self.create_campaign(
            strategy_slug=src["strategy_slug"],
            initial_cash=src.get("initial_cash", "100000"),
            operator_notes=operator_notes or f"clone of {campaign_id}",
            org_id=src.get("org_id", "local"),
            workspace_id=src.get("workspace_id", "local"),
            group_id=src.get("group_id", ""),
            template_id=src.get("template_id", ""),
            owner=owner or src.get("owner", ""),
            tags=list(src.get("tags") or []),
            metadata={**(src.get("metadata") or {}), "cloned_from": campaign_id},
            objectives=src.get("objectives") or {},
            objectives_text=src.get("objectives_text", ""),
            schedule={},
            depends_on=[],
            min_trade_count=int(src.get("min_trade_count") or 0),
            min_duration_sec=float(src.get("min_duration_sec") or 0),
        )
        new_id = out["campaign"]["id"]
        ext = self.get_ext(new_id)
        ext["cloned_from"] = campaign_id
        self._save_ext(new_id, ext)
        out["campaign"] = self.get_campaign_full(new_id)
        out["cloned_from"] = campaign_id
        return out

    def compare_campaigns(self, campaign_ids: list[str]) -> dict[str, Any]:
        rows = {}
        for cid in campaign_ids:
            try:
                c = self.get_campaign_full(cid)
            except DurableGovError:
                continue
            analytics = {}
            if c.get("portfolio_id"):
                try:
                    analytics = self.gov.analytics(c["portfolio_id"]).get("analytics", {})
                except Exception:
                    analytics = {}
            rows[cid] = {
                "id": cid,
                "strategy_slug": c.get("strategy_slug"),
                "status": c.get("status"),
                "group_id": c.get("group_id", ""),
                "tags": c.get("tags", []),
                "owner": c.get("owner", ""),
                "total_return": analytics.get("total_return"),
                "sharpe": analytics.get("sharpe"),
                "max_drawdown_pct": analytics.get("max_drawdown_pct"),
                "trade_count": analytics.get("trade_count"),
                "win_rate": analytics.get("win_rate"),
            }
        ranking = sorted(
            rows.keys(),
            key=lambda i: (
                -(rows[i].get("sharpe") or 0),
                -(rows[i].get("total_return") or 0),
            ),
        )
        return {
            "campaigns": rows,
            "ranking": ranking,
            "paper_only": True,
            "live_authorized": False,
            "note": "Comparison is operational, not a profitability claim.",
        }

    def resume(self, campaign_id: str, *, operator_identity: str) -> dict[str, Any]:
        c = self.store.get_campaign(campaign_id)
        if not c:
            raise DurableGovError("NOT_FOUND", "campaign not found")
        if c["status"] not in ("PAUSED", "SCHEDULED"):
            raise DurableGovError("INVALID_STATE", f"cannot resume from {c['status']}")
        # dependency check
        ext = self.get_ext(campaign_id)
        for dep in ext.get("depends_on") or []:
            d = self.store.get_campaign(dep)
            if not d or d.get("status") not in ("COMPLETED", "ACTIVE"):
                raise DurableGovError("DEPENDENCY_BLOCKED", f"depends on {dep}")
        return self.gov.campaign_start(campaign_id, operator_identity=operator_identity)

    def archive(self, campaign_id: str, *, operator_identity: str, reason: str = "archive") -> dict[str, Any]:
        c = self.store.get_campaign(campaign_id)
        if not c:
            raise DurableGovError("NOT_FOUND", "campaign not found")
        if c["status"] not in ("COMPLETED", "PAUSED", "DRAFT"):
            raise DurableGovError("INVALID_STATE", f"cannot archive from {c['status']}")
        c["status"] = CampaignStatusExt.ARCHIVED.value
        self.store.save_campaign(c)
        ext = self.get_ext(campaign_id)
        hist = list(ext.get("version_history") or [])
        hist.append({"event": "archived", "ts": time.time(), "reason": reason, "by": operator_identity})
        ext["version_history"] = hist
        ext["archived_at"] = time.time()
        ext["notes"] = (ext.get("notes") or "") + f"\narchived: {reason}"
        self._save_ext(campaign_id, ext)
        self.store.append_event(make_event(
            "campaign.paused",  # reuse closest; payload marks archive
            aggregate_type="campaign", aggregate_id=campaign_id,
            payload={"action": "archived", "reason": reason},
            actor_type="operator", actor_id=operator_identity,
            idempotency_key=f"archive:{campaign_id}:{int(time.time())}",
        ))
        return {"campaign": self.get_campaign_full(campaign_id), "paper_only": True}

    def schedule_campaign(
        self, campaign_id: str, *, start_at: float, operator_identity: str = "operator",
    ) -> dict[str, Any]:
        c = self.store.get_campaign(campaign_id)
        if not c:
            raise DurableGovError("NOT_FOUND", "campaign not found")
        if c["status"] not in ("DRAFT", "APPROVED", "PAUSED", "SCHEDULED"):
            raise DurableGovError("INVALID_STATE", f"cannot schedule from {c['status']}")
        c["status"] = CampaignStatusExt.SCHEDULED.value
        self.store.save_campaign(c)
        ext = self.get_ext(campaign_id)
        ext["schedule"] = {**(ext.get("schedule") or {}), "start_at": start_at, "scheduled_by": operator_identity}
        hist = list(ext.get("version_history") or [])
        hist.append({"event": "scheduled", "ts": time.time(), "start_at": start_at})
        ext["version_history"] = hist
        self._save_ext(campaign_id, ext)
        return {"campaign": self.get_campaign_full(campaign_id), "paper_only": True}

    def update_notes_metadata(
        self,
        campaign_id: str,
        *,
        notes: str | None = None,
        tags: list | None = None,
        owner: str | None = None,
        metadata: dict | None = None,
        objectives_text: str | None = None,
        group_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.store.get_campaign(campaign_id):
            raise DurableGovError("NOT_FOUND", "campaign not found")
        ext = self.get_ext(campaign_id)
        if notes is not None:
            ext["notes"] = notes
        if tags is not None:
            ext["tags"] = tags
        if owner is not None:
            ext["owner"] = owner
        if metadata is not None:
            ext["metadata"] = {**(ext.get("metadata") or {}), **metadata}
        if objectives_text is not None:
            ext["objectives_text"] = objectives_text
        if group_id is not None:
            ext["group_id"] = group_id
        hist = list(ext.get("version_history") or [])
        hist.append({"event": "metadata_updated", "ts": time.time()})
        ext["version_history"] = hist
        self._save_ext(campaign_id, ext)
        return {"campaign": self.get_campaign_full(campaign_id), "paper_only": True}

    def set_dependencies(self, campaign_id: str, depends_on: list[str]) -> dict[str, Any]:
        if not self.store.get_campaign(campaign_id):
            raise DurableGovError("NOT_FOUND", "campaign not found")
        if campaign_id in depends_on:
            raise DurableGovError("INVALID_DEPENDENCY", "campaign cannot depend on itself")
        ext = self.get_ext(campaign_id)
        ext["depends_on"] = list(depends_on)
        self._save_ext(campaign_id, ext)
        return {"campaign": self.get_campaign_full(campaign_id), "paper_only": True}
