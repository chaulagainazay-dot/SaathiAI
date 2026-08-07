"""M212 — Advanced rolling analytics and reports for paper campaigns."""
from __future__ import annotations

import math
import statistics
import time
import uuid
from typing import Any


def _id(prefix: str = "eq") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class AdvancedAnalytics:
    def __init__(self, gov: Any):
        self.gov = gov
        self.store = gov.store

    def record_equity_point(
        self, portfolio_id: str, *, campaign_id: str = "", equity: str | None = None,
    ) -> dict[str, Any]:
        pub = self.gov.get_portfolio(portfolio_id)["portfolio"]
        eq = equity or pub.get("equity") or pub.get("cash")
        dd = pub.get("drawdown_pct", "0")

        def _do(store):
            store.execute(
                """INSERT INTO pg_equity_points(portfolio_id, campaign_id, ts, equity, drawdown_pct, mark_json)
                VALUES (?,?,?,?,?,?)""",
                (portfolio_id, campaign_id, time.time(), str(eq), str(dd), "{}"),
            )
            return {"portfolio_id": portfolio_id, "equity": str(eq), "drawdown_pct": str(dd), "paper_only": True}

        return self.store.with_tx(_do)

    def equity_series(self, portfolio_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        with self.store._lock:
            rows = self.store.execute(
                "SELECT * FROM pg_equity_points WHERE portfolio_id=? ORDER BY ts ASC LIMIT ?",
                (portfolio_id, limit),
            ).fetchall()
        return [
            {
                "ts": r["ts"], "equity": float(r["equity"]),
                "drawdown_pct": float(r["drawdown_pct"] or 0),
                "campaign_id": r["campaign_id"],
            }
            for r in rows
        ]

    def rolling_stats(self, portfolio_id: str, *, window: int = 20) -> dict[str, Any]:
        series = self.equity_series(portfolio_id)
        if len(series) < 2:
            # fall back to current analytics snapshot
            a = self.gov.analytics(portfolio_id).get("analytics", {})
            return {
                "window": window,
                "points": len(series),
                "rolling_sharpe": a.get("sharpe"),
                "rolling_sortino": a.get("sortino"),
                "rolling_drawdown": a.get("max_drawdown_pct"),
                "rolling_volatility": None,
                "rolling_expectancy": a.get("expectancy"),
                "confidence_interval_return_95": None,
                "paper_only": True,
                "note": "Insufficient equity points; using snapshot analytics.",
            }
        rets = []
        for i in range(1, len(series)):
            prev, cur = series[i - 1]["equity"], series[i]["equity"]
            if prev > 0:
                rets.append((cur - prev) / prev)
        w = rets[-window:] if len(rets) >= window else rets
        mean = statistics.fmean(w) if w else 0.0
        std = statistics.pstdev(w) if len(w) > 1 else 0.0
        sharpe = (mean / std) * math.sqrt(252) if std > 0 else 0.0
        downside = [r for r in w if r < 0]
        dstd = statistics.pstdev(downside) if len(downside) > 1 else (abs(downside[0]) if downside else 0.0)
        sortino = (mean / dstd) * math.sqrt(252) if dstd > 0 else 0.0
        # rolling drawdown from series window
        eq_w = [s["equity"] for s in series[-window:]]
        peak = eq_w[0]
        max_dd = 0.0
        for e in eq_w:
            peak = max(peak, e)
            if peak > 0:
                max_dd = max(max_dd, (peak - e) / peak * 100)
        # CI 95% on mean return (normal approx)
        if len(w) > 1 and std > 0:
            se = std / math.sqrt(len(w))
            ci = (mean - 1.96 * se, mean + 1.96 * se)
        else:
            ci = None
        return {
            "window": window,
            "points": len(series),
            "rolling_sharpe": round(sharpe, 6),
            "rolling_sortino": round(sortino, 6),
            "rolling_drawdown": round(max_dd, 6),
            "rolling_volatility": round(std * math.sqrt(252), 6) if std else 0.0,
            "rolling_expectancy": round(mean, 8),
            "confidence_interval_return_95": ci,
            "timeline": series[-window:],
            "paper_only": True,
            "live_authorized": False,
        }

    def heatmap(self, portfolio_id: str) -> dict[str, Any]:
        a = self.gov.analytics(portfolio_id).get("analytics", {})
        return {
            "exposure_heatmap": a.get("exposure_heatmap", {}),
            "paper_only": True,
        }

    def campaign_report(self, campaign_id: str) -> dict[str, Any]:
        c = self.store.get_campaign(campaign_id)
        if not c:
            return {"error": "not found", "paper_only": True}
        analytics = {}
        rolling = {}
        if c.get("portfolio_id"):
            analytics = self.gov.analytics(c["portfolio_id"]).get("analytics", {})
            rolling = self.rolling_stats(c["portfolio_id"])
            self.record_equity_point(c["portfolio_id"], campaign_id=campaign_id)
        return {
            "kind": "campaign_report",
            "campaign": c,
            "analytics": analytics,
            "rolling": rolling,
            "regime_overlay": {"note": "Regime overlay is advisory paper context only."},
            "paper_only": True,
            "live_authorized": False,
            "disclaimer": "Simulated analytics. Not future results.",
        }

    def weekly_report(self) -> dict[str, Any]:
        base = self.gov.report_weekly() if hasattr(self.gov, "report_weekly") else {}
        camps = self.store.list_campaigns()
        rankings = []
        for c in camps:
            if not c.get("portfolio_id"):
                continue
            try:
                a = self.gov.analytics(c["portfolio_id"]).get("analytics", {})
            except Exception:
                a = {}
            rankings.append({
                "campaign_id": c["id"],
                "strategy_slug": c.get("strategy_slug"),
                "status": c.get("status"),
                "total_return": a.get("total_return"),
                "sharpe": a.get("sharpe"),
                "max_drawdown_pct": a.get("max_drawdown_pct"),
            })
        rankings.sort(key=lambda x: -(x.get("sharpe") or 0))
        return {
            **base,
            "kind": "weekly_ops_report",
            "campaign_rankings": rankings,
            "portfolio_rankings": rankings,  # same source for paper ops
            "paper_only": True,
            "live_authorized": False,
        }

    def monthly_report(self) -> dict[str, Any]:
        w = self.weekly_report()
        w["kind"] = "monthly_ops_report"
        w["period"] = "month"
        return w

    def comparison_report(self, campaign_ids: list[str]) -> dict[str, Any]:
        rows = {}
        for cid in campaign_ids:
            rows[cid] = self.campaign_report(cid)
        return {
            "kind": "comparison_report",
            "campaigns": rows,
            "paper_only": True,
            "live_authorized": False,
        }

    def strategy_ranking(self) -> dict[str, Any]:
        by_slug: dict[str, list] = {}
        for c in self.store.list_campaigns():
            by_slug.setdefault(c.get("strategy_slug", "unknown"), []).append(c)
        ranking = []
        for slug, camps in by_slug.items():
            sharpes = []
            for c in camps:
                if c.get("portfolio_id"):
                    try:
                        a = self.gov.analytics(c["portfolio_id"]).get("analytics", {})
                        if a.get("sharpe") is not None:
                            sharpes.append(float(a["sharpe"]))
                    except Exception:
                        pass
            ranking.append({
                "strategy_slug": slug,
                "campaign_count": len(camps),
                "avg_sharpe": (sum(sharpes) / len(sharpes)) if sharpes else None,
                "paper_only": True,
            })
        ranking.sort(key=lambda x: -(x["avg_sharpe"] if x["avg_sharpe"] is not None else -999))
        return {"strategies": ranking, "paper_only": True, "live_authorized": False}
