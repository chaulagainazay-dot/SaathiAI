"""HCG Live Signal business event source → Evidence."""
from __future__ import annotations
from saathi.evidence.schema import Evidence
_H = "hcg"


def handle(event_type: str, payload: dict, *, subject: str = "") -> list[Evidence]:
    p = payload or {}
    subject = subject or p.get("trade_id") or p.get("signal_id") or ""
    if event_type in ("trade.closed", "trade.won", "trade.lost"):
        result = "win" if event_type == "trade.won" else "loss" if event_type == "trade.lost" else p.get("result", "")
        return [Evidence(department=_H, project="hcg_signal", episode=subject, director="signal_engine",
                         prompt_version=p.get("prompt_version", ""), provider=p.get("provider", ""),
                         model=p.get("model", ""), confidence=float(p.get("confidence", 0) or 0), status=result,
                         metrics={"asset": p.get("asset", ""), "return": p.get("return"),
                                  "risk": p.get("risk"), "reason": p.get("reason", "")})]
    if event_type in ("daily.pnl", "monthly.pnl"):
        return [Evidence(department=_H, project="hcg_signal", episode=subject, director="portfolio",
                         status=event_type, metrics={"pnl": p.get("pnl"), "period": event_type})]
    if event_type == "subscription.started":
        return [Evidence(department=_H, project="hcg_signal", episode=subject, director="revenue",
                         status="subscribed", metrics={"plan": p.get("plan"), "amount": p.get("amount")})]
    return []
