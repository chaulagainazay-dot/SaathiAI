"""M211 — Operational Intelligence (recommendations only).

Never modifies portfolios, journals, evidence, or risk controls.
"""
from __future__ import annotations

import time
import uuid
from typing import Any


def _id(prefix: str = "rec") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class OperationalIntelligence:
    def __init__(self, gov: Any, monitor: Any | None = None):
        self.gov = gov
        self.store = gov.store
        self.monitor = monitor

    def scan(self, *, persist: bool = True) -> dict[str, Any]:
        recs: list[dict[str, Any]] = []
        health = self.monitor.assess(persist=False) if self.monitor else {}
        components = health.get("components") or {}

        # storage anomalies
        storage = components.get("storage_health") or {}
        if storage.get("classification") in ("CRITICAL", "DEGRADED"):
            recs.append(self._rec(
                "storage_anomaly", "critical",
                "Storage health degraded — run backup and free disk",
                detail=storage,
            ))

        # worker instability
        workers = components.get("worker_health") or {}
        if workers.get("poison", 0) > 0:
            recs.append(self._rec(
                "worker_instability", "warning",
                "Poison queue entries detected — inspect order queue",
                detail=workers,
            ))

        # risk deterioration
        risk = components.get("risk_health") or {}
        if risk.get("kill_switch"):
            recs.append(self._rec(
                "risk_deterioration", "critical",
                "Kill switch engaged — review halted paper portfolios",
                detail=risk,
            ))
        elif risk.get("risk_halts", 0) > 0:
            recs.append(self._rec(
                "risk_deterioration", "warning",
                "Risk limit halt(s) present on paper portfolios",
                detail=risk,
            ))

        # strategy / campaign issues
        for c in self.store.list_campaigns(status="ACTIVE"):
            if not c.get("portfolio_id"):
                recs.append(self._rec(
                    "inactive_portfolio", "warning",
                    f"Active campaign {c['id']} missing portfolio link",
                    campaign_id=c["id"], strategy_slug=c.get("strategy_slug", ""),
                ))
            else:
                p = self.store.get_portfolio(c["portfolio_id"])
                if p and p.get("status") == "HALTED":
                    recs.append(self._rec(
                        "performance_deterioration", "warning",
                        f"Portfolio {p['id']} halted under campaign {c['id']}",
                        campaign_id=c["id"], portfolio_id=p["id"],
                        detail={"halt_reason": p.get("halt_reason")},
                    ))
                # stale marks
                if p and not (p.get("marks") or {}):
                    recs.append(self._rec(
                        "stale_datasets", "info",
                        f"Portfolio {p['id']} has no market marks",
                        portfolio_id=p["id"], campaign_id=c["id"],
                    ))
                positions = self.store.list_positions(c["portfolio_id"]) if p else []
                open_pos = [x for x in positions if float(x.get("quantity") or 0) != 0]
                if open_pos and p and not (p.get("marks") or {}):
                    recs.append(self._rec(
                        "stale_positions", "warning",
                        f"Open positions without marks on {p['id']}",
                        portfolio_id=p["id"], campaign_id=c["id"],
                        detail={"symbols": [x["symbol"] for x in open_pos]},
                    ))

            # planned end overdue
            if c.get("planned_end_date") and c["planned_end_date"] < time.time():
                recs.append(self._rec(
                    "strategy_drift", "info",
                    f"Campaign {c['id']} past planned end — complete or extend",
                    campaign_id=c["id"], strategy_slug=c.get("strategy_slug", ""),
                ))

        # excessive interventions
        for c in self.store.list_campaigns():
            try:
                ev = self.store.list_events(aggregate_id=c["id"], limit=200)
                pauses = sum(1 for e in ev if e.event_type == "campaign.paused")
            except Exception:
                pauses = 0
            if pauses >= 5:
                recs.append(self._rec(
                    "excessive_interventions", "warning",
                    f"Campaign {c['id']} has {pauses} pause events",
                    campaign_id=c["id"], detail={"pauses": pauses},
                ))

        # duplicate behaviour: same strategy many active campaigns
        active = self.store.list_campaigns(status="ACTIVE")
        by_strat: dict[str, list] = {}
        for c in active:
            by_strat.setdefault(c.get("strategy_slug", ""), []).append(c["id"])
        for slug, ids in by_strat.items():
            if len(ids) >= 3:
                recs.append(self._rec(
                    "duplicate_behaviour", "info",
                    f"Strategy {slug} has {len(ids)} concurrent active paper campaigns",
                    strategy_slug=slug, detail={"campaign_ids": ids},
                ))

        # market regime / unexpected vol proxies from equity points if any
        with self.store._lock:
            try:
                n_eq = self.store.execute("SELECT COUNT(*) AS c FROM pg_equity_points").fetchone()["c"]
            except Exception:
                n_eq = 0
        if n_eq == 0 and active:
            recs.append(self._rec(
                "unexpected_volatility", "info",
                "No equity time-series yet — record equity points for rolling analytics",
                detail={"equity_points": n_eq},
            ))

        for r in recs:
            r["auto_applied"] = False  # hard guarantee
            r["modifies_portfolio"] = False
            r["paper_only"] = True
            if persist:
                self._persist(r)

        return {
            "recommendations": recs,
            "count": len(recs),
            "auto_applied": False,
            "modifies_portfolios": False,
            "paper_only": True,
            "live_authorized": False,
            "llm_boundary": {
                "may_recommend": True,
                "may_modify_portfolios": False,
                "may_execute_trades": False,
            },
        }

    def _rec(
        self,
        kind: str,
        severity: str,
        title: str,
        *,
        detail: dict | None = None,
        campaign_id: str = "",
        portfolio_id: str = "",
        strategy_slug: str = "",
    ) -> dict[str, Any]:
        return {
            "id": _id(),
            "kind": kind,
            "severity": severity,
            "title": title,
            "detail": detail or {},
            "campaign_id": campaign_id,
            "portfolio_id": portfolio_id,
            "strategy_slug": strategy_slug,
            "actionable": True,
            "auto_applied": False,
            "created_at": time.time(),
        }

    def _persist(self, r: dict[str, Any]) -> None:
        import json

        def _do(store):
            store.execute(
                """INSERT INTO pg_ops_recommendations(
                    id, kind, severity, title, detail_json, campaign_id, portfolio_id,
                    strategy_slug, actionable, auto_applied, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    r["id"], r["kind"], r["severity"], r["title"],
                    json.dumps(r.get("detail") or {}, sort_keys=True, default=str),
                    r.get("campaign_id", ""), r.get("portfolio_id", ""),
                    r.get("strategy_slug", ""), 1, 0, r["created_at"],
                ),
            )

        try:
            self.store.with_tx(_do)
        except Exception:
            pass

    def list_recommendations(self, *, limit: int = 50) -> dict[str, Any]:
        import json
        with self.store._lock:
            try:
                rows = self.store.execute(
                    "SELECT * FROM pg_ops_recommendations ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            except Exception:
                rows = []
        return {
            "recommendations": [
                {
                    "id": r["id"], "kind": r["kind"], "severity": r["severity"],
                    "title": r["title"], "detail": json.loads(r["detail_json"] or "{}"),
                    "campaign_id": r["campaign_id"], "portfolio_id": r["portfolio_id"],
                    "strategy_slug": r["strategy_slug"],
                    "auto_applied": bool(r["auto_applied"]),
                    "created_at": r["created_at"], "paper_only": True,
                }
                for r in rows
            ],
            "paper_only": True,
            "modifies_portfolios": False,
        }
