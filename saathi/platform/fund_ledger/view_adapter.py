"""Read adapter: canonical ledger state → legacy-shaped DTOs (no second authority)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.fund_ledger.money import D, q_money, q_price, q_qty


class LedgerPortfolioViewAdapter:
    """Translate PortfolioLedgerService public state into OMS-compatible shapes.

    Does NOT persist. Does NOT recompute avg-cost books from scratch outside ledger.
    avg_cost is cost-weighted open-lot average from the ledger state payload.
    """

    @staticmethod
    def from_ledger_state(
        state: dict[str, Any],
        *,
        account_id: str = "",
        reserved_cash: Any = "0",
        reserved_by_symbol: dict[str, Any] | None = None,
    ) -> dict:
        reserved_cash_d = q_money(reserved_cash)
        cash = q_money(state.get("cash") or "0")
        available = q_money(cash - reserved_cash_d)
        positions_out = []
        reserved_by_symbol = reserved_by_symbol or {}
        for p in state.get("positions") or []:
            sym = p.get("symbol") or p.get("security_id")
            qty = q_qty(p.get("quantity") or "0")
            rsv = q_qty(reserved_by_symbol.get(sym) or "0")
            positions_out.append(
                {
                    "symbol": sym,
                    "security_id": p.get("security_id"),
                    "quantity": str(qty),
                    "reserved_quantity": str(rsv),
                    "available_quantity": str(q_qty(qty - rsv)),
                    "avg_cost": str(q_price(p.get("avg_cost") or "0")),
                    "realized_pnl": str(q_money(p.get("realized_pnl") or "0")),
                    "unrealized_pnl": str(q_money(p.get("unrealized_pnl") or "0")),
                    "market_value": str(q_money(p.get("market_value") or "0")),
                    "mark_stale": bool(p.get("mark_stale")),
                    "source": "canonical_fund_ledger",
                }
            )
        return {
            "account_id": account_id,
            "fund_id": state.get("fund_id"),
            "mode": "PAPER",
            "books_authority": "canonical_fund_ledger",
            "legacy_oms_state_not_books_authority": True,
            "currency": state.get("currency") or "USD",
            "cash": str(cash),
            "reserved_cash": str(reserved_cash_d),
            "available_cash": str(available),
            "realized_pnl": str(q_money(state.get("realized_pnl") or "0")),
            "unrealized_pnl": str(q_money(state.get("unrealized_pnl") or "0")),
            "total_pnl": str(q_money(state.get("total_pnl") or "0")),
            "positions_value": str(q_money(state.get("positions_value") or "0")),
            "nav": str(q_money(state.get("nav") or "0")),
            "paper_nav": str(q_money(state.get("paper_nav") or state.get("nav") or "0")),
            "exposure": state.get("exposure") or {},
            "positions": positions_out,
            "open_lots": state.get("open_lots") or [],
            "invariants_ok": bool(state.get("invariants_ok", True)),
            "event_count": state.get("event_count"),
            "source": "canonical_fund_ledger",
        }

    @staticmethod
    def command_summary(state: dict[str, Any], *, recon: dict | None = None) -> dict:
        healthy = True
        recon_status = "HEALTHY"
        if recon is not None:
            healthy = bool(recon.get("ok", False)) and recon.get("portfolio_status") != "RECONCILIATION_REQUIRED"
            recon_status = recon.get("portfolio_status") or ("HEALTHY" if recon.get("ok") else "RECONCILIATION_REQUIRED")
        if state.get("invariants_ok") is False:
            healthy = False
            recon_status = "RECONCILIATION_REQUIRED"
        return {
            "mode": "PAPER",
            "live_execution": "UNAVAILABLE",
            "liveExecution": "UNAVAILABLE",
            "source": "canonical_fund_ledger",
            "ledger": True,
            "fund_id": state.get("fund_id"),
            "equity": state.get("nav"),
            "paper_nav": state.get("nav") or state.get("paper_nav"),
            "nav": state.get("nav"),
            "cash": state.get("cash"),
            "pnl": state.get("total_pnl"),
            "total_pnl": state.get("total_pnl"),
            "realized_pnl": state.get("realized_pnl"),
            "unrealized_pnl": state.get("unrealized_pnl"),
            "gross_exposure": (state.get("exposure") or {}).get("gross"),
            "net_exposure": (state.get("exposure") or {}).get("net"),
            "positions": state.get("positions") or [],
            "invariants_ok": state.get("invariants_ok"),
            "reconciliation_status": recon_status,
            "portfolio_status": recon_status if not healthy else "HEALTHY",
            "portfolio_healthy": healthy,
        }
