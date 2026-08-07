"""Corporate action and dividend replay for paper portfolios."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.paper_simulation.errors import PaperSimError
from saathi.platform.tg.paper_simulation.models import AUTHORITY_VALUES
from saathi.platform.tg.paper_simulation.storage import PaperSimStore, _uid


class CorporateActionEngine:
    def __init__(self, store: PaperSimStore, ledger: Any):
        self.store = store
        self.ledger = ledger

    def register(
        self,
        symbol: str,
        action_type: str,
        *,
        ex_date: str,
        ratio: float | None = None,
        amount: float | None = None,
        detail: dict | None = None,
    ) -> dict[str, Any]:
        action_type = action_type.upper()
        if action_type not in ("SPLIT", "DIVIDEND", "MERGER"):
            raise PaperSimError("INVALID_CA_TYPE", action_type)
        cid = _uid("ca")
        self.store.execute(
            "INSERT INTO ps_corporate_actions(id, symbol, action_type, ratio, amount, ex_date, applied, detail_json, created_at) "
            "VALUES(?,?,?,?,?,?,0,?,?)",
            (
                cid, symbol.upper(), action_type, ratio, amount, ex_date,
                __import__("json").dumps(detail or {}, sort_keys=True), time.time(),
            ),
        )
        return {"ok": True, "ca_id": cid, "symbol": symbol.upper(), "action_type": action_type, **AUTHORITY_VALUES}

    def list(self, symbol: str | None = None) -> dict[str, Any]:
        if symbol:
            rows = self.store.fetchall(
                "SELECT * FROM ps_corporate_actions WHERE symbol=? ORDER BY ex_date",
                (symbol.upper(),),
            )
        else:
            rows = self.store.fetchall("SELECT * FROM ps_corporate_actions ORDER BY ex_date")
        return {"ok": True, "count": len(rows), "actions": rows, **AUTHORITY_VALUES}

    def apply(self, ca_id: str, portfolio_id: str) -> dict[str, Any]:
        ca = self.store.fetchone("SELECT * FROM ps_corporate_actions WHERE id=?", (ca_id,))
        if not ca:
            raise PaperSimError("CA_NOT_FOUND", ca_id)
        if ca["applied"]:
            return {"ok": True, "idempotent": True, "ca_id": ca_id, **AUTHORITY_VALUES}
        pos = self.store.fetchone(
            "SELECT * FROM ps_positions WHERE portfolio_id=? AND symbol=?",
            (portfolio_id, ca["symbol"]),
        )
        if not pos:
            self.store.execute("UPDATE ps_corporate_actions SET applied=1 WHERE id=?", (ca_id,))
            return {"ok": True, "applied": False, "reason": "no_position", **AUTHORITY_VALUES}

        if ca["action_type"] == "SPLIT":
            ratio = float(ca["ratio"] or 1.0)
            new_qty = float(pos["quantity"]) * ratio
            new_avg = float(pos["avg_cost"]) / ratio if ratio else float(pos["avg_cost"])
            new_mark = float(pos["mark"]) / ratio if ratio else float(pos["mark"])
            self.store.execute(
                "UPDATE ps_positions SET quantity=?, avg_cost=?, mark=?, updated_at=? WHERE id=?",
                (new_qty, new_avg, new_mark, time.time(), pos["id"]),
            )
        elif ca["action_type"] == "DIVIDEND":
            amount = float(ca["amount"] or 0.0)
            qty = float(pos["quantity"])
            if qty > 0 and amount > 0:
                cash_in = qty * amount
                pf = self.store.fetchone("SELECT cash FROM ps_portfolios WHERE portfolio_id=?", (portfolio_id,))
                new_cash = float(pf["cash"]) + cash_in
                self.store.execute(
                    "UPDATE ps_portfolios SET cash=?, updated_at=? WHERE portfolio_id=?",
                    (new_cash, time.time(), portfolio_id),
                )
                self.ledger._cash_entry(portfolio_id, "DIVIDEND", cash_in, new_cash, ref=ca_id)
        self.store.execute("UPDATE ps_corporate_actions SET applied=1 WHERE id=?", (ca_id,))
        self.store.audit("corporate_action.applied", subject=ca_id, detail={"portfolio_id": portfolio_id})
        return {"ok": True, "applied": True, "ca_id": ca_id, "portfolio_id": portfolio_id, **AUTHORITY_VALUES}
