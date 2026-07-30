"""Cash ledger, positions, and portfolio accounting."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.paper_simulation.errors import PaperSimError
from saathi.platform.tg.paper_simulation.models import (
    AUTHORITY_VALUES,
    DEFAULT_INITIAL_CASH,
    DEFAULT_MAX_LEVERAGE,
    MAX_POSITIONS,
    PortfolioState,
)
from saathi.platform.tg.paper_simulation.storage import PaperSimStore, _uid


class PortfolioLedger:
    def __init__(self, store: PaperSimStore):
        self.store = store

    def create_portfolio(
        self,
        name: str = "Paper Core",
        *,
        initial_cash: float = DEFAULT_INITIAL_CASH,
        margin_enabled: bool = False,
        max_leverage: float = DEFAULT_MAX_LEVERAGE,
    ) -> dict[str, Any]:
        if max_leverage > DEFAULT_MAX_LEVERAGE + 1e-9 and not margin_enabled:
            raise PaperSimError("LEVERAGE_POLICY", "max_leverage > 1.0 requires margin_enabled (research only)")
        if max_leverage > 2.0 + 1e-9:
            raise PaperSimError("LEVERAGE_CAP", "research margin leverage capped at 2.0")
        pid = _uid("pf")
        now = time.time()
        self.store.execute(
            "INSERT INTO ps_portfolios(portfolio_id, name, currency, cash, initial_cash, state, "
            "margin_enabled, max_leverage, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                pid, name, "USD", float(initial_cash), float(initial_cash),
                PortfolioState.ACTIVE.value, 1 if margin_enabled else 0, float(max_leverage), now, now,
            ),
        )
        self._cash_entry(pid, "INITIAL_FUNDING", float(initial_cash), float(initial_cash), ref="seed")
        self.store.audit("portfolio.created", subject=pid, detail={"initial_cash": initial_cash})
        return {"ok": True, "portfolio_id": pid, "name": name, "cash": initial_cash, **AUTHORITY_VALUES}

    def get_portfolio(self, portfolio_id: str) -> dict[str, Any]:
        pf = self.store.fetchone("SELECT * FROM ps_portfolios WHERE portfolio_id=?", (portfolio_id,))
        if not pf:
            return {"ok": False, "code": "PORTFOLIO_NOT_FOUND", **AUTHORITY_VALUES}
        positions = self.store.fetchall(
            "SELECT * FROM ps_positions WHERE portfolio_id=? ORDER BY symbol", (portfolio_id,)
        )
        equity = float(pf["cash"])
        gross = 0.0
        unrealized = 0.0
        for p in positions:
            mv = float(p["quantity"]) * float(p["mark"])
            cost = float(p["quantity"]) * float(p["avg_cost"])
            equity += mv
            gross += abs(mv)
            unrealized += mv - cost
        return {
            "ok": True,
            "portfolio": pf,
            "positions": positions,
            "metrics": {
                "cash": pf["cash"],
                "equity": round(equity, 4),
                "gross_exposure": round(gross, 4),
                "net_exposure": round(equity - float(pf["cash"]), 4),
                "unrealized_pnl": round(unrealized, 4),
                "realized_pnl": round(sum(float(p["realized_pnl"]) for p in positions), 4),
                "leverage": round(gross / equity, 6) if equity > 0 else 0.0,
            },
            **AUTHORITY_VALUES,
        }

    def list_portfolios(self) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT portfolio_id, name, cash, state, margin_enabled, max_leverage, created_at FROM ps_portfolios"
        )
        return {"ok": True, "count": len(rows), "portfolios": rows, **AUTHORITY_VALUES}

    def apply_fill(
        self,
        portfolio_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        fee: float,
        *,
        ref: str = "",
    ) -> dict[str, Any]:
        pf = self.store.fetchone("SELECT * FROM ps_portfolios WHERE portfolio_id=?", (portfolio_id,))
        if not pf:
            raise PaperSimError("PORTFOLIO_NOT_FOUND", portfolio_id)
        if pf["state"] != PortfolioState.ACTIVE.value:
            raise PaperSimError("PORTFOLIO_NOT_ACTIVE", pf["state"])

        notional = quantity * price
        cash = float(pf["cash"])
        pos = self.store.fetchone(
            "SELECT * FROM ps_positions WHERE portfolio_id=? AND symbol=?",
            (portfolio_id, symbol),
        )

        if side == "BUY":
            cost = notional + fee
            if cash + 1e-9 < cost and not pf["margin_enabled"]:
                raise PaperSimError("INSUFFICIENT_CASH", f"need {cost}, have {cash}")
            # margin: allow negative cash up to leverage policy checked by risk
            new_cash = cash - cost
            if pos:
                old_qty = float(pos["quantity"])
                old_cost = float(pos["avg_cost"])
                if old_qty >= 0:
                    new_qty = old_qty + quantity
                    new_avg = ((old_qty * old_cost) + notional) / new_qty if new_qty else price
                else:
                    # covering short
                    cover = min(quantity, abs(old_qty))
                    realized = cover * (old_cost - price)
                    new_qty = old_qty + quantity
                    new_avg = price if new_qty > 0 else old_cost
                    self.store.execute(
                        "UPDATE ps_positions SET realized_pnl=realized_pnl+? WHERE id=?",
                        (realized, pos["id"]),
                    )
                self.store.execute(
                    "UPDATE ps_positions SET quantity=?, avg_cost=?, mark=?, updated_at=? WHERE id=?",
                    (new_qty, new_avg, price, time.time(), pos["id"]),
                )
            else:
                npos = self.store.fetchone(
                    "SELECT COUNT(*) AS c FROM ps_positions WHERE portfolio_id=?", (portfolio_id,)
                )
                if (npos or {}).get("c", 0) >= MAX_POSITIONS:
                    raise PaperSimError("MAX_POSITIONS", str(MAX_POSITIONS))
                self.store.execute(
                    "INSERT INTO ps_positions(id, portfolio_id, symbol, quantity, avg_cost, mark, realized_pnl, updated_at) "
                    "VALUES(?,?,?,?,?,?,0,?)",
                    (_uid("pos"), portfolio_id, symbol, quantity, price, price, time.time()),
                )
            self.store.execute(
                "UPDATE ps_portfolios SET cash=?, updated_at=? WHERE portfolio_id=?",
                (new_cash, time.time(), portfolio_id),
            )
            self._cash_entry(portfolio_id, "BUY", -cost, new_cash, ref=ref)
        else:  # SELL
            proceeds = notional - fee
            if pos:
                old_qty = float(pos["quantity"])
                old_cost = float(pos["avg_cost"])
                if old_qty > 0:
                    sell_qty = min(quantity, old_qty)
                    realized = sell_qty * (price - old_cost)
                    new_qty = old_qty - quantity  # allow oversell -> short if margin
                    if new_qty < -1e-9 and not pf["margin_enabled"]:
                        raise PaperSimError("SHORT_NOT_ALLOWED", "margin_enabled required for shorts")
                    if quantity > old_qty + 1e-9 and not pf["margin_enabled"]:
                        raise PaperSimError("INSUFFICIENT_POSITION", f"have {old_qty}")
                    # recompute for exact short open
                    if quantity > old_qty and pf["margin_enabled"]:
                        new_qty = old_qty - quantity
                        realized = old_qty * (price - old_cost)
                        new_avg = price if new_qty < 0 else old_cost
                    else:
                        new_qty = old_qty - quantity
                        new_avg = old_cost
                    self.store.execute(
                        "UPDATE ps_positions SET quantity=?, avg_cost=?, mark=?, realized_pnl=realized_pnl+?, updated_at=? WHERE id=?",
                        (new_qty, new_avg, price, realized, time.time(), pos["id"]),
                    )
                    if abs(new_qty) < 1e-12:
                        self.store.execute("DELETE FROM ps_positions WHERE id=?", (pos["id"],))
                else:
                    # increase short
                    if not pf["margin_enabled"]:
                        raise PaperSimError("SHORT_NOT_ALLOWED", "margin required")
                    new_qty = old_qty - quantity
                    new_avg = ((abs(old_qty) * old_cost) + notional) / abs(new_qty) if new_qty else price
                    self.store.execute(
                        "UPDATE ps_positions SET quantity=?, avg_cost=?, mark=?, updated_at=? WHERE id=?",
                        (new_qty, new_avg, price, time.time(), pos["id"]),
                    )
            else:
                if not pf["margin_enabled"]:
                    raise PaperSimError("INSUFFICIENT_POSITION", "no position")
                self.store.execute(
                    "INSERT INTO ps_positions(id, portfolio_id, symbol, quantity, avg_cost, mark, realized_pnl, updated_at) "
                    "VALUES(?,?,?,?,?,?,0,?)",
                    (_uid("pos"), portfolio_id, symbol, -quantity, price, price, time.time()),
                )
            new_cash = cash + proceeds
            self.store.execute(
                "UPDATE ps_portfolios SET cash=?, updated_at=? WHERE portfolio_id=?",
                (new_cash, time.time(), portfolio_id),
            )
            self._cash_entry(portfolio_id, "SELL", proceeds, new_cash, ref=ref)

        return {"ok": True, "portfolio_id": portfolio_id, "symbol": symbol, **AUTHORITY_VALUES}

    def mark_positions(self, portfolio_id: str, marks: dict[str, float]) -> dict[str, Any]:
        for sym, mark in marks.items():
            self.store.execute(
                "UPDATE ps_positions SET mark=?, updated_at=? WHERE portfolio_id=? AND symbol=?",
                (float(mark), time.time(), portfolio_id, sym.upper()),
            )
        return self.get_portfolio(portfolio_id)

    def cash_history(self, portfolio_id: str, limit: int = 100) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT * FROM ps_cash_ledger WHERE portfolio_id=? ORDER BY created_at DESC LIMIT ?",
            (portfolio_id, limit),
        )
        return {"ok": True, "count": len(rows), "entries": rows, **AUTHORITY_VALUES}

    def _cash_entry(self, portfolio_id: str, kind: str, amount: float, balance_after: float, ref: str = "") -> None:
        self.store.execute(
            "INSERT INTO ps_cash_ledger(entry_id, portfolio_id, kind, amount, balance_after, ref, detail_json, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (_uid("csh"), portfolio_id, kind, amount, balance_after, ref, "{}", time.time()),
        )
