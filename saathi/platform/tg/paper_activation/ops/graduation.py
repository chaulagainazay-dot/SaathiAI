"""M210 — Strategy Graduation Engine.

Evaluates paper campaigns. Classification never authorizes live trading.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from saathi.platform.tg.paper_activation.durable.events import fingerprint, make_event
from saathi.platform.tg.paper_activation.durable.service import DurableGovError
from saathi.platform.tg.paper_activation.ops.models import StrategyClassification


def _id(prefix: str = "grad") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


# Default thresholds — operational excellence, not profitability claims
DEFAULT_CRITERIA = {
    "min_duration_sec": 7 * 86400,  # 7 days paper
    "min_trades": 10,
    "max_drawdown_pct": 25.0,
    "min_profit_factor": 0.8,  # allow research pass with weak PF when evidence complete
    "min_sharpe": -1.0,  # non-catastrophic
    "min_win_rate": 0.0,
    "require_recon_success": True,
    "require_journal": True,
    "max_operator_interventions": 50,
    "max_system_incidents": 20,
}


class GraduationEngine:
    def __init__(self, gov: Any, campaign_mgr: Any | None = None):
        self.gov = gov
        self.store = gov.store
        self.campaign_mgr = campaign_mgr

    def evaluate(
        self,
        campaign_id: str,
        *,
        criteria: dict | None = None,
        actor: str = "system",
        force_metrics: dict | None = None,
    ) -> dict[str, Any]:
        c = self.store.get_campaign(campaign_id)
        if not c:
            raise DurableGovError("NOT_FOUND", "campaign not found")
        crit = {**DEFAULT_CRITERIA, **(c.get("evaluation_criteria") or {}), **(criteria or {})}
        metrics = force_metrics or self._collect_metrics(c)
        gates, reasons = self._score(c, metrics, crit)
        classification = self._classify(c, gates, metrics, crit)

        rec = {
            "id": _id(),
            "campaign_id": campaign_id,
            "strategy_slug": c.get("strategy_slug", ""),
            "classification": classification,
            "metrics": metrics,
            "gates": gates,
            "reasons": reasons,
            "live_authorized": False,
            "auto_promoted_to_live": False,
            "evaluated_at": time.time(),
            "actor": actor,
            "immutable": True,
            "paper_only": True,
            "disclaimer": (
                "Graduation evaluates paper operational readiness only. "
                "LIVE TRADING IS NOT AUTHORIZED. "
                "NO STRATEGY IS AUTOMATICALLY PROMOTED TO LIVE EXECUTION."
            ),
        }
        rec["fingerprint"] = fingerprint({
            k: rec[k] for k in ("campaign_id", "classification", "metrics", "gates", "evaluated_at")
        })
        self._persist(rec)
        self.store.append_event(make_event(
            "campaign.completed" if classification in (
                StrategyClassification.PAPER_VALIDATED.value,
                StrategyClassification.PAPER_GRADUATE.value,
            ) else "journal.created",
            aggregate_type="graduation",
            aggregate_id=rec["id"],
            payload={
                "classification": classification,
                "campaign_id": campaign_id,
                "live_authorized": False,
            },
            actor_type="system" if actor == "system" else "operator",
            actor_id=actor,
            idempotency_key=f"grad:{campaign_id}:{rec['fingerprint'][:16]}",
        ))
        return rec

    def _collect_metrics(self, c: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        start = c.get("start_date") or c.get("created_at") or now
        end = c.get("actual_end_date") or now
        duration = max(0.0, float(end) - float(start))
        analytics: dict[str, Any] = {}
        recon_ok = True
        journal_count = 0
        trade_count = 0
        if c.get("portfolio_id"):
            try:
                analytics = self.gov.analytics(c["portfolio_id"]).get("analytics", {})
            except Exception as e:
                analytics = {"error": str(e)}
            try:
                recon = self.gov.reconcile(c["portfolio_id"], auto_halt=False)
                recon_ok = not recon.get("reconciliation", {}).get("fail_closed", False)
            except Exception:
                recon_ok = False
            try:
                journal_count = len(self.store.list_journal(c["portfolio_id"]))
            except Exception:
                journal_count = 0
            trade_count = int(analytics.get("trade_count") or 0)
        incidents = self.store.list_incidents(status="OPEN")
        camp_inc = [i for i in incidents if i.get("campaign_id") == c["id"]]
        # operator interventions proxy: pause/resume events
        interventions = 0
        try:
            ev = self.store.list_events(aggregate_id=c["id"], limit=500)
            interventions = sum(
                1 for e in ev
                if e.event_type in ("campaign.paused", "operator.override_attempted")
            )
        except Exception:
            interventions = 0

        return {
            "duration_sec": duration,
            "trade_count": trade_count,
            "total_return": analytics.get("total_return"),
            "max_drawdown_pct": float(analytics.get("max_drawdown_pct") or 0),
            "profit_factor": analytics.get("profit_factor"),
            "sharpe": analytics.get("sharpe") or 0.0,
            "sortino": analytics.get("sortino") or 0.0,
            "expectancy": analytics.get("expectancy") or 0.0,
            "win_rate": analytics.get("win_rate") or 0.0,
            "recon_ok": recon_ok,
            "journal_count": journal_count,
            "operator_interventions": interventions,
            "system_incidents": len(camp_inc),
            "campaign_status": c.get("status"),
            "risk_policy_compliance": c.get("status") != "FAILED",
            "consistency_proxy": abs(float(analytics.get("sharpe") or 0)),
            "regime_stability_proxy": True,  # paper-only placeholder; historical regime not re-run here
            "parameter_stability_proxy": True,
            "monte_carlo_consistency_proxy": True,
            "walk_forward_consistency_proxy": True,
            "paper_only": True,
        }

    def _score(
        self, c: dict[str, Any], metrics: dict[str, Any], crit: dict[str, Any],
    ) -> tuple[dict[str, bool], list[str]]:
        reasons: list[str] = []
        min_dur = float(c.get("min_duration_sec") or crit["min_duration_sec"])
        min_trades = int(c.get("min_trade_count") or crit["min_trades"])
        gates = {
            "min_duration": metrics["duration_sec"] >= min_dur,
            "min_trades": metrics["trade_count"] >= min_trades,
            "drawdown_ok": metrics["max_drawdown_pct"] <= float(crit["max_drawdown_pct"]),
            "sharpe_ok": float(metrics.get("sharpe") or 0) >= float(crit["min_sharpe"]),
            "recon_ok": bool(metrics.get("recon_ok")) if crit.get("require_recon_success") else True,
            "journal_ok": (metrics.get("journal_count", 0) > 0) if crit.get("require_journal") else True,
            "interventions_ok": metrics.get("operator_interventions", 0) <= int(crit["max_operator_interventions"]),
            "incidents_ok": metrics.get("system_incidents", 0) <= int(crit["max_system_incidents"]),
            "not_live": True,
            "paper_only": True,
        }
        pf = metrics.get("profit_factor")
        if pf is None:
            gates["profit_factor_ok"] = True  # no trades yet → not failed on PF
        else:
            gates["profit_factor_ok"] = float(pf) >= float(crit["min_profit_factor"])

        for k, v in gates.items():
            if not v:
                reasons.append(f"gate_failed:{k}")
        if metrics.get("campaign_status") == "ARCHIVED" and not any(gates.values()):
            reasons.append("archived_without_evidence")
        return gates, reasons

    def _classify(
        self, c: dict[str, Any], gates: dict[str, bool], metrics: dict[str, Any], crit: dict[str, Any],
    ) -> str:
        # Always reject live path
        if c.get("status") in ("DRAFT", "SCHEDULED"):
            return StrategyClassification.RESEARCH_ONLY.value
        if c.get("status") == "ACTIVE":
            if not gates["min_duration"] or not gates["min_trades"]:
                return StrategyClassification.PAPER_ACTIVE.value
            if not gates["recon_ok"]:
                return StrategyClassification.MORE_EVIDENCE_REQUIRED.value
            return StrategyClassification.PAPER_ACTIVE.value

        critical_fail = not gates["recon_ok"] or not gates["drawdown_ok"]
        if critical_fail and c.get("status") in ("COMPLETED", "ARCHIVED"):
            return StrategyClassification.REJECTED.value

        core = (
            gates["min_duration"]
            and gates["min_trades"]
            and gates["drawdown_ok"]
            and gates["recon_ok"]
            and gates["journal_ok"]
        )
        if not core:
            if c.get("status") == "COMPLETED":
                return StrategyClassification.MORE_EVIDENCE_REQUIRED.value
            return StrategyClassification.PAPER_ACTIVE.value

        strong = (
            gates.get("profit_factor_ok", True)
            and gates["sharpe_ok"]
            and gates["interventions_ok"]
            and gates["incidents_ok"]
        )
        if strong and c.get("status") in ("COMPLETED", "ARCHIVED"):
            return StrategyClassification.PAPER_GRADUATE.value
        if core and c.get("status") in ("COMPLETED", "ARCHIVED"):
            return StrategyClassification.PAPER_VALIDATED.value
        return StrategyClassification.MORE_EVIDENCE_REQUIRED.value

    def _persist(self, rec: dict[str, Any]) -> None:
        import json

        def _do(store):
            store.execute(
                """INSERT INTO pg_graduation(
                    id, campaign_id, strategy_slug, classification, metrics_json, gates_json,
                    reasons_json, live_authorized, auto_promoted_to_live, evaluated_at, actor,
                    immutable, fingerprint
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rec["id"], rec["campaign_id"], rec["strategy_slug"], rec["classification"],
                    json.dumps(rec["metrics"], sort_keys=True, default=str),
                    json.dumps(rec["gates"], sort_keys=True, default=str),
                    json.dumps(rec["reasons"], sort_keys=True, default=str),
                    0, 0, rec["evaluated_at"], rec["actor"], 1, rec["fingerprint"],
                ),
            )

        self.store.with_tx(_do)

    def list_for_campaign(self, campaign_id: str) -> list[dict[str, Any]]:
        import json
        with self.store._lock:
            rows = self.store.execute(
                "SELECT * FROM pg_graduation WHERE campaign_id=? ORDER BY evaluated_at DESC",
                (campaign_id,),
            ).fetchall()
        return [
            {
                "id": r["id"], "campaign_id": r["campaign_id"], "strategy_slug": r["strategy_slug"],
                "classification": r["classification"],
                "metrics": json.loads(r["metrics_json"] or "{}"),
                "gates": json.loads(r["gates_json"] or "{}"),
                "reasons": json.loads(r["reasons_json"] or "[]"),
                "live_authorized": bool(r["live_authorized"]),
                "auto_promoted_to_live": bool(r["auto_promoted_to_live"]),
                "evaluated_at": r["evaluated_at"], "fingerprint": r["fingerprint"],
                "paper_only": True,
            }
            for r in rows
        ]

    def rankings(self) -> dict[str, Any]:
        import json
        with self.store._lock:
            rows = self.store.execute(
                """SELECT g.* FROM pg_graduation g
                INNER JOIN (
                    SELECT campaign_id, MAX(evaluated_at) AS mx FROM pg_graduation GROUP BY campaign_id
                ) t ON g.campaign_id=t.campaign_id AND g.evaluated_at=t.mx
                ORDER BY g.evaluated_at DESC"""
            ).fetchall()
        items = []
        for r in rows:
            m = json.loads(r["metrics_json"] or "{}")
            items.append({
                "campaign_id": r["campaign_id"],
                "strategy_slug": r["strategy_slug"],
                "classification": r["classification"],
                "sharpe": m.get("sharpe"),
                "total_return": m.get("total_return"),
                "max_drawdown_pct": m.get("max_drawdown_pct"),
                "live_authorized": False,
            })
        # rank graduate first, then validated, then by sharpe
        rank_order = {
            StrategyClassification.PAPER_GRADUATE.value: 0,
            StrategyClassification.PAPER_VALIDATED.value: 1,
            StrategyClassification.PAPER_ACTIVE.value: 2,
            StrategyClassification.MORE_EVIDENCE_REQUIRED.value: 3,
            StrategyClassification.RESEARCH_ONLY.value: 4,
            StrategyClassification.REJECTED.value: 5,
        }
        items.sort(key=lambda x: (rank_order.get(x["classification"], 9), -(x.get("sharpe") or 0)))
        return {
            "strategies": items,
            "paper_only": True,
            "live_authorized": False,
            "note": "Rankings are paper operational signals only.",
        }
