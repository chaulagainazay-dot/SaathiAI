"""Paper portfolio engine — multi-portfolio fund simulator (paper only)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.tg.paper_activation.models import (
    D,
    PaperPortfolio,
    PaperPosition,
    PositionLot,
    PortfolioStatus,
    PortfolioSnapshot,
    RiskHaltReason,
    RiskLimits,
    SimOrder,
    _id,
    _now,
)
from saathi.platform.tg.paper_activation.order_simulator import MarketTick, OrderSimulator
from saathi.platform.tg.paper_activation.risk_controls import RiskController


class PortfolioEngineError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class PaperPortfolioEngine:
    def __init__(self) -> None:
        self._portfolios: dict[str, PaperPortfolio] = {}
        self._orders: dict[str, SimOrder] = {}
        self._by_portfolio_orders: dict[str, list[str]] = {}

    def create(
        self,
        *,
        name: str = "Paper Fund",
        starting_cash: str | Decimal = "100000",
        base_currency: str = "USD",
        org_id: str = "local",
        workspace_id: str = "local",
        risk_limits: RiskLimits | None = None,
    ) -> PaperPortfolio:
        cash = D(starting_cash)
        if cash <= 0:
            raise PortfolioEngineError("VALIDATION", "starting cash must be positive")
        p = PaperPortfolio(
            name=name,
            starting_cash=cash,
            cash=cash,
            peak_equity=cash,
            day_start_equity=cash,
            week_start_equity=cash,
            month_start_equity=cash,
            base_currency=base_currency,
            org_id=org_id,
            workspace_id=workspace_id,
            risk_limits=risk_limits or RiskLimits(),
            status=PortfolioStatus.ACTIVE,
        )
        p.audit("portfolio_created", starting_cash=str(cash))
        p.snapshot("created")
        self._portfolios[p.id] = p
        self._by_portfolio_orders[p.id] = []
        return p

    def get(self, portfolio_id: str) -> PaperPortfolio | None:
        return self._portfolios.get(portfolio_id)

    def list(self, *, org_id: str = "", workspace_id: str = "") -> list[PaperPortfolio]:
        out = []
        for p in self._portfolios.values():
            if org_id and p.org_id != org_id:
                continue
            if workspace_id and p.workspace_id != workspace_id:
                continue
            out.append(p)
        return out

    def set_mark(self, portfolio_id: str, symbol: str, price: Decimal | str) -> PaperPortfolio:
        p = self._require(portfolio_id)
        p.marks[symbol] = D(price)
        p.updated_at = _now()
        return p

    def halt(self, portfolio_id: str, *, reason: RiskHaltReason, detail: str = "") -> PaperPortfolio:
        p = self._require(portfolio_id)
        p.status = PortfolioStatus.HALTED
        p.halt_reason = reason
        p.halt_detail = detail
        p.audit("halted", reason=reason.value, detail=detail)
        return p

    def lock(self, portfolio_id: str, *, detail: str = "") -> PaperPortfolio:
        p = self._require(portfolio_id)
        p.status = PortfolioStatus.LOCKED
        p.halt_reason = RiskHaltReason.OPERATOR
        p.halt_detail = detail
        p.audit("locked", detail=detail)
        return p

    def resume(self, portfolio_id: str) -> PaperPortfolio:
        p = self._require(portfolio_id)
        if p.status not in (PortfolioStatus.HALTED, PortfolioStatus.LOCKED):
            raise PortfolioEngineError("NOT_HALTED", f"status is {p.status.value}")
        p.status = PortfolioStatus.ACTIVE
        p.halt_reason = RiskHaltReason.NONE
        p.halt_detail = ""
        p.audit("resumed")
        return p

    def submit_order(self, order: SimOrder, *, strategy_active: bool = True) -> SimOrder:
        from saathi.platform.tg.paper_activation.models import SimOrderStatus

        p = self._require(order.portfolio_id)
        if p.status != PortfolioStatus.ACTIVE:
            order.status = SimOrderStatus.REJECTED
            order.reject_reason = f"portfolio_{p.status.value.lower()}"
            self._store_order(order)
            return order
        if not strategy_active:
            order.status = SimOrderStatus.REJECTED
            order.reject_reason = "strategy_not_paper_active"
            self._store_order(order)
            return order

        risk = RiskController(p.risk_limits)
        gate = risk.pre_trade_check(p, order)
        if not gate["ok"]:
            order.status = SimOrderStatus.REJECTED
            order.reject_reason = gate["reason"]
            p.audit("order_rejected", order_id=order.id, reason=gate["reason"])
            self._store_order(order)
            return order

        order.status = SimOrderStatus.ACCEPTED
        self._store_order(order)
        p.audit("order_accepted", order_id=order.id, symbol=order.symbol, side=order.side)
        return order

    def _store_order(self, order: SimOrder) -> None:
        self._orders[order.id] = order
        ids = self._by_portfolio_orders.setdefault(order.portfolio_id, [])
        if order.id not in ids:
            ids.append(order.id)

    def process_tick(self, portfolio_id: str, tick: MarketTick) -> dict[str, Any]:
        p = self._require(portfolio_id)
        p.marks[tick.symbol] = tick.last
        sim = OrderSimulator(p.risk_limits)
        results = []
        for oid in list(self._by_portfolio_orders.get(portfolio_id, [])):
            order = self._orders.get(oid)
            if not order or order.symbol != tick.symbol:
                continue
            if order.status.value in ("FILLED", "CANCELLED", "REJECTED", "EXPIRED"):
                continue
            r = sim.try_fill(order, tick)
            if r.get("filled"):
                self._apply_fill(p, order, r)
            results.append({"order_id": order.id, **r, "status": order.status.value})

        # post-trade risk
        risk = RiskController(p.risk_limits)
        post = risk.post_trade_check(p)
        if post.get("halt"):
            self.halt(portfolio_id, reason=RiskHaltReason(post["reason"]), detail=post.get("detail", ""))
        p.snapshot("tick")
        return {"results": results, "portfolio": p.to_public(), "risk": post, "paper_only": True}

    def _apply_fill(self, p: PaperPortfolio, order: SimOrder, fill_result: dict[str, Any]) -> None:
        qty = D(fill_result["qty"])
        px = D(fill_result["price"])
        fee = D(fill_result.get("fee", 0))
        side = order.side.upper()
        sym = order.symbol

        if side == "BUY":
            cost = qty * px + fee
            if cost > p.cash:
                # should have been gated; fail closed partial skip
                return
            p.cash -= cost
            p.fees_paid += fee
            pos = p.positions.get(sym) or PaperPosition(symbol=sym, strategy_slug=order.strategy_slug)
            new_qty = pos.quantity + qty
            if new_qty > 0:
                pos.avg_price = ((pos.avg_price * pos.quantity) + (px * qty)) / new_qty
            pos.quantity = new_qty
            pos.fees += fee
            pos.lots.append(PositionLot(quantity=qty, avg_price=px, fees=fee))
            pos.history.append({"event": "buy", "qty": str(qty), "price": str(px), "fee": str(fee)})
            p.positions[sym] = pos
        else:  # SELL long-only
            pos = p.positions.get(sym)
            if not pos or pos.quantity < qty:
                return
            proceeds = qty * px - fee
            # realized pnl
            pnl = (px - pos.avg_price) * qty - fee
            pos.realized_pnl += pnl
            p.realized_pnl += pnl
            p.cash += proceeds
            p.fees_paid += fee
            pos.quantity -= qty
            pos.fees += fee
            pos.history.append({"event": "sell", "qty": str(qty), "price": str(px), "pnl": str(pnl)})
            # reduce lots FIFO
            left = qty
            new_lots = []
            for lot in pos.lots:
                if left <= 0:
                    new_lots.append(lot)
                    continue
                if lot.quantity <= left:
                    left -= lot.quantity
                else:
                    lot.quantity -= left
                    left = Decimal("0")
                    new_lots.append(lot)
            pos.lots = new_lots
            if pos.quantity == 0:
                pos.avg_price = Decimal("0")
            p.positions[sym] = pos

        p.slippage_paid += D(fill_result.get("slippage", 0)) if "slippage" in fill_result else Decimal("0")
        p.trade_ledger.append({
            "ts": _now(),
            "order_id": order.id,
            "symbol": sym,
            "side": side,
            "qty": str(qty),
            "price": str(px),
            "fee": str(fee),
            "strategy_slug": order.strategy_slug,
            "paper_only": True,
        })
        p.audit("fill_applied", order_id=order.id, symbol=sym, qty=str(qty), price=str(px))

    def get_order(self, order_id: str) -> SimOrder | None:
        return self._orders.get(order_id)

    def list_orders(self, portfolio_id: str) -> list[SimOrder]:
        return [self._orders[oid] for oid in self._by_portfolio_orders.get(portfolio_id, []) if oid in self._orders]

    def list_positions(self, portfolio_id: str) -> list[dict[str, Any]]:
        p = self._require(portfolio_id)
        return [
            pos.to_public(p.marks.get(sym, pos.avg_price))
            for sym, pos in p.positions.items() if pos.quantity != 0
        ]

    def _require(self, portfolio_id: str) -> PaperPortfolio:
        p = self._portfolios.get(portfolio_id)
        if not p:
            raise PortfolioEngineError("NOT_FOUND", f"portfolio {portfolio_id} not found")
        return p
