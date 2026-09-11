"""COMMAND-SURFACE-1 — read-only trading state for Central Command.

Aggregates the trading program's observable state into the five panels Central
Command renders: MARKETS, RESEARCH, PORTFOLIO, TRADING, SAFETY.

Hard boundary: this surface is READ-ONLY. It exposes no action, no approval, and no
order entrypoint, and it never computes or overrides an authority's decision — it
reports what the authorities already decided. No UI route may bypass an authority,
so there is deliberately nothing here to bypass one with.

Unknown or degraded state is SURFACED, never hidden or defaulted to healthy: a
missing input renders as UNKNOWN so an operator sees the gap.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


UNKNOWN = "UNKNOWN"


class PanelStatus(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Panel:
    name: str
    status: PanelStatus
    rows: dict

    def to_public(self) -> dict:
        return {"panel": self.name, "status": self.status.value, **self.rows}


def _status_from(*, blocked: bool = False, degraded: bool = False, known: bool = True) -> PanelStatus:
    if not known:
        return PanelStatus.UNKNOWN
    if blocked:
        return PanelStatus.BLOCKED
    if degraded:
        return PanelStatus.DEGRADED
    return PanelStatus.OK


def markets_panel(provider_health=None) -> Panel:
    """Provider health, data quality, staleness, gaps."""
    if provider_health is None:
        return Panel("MARKETS", PanelStatus.UNKNOWN, {
            "providers": [], "detail": "no provider health reported",
        })
    stale = [p for p in provider_health if p.get("stale")]
    gaps = [p for p in provider_health if p.get("gap")]
    down = [p for p in provider_health if p.get("connected") is False]
    return Panel("MARKETS", _status_from(blocked=bool(down), degraded=bool(stale or gaps)), {
        "providers": list(provider_health),
        "stale_count": len(stale),
        "gap_count": len(gaps),
        "disconnected_count": len(down),
    })


def research_panel(theses=None) -> Panel:
    """Current thesis, contradictions, evidence quality."""
    if theses is None:
        return Panel("RESEARCH", PanelStatus.UNKNOWN, {"theses": [], "detail": "no research reported"})
    contradictions = sum(int(t.get("contradictions", 0) or 0) for t in theses)
    unverified = [t for t in theses if t.get("evidence_quality") in (None, "", "UNVERIFIED")]
    return Panel("RESEARCH", _status_from(degraded=bool(contradictions or unverified)), {
        "theses": list(theses),
        "contradiction_count": contradictions,
        "unverified_evidence_count": len(unverified),
    })


def portfolio_panel(snapshot=None, candidate=None, risk=None) -> Panel:
    """NAV, cash, positions, candidate allocations, risk decision."""
    if snapshot is None:
        return Panel("PORTFOLIO", PanelStatus.UNKNOWN, {"detail": "no ledger snapshot"})
    risk_result = (risk or {}).get("result", UNKNOWN)
    return Panel("PORTFOLIO", _status_from(
        blocked=risk_result == "BLOCK", degraded=risk_result == "REDUCE",
        known=risk_result != UNKNOWN,
    ), {
        "nav": str(snapshot.get("nav", UNKNOWN)),
        "cash": str(snapshot.get("cash", UNKNOWN)),
        "available_cash": str(snapshot.get("available_cash", UNKNOWN)),
        "positions": snapshot.get("positions", []),
        "candidate_allocations": (candidate or {}).get("allocations", []),
        "risk_result": risk_result,
        "risk_reason_codes": (risk or {}).get("reason_codes", []),
    })


def trading_panel(signals=None, intents=None, guardian=None, oms=None, reconciliation=None) -> Panel:
    """Signals, intents, Guardian state, paper OMS/fills, UNKNOWN + reconciliation."""
    open_recon = list((reconciliation or {}).get("open_items", []))
    guardian_state = (guardian or {}).get("state", UNKNOWN)
    unknown_orders = list((oms or {}).get("unknown_orders", []))
    return Panel("TRADING", _status_from(
        blocked=bool(open_recon or unknown_orders),
        degraded=guardian_state not in ("OK", UNKNOWN) and bool(guardian),
        known=guardian is not None or oms is not None or reconciliation is not None,
    ), {
        "signals": list(signals or []),
        "intents": list(intents or []),
        "guardian_state": guardian_state,
        "paper_orders": list((oms or {}).get("orders", [])),
        "fills": list((oms or {}).get("fills", [])),
        "unknown_orders": unknown_orders,
        "reconciliation_open_items": open_recon,
    })


def safety_panel(kill_switch=None, risk_limits=None, blocked_actions=None) -> Panel:
    """Kill switch, risk limits, blocked actions."""
    if kill_switch is None:
        return Panel("SAFETY", PanelStatus.UNKNOWN, {"detail": "kill switch state unknown"})
    active = bool(kill_switch.get("active"))
    return Panel("SAFETY", PanelStatus.BLOCKED if active else PanelStatus.OK, {
        "kill_switch_active": active,
        "risk_limits": risk_limits or {},
        "blocked_actions": list(blocked_actions or []),
    })


class CommandSurface:
    """Read-only aggregator. Exposes no mutating operation by design."""

    # Declared, and asserted by test, so a future edit that adds an action is caught.
    READ_ONLY = True

    def render(
        self,
        *,
        provider_health=None,
        theses=None,
        snapshot=None,
        candidate=None,
        risk=None,
        signals=None,
        intents=None,
        guardian=None,
        oms=None,
        reconciliation=None,
        kill_switch=None,
        risk_limits=None,
        blocked_actions=None,
    ) -> dict:
        panels = [
            markets_panel(provider_health),
            research_panel(theses),
            portfolio_panel(snapshot, candidate, risk),
            trading_panel(signals, intents, guardian, oms, reconciliation),
            safety_panel(kill_switch, risk_limits, blocked_actions),
        ]
        worst = PanelStatus.OK
        rank = {PanelStatus.OK: 0, PanelStatus.DEGRADED: 1, PanelStatus.UNKNOWN: 2, PanelStatus.BLOCKED: 3}
        for p in panels:
            if rank[p.status] > rank[worst]:
                worst = p.status
        return {
            "surface": "CENTRAL_COMMAND_TRADING",
            "read_only": True,
            "authorizes_execution": False,
            "authorizes_approval": False,
            "overall_status": worst.value,
            "panels": [p.to_public() for p in panels],
        }
