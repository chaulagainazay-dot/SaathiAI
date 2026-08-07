"""Matching engine — market/limit/stop with partial fills, slippage, fees."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.paper_simulation.errors import PaperSimError
from saathi.platform.tg.paper_simulation.models import (
    AUTHORITY_VALUES,
    DEFAULT_FEE_BPS,
    DEFAULT_LATENCY_MS,
    DEFAULT_SLIPPAGE_BPS,
    MAX_OPEN_ORDERS,
    OrderSide,
    OrderStatus,
    OrderType,
    SessionState,
    TimeInForce,
)
from saathi.platform.tg.paper_simulation.storage import PaperSimStore, evidence_hash, _uid


class MatchingEngine:
    def __init__(
        self,
        store: PaperSimStore,
        exchange: Any,
        ledger: Any,
        risk: Any,
        *,
        fee_bps: float = DEFAULT_FEE_BPS,
        slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
        default_latency_ms: int = DEFAULT_LATENCY_MS,
    ):
        self.store = store
        self.exchange = exchange
        self.ledger = ledger
        self.risk = risk
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self.default_latency_ms = default_latency_ms

    def submit_order(
        self,
        portfolio_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        *,
        limit_price: float | None = None,
        stop_price: float | None = None,
        tif: str = TimeInForce.DAY.value,
        actor: str = "system",
        latency_ms: int | None = None,
    ) -> dict[str, Any]:
        # Kill switch
        if self.risk.is_halted(portfolio_id):
            raise PaperSimError("KILL_SWITCH_ACTIVE", "Orders blocked by kill switch")

        open_count = self.store.fetchone(
            "SELECT COUNT(*) AS c FROM ps_orders WHERE portfolio_id=? AND status IN ('NEW','ACCEPTED','PARTIALLY_FILLED')",
            (portfolio_id,),
        )
        if (open_count or {}).get("c", 0) >= MAX_OPEN_ORDERS:
            raise PaperSimError("MAX_OPEN_ORDERS", f"Exceeds {MAX_OPEN_ORDERS}")

        symbol = symbol.upper()
        side = side.upper()
        order_type = order_type.upper()
        tif = tif.upper()
        if side not in (OrderSide.BUY.value, OrderSide.SELL.value):
            raise PaperSimError("INVALID_SIDE", side)
        if order_type not in {e.value for e in OrderType}:
            raise PaperSimError("INVALID_ORDER_TYPE", order_type)
        if quantity <= 0:
            raise PaperSimError("INVALID_QUANTITY", "quantity must be positive")

        sess = self.exchange.get_session(symbol)
        if not sess.get("ok"):
            raise PaperSimError("UNKNOWN_SYMBOL", symbol)
        if sess.get("state") in (SessionState.CLOSED.value, SessionState.HALTED.value):
            raise PaperSimError("SESSION_NOT_OPEN", f"session={sess.get('state')}")

        # Risk pre-trade
        pre = self.risk.pre_trade_check(portfolio_id, symbol, side, quantity, limit_price or stop_price)
        if not pre.get("ok"):
            raise PaperSimError(pre.get("code", "RISK_REJECT"), pre.get("message", "risk reject"), detail=pre)

        order_id = _uid("ord")
        now = time.time()
        lat = int(latency_ms if latency_ms is not None else self.default_latency_ms)
        self.store.execute(
            "INSERT INTO ps_orders(order_id, portfolio_id, symbol, side, order_type, quantity, filled_qty, "
            "limit_price, stop_price, tif, status, latency_ms, created_at, updated_at, accepted_at) "
            "VALUES(?,?,?,?,?,?,0,?,?,?,?,?,?,?,?)",
            (
                order_id, portfolio_id, symbol, side, order_type, float(quantity),
                limit_price, stop_price, tif, OrderStatus.ACCEPTED.value, lat, now, now, now,
            ),
        )
        self.store.audit("order.submitted", actor=actor, subject=order_id, detail={
            "symbol": symbol, "side": side, "type": order_type, "qty": quantity, "simulated": True,
        })

        # Immediate match attempt for MARKET / triggered orders
        result = self._try_match(order_id)
        order = self.store.fetchone("SELECT * FROM ps_orders WHERE order_id=?", (order_id,))
        return {
            "ok": True,
            "order": order,
            "match": result,
            "simulated": True,
            "real_exchange": False,
            **AUTHORITY_VALUES,
        }

    def cancel_order(self, order_id: str, *, actor: str = "system") -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM ps_orders WHERE order_id=?", (order_id,))
        if not row:
            raise PaperSimError("ORDER_NOT_FOUND", order_id)
        if row["status"] in (
            OrderStatus.FILLED.value, OrderStatus.CANCELLED.value,
            OrderStatus.REJECTED.value, OrderStatus.EXPIRED.value,
        ):
            raise PaperSimError("ORDER_TERMINAL", f"status={row['status']}")
        self.store.execute(
            "UPDATE ps_orders SET status=?, updated_at=?, finished_at=? WHERE order_id=?",
            (OrderStatus.CANCELLED.value, time.time(), time.time(), order_id),
        )
        self.store.audit("order.cancelled", actor=actor, subject=order_id, detail={})
        return {"ok": True, "order_id": order_id, "status": OrderStatus.CANCELLED.value, **AUTHORITY_VALUES}

    def process_tick(self, symbol: str) -> dict[str, Any]:
        """Match resting orders against latest tick for symbol."""
        open_orders = self.store.fetchall(
            "SELECT order_id FROM ps_orders WHERE symbol=? AND status IN ('ACCEPTED','PARTIALLY_FILLED') "
            "ORDER BY created_at ASC",
            (symbol.upper(),),
        )
        results = []
        for o in open_orders:
            results.append(self._try_match(o["order_id"]))
        return {"ok": True, "symbol": symbol, "processed": len(results), "results": results, **AUTHORITY_VALUES}

    def _try_match(self, order_id: str) -> dict[str, Any]:
        order = self.store.fetchone("SELECT * FROM ps_orders WHERE order_id=?", (order_id,))
        if not order:
            return {"filled": False, "reason": "not_found"}
        if order["status"] in (
            OrderStatus.FILLED.value, OrderStatus.CANCELLED.value,
            OrderStatus.REJECTED.value, OrderStatus.EXPIRED.value, OrderStatus.STOPPED.value,
        ):
            return {"filled": False, "reason": f"terminal:{order['status']}"}

        tick = self.exchange.latest_tick(order["symbol"])
        if not tick:
            return {"filled": False, "reason": "no_tick"}
        if tick.get("session_state") not in (SessionState.OPEN.value, SessionState.PRE_OPEN.value):
            if order["order_type"] == OrderType.MARKET.value:
                self._reject(order_id, "SESSION_NOT_OPEN")
                return {"filled": False, "reason": "SESSION_NOT_OPEN"}
            return {"filled": False, "reason": "session_not_open_resting"}

        remaining = float(order["quantity"]) - float(order["filled_qty"])
        if remaining <= 0:
            return {"filled": False, "reason": "fully_filled"}

        side = order["side"]
        otype = order["order_type"]
        bid, ask, last = float(tick["bid"]), float(tick["ask"]), float(tick["last"])
        vol = float(tick["volume"])

        # Stop trigger
        if otype in (OrderType.STOP.value, OrderType.STOP_LIMIT.value):
            sp = float(order["stop_price"] or 0)
            triggered = (side == OrderSide.BUY.value and last >= sp) or (
                side == OrderSide.SELL.value and last <= sp
            )
            if not triggered:
                return {"filled": False, "reason": "stop_not_triggered"}
            if otype == OrderType.STOP.value:
                otype = OrderType.MARKET.value  # convert
            else:
                otype = OrderType.LIMIT.value

        # Determine fill price eligibility
        fill_price = None
        if otype == OrderType.MARKET.value:
            ref = ask if side == OrderSide.BUY.value else bid
            slip = ref * (self.slippage_bps / 10000.0)
            fill_price = ref + slip if side == OrderSide.BUY.value else ref - slip
        elif otype == OrderType.LIMIT.value:
            lp = float(order["limit_price"] or 0)
            if side == OrderSide.BUY.value:
                if ask <= lp:
                    fill_price = min(ask, lp)
                else:
                    return self._tif_no_fill(order, "limit_not_marketable")
            else:
                if bid >= lp:
                    fill_price = max(bid, lp)
                else:
                    return self._tif_no_fill(order, "limit_not_marketable")
        else:
            return {"filled": False, "reason": f"unhandled_type:{otype}"}

        # Liquidity cap: 25% of volume
        max_liq = max(vol * 0.25, 1.0)
        fill_qty = min(remaining, max_liq)

        tif = order["tif"]
        if tif == TimeInForce.FOK.value and fill_qty + 1e-12 < remaining:
            self._reject(order_id, "FOK_INCOMPLETE")
            return {"filled": False, "reason": "FOK_INCOMPLETE"}
        if tif == TimeInForce.IOC.value and fill_qty <= 0:
            self.store.execute(
                "UPDATE ps_orders SET status=?, updated_at=?, finished_at=? WHERE order_id=?",
                (OrderStatus.CANCELLED.value, time.time(), time.time(), order_id),
            )
            return {"filled": False, "reason": "IOC_NO_FILL"}

        # Apply fill via ledger
        fee = abs(fill_qty * fill_price) * (self.fee_bps / 10000.0)
        fill_id = _uid("fill")
        self.store.execute(
            "INSERT INTO ps_fills(fill_id, order_id, portfolio_id, symbol, side, quantity, price, fee, "
            "slippage_bps, liquidity_flag, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                fill_id, order_id, order["portfolio_id"], order["symbol"], side,
                fill_qty, fill_price, fee, self.slippage_bps, "SIMULATED", time.time(),
            ),
        )
        self.ledger.apply_fill(
            order["portfolio_id"], order["symbol"], side, fill_qty, fill_price, fee,
            ref=fill_id,
        )
        new_filled = float(order["filled_qty"]) + fill_qty
        status = OrderStatus.FILLED.value if new_filled + 1e-9 >= float(order["quantity"]) else OrderStatus.PARTIALLY_FILLED.value
        finished = time.time() if status == OrderStatus.FILLED.value else None
        self.store.execute(
            "UPDATE ps_orders SET filled_qty=?, status=?, updated_at=?, finished_at=COALESCE(?, finished_at) WHERE order_id=?",
            (new_filled, status, time.time(), finished, order_id),
        )
        if tif == TimeInForce.IOC.value and status == OrderStatus.PARTIALLY_FILLED.value:
            self.store.execute(
                "UPDATE ps_orders SET status=?, finished_at=?, updated_at=? WHERE order_id=?",
                (OrderStatus.CANCELLED.value, time.time(), time.time(), order_id),
            )
            status = OrderStatus.CANCELLED.value

        self.store.audit("order.fill", subject=order_id, detail={
            "fill_id": fill_id, "qty": fill_qty, "price": fill_price, "fee": fee,
        })
        self.risk.post_trade_check(order["portfolio_id"])
        return {
            "filled": True,
            "fill_id": fill_id,
            "quantity": fill_qty,
            "price": fill_price,
            "fee": fee,
            "status": status,
            "latency_ms": order["latency_ms"],
            "simulated": True,
        }

    def _tif_no_fill(self, order: dict, reason: str) -> dict[str, Any]:
        if order["tif"] == TimeInForce.IOC.value:
            self.store.execute(
                "UPDATE ps_orders SET status=?, updated_at=?, finished_at=? WHERE order_id=?",
                (OrderStatus.CANCELLED.value, time.time(), time.time(), order["order_id"]),
            )
        elif order["tif"] == TimeInForce.FOK.value:
            self._reject(order["order_id"], "FOK_NOT_MARKETABLE")
        return {"filled": False, "reason": reason}

    def _reject(self, order_id: str, reason: str) -> None:
        self.store.execute(
            "UPDATE ps_orders SET status=?, reject_reason=?, updated_at=?, finished_at=? WHERE order_id=?",
            (OrderStatus.REJECTED.value, reason, time.time(), time.time(), order_id),
        )

    def list_orders(self, portfolio_id: str, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        if status:
            rows = self.store.fetchall(
                "SELECT * FROM ps_orders WHERE portfolio_id=? AND status=? ORDER BY created_at DESC LIMIT ?",
                (portfolio_id, status, limit),
            )
        else:
            rows = self.store.fetchall(
                "SELECT * FROM ps_orders WHERE portfolio_id=? ORDER BY created_at DESC LIMIT ?",
                (portfolio_id, limit),
            )
        return {"ok": True, "count": len(rows), "orders": rows, **AUTHORITY_VALUES}

    def list_fills(self, portfolio_id: str, limit: int = 100) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT * FROM ps_fills WHERE portfolio_id=? ORDER BY created_at DESC LIMIT ?",
            (portfolio_id, limit),
        )
        return {"ok": True, "count": len(rows), "fills": rows, "audit": True, **AUTHORITY_VALUES}
