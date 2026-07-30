"""M209 — Long-term operational monitoring for paper campaigns.

Produces health classifications. Never mutates portfolios.
"""
from __future__ import annotations

import os
import resource
import time
import uuid
from typing import Any

from saathi.platform.tg.paper_activation.ops.models import HealthClass


def _id(prefix: str = "hlth") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _rank(h: str) -> int:
    order = {
        HealthClass.HEALTHY.value: 0,
        HealthClass.WARNING.value: 1,
        HealthClass.DEGRADED.value: 2,
        HealthClass.CRITICAL.value: 3,
        HealthClass.FAILED_SAFE.value: 4,
    }
    return order.get(h, 0)


def _worst(*classes: str) -> str:
    return max(classes, key=_rank) if classes else HealthClass.HEALTHY.value


class OperationalMonitor:
    def __init__(self, gov: Any):
        self.gov = gov
        self.store = gov.store

    def _component_storage(self) -> dict[str, Any]:
        h = self.store.health()
        disk = h.get("disk") or self.store.disk_preflight()
        if h.get("status") != "HEALTHY":
            cls = HealthClass.CRITICAL.value
        elif not disk.get("ok", True):
            cls = HealthClass.CRITICAL.value
        elif disk.get("free_mb", 9999) < 512:
            cls = HealthClass.WARNING.value
        else:
            cls = HealthClass.HEALTHY.value
        return {"classification": cls, "detail": h, "disk": disk}

    def _component_portfolio(self) -> dict[str, Any]:
        ports = self.store.list_portfolios()
        halted = [p for p in ports if p.get("status") == "HALTED"]
        unrec = [p for p in ports if p.get("halt_reason") == "UNRECONCILED"]
        if unrec:
            cls = HealthClass.FAILED_SAFE.value
        elif len(halted) > len(ports) / 2 and ports:
            cls = HealthClass.DEGRADED.value
        elif halted:
            cls = HealthClass.WARNING.value
        else:
            cls = HealthClass.HEALTHY.value
        return {
            "classification": cls,
            "portfolio_count": len(ports),
            "halted": len(halted),
            "unreconciled": len(unrec),
        }

    def _component_risk(self) -> dict[str, Any]:
        if self.store.kill_switch_active():
            return {"classification": HealthClass.FAILED_SAFE.value, "kill_switch": True}
        ports = self.store.list_portfolios()
        risk_halts = [p for p in ports if p.get("halt_reason") in (
            "DAILY_LOSS", "WEEKLY_LOSS", "MAX_DRAWDOWN", "EXPOSURE_LIMIT", "CIRCUIT_BREAKER",
        )]
        if risk_halts:
            return {"classification": HealthClass.WARNING.value, "risk_halts": len(risk_halts)}
        return {"classification": HealthClass.HEALTHY.value, "risk_halts": 0, "kill_switch": False}

    def _component_campaign(self) -> dict[str, Any]:
        camps = self.store.list_campaigns()
        active = [c for c in camps if c.get("status") == "ACTIVE"]
        stale = []
        now = time.time()
        for c in active:
            start = c.get("start_date") or c.get("created_at") or now
            # flag campaigns without portfolio as degraded
            if not c.get("portfolio_id"):
                stale.append(c["id"])
            # planned end overdue
            if c.get("planned_end_date") and c["planned_end_date"] < now:
                stale.append(c["id"])
        if stale and active:
            cls = HealthClass.WARNING.value
        else:
            cls = HealthClass.HEALTHY.value
        return {
            "classification": cls,
            "total": len(camps),
            "active": len(active),
            "stale_or_overdue": list(set(stale)),
        }

    def _component_workers(self) -> dict[str, Any]:
        # queue leases: any poison or stuck
        with self.store._lock:
            try:
                poison = self.store.execute(
                    "SELECT COUNT(*) AS c FROM pg_order_queue WHERE poison=1"
                ).fetchone()["c"]
                pending = self.store.execute(
                    "SELECT COUNT(*) AS c FROM pg_order_queue WHERE status='PENDING'"
                ).fetchone()["c"]
            except Exception:
                poison, pending = 0, 0
        if poison:
            cls = HealthClass.DEGRADED.value
        elif pending > 100:
            cls = HealthClass.WARNING.value
        else:
            cls = HealthClass.HEALTHY.value
        return {
            "classification": cls,
            "worker_id": getattr(self.gov, "worker_id", None),
            "poison": poison,
            "pending_queue": pending,
        }

    def _component_reconciliation(self) -> dict[str, Any]:
        with self.store._lock:
            try:
                rows = self.store.execute(
                    "SELECT verdict FROM pg_reconciliation ORDER BY created_at DESC LIMIT 20"
                ).fetchall()
            except Exception:
                rows = []
        fails = [r for r in rows if "FAIL" in str(r["verdict"]).upper() or "UNREC" in str(r["verdict"]).upper()]
        if fails:
            return {"classification": HealthClass.DEGRADED.value, "recent_fails": len(fails), "samples": len(rows)}
        return {"classification": HealthClass.HEALTHY.value, "recent_fails": 0, "samples": len(rows)}

    def _component_scheduler(self) -> dict[str, Any]:
        jobs = self.store.list_jobs()
        errors = [j for j in jobs if j.get("last_status") == "ERROR"]
        enabled = [j for j in jobs if j.get("enabled")]
        if errors:
            cls = HealthClass.WARNING.value
        elif not enabled:
            cls = HealthClass.HEALTHY.value  # disabled by default is OK
        else:
            cls = HealthClass.HEALTHY.value
        return {
            "classification": cls,
            "jobs": len(jobs),
            "enabled": len(enabled),
            "errors": len(errors),
            "note": "scheduler disabled by default",
        }

    def _component_events(self) -> dict[str, Any]:
        h = self.store.health()
        n = h.get("event_count", 0)
        return {"classification": HealthClass.HEALTHY.value, "event_count": n}

    def _component_memory(self) -> dict[str, Any]:
        try:
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # macOS ru_maxrss is bytes; Linux is KB
            rss_mb = rss / (1024 * 1024) if rss > 10_000_000 else rss / 1024
        except Exception:
            rss_mb = 0.0
        if rss_mb > 1500:
            cls = HealthClass.WARNING.value
        else:
            cls = HealthClass.HEALTHY.value
        return {"classification": cls, "rss_mb_approx": round(rss_mb, 2)}

    def _component_strategy(self) -> dict[str, Any]:
        with self.store._lock:
            try:
                acts = self.store.execute("SELECT state, strategy_slug FROM pg_activations").fetchall()
            except Exception:
                acts = []
        active = [a for a in acts if a["state"] == "PAPER_ACTIVE"]
        halted = [a for a in acts if a["state"] in ("PAPER_HALTED", "PAPER_SUSPENDED")]
        if halted and not active:
            cls = HealthClass.WARNING.value
        else:
            cls = HealthClass.HEALTHY.value
        return {
            "classification": cls,
            "active": len(active),
            "halted": len(halted),
            "total": len(acts),
        }

    def _component_market_coverage(self) -> dict[str, Any]:
        # coverage proxy: distinct symbols in positions + orders
        with self.store._lock:
            try:
                n_sym = self.store.execute(
                    "SELECT COUNT(DISTINCT symbol) AS c FROM pg_positions WHERE CAST(quantity AS REAL) != 0"
                ).fetchone()["c"]
            except Exception:
                n_sym = 0
        return {"classification": HealthClass.HEALTHY.value, "open_symbols": n_sym}

    def _component_recovery(self) -> dict[str, Any]:
        # readiness: WAL + healthy schema
        h = self.store.health()
        if h.get("status") == "HEALTHY" and h.get("readiness") == "READY":
            cls = HealthClass.HEALTHY.value
        else:
            cls = HealthClass.DEGRADED.value
        return {"classification": cls, "readiness": h.get("readiness"), "can_backup": True}

    def _component_incidents(self) -> dict[str, Any]:
        incs = self.store.list_incidents(status="OPEN")
        crit = [i for i in incs if str(i.get("severity", "")).lower() in ("critical", "fatal")]
        if crit:
            cls = HealthClass.CRITICAL.value
        elif incs:
            cls = HealthClass.WARNING.value
        else:
            cls = HealthClass.HEALTHY.value
        return {"classification": cls, "open": len(incs), "critical": len(crit)}

    def assess(self, *, persist: bool = True) -> dict[str, Any]:
        components = {
            "portfolio_health": self._component_portfolio(),
            "risk_health": self._component_risk(),
            "campaign_health": self._component_campaign(),
            "system_health": {"classification": HealthClass.HEALTHY.value, "pid": os.getpid()},
            "storage_health": self._component_storage(),
            "worker_health": self._component_workers(),
            "reconciliation_health": self._component_reconciliation(),
            "strategy_health": self._component_strategy(),
            "market_coverage": self._component_market_coverage(),
            "event_processing": self._component_events(),
            "scheduler_health": self._component_scheduler(),
            "disk_usage": self._component_storage().get("disk", {}),
            "memory_usage": self._component_memory(),
            "recovery_readiness": self._component_recovery(),
            "incidents": self._component_incidents(),
        }
        classes = [
            c.get("classification", HealthClass.HEALTHY.value)
            for c in components.values()
            if isinstance(c, dict) and "classification" in c
        ]
        overall = _worst(*classes) if classes else HealthClass.HEALTHY.value
        snap = {
            "id": _id(),
            "scope": "system",
            "scope_ref": "",
            "classification": overall,
            "components": components,
            "created_at": time.time(),
            "paper_only": True,
            "live_authorized": False,
            "health_classes": [e.value for e in HealthClass],
        }
        if persist:
            self._persist(snap)
        return snap

    def _persist(self, snap: dict[str, Any]) -> None:
        import json

        def _do(store):
            store.execute(
                """INSERT INTO pg_ops_health(id, scope, scope_ref, classification, components_json, detail_json, created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (
                    snap["id"], snap["scope"], snap.get("scope_ref", ""),
                    snap["classification"],
                    json.dumps(snap["components"], sort_keys=True, default=str),
                    json.dumps({"paper_only": True}, sort_keys=True),
                    snap["created_at"],
                ),
            )

        try:
            self.store.with_tx(_do)
        except Exception:
            pass  # monitoring must not break ops if table not ready

    def campaign_health(self, campaign_id: str) -> dict[str, Any]:
        c = self.store.get_campaign(campaign_id)
        if not c:
            return {"classification": HealthClass.CRITICAL.value, "error": "not found", "paper_only": True}
        parts = [HealthClass.HEALTHY.value]
        detail: dict[str, Any] = {"campaign": c}
        if c.get("status") == "ACTIVE" and not c.get("portfolio_id"):
            parts.append(HealthClass.DEGRADED.value)
            detail["missing_portfolio"] = True
        if c.get("portfolio_id"):
            p = self.store.get_portfolio(c["portfolio_id"])
            if p and p.get("status") == "HALTED":
                parts.append(HealthClass.WARNING.value)
                detail["portfolio_halted"] = p.get("halt_reason")
            if p and p.get("halt_reason") == "UNRECONCILED":
                parts.append(HealthClass.FAILED_SAFE.value)
        cls = _worst(*parts)
        return {
            "campaign_id": campaign_id,
            "classification": cls,
            "detail": detail,
            "paper_only": True,
        }
