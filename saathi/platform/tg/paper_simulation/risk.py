"""Risk monitor and kill switch for paper simulation."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.paper_simulation.errors import PaperSimError
from saathi.platform.tg.paper_simulation.models import (
    AUTHORITY_VALUES,
    DEFAULT_MAX_LEVERAGE,
    KillSwitchState,
    PortfolioState,
)
from saathi.platform.tg.paper_simulation.storage import PaperSimStore, _uid


class RiskMonitor:
    def __init__(self, store: PaperSimStore, ledger: Any):
        self.store = store
        self.ledger = ledger
        self.max_order_notional = 250_000.0
        self.max_position_pct = 0.5
        self.max_drawdown = 0.25

    def is_halted(self, portfolio_id: str = "") -> bool:
        global_ks = self.store.fetchone(
            "SELECT * FROM ps_kill_switch WHERE active=1 AND scope='GLOBAL' ORDER BY updated_at DESC LIMIT 1"
        )
        if global_ks:
            return True
        if portfolio_id:
            pf_ks = self.store.fetchone(
                "SELECT * FROM ps_kill_switch WHERE active=1 AND scope='PORTFOLIO' AND scope_ref=? "
                "ORDER BY updated_at DESC LIMIT 1",
                (portfolio_id,),
            )
            if pf_ks:
                return True
            pf = self.store.fetchone("SELECT state FROM ps_portfolios WHERE portfolio_id=?", (portfolio_id,))
            if pf and pf["state"] == PortfolioState.HALTED.value:
                return True
        return False

    def activate_kill_switch(
        self,
        reason: str,
        *,
        scope: str = "GLOBAL",
        scope_ref: str = "",
        actor: str = "operator",
    ) -> dict[str, Any]:
        if actor in ("strategy", "llm", "agent") or actor.startswith(("strategy:", "llm:", "agent:")):
            raise PaperSimError("KILL_SWITCH_AUTHORITY", "strategy/LLM/agent cannot activate kill switch")
        if not reason:
            raise PaperSimError("REASON_REQUIRED", "kill switch reason required")
        kid = _uid("ks")
        now = time.time()
        self.store.execute(
            "INSERT INTO ps_kill_switch(id, scope, scope_ref, active, reason, activated_by, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (kid, scope, scope_ref, 1, reason, actor, now, now),
        )
        if scope == "PORTFOLIO" and scope_ref:
            self.store.execute(
                "UPDATE ps_portfolios SET state=?, updated_at=? WHERE portfolio_id=?",
                (PortfolioState.HALTED.value, now, scope_ref),
            )
            # stop open orders
            self.store.execute(
                "UPDATE ps_orders SET status='STOPPED', updated_at=?, finished_at=? "
                "WHERE portfolio_id=? AND status IN ('NEW','ACCEPTED','PARTIALLY_FILLED')",
                (now, now, scope_ref),
            )
        elif scope == "GLOBAL":
            self.store.execute(
                "UPDATE ps_orders SET status='STOPPED', updated_at=?, finished_at=? "
                "WHERE status IN ('NEW','ACCEPTED','PARTIALLY_FILLED')",
                (now, now),
            )
        self.store.audit("kill_switch.activate", actor=actor, subject=kid, detail={
            "scope": scope, "scope_ref": scope_ref, "reason": reason,
        })
        return {
            "ok": True,
            "kill_switch_id": kid,
            "state": KillSwitchState.ACTIVE.value,
            "scope": scope,
            "reason": reason,
            **AUTHORITY_VALUES,
        }

    def deactivate_kill_switch(self, kill_switch_id: str, *, actor: str = "operator") -> dict[str, Any]:
        if actor in ("strategy", "llm", "agent"):
            raise PaperSimError("KILL_SWITCH_AUTHORITY", "cannot deactivate by strategy/LLM")
        row = self.store.fetchone("SELECT * FROM ps_kill_switch WHERE id=?", (kill_switch_id,))
        if not row:
            raise PaperSimError("KILL_SWITCH_NOT_FOUND", kill_switch_id)
        self.store.execute(
            "UPDATE ps_kill_switch SET active=0, updated_at=? WHERE id=?",
            (time.time(), kill_switch_id),
        )
        if row["scope"] == "PORTFOLIO" and row["scope_ref"]:
            self.store.execute(
                "UPDATE ps_portfolios SET state=?, updated_at=? WHERE portfolio_id=?",
                (PortfolioState.ACTIVE.value, time.time(), row["scope_ref"]),
            )
        self.store.audit("kill_switch.deactivate", actor=actor, subject=kill_switch_id, detail={})
        return {"ok": True, "kill_switch_id": kill_switch_id, "state": KillSwitchState.INACTIVE.value, **AUTHORITY_VALUES}

    def kill_switch_status(self) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT * FROM ps_kill_switch WHERE active=1 ORDER BY updated_at DESC"
        )
        return {
            "ok": True,
            "active": len(rows) > 0,
            "switches": rows,
            "state": KillSwitchState.ACTIVE.value if rows else KillSwitchState.INACTIVE.value,
            **AUTHORITY_VALUES,
        }

    def pre_trade_check(
        self,
        portfolio_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float | None,
    ) -> dict[str, Any]:
        if self.is_halted(portfolio_id):
            return {"ok": False, "code": "KILL_SWITCH_ACTIVE", "message": "portfolio or global halt"}
        pf = self.ledger.get_portfolio(portfolio_id)
        if not pf.get("ok"):
            return {"ok": False, "code": "PORTFOLIO_NOT_FOUND", "message": portfolio_id}
        px = float(price or 0) or 100.0
        notional = quantity * px
        if notional > self.max_order_notional:
            return {"ok": False, "code": "MAX_ORDER_NOTIONAL", "message": str(self.max_order_notional)}
        equity = float(pf["metrics"]["equity"])
        if equity > 0 and notional / equity > self.max_position_pct * 1.5:
            return {"ok": False, "code": "CONCENTRATION_LIMIT", "message": "order too large vs equity"}
        lev_limit = float(pf["portfolio"]["max_leverage"] or DEFAULT_MAX_LEVERAGE)
        if not pf["portfolio"]["margin_enabled"] and side == "SELL":
            # short check deferred to ledger
            pass
        # projected leverage rough
        gross = float(pf["metrics"]["gross_exposure"]) + notional
        if equity > 0 and gross / equity > lev_limit + 1e-6:
            return {"ok": False, "code": "LEVERAGE_LIMIT", "message": f"exceeds {lev_limit}"}
        return {"ok": True, **AUTHORITY_VALUES}

    def post_trade_check(self, portfolio_id: str) -> dict[str, Any]:
        pf = self.ledger.get_portfolio(portfolio_id)
        if not pf.get("ok"):
            return pf
        metrics = pf["metrics"]
        events = []
        lev_limit = float(pf["portfolio"]["max_leverage"] or 1.0)
        if metrics["leverage"] > lev_limit + 1e-6:
            events.append(self._event(portfolio_id, "LEVERAGE_BREACH", "high", f"lev={metrics['leverage']}"))
        initial = float(pf["portfolio"]["initial_cash"])
        if initial > 0:
            dd = 1.0 - (metrics["equity"] / initial)
            if dd > self.max_drawdown:
                events.append(self._event(portfolio_id, "DRAWDOWN_BREACH", "critical", f"dd={dd:.4f}"))
                try:
                    self.activate_kill_switch(
                        f"max drawdown {dd:.2%}",
                        scope="PORTFOLIO",
                        scope_ref=portfolio_id,
                        actor="risk_monitor",
                    )
                except PaperSimError:
                    pass
        return {"ok": True, "events": events, "metrics": metrics, **AUTHORITY_VALUES}

    def _event(self, portfolio_id: str, kind: str, severity: str, message: str) -> dict[str, Any]:
        eid = _uid("risk")
        self.store.execute(
            "INSERT INTO ps_risk_events(id, portfolio_id, kind, severity, message, detail_json, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (eid, portfolio_id, kind, severity, message, "{}", time.time()),
        )
        return {"id": eid, "kind": kind, "severity": severity, "message": message}

    def risk_events(self, portfolio_id: str, limit: int = 50) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT * FROM ps_risk_events WHERE portfolio_id=? ORDER BY created_at DESC LIMIT ?",
            (portfolio_id, limit),
        )
        return {"ok": True, "count": len(rows), "events": rows, **AUTHORITY_VALUES}
