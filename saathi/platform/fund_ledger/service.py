"""PortfolioLedgerService — single portfolio authority boundary (paper).

Mutation surface is event-based only:
  record_deposit / record_withdrawal_sim / record_fill / record_fee /
  record_adjustment / record_mark / reverse_event

No set_position / set_nav / set_pnl (except test fixtures via inject_test_state).
"""
from __future__ import annotations

import time as _time
import uuid
from decimal import Decimal
from typing import Any

from saathi.platform.fund_ledger.money import D, q_money, q_price, q_qty
from saathi.platform.fund_ledger.models import (
    EventType,
    Fund,
    LedgerEvent,
    Security,
    ValuationSnapshot,
    new_event_id,
)
from saathi.platform.fund_ledger.reducer import LedgerError, reduce_events, state_hash
from saathi.platform.fund_ledger.reconcile import reconcile_fills
from saathi.platform.fund_ledger.store import DuplicateEventError, FundLedgerStore

ENGINE_VERSION = "fund-ledger/1.0.0"


class PortfolioLedgerService:
    """Canonical paper fund ledger writer + reader."""

    def __init__(self, store: FundLedgerStore | None = None):
        self.store = store or FundLedgerStore()

    # ── fund / security master ───────────────────────────────────────────
    def create_fund(
        self,
        *,
        fund_id: str | None = None,
        name: str = "SaathiOS Paper Fund",
        base_currency: str = "USD",
        opening_cash: Any = "0",
        actor: str = "system",
    ) -> dict:
        fid = fund_id or f"fund_{uuid.uuid4().hex[:12]}"
        if self.store.get_fund(fid):
            raise LedgerError(f"fund exists: {fid}")
        fund = Fund(fund_id=fid, name=name, base_currency=base_currency.upper(), environment="PAPER")
        self.store.create_fund(fund)
        cash = D(opening_cash)
        if cash < 0:
            raise LedgerError("opening cash must be non-negative")
        if cash > 0:
            self.record_deposit(fid, amount=cash, actor=actor, reason="opening_balance")
        return fund.to_public()

    def register_security(
        self,
        *,
        security_id: str | None = None,
        symbol: str,
        venue: str = "PAPER",
        asset_class: str = "EQUITY",
        currency: str = "USD",
    ) -> dict:
        sid = security_id or f"sec_{symbol.upper()}_{venue}"
        sec = Security(
            security_id=sid,
            symbol=symbol.upper(),
            venue=venue,
            asset_class=asset_class,
            currency=currency.upper(),
        )
        self.store.upsert_security(sec)
        return sec.to_public()

    # ── mutations (event append only) ────────────────────────────────────
    def record_deposit(
        self,
        fund_id: str,
        *,
        amount: Any,
        actor: str = "system",
        reason: str = "deposit",
        idempotency_key: str = "",
        ts: float | None = None,
    ) -> dict:
        amt = q_money(amount)
        if amt <= 0:
            raise LedgerError("deposit must be positive")
        return self._append(
            fund_id,
            EventType.DEPOSIT,
            cash_delta=amt,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key or f"dep:{fund_id}:{amt}:{reason}",
            ts=ts,
        )

    def record_withdrawal_sim(
        self,
        fund_id: str,
        *,
        amount: Any,
        actor: str = "system",
        reason: str = "paper_withdrawal",
        idempotency_key: str = "",
        ts: float | None = None,
    ) -> dict:
        """Paper-only simulated withdrawal — not a real transfer."""
        amt = q_money(amount)
        if amt <= 0:
            raise LedgerError("withdrawal amount must be positive")
        return self._append(
            fund_id,
            EventType.WITHDRAWAL_SIM,
            cash_delta=-amt,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key or f"wd:{fund_id}:{amt}:{reason}",
            ts=ts,
        )

    def record_fill(
        self,
        fund_id: str,
        *,
        side: str,
        security_id: str,
        symbol: str = "",
        quantity: Any,
        price: Any,
        fee: Any = "0",
        fill_ref: str = "",
        order_ref: str = "",
        actor: str = "paper_oms",
        source: str = "paper_fill",
        idempotency_key: str = "",
        ts: float | None = None,
        currency: str = "USD",
    ) -> dict:
        """Ingest a canonical accepted paper fill. Agents cannot call arbitrary set_*."""
        side_u = side.upper()
        if side_u not in ("BUY", "SELL"):
            raise LedgerError("side must be BUY or SELL")
        qty = q_qty(quantity)
        px = q_price(price)
        fee_d = q_money(fee)
        if qty <= 0:
            raise LedgerError("quantity must be positive")
        et = EventType.BUY_FILL if side_u == "BUY" else EventType.SELL_FILL
        fill_id = fill_ref or new_event_id("fill_")
        return self._append(
            fund_id,
            et,
            security_id=security_id,
            symbol=symbol or security_id,
            side=side_u,
            quantity=qty,
            price=px,
            fee=fee_d,
            fill_ref=fill_id,
            order_ref=order_ref,
            actor=actor,
            source=source,
            currency=currency,
            idempotency_key=idempotency_key or f"fill:{fill_id}",
            ts=ts,
            reason=f"paper_{side_u.lower()}_fill",
        )

    def record_fee(
        self,
        fund_id: str,
        *,
        amount: Any,
        actor: str = "system",
        reason: str = "fee",
        idempotency_key: str = "",
        ts: float | None = None,
    ) -> dict:
        amt = q_money(amount)
        if amt <= 0:
            raise LedgerError("fee must be positive")
        return self._append(
            fund_id,
            EventType.FEE,
            fee=amt,
            cash_delta=-amt,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key or f"fee:{fund_id}:{amt}:{reason}",
            ts=ts,
        )

    def record_adjustment(
        self,
        fund_id: str,
        *,
        cash_delta: Any,
        actor: str = "system",
        reason: str,
        idempotency_key: str = "",
        ts: float | None = None,
    ) -> dict:
        if not reason:
            raise LedgerError("adjustment requires reason")
        return self._append(
            fund_id,
            EventType.ADJUSTMENT,
            cash_delta=q_money(cash_delta),
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key or f"adj:{fund_id}:{reason}:{cash_delta}",
            ts=ts,
        )

    def record_mark(
        self,
        fund_id: str,
        *,
        security_id: str,
        price: Any,
        source: str = "fixture",
        symbol: str = "",
        max_age_seconds: float = 86400.0,
        ts: float | None = None,
        idempotency_key: str = "",
    ) -> dict:
        return self._append(
            fund_id,
            EventType.MARK,
            security_id=security_id,
            symbol=symbol,
            price=q_price(price),
            source=source,
            actor="mark_service",
            reason="valuation_mark",
            payload={"max_age_seconds": max_age_seconds},
            idempotency_key=idempotency_key
            or f"mark:{fund_id}:{security_id}:{ts or _time.time()}:{price}",
            ts=ts,
        )

    def reverse_event(
        self,
        fund_id: str,
        *,
        target_event_id: str,
        actor: str = "system",
        reason: str = "reversal",
    ) -> dict:
        """Append a CORRECTION that reverses cash impact of a non-fill event.

        Fill reversals must be explicit opposite fills (audit trail). This method
        only auto-reverses pure cash events (DEPOSIT/WITHDRAWAL_SIM/FEE/ADJUSTMENT/DIVIDEND).
        """
        events = self.store.list_events(fund_id)
        target = next((e for e in events if e.event_id == target_event_id), None)
        if not target:
            raise LedgerError(f"event not found: {target_event_id}")
        et = target.event_type if isinstance(target.event_type, EventType) else EventType(target.event_type)
        if et in (EventType.BUY_FILL, EventType.SELL_FILL):
            raise LedgerError("fill reversal requires explicit opposite fill + reason; not silent delete")
        inv_cash = -D(target.cash_delta)
        if et == EventType.FEE and inv_cash == 0:
            inv_cash = D(target.fee)
        return self._append(
            fund_id,
            EventType.CORRECTION,
            cash_delta=q_money(inv_cash),
            actor=actor,
            reason=reason,
            reverses_event_id=target_event_id,
            idempotency_key=f"rev:{target_event_id}",
            source="correction",
        )

    def _append(self, fund_id: str, event_type: EventType, **kwargs) -> dict:
        fund = self.store.get_fund(fund_id)
        if not fund:
            raise LedgerError(f"unknown fund: {fund_id}")
        if fund.environment != "PAPER":
            raise LedgerError("fund environment must be PAPER")
        ts = kwargs.pop("ts", None)
        event = LedgerEvent(
            event_id=new_event_id(),
            fund_id=fund_id,
            event_type=event_type,
            ts=float(ts if ts is not None else _time.time()),
            actor=kwargs.pop("actor", "system"),
            source=kwargs.pop("source", "paper"),
            security_id=kwargs.pop("security_id", ""),
            symbol=kwargs.pop("symbol", ""),
            side=kwargs.pop("side", ""),
            quantity=D(kwargs.pop("quantity", 0)),
            price=D(kwargs.pop("price", 0)),
            fee=D(kwargs.pop("fee", 0)),
            cash_delta=D(kwargs.pop("cash_delta", 0)),
            currency=kwargs.pop("currency", fund.base_currency),
            fill_ref=kwargs.pop("fill_ref", ""),
            order_ref=kwargs.pop("order_ref", ""),
            reason=kwargs.pop("reason", ""),
            reverses_event_id=kwargs.pop("reverses_event_id", ""),
            payload=dict(kwargs.pop("payload", {}) or {}),
            idempotency_key=kwargs.pop("idempotency_key", "") or new_event_id("idem_"),
        )
        if kwargs:
            raise LedgerError(f"unknown fields: {sorted(kwargs)}")
        # Idempotent path: if key already stored, return without re-validate mutation
        existing = self.store.list_events(fund_id)
        for prior in existing:
            if (prior.idempotency_key or prior.event_id) == event.idempotency_key:
                state = self.get_state(fund_id)
                return {
                    "status": "duplicate",
                    "event": prior.to_record(),
                    "state": state,
                    "engine_version": ENGINE_VERSION,
                }
        # validate by dry-run reduce including new event
        try:
            reduce_events(existing + [event], fund_id=fund_id, currency=fund.base_currency)
        except LedgerError:
            raise
        status, stored = self.store.append_event(event)
        state = self.get_state(fund_id)
        return {
            "status": status,
            "event": stored.to_record(),
            "state": state,
            "engine_version": ENGINE_VERSION,
        }

    # ── readers ──────────────────────────────────────────────────────────
    def get_state(self, fund_id: str, *, now: float | None = None) -> dict:
        fund = self.store.get_fund(fund_id)
        if not fund:
            raise LedgerError(f"unknown fund: {fund_id}")
        events = self.store.list_events(fund_id)
        state = reduce_events(events, fund_id=fund_id, currency=fund.base_currency, now=now)
        return state.to_public()

    def get_cash(self, fund_id: str) -> dict:
        s = self.get_state(fund_id)
        return {"fund_id": fund_id, "cash": s["cash"], "currency": s["currency"], "mode": "PAPER"}

    def get_positions(self, fund_id: str) -> list[dict]:
        return self.get_state(fund_id)["positions"]

    def get_lots(self, fund_id: str) -> list[dict]:
        return self.get_state(fund_id)["open_lots"]

    def get_nav(self, fund_id: str) -> dict:
        s = self.get_state(fund_id)
        return {
            "fund_id": fund_id,
            "nav": s["nav"],
            "paper_nav": s["paper_nav"],
            "cash": s["cash"],
            "positions_value": s["positions_value"],
            "currency": s["currency"],
            "mode": "PAPER",
        }

    def get_pnl(self, fund_id: str) -> dict:
        s = self.get_state(fund_id)
        return {
            "fund_id": fund_id,
            "realized_pnl": s["realized_pnl"],
            "unrealized_pnl": s["unrealized_pnl"],
            "total_pnl": s["total_pnl"],
            "total_fees": s["total_fees"],
            "mode": "PAPER",
        }

    def get_exposure(self, fund_id: str) -> dict:
        s = self.get_state(fund_id)
        return {"fund_id": fund_id, **s["exposure"], "mode": "PAPER"}

    def list_events(self, fund_id: str) -> list[dict]:
        return [e.to_record() for e in self.store.list_events(fund_id)]

    def replay(self, fund_id: str) -> dict:
        """Rebuild state from events only (authority = ledger history)."""
        return self.get_state(fund_id)

    def snapshot(self, fund_id: str) -> dict:
        state = self.get_state(fund_id)
        h = state_hash(
            reduce_events(
                self.store.list_events(fund_id),
                fund_id=fund_id,
                currency=self.store.get_fund(fund_id).base_currency,
            )
        )
        snap_id = new_event_id("snap_")
        pub = {**state, "ts": _time.time(), "event_count": state["event_count"]}
        self.store.save_snapshot(snap_id, fund_id, pub, h)
        return ValuationSnapshot(
            snapshot_id=snap_id,
            fund_id=fund_id,
            ts=pub["ts"],
            nav=D(state["nav"]),
            cash=D(state["cash"]),
            positions_value=D(state["positions_value"]),
            realized_pnl=D(state["realized_pnl"]),
            unrealized_pnl=D(state["unrealized_pnl"]),
            event_count=int(state["event_count"]),
            state_hash=h,
        ).to_public()

    def reconcile(self, fund_id: str, oms_fills: list[dict] | None = None, expected_cash=None) -> dict:
        fund = self.store.get_fund(fund_id)
        if not fund:
            raise LedgerError(f"unknown fund: {fund_id}")
        events = self.store.list_events(fund_id)
        state = reduce_events(events, fund_id=fund_id, currency=fund.base_currency)
        report = reconcile_fills(
            fund_id=fund_id,
            ledger_events=events,
            oms_fills=oms_fills or [],
            state=state,
            expected_cash=D(expected_cash) if expected_cash is not None else None,
        )
        return report.to_public()

    def command_center_summary(self, fund_id: str) -> dict:
        """Payload shaped for Central Command investment snapshot (PAPER)."""
        s = self.get_state(fund_id)
        return {
            "mode": "PAPER",
            "live_execution": "UNAVAILABLE",
            "fund_id": fund_id,
            "equity": s["nav"],
            "paper_nav": s["nav"],
            "cash": s["cash"],
            "pnl": s["total_pnl"],
            "realized_pnl": s["realized_pnl"],
            "unrealized_pnl": s["unrealized_pnl"],
            "gross_exposure": s["exposure"]["gross"],
            "net_exposure": s["exposure"]["net"],
            "positions": s["positions"],
            "invariants_ok": s["invariants_ok"],
            "source": "canonical_fund_ledger",
            "engine_version": ENGINE_VERSION,
        }
