"""Deterministic event reducer: ledger events → portfolio state (FIFO lots)."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import Decimal
from typing import Iterable

from saathi.platform.fund_ledger.money import D, q_money, q_price, q_qty
from saathi.platform.fund_ledger.models import (
    EventType,
    Exposure,
    LedgerEvent,
    Mark,
    PortfolioState,
    PositionLot,
    PositionView,
    new_event_id,
)


class LedgerError(ValueError):
    """Accounting rule violation (e.g. short, negative cash, unknown event)."""


class _Book:
    """Mutable reduction state (not the public API)."""

    def __init__(self, fund_id: str, currency: str = "USD", *, allow_negative_cash: bool = False):
        self.fund_id = fund_id
        self.currency = currency
        self.cash = Decimal("0")
        self.realized_pnl = Decimal("0")
        self.total_fees = Decimal("0")
        self.lots: list[PositionLot] = []  # FIFO open lots
        self.realized_by_security: dict[str, Decimal] = {}
        self.marks: dict[str, Mark] = {}
        self.symbols: dict[str, str] = {}  # security_id -> symbol
        self.event_count = 0
        self.last_event_id = ""
        self.allow_negative_cash = allow_negative_cash
        self.seen_event_ids: set[str] = set()
        self.seen_idempotency: set[str] = set()

    def apply(self, ev: LedgerEvent) -> None:
        if ev.event_id in self.seen_event_ids:
            return  # exact event already applied (replay-safe)
        key = ev.idempotency_key or ev.event_id
        if key in self.seen_idempotency:
            # duplicate logical fill — no-op, still mark event id
            self.seen_event_ids.add(ev.event_id)
            return
        self.seen_event_ids.add(ev.event_id)
        self.seen_idempotency.add(key)

        et = ev.event_type if isinstance(ev.event_type, EventType) else EventType(ev.event_type)
        if et == EventType.DEPOSIT:
            self._cash(ev.cash_delta if ev.cash_delta != 0 else D(ev.payload.get("amount", 0)), ev)
        elif et == EventType.WITHDRAWAL_SIM:
            amt = ev.cash_delta if ev.cash_delta != 0 else -abs(D(ev.payload.get("amount", 0)))
            if amt > 0:
                amt = -amt
            self._cash(amt, ev)
        elif et == EventType.BUY_FILL:
            self._buy(ev)
        elif et == EventType.SELL_FILL:
            self._sell(ev)
        elif et == EventType.FEE:
            fee = abs(D(ev.fee if ev.fee != 0 else ev.cash_delta or ev.payload.get("amount", 0)))
            self.total_fees = q_money(self.total_fees + fee)
            self._cash(-fee, ev)
        elif et == EventType.DIVIDEND:
            amt = ev.cash_delta if ev.cash_delta != 0 else D(ev.payload.get("amount", 0))
            self._cash(amt, ev)
        elif et == EventType.ADJUSTMENT:
            self._cash(ev.cash_delta, ev)
            if ev.reason:
                pass
        elif et == EventType.CORRECTION:
            # correction carries inverse cash/qty encoded in fields
            if ev.cash_delta != 0:
                self._cash(ev.cash_delta, ev)
            # lot-level correction: payload may include full re-apply instructions
            if ev.payload.get("rebuild_from_events"):
                raise LedgerError("rebuild corrections must be applied by service.replay, not inline")
        elif et == EventType.MARK:
            sid = ev.security_id or ev.payload.get("security_id") or ""
            if not sid:
                raise LedgerError("MARK requires security_id")
            self.marks[sid] = Mark(
                security_id=sid,
                price=q_price(ev.price if ev.price != 0 else ev.payload.get("price", 0)),
                ts=float(ev.ts),
                source=ev.source or "mark",
                max_age_seconds=float(ev.payload.get("max_age_seconds", 86400)),
            )
            if ev.symbol:
                self.symbols[sid] = ev.symbol
        else:
            raise LedgerError(f"unsupported event type: {et}")

        self.event_count += 1
        self.last_event_id = ev.event_id

    def _cash(self, delta: Decimal, ev: LedgerEvent) -> None:
        new_cash = q_money(self.cash + D(delta))
        if new_cash < 0 and not self.allow_negative_cash:
            raise LedgerError(f"negative cash forbidden: {new_cash} after {ev.event_type}")
        self.cash = new_cash

    def _buy(self, ev: LedgerEvent) -> None:
        qty = q_qty(ev.quantity)
        px = q_price(ev.price)
        fee = q_money(ev.fee)
        if qty <= 0 or px < 0:
            raise LedgerError("BUY requires positive quantity and non-negative price")
        notional = q_money(qty * px)
        cash_out = q_money(notional + fee)
        self._cash(-cash_out, ev)
        self.total_fees = q_money(self.total_fees + fee)
        sid = ev.security_id or ev.symbol
        sym = ev.symbol or sid
        self.symbols[sid] = sym
        # cost price includes fee allocation into lot cost (per share)
        fee_ps = q_price(fee / qty) if qty else Decimal("0")
        cost = q_price(px + fee_ps)
        # Stable lot_id from fill/event identity so replay yields identical state.
        lot_id = f"lot_{ev.fill_ref or ev.event_id}"
        lot = PositionLot(
            lot_id=lot_id,
            security_id=sid,
            symbol=sym,
            quantity_open=qty,
            quantity_original=qty,
            cost_price=cost,
            opened_ts=float(ev.ts),
            fill_ref=ev.fill_ref or ev.event_id,
            fees_allocated=fee,
            currency=ev.currency or self.currency,
        )
        self.lots.append(lot)

    def _sell(self, ev: LedgerEvent) -> None:
        qty = q_qty(ev.quantity)
        px = q_price(ev.price)
        fee = q_money(ev.fee)
        if qty <= 0 or px < 0:
            raise LedgerError("SELL requires positive quantity and non-negative price")
        sid = ev.security_id or ev.symbol
        open_qty = sum((l.quantity_open for l in self.lots if l.security_id == sid), Decimal("0"))
        if qty > open_qty:
            raise LedgerError(f"SELL {qty} exceeds open {open_qty} for {sid} (shorts disabled)")
        remaining = qty
        realized = Decimal("0")
        # FIFO
        for lot in self.lots:
            if remaining <= 0:
                break
            if lot.security_id != sid or lot.quantity_open <= 0:
                continue
            take = min(lot.quantity_open, remaining)
            realized += q_money((px - lot.cost_price) * take)
            lot.quantity_open = q_qty(lot.quantity_open - take)
            remaining = q_qty(remaining - take)
        # proceeds - fee
        proceeds = q_money(qty * px - fee)
        self._cash(proceeds, ev)
        self.total_fees = q_money(self.total_fees + fee)
        self.realized_pnl = q_money(self.realized_pnl + realized)
        self.realized_by_security[sid] = q_money(
            self.realized_by_security.get(sid, Decimal("0")) + realized
        )
        if ev.symbol:
            self.symbols[sid] = ev.symbol

    def to_state(self, *, now: float | None = None) -> PortfolioState:
        # aggregate positions
        by_sid: dict[str, list[PositionLot]] = {}
        for lot in self.lots:
            if lot.quantity_open <= 0:
                continue
            by_sid.setdefault(lot.security_id, []).append(lot)

        positions: list[PositionView] = []
        positions_value = Decimal("0")
        unrealized = Decimal("0")
        long_exp = Decimal("0")

        for sid, lots in sorted(by_sid.items()):
            qty = q_qty(sum((l.quantity_open for l in lots), Decimal("0")))
            cost_basis = q_money(sum((l.quantity_open * l.cost_price for l in lots), Decimal("0")))
            avg_cost = q_price(cost_basis / qty) if qty else Decimal("0")
            mark = self.marks.get(sid)
            stale = bool(mark and mark.is_stale(now))
            if mark and not stale:
                mpx = mark.price
            elif mark and stale:
                # stale: still compute but flag — do not invent fresher price
                mpx = mark.price
            else:
                mpx = avg_cost  # no mark: use cost (unrealized 0)
            mv = q_money(qty * mpx)
            upnl = q_money(mv - cost_basis)
            positions_value = q_money(positions_value + mv)
            unrealized = q_money(unrealized + upnl)
            long_exp = q_money(long_exp + mv)
            positions.append(
                PositionView(
                    security_id=sid,
                    symbol=self.symbols.get(sid, lots[0].symbol),
                    quantity=qty,
                    avg_cost=avg_cost,
                    cost_basis=cost_basis,
                    market_value=mv,
                    unrealized_pnl=upnl,
                    realized_pnl=q_money(self.realized_by_security.get(sid, Decimal("0"))),
                    mark=mark,
                    mark_stale=stale,
                )
            )

        nav = q_money(self.cash + positions_value)
        # weights
        for p in positions:
            p.weight = q_money(p.market_value / nav) if nav != 0 else Decimal("0")

        cash_weight = q_money(self.cash / nav) if nav != 0 else Decimal("0")
        exposure = Exposure(
            gross=long_exp,  # long-only: gross == long
            net=long_exp,
            long=long_exp,
            short=Decimal("0"),
            cash_weight=cash_weight,
            currency=self.currency,
        )

        state = PortfolioState(
            fund_id=self.fund_id,
            currency=self.currency,
            cash=q_money(self.cash),
            realized_pnl=q_money(self.realized_pnl),
            unrealized_pnl=unrealized,
            total_fees=q_money(self.total_fees),
            positions_value=positions_value,
            nav=nav,
            positions=positions,
            open_lots=[deepcopy(l) for l in self.lots if l.quantity_open > 0],
            exposure=exposure,
            event_count=self.event_count,
            last_event_id=self.last_event_id,
            marks=dict(self.marks),
            invariants=[],
            mode="PAPER",
        )
        state.invariants = check_invariants(state, self)
        return state


def check_invariants(state: PortfolioState, book: _Book | None = None) -> list[str]:
    errors: list[str] = []
    # NAV = cash + positions_value
    recomputed = q_money(state.cash + state.positions_value)
    if recomputed != state.nav:
        errors.append(f"nav_mismatch nav={state.nav} cash+pv={recomputed}")
    # position qty = sum open lots
    lot_qty: dict[str, Decimal] = {}
    for lot in state.open_lots:
        lot_qty[lot.security_id] = q_qty(lot_qty.get(lot.security_id, Decimal("0")) + lot.quantity_open)
    for p in state.positions:
        lq = lot_qty.get(p.security_id, Decimal("0"))
        if q_qty(p.quantity) != q_qty(lq):
            errors.append(f"lot_qty_mismatch {p.security_id} pos={p.quantity} lots={lq}")
        if p.quantity < 0:
            errors.append(f"negative_position {p.security_id}")
    if state.cash < 0:
        errors.append(f"negative_cash {state.cash}")
    if state.exposure.short != 0:
        errors.append("shorts_not_zero")
    return errors


def reduce_events(
    events: Iterable[LedgerEvent],
    *,
    fund_id: str,
    currency: str = "USD",
    allow_negative_cash: bool = False,
    now: float | None = None,
) -> PortfolioState:
    book = _Book(fund_id, currency, allow_negative_cash=allow_negative_cash)
    for ev in events:
        if ev.fund_id and ev.fund_id != fund_id:
            raise LedgerError(f"event fund mismatch {ev.fund_id} != {fund_id}")
        book.apply(ev)
    return book.to_state(now=now)


def state_hash(state: PortfolioState) -> str:
    payload = state.to_public()
    # drop non-deterministic noise
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
