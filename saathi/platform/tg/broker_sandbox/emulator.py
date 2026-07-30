"""M219 — Sandbox Broker Emulator.

Deterministic in-process broker simulator. Everything simulated.
No network. No real exchange. No credentials.
"""
from __future__ import annotations

import json
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from saathi.platform.tg.broker_sandbox.abstraction import (
    AbstractBrokerAdapter,
    Capability,
    Connection,
    ExecutionReport,
    MarketData,
    Order,
)
from saathi.platform.tg.broker_sandbox.models import (
    AuthMethodDeclared,
    ConnectionStatus,
    EmulatorOrderState,
)
from saathi.platform.tg.broker_sandbox.store import SandboxStore, _uid

D = Decimal
Q6 = Decimal("0.000001")
Q2 = Decimal("0.01")


def _q(v: Any, places: Decimal = Q6) -> Decimal:
    return D(str(v)).quantize(places, rounding=ROUND_HALF_UP)


class SandboxBrokerError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class SandboxEmulator:
    """Deterministic sandbox broker. Supports market/limit, partials, rejects, etc."""

    BROKER_ID = "sandbox.emulator"
    VALID_SYMBOLS = frozenset({"AAA", "BBB", "CCC", "SIM-USD", "PAPER"})

    def __init__(self, store: SandboxStore, *, seed: int = 42):
        self.store = store
        self.seed = seed

    def create_session(
        self,
        *,
        seed: int | None = None,
        latency_ms: int = 0,
        rate_limit_per_sec: int = 100,
        market_open: bool = True,
    ) -> dict[str, Any]:
        sid = _uid("esess")
        now = time.time()
        self.store.execute(
            """INSERT INTO bs_emulator_sessions(
                id, broker_id, seed, connected, market_open, latency_ms,
                rate_limit_per_sec, requests_window_json, failure_mode,
                clock_skew_sec, sequence_counter, detail_json, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                sid, self.BROKER_ID, seed if seed is not None else self.seed,
                1, 1 if market_open else 0, latency_ms, rate_limit_per_sec,
                json.dumps([]), "", 0, 0, json.dumps({"simulated": True}),
                now, now,
            ),
        )
        self.store.audit("emulator.session_created", subject=sid, detail={"seed": seed or self.seed})
        return self.get_session(sid)

    def get_session(self, session_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM bs_emulator_sessions WHERE id=?", (session_id,))
        if not row:
            raise SandboxBrokerError("SESSION_NOT_FOUND", session_id)
        return {
            "id": row["id"],
            "broker_id": row["broker_id"],
            "seed": row["seed"],
            "connected": bool(row["connected"]),
            "market_open": bool(row["market_open"]),
            "latency_ms": row["latency_ms"],
            "rate_limit_per_sec": row["rate_limit_per_sec"],
            "failure_mode": row["failure_mode"] or "",
            "clock_skew_sec": row["clock_skew_sec"],
            "sequence_counter": row["sequence_counter"],
            "simulated": True,
            "real_network": False,
            "paper_only": True,
        }

    def _bump_seq(self, session_id: str) -> int:
        row = self.store.fetchone(
            "SELECT sequence_counter FROM bs_emulator_sessions WHERE id=?", (session_id,)
        )
        if not row:
            raise SandboxBrokerError("SESSION_NOT_FOUND", session_id)
        seq = int(row["sequence_counter"]) + 1
        self.store.execute(
            "UPDATE bs_emulator_sessions SET sequence_counter=?, updated_at=? WHERE id=?",
            (seq, time.time(), session_id),
        )
        return seq

    def _check_rate(self, session: dict[str, Any]) -> None:
        # Deterministic rate-limit simulation via counter in detail — simplified window check
        limit = int(session["rate_limit_per_sec"])
        if limit <= 0:
            raise SandboxBrokerError("RATE_LIMITED", "Rate limit set to zero")
        # Use sequence as proxy: if failure_mode is RATE_LIMIT, always reject
        if session.get("failure_mode") == "RATE_LIMIT":
            raise SandboxBrokerError("RATE_LIMITED", "Emulator rate limit engaged")

    def set_failure_mode(self, session_id: str, mode: str) -> dict[str, Any]:
        self.store.execute(
            "UPDATE bs_emulator_sessions SET failure_mode=?, updated_at=? WHERE id=?",
            (mode, time.time(), session_id),
        )
        return self.get_session(session_id)

    def set_market_open(self, session_id: str, open_: bool) -> dict[str, Any]:
        self.store.execute(
            "UPDATE bs_emulator_sessions SET market_open=?, updated_at=? WHERE id=?",
            (1 if open_ else 0, time.time(), session_id),
        )
        return self.get_session(session_id)

    def set_connected(self, session_id: str, connected: bool) -> dict[str, Any]:
        self.store.execute(
            "UPDATE bs_emulator_sessions SET connected=?, updated_at=? WHERE id=?",
            (1 if connected else 0, time.time(), session_id),
        )
        return self.get_session(session_id)

    def set_latency(self, session_id: str, latency_ms: int) -> dict[str, Any]:
        self.store.execute(
            "UPDATE bs_emulator_sessions SET latency_ms=?, updated_at=? WHERE id=?",
            (int(latency_ms), time.time(), session_id),
        )
        return self.get_session(session_id)

    def set_clock_skew(self, session_id: str, skew_sec: float) -> dict[str, Any]:
        self.store.execute(
            "UPDATE bs_emulator_sessions SET clock_skew_sec=?, updated_at=? WHERE id=?",
            (float(skew_sec), time.time(), session_id),
        )
        return self.get_session(session_id)

    def place_order(
        self,
        session_id: str,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str,
        limit_price: str | None = None,
        stop_price: str | None = None,
        client_order_id: str = "",
        market: MarketData | None = None,
        partial_fill_ratio: str | None = None,
    ) -> dict[str, Any]:
        session = self.get_session(session_id)
        now = time.time() + float(session["clock_skew_sec"])

        if not session["connected"]:
            raise SandboxBrokerError("DISCONNECTED", "Emulator session is disconnected")
        if session["failure_mode"] == "TIMEOUT":
            oid = _uid("eord")
            seq = self._bump_seq(session_id)
            self.store.execute(
                """INSERT INTO bs_emulator_orders(
                    id, session_id, client_order_id, symbol, side, order_type, quantity,
                    limit_price, stop_price, filled_qty, avg_price, state, reject_reason,
                    sequence, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    oid, session_id, client_order_id, symbol, side.upper(), order_type.upper(),
                    str(quantity), limit_price, stop_price, "0", "0",
                    EmulatorOrderState.TIMED_OUT.value, "SIMULATED_TIMEOUT",
                    seq, now, now,
                ),
            )
            return self.get_order(oid)

        if session["failure_mode"] == "NETWORK_LOSS":
            raise SandboxBrokerError("NETWORK_LOSS", "Simulated network loss")
        if session["failure_mode"] == "BROKER_OUTAGE":
            raise SandboxBrokerError("BROKER_OUTAGE", "Simulated broker outage")

        try:
            self._check_rate(session)
        except SandboxBrokerError:
            oid = _uid("eord")
            seq = self._bump_seq(session_id)
            self.store.execute(
                """INSERT INTO bs_emulator_orders(
                    id, session_id, client_order_id, symbol, side, order_type, quantity,
                    limit_price, stop_price, filled_qty, avg_price, state, reject_reason,
                    sequence, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    oid, session_id, client_order_id, symbol, side.upper(), order_type.upper(),
                    str(quantity), limit_price, stop_price, "0", "0",
                    EmulatorOrderState.REJECTED.value, "RATE_LIMITED",
                    seq, now, now,
                ),
            )
            return self.get_order(oid)

        if not session["market_open"] or session["failure_mode"] == "MARKET_CLOSED":
            oid = _uid("eord")
            seq = self._bump_seq(session_id)
            self.store.execute(
                """INSERT INTO bs_emulator_orders(
                    id, session_id, client_order_id, symbol, side, order_type, quantity,
                    limit_price, stop_price, filled_qty, avg_price, state, reject_reason,
                    sequence, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    oid, session_id, client_order_id, symbol, side.upper(), order_type.upper(),
                    str(quantity), limit_price, stop_price, "0", "0",
                    EmulatorOrderState.REJECTED.value, "MARKET_CLOSED",
                    seq, now, now,
                ),
            )
            return self.get_order(oid)

        sym = symbol.upper()
        if session["failure_mode"] == "INVALID_SYMBOL" or sym not in self.VALID_SYMBOLS:
            if sym not in self.VALID_SYMBOLS or session["failure_mode"] == "INVALID_SYMBOL":
                oid = _uid("eord")
                seq = self._bump_seq(session_id)
                self.store.execute(
                    """INSERT INTO bs_emulator_orders(
                        id, session_id, client_order_id, symbol, side, order_type, quantity,
                        limit_price, stop_price, filled_qty, avg_price, state, reject_reason,
                        sequence, created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        oid, session_id, client_order_id, symbol, side.upper(), order_type.upper(),
                        str(quantity), limit_price, stop_price, "0", "0",
                        EmulatorOrderState.REJECTED.value, "INVALID_SYMBOL",
                        seq, now, now,
                    ),
                )
                return self.get_order(oid)

        if session["failure_mode"] == "REJECT":
            oid = _uid("eord")
            seq = self._bump_seq(session_id)
            self.store.execute(
                """INSERT INTO bs_emulator_orders(
                    id, session_id, client_order_id, symbol, side, order_type, quantity,
                    limit_price, stop_price, filled_qty, avg_price, state, reject_reason,
                    sequence, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    oid, session_id, client_order_id, symbol, side.upper(), order_type.upper(),
                    str(quantity), limit_price, stop_price, "0", "0",
                    EmulatorOrderState.REJECTED.value, "FORCED_REJECT",
                    seq, now, now,
                ),
            )
            return self.get_order(oid)

        qty = _q(quantity)
        if qty <= 0:
            raise SandboxBrokerError("INVALID_QUANTITY", "quantity must be positive")

        ot = order_type.upper()
        if ot not in ("MARKET", "LIMIT", "STOP"):
            raise SandboxBrokerError("UNSUPPORTED_ORDER_TYPE", ot)

        # Market price
        if market is None:
            # Deterministic price from seed + symbol
            base = 100 + (self.seed % 17) + (sum(ord(c) for c in sym) % 10)
            md = MarketData(
                symbol=sym,
                bid=str(base - 1),
                ask=str(base + 1),
                last=str(base),
                ts=now,
            )
        else:
            md = market

        fill_price = _q(md.ask if side.upper() == "BUY" else md.bid, Q2)
        if ot == "LIMIT" and limit_price is not None:
            lp = _q(limit_price, Q2)
            if side.upper() == "BUY" and lp < _q(md.ask, Q2):
                # Resting — leave open (no fill)
                oid = _uid("eord")
                seq = self._bump_seq(session_id)
                self.store.execute(
                    """INSERT INTO bs_emulator_orders(
                        id, session_id, client_order_id, symbol, side, order_type, quantity,
                        limit_price, stop_price, filled_qty, avg_price, state, reject_reason,
                        sequence, created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        oid, session_id, client_order_id, sym, side.upper(), ot,
                        str(qty), str(lp), stop_price, "0", "0",
                        EmulatorOrderState.OPEN.value, "",
                        seq, now, now,
                    ),
                )
                return self.get_order(oid)
            if side.upper() == "SELL" and lp > _q(md.bid, Q2):
                oid = _uid("eord")
                seq = self._bump_seq(session_id)
                self.store.execute(
                    """INSERT INTO bs_emulator_orders(
                        id, session_id, client_order_id, symbol, side, order_type, quantity,
                        limit_price, stop_price, filled_qty, avg_price, state, reject_reason,
                        sequence, created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        oid, session_id, client_order_id, sym, side.upper(), ot,
                        str(qty), str(lp), stop_price, "0", "0",
                        EmulatorOrderState.OPEN.value, "",
                        seq, now, now,
                    ),
                )
                return self.get_order(oid)
            fill_price = lp

        # Partial fill simulation
        do_partial = (
            session["failure_mode"] == "PARTIAL_FILL"
            or (partial_fill_ratio is not None and _q(partial_fill_ratio) < 1)
        )
        if do_partial:
            ratio = _q(partial_fill_ratio or "0.5")
            fill_qty = _q(qty * ratio)
            if fill_qty <= 0:
                fill_qty = _q(qty * D("0.5"))
            state = EmulatorOrderState.PARTIALLY_FILLED
        else:
            fill_qty = qty
            state = EmulatorOrderState.FILLED

        oid = _uid("eord")
        seq = self._bump_seq(session_id)
        self.store.execute(
            """INSERT INTO bs_emulator_orders(
                id, session_id, client_order_id, symbol, side, order_type, quantity,
                limit_price, stop_price, filled_qty, avg_price, state, reject_reason,
                sequence, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                oid, session_id, client_order_id, sym, side.upper(), ot,
                str(qty), limit_price, stop_price, str(fill_qty), str(fill_price),
                state.value, "",
                seq, now, now,
            ),
        )
        fid = _uid("efill")
        fseq = self._bump_seq(session_id)
        is_late = 1 if session["failure_mode"] == "LATE_FILLS" else 0
        is_dup = 1 if session["failure_mode"] == "DUPLICATE_FILLS" else 0
        self.store.execute(
            """INSERT INTO bs_emulator_fills(
                id, order_id, session_id, quantity, price, is_duplicate, is_late,
                sequence, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (fid, oid, session_id, str(fill_qty), str(fill_price), is_dup, is_late, fseq, now),
        )
        if is_dup:
            fid2 = _uid("efill")
            fseq2 = self._bump_seq(session_id)
            self.store.execute(
                """INSERT INTO bs_emulator_fills(
                    id, order_id, session_id, quantity, price, is_duplicate, is_late,
                    sequence, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (fid2, oid, session_id, str(fill_qty), str(fill_price), 1, 0, fseq2, now),
            )

        self.store.audit(
            "emulator.order_placed",
            subject=oid,
            detail={"state": state.value, "symbol": sym, "simulated": True},
        )
        return self.get_order(oid)

    def get_order(self, order_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM bs_emulator_orders WHERE id=?", (order_id,))
        if not row:
            raise SandboxBrokerError("ORDER_NOT_FOUND", order_id)
        fills = self.store.fetchall(
            "SELECT * FROM bs_emulator_fills WHERE order_id=? ORDER BY sequence",
            (order_id,),
        )
        return {
            "order_id": row["id"],
            "session_id": row["session_id"],
            "client_order_id": row["client_order_id"],
            "symbol": row["symbol"],
            "side": row["side"],
            "order_type": row["order_type"],
            "quantity": row["quantity"],
            "limit_price": row["limit_price"],
            "stop_price": row["stop_price"],
            "filled_qty": row["filled_qty"],
            "avg_price": row["avg_price"],
            "state": row["state"],
            "reject_reason": row["reject_reason"],
            "sequence": row["sequence"],
            "fills": [
                {
                    "id": f["id"],
                    "quantity": f["quantity"],
                    "price": f["price"],
                    "is_duplicate": bool(f["is_duplicate"]),
                    "is_late": bool(f["is_late"]),
                    "sequence": f["sequence"],
                    "simulated": True,
                }
                for f in fills
            ],
            "simulated": True,
            "paper_only": True,
            "live_order": False,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_orders(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.store.fetchall(
            "SELECT id FROM bs_emulator_orders WHERE session_id=? ORDER BY sequence",
            (session_id,),
        )
        return [self.get_order(r["id"]) for r in rows]

    def execution_report(self, order_id: str) -> dict[str, Any]:
        o = self.get_order(order_id)
        remaining = str(_q(o["quantity"]) - _q(o["filled_qty"]))
        return ExecutionReport(
            report_id=_uid("erpt"),
            order_id=order_id,
            state=o["state"],
            filled_qty=o["filled_qty"],
            remaining_qty=remaining,
            avg_price=o["avg_price"],
            reason=o["reject_reason"],
            simulated=True,
        ).to_public()


class SandboxEmulatorAdapter(AbstractBrokerAdapter):
    """Adapter wrapping the emulator — only sandbox surface that 'executes'."""

    def __init__(self, emulator: SandboxEmulator):
        super().__init__(SandboxEmulator.BROKER_ID)
        self.emulator = emulator

    def capabilities(self) -> Capability:
        return Capability(
            broker_id=self._broker_id,
            supported_assets=list(SandboxEmulator.VALID_SYMBOLS),
            paper_support=True,
            market_orders=True,
            limit_orders=True,
            stop_orders=True,
            margin=False,
            options=False,
            futures=False,
            crypto=False,
            equities=True,
            rate_limits={"requests_per_sec": 100},
            authentication_method=AuthMethodDeclared.SANDBOX_EMULATOR,
            streaming_support=False,
            order_events=True,
            time_zones=["UTC"],
            status=ConnectionStatus.SANDBOX_ONLY,
        )

    def connection(self) -> Connection:
        return Connection(
            broker_id=self._broker_id,
            status=ConnectionStatus.SANDBOX_ONLY,
            endpoint="in-process://sandbox.emulator",
            real_network=False,
        )

    def connect(self, *args: Any, **kwargs: Any) -> Connection:
        # Emulator "connect" is in-process only
        return self.connection()


__all__ = [
    "SandboxEmulator",
    "SandboxEmulatorAdapter",
    "SandboxBrokerError",
]
