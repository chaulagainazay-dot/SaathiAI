"""M62.5 — PaperTradingService: server-authoritative paper-broker orchestration.

Permission-gated, tenant-scoped, audited. Owns the authoritative flow:

    OrderIntent → Trading Guardian veto → approval verification/consumption →
    cash/position reservation → durable PaperOrder → deterministic fills →
    (T-NEXT-1.1) canonical fund ledger post → books & records.

OMS owns order lifecycle and fill production.
PortfolioLedgerService owns cash/lots/P&L/NAV/exposure (books authority).
OMS avg-cost tables remain LEGACY_OMS_STATE_NOT_BOOKS_AUTHORITY for reservations
and compatibility only.

The MUTATION methods (:meth:`submit_order`, :meth:`cancel_order`,
:meth:`process_market_event`) are INTERNAL — they must be reached only through the
registered paper-trading tool under ExecutionGateway (see ``execution_tool.py`` /
``orchestration.py``). Read methods are safe for direct authenticated API use.

No live broker, no network, no credentials. PAPER environment only, long-only.
"""
from __future__ import annotations

import sqlite3
import time as _time
from decimal import Decimal
from pathlib import Path
from typing import Any

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformPermission, ApprovalStatus, new_id
from saathi.platform.trading_models import (
    D, Environment, OrderSide, OrderType, TimeInForce, DataQuality, MarketState,
    OrderIntent, OrderState, Account as TAccount, Position as TPosition,
)
from saathi.platform.trading_guardian import TradingGuardian, RiskLimits
from saathi.platform.paper_trading.models import (
    PaperAccount, PaperPosition, PaperOrder, PaperFill, AccountStatus, BrokerOrderState,
    FeeModel, SlippageModel, REALISTIC_FEE, REALISTIC_SLIP, assert_paper_safe, PaperSafetyError,
    can_account_transition, can_broker_transition, ENGINE_VERSION, q2, q6,
)
from saathi.platform.paper_trading.store import PaperStore, IdempotencyConflict
from saathi.platform.paper_trading.broker import PaperBroker, MarketEvent
from saathi.platform.fund_ledger.service import PortfolioLedgerService
from saathi.platform.fund_ledger.store import FundLedgerStore
from saathi.platform.fund_ledger.cutover import fund_id_for_account, DEFAULT_MARKER
from saathi.platform.fund_ledger.posting import (
    FillPostingStore, post_accepted_fill, retry_pending_posts, POST_POSTED, POST_DUPLICATE, POST_FAILED, POST_PENDING,
)
from saathi.platform.fund_ledger.view_adapter import LedgerPortfolioViewAdapter
from saathi.platform.fund_ledger.reducer import LedgerError

APPROVAL_NOTIONAL_THRESHOLD = Decimal("2500")   # orders at/above this need an approval
LEGACY_OMS_STATE_NOT_BOOKS_AUTHORITY = True


class PaperTradingService:
    def __init__(self, store: PaperStore | None = None, *, platform_store=None,
                 fee_model: FeeModel | None = None, slippage_model: SlippageModel | None = None,
                 guardian_limits: RiskLimits | None = None, seed: int = 0,
                 ledger: PortfolioLedgerService | None = None,
                 fill_posts: FillPostingStore | None = None,
                 auto_post_ledger: bool = True):
        assert_paper_safe()
        self.store = store or PaperStore()
        self._platform_store = platform_store
        self.fee_model = fee_model or REALISTIC_FEE
        self.slippage_model = slippage_model or REALISTIC_SLIP
        self._guardian_limits = guardian_limits
        self.broker = PaperBroker(fee_model=self.fee_model, slippage_model=self.slippage_model, seed=seed)
        self._audit_sink = None
        self._safety = None   # optional M62.7 SafetyService (breaker posture veto)
        self.auto_post_ledger = auto_post_ledger
        # Canonical books: separate SQLite next to paper OMS DB (or memory)
        if ledger is not None:
            self.ledger = ledger
        else:
            paper_path = getattr(self.store, "db_path", None)
            if paper_path is not None:
                lp = Path(str(paper_path))
                fund_path = lp.with_name(lp.stem + "_fund_ledger.db")
            else:
                fund_path = None
            self.ledger = PortfolioLedgerService(FundLedgerStore(fund_path))
        if fill_posts is not None:
            self.fill_posts = fill_posts
        else:
            paper_path = getattr(self.store, "db_path", None)
            if paper_path is not None:
                pp = Path(str(paper_path))
                self.fill_posts = FillPostingStore(pp.with_name(pp.stem + "_fill_posts.db"))
            else:
                self.fill_posts = FillPostingStore()
        self.cutover_marker = DEFAULT_MARKER.to_public()

    def bind_safety(self, safety_service):
        """Attach the M62.7 SafetyService so submissions consult breaker posture.
        Kept optional + injected to avoid a hard dependency / circular import."""
        self._safety = safety_service
        return self

    def bind_audit(self, platform_store):
        self._audit_sink = platform_store
        if self._platform_store is None:
            self._platform_store = platform_store
        return self

    def _audit(self, ctx, event, **detail):
        if not self._audit_sink:
            return
        try:
            self._audit_sink.append_audit(event, org_id=ctx.org_id, workspace_id=ctx.workspace_id,
                                          user_id=ctx.user_id, role=ctx.role, outcome=detail.pop("outcome", "ok"),
                                          detail=detail)
        except Exception:
            pass

    # ── accounts ────────────────────────────────────────────────────────────
    def create_account(self, ctx, *, name: str, starting_cash, base_currency="USD", project_id="",
                       config: dict | None = None) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_CREATE)
        assert_paper_safe(config, environment=Environment.PAPER)
        cash = D(starting_cash)
        if cash <= 0:
            raise PlatformContextError("VALIDATION_FAILED", "starting cash must be positive")
        acct = PaperAccount(id=new_id("pacc_"), org_id=ctx.org_id, workspace_id=ctx.workspace_id,
                            project_id=project_id, name=name or "paper account", base_currency=base_currency,
                            starting_cash=cash, current_cash=cash, status=AccountStatus.ACTIVE,
                            environment=Environment.PAPER, created_by=ctx.user_id)
        rec = self.store.create_account(acct)
        # T-NEXT-1.1: open canonical fund books (fresh fund; no historical OMS migration)
        fund_id = fund_id_for_account(acct.id)
        try:
            if not self.ledger.store.get_fund(fund_id):
                self.ledger.create_fund(
                    fund_id=fund_id,
                    name=f"paper:{acct.name}",
                    base_currency=base_currency,
                    opening_cash=cash,
                    actor=ctx.user_id or "system",
                )
            self.fill_posts.bind_account(acct.id, fund_id, org_id=ctx.org_id)
        except Exception as e:  # noqa: BLE001
            # Account exists; books open failure is visible and blocks healthy status
            self._audit(ctx, "paper.ledger.fund_open_failed", account_id=acct.id, error=str(e),
                        outcome="error")
            out = rec.to_public()
            out["fund_id"] = fund_id
            out["ledger_fund_open"] = "FAILED"
            out["portfolio_status"] = "RECONCILIATION_REQUIRED"
            out["legacy_oms_state_not_books_authority"] = LEGACY_OMS_STATE_NOT_BOOKS_AUTHORITY
            return out
        self._audit(ctx, "paper.account.created", account_id=acct.id, starting_cash=str(cash),
                    fund_id=fund_id)
        out = rec.to_public()
        out["fund_id"] = fund_id
        out["books_authority"] = "canonical_fund_ledger"
        out["legacy_oms_state_not_books_authority"] = LEGACY_OMS_STATE_NOT_BOOKS_AUTHORITY
        out["cutover"] = self.cutover_marker
        return out

    def get_account(self, ctx, account_id: str) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        acct = self._account_or_404(ctx, account_id)
        # OMS lifecycle fields (reservations) still from OMS store
        oms_positions = self.store.list_positions(ctx.org_id, account_id)
        reserved_by_symbol = {p.symbol: p.reserved_quantity for p in oms_positions}
        fund_id = self.fill_posts.fund_for_account(account_id) or fund_id_for_account(account_id)
        books = None
        try:
            if self.ledger.store.get_fund(fund_id):
                state = self.ledger.get_state(fund_id)
                books = LedgerPortfolioViewAdapter.from_ledger_state(
                    state,
                    account_id=account_id,
                    reserved_cash=acct.reserved_cash,
                    reserved_by_symbol=reserved_by_symbol,
                )
        except Exception:
            books = None

        recon = self.portfolio_reconciliation_status(ctx, account_id)
        if books:
            out = acct.to_public(
                unrealized_pnl=D(books["unrealized_pnl"]),
                positions_value=D(books["positions_value"]),
            )
            # Overlay canonical books fields
            out["cash"] = books["cash"]
            out["current_cash"] = books["cash"]  # books authority (OMS current_cash is lifecycle shadow)
            out["available_cash"] = books["available_cash"]
            out["realized_pnl"] = books["realized_pnl"]
            out["unrealized_pnl"] = books["unrealized_pnl"]
            out["nav"] = books["nav"]
            out["paper_nav"] = books["paper_nav"]
            out["equity"] = books["nav"]
            out["positions_value"] = books["positions_value"]
            out["exposure"] = books["exposure"]
            out["positions"] = books["positions"]
            out["open_lots"] = books["open_lots"]
            out["books_authority"] = "canonical_fund_ledger"
            out["source"] = "canonical_fund_ledger"
            out["mark_source"] = "canonical_fund_ledger_marks_or_cost"
        else:
            # Fallback only if fund missing — still mark non-canonical
            pv = sum((p.market_value(p.avg_cost) for p in oms_positions if p.quantity != 0), Decimal("0"))
            out = acct.to_public(unrealized_pnl=Decimal("0"), positions_value=pv)
            out["positions"] = [p.to_public(mark=p.avg_cost) for p in oms_positions if p.quantity != 0]
            out["books_authority"] = "UNAVAILABLE"
            out["mark_source"] = "oms_lifecycle_fallback"
        out["halt_reason"] = self.store.account_halt_reason(ctx.org_id, account_id)
        out["fund_id"] = fund_id
        out["legacy_oms_state_not_books_authority"] = LEGACY_OMS_STATE_NOT_BOOKS_AUTHORITY
        out["oms_lifecycle"] = {
            "reserved_cash": str(q2(acct.reserved_cash)),
            "oms_current_cash_shadow": str(q2(acct.current_cash)),
            "oms_realized_pnl_shadow": str(q2(acct.realized_pnl)),
            "note": "OMS cash/avg-cost shadows are not books authority after T-NEXT-1.1",
        }
        out["portfolio_status"] = recon.get("portfolio_status")
        out["reconciliation"] = recon
        out["mode"] = "PAPER"
        out["live_execution"] = "UNAVAILABLE"
        return out

    def list_accounts(self, ctx) -> list[dict]:
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        return [a.to_public() for a in self.store.list_accounts(ctx.org_id)]

    def halt_account(self, ctx, account_id: str, *, expected_version: int, reason: str = "manual halt") -> dict:
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_HALT)
        acct = self._account_or_404(ctx, account_id)
        if not can_account_transition(acct.status, AccountStatus.HALTED):
            raise PlatformContextError("VALIDATION_FAILED", f"cannot halt from {acct.status.value}")
        kind, rec = self.store.update_account_status(ctx.org_id, account_id, expected_version=expected_version,
                                                     status=AccountStatus.HALTED, halt_reason=reason)
        if kind == "conflict":
            raise PlatformContextError("STALE_STATE", "account version conflict")
        if kind == "not_found":
            raise PlatformContextError("NOT_FOUND", "account not found")
        self._audit(ctx, "paper.account.halted", account_id=account_id, reason=reason)
        return rec.to_public()

    def _account_or_404(self, ctx, account_id: str) -> PaperAccount:
        acct = self.store.get_account(ctx.org_id, account_id)
        if not acct:
            raise PlatformContextError("NOT_FOUND", "paper account not found for tenant")
        return acct

    # ── intents (proposal) ──────────────────────────────────────────────────
    def create_intent(self, ctx, *, account_id: str, symbol: str, side: str, order_type: str, quantity,
                      limit_price=None, time_in_force="DAY", idempotency_key: str = "", reason: str = "",
                      strategy_ref: str = "", thesis_ref: str = "", market_data_ref: str = "") -> dict:
        ctx.require_permission(PlatformPermission.PAPER_ORDER_PROPOSE)
        acct = self._account_or_404(ctx, account_id)
        try:
            side_e = OrderSide(side); type_e = OrderType(order_type); tif_e = TimeInForce(time_in_force)
        except ValueError as e:
            raise PlatformContextError("VALIDATION_FAILED", f"invalid enum: {e}") from e
        if type_e not in (OrderType.MARKET, OrderType.LIMIT):
            raise PlatformContextError("VALIDATION_FAILED", "only MARKET and LIMIT supported")
        if D(quantity) <= 0:
            raise PlatformContextError("VALIDATION_FAILED", "quantity must be positive")
        intent_id = new_id("pint_")
        corr = new_id("corr_")
        intent = OrderIntent(
            intent_id=intent_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, account_id=account_id,
            environment=Environment.PAPER, symbol=symbol, side=side_e, order_type=type_e, quantity=D(quantity),
            limit_price=D(limit_price) if limit_price is not None else None, time_in_force=tif_e,
            idempotency_key=idempotency_key or new_id("idem_"), strategy_id=strategy_ref,
            state=OrderState.APPROVAL_REQUIRED, audit_correlation_id=corr)
        rec = self.store.create_intent(intent_id=intent_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id,
                                       account_id=account_id, payload=intent.to_public(),
                                       state=OrderState.APPROVAL_REQUIRED.value, correlation_id=corr,
                                       idempotency_key=intent.idempotency_key, strategy_ref=strategy_ref,
                                       thesis_ref=thesis_ref, market_data_ref=market_data_ref,
                                       proposed_by=ctx.user_id, reason=reason)
        self._audit(ctx, "paper.intent.created", intent_id=intent_id, account_id=account_id, symbol=symbol)
        return rec

    def get_intent(self, ctx, intent_id: str) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_ORDER_READ)
        rec = self.store.get_intent(ctx.org_id, intent_id)
        if not rec:
            raise PlatformContextError("NOT_FOUND", "intent not found for tenant")
        return rec

    def list_intents(self, ctx, *, account_id=None) -> list[dict]:
        ctx.require_permission(PlatformPermission.PAPER_ORDER_READ)
        return self.store.list_intents(ctx.org_id, account_id=account_id)

    # ── the Guardian veto (independent, fail-closed) ────────────────────────
    def _guardian_review(self, acct: PaperAccount, intent: OrderIntent, event: MarketEvent) -> dict:
        """TG portfolio inputs: canonical ledger positions/cash when available.

        Reservations still subtract OMS reserved_cash so buy capacity stays fail-closed.
        TG is not redesigned — only the ownership snapshot source is canonicalized.
        """
        fund_id = self.fill_posts.fund_for_account(acct.id) or fund_id_for_account(acct.id)
        tpos: dict[str, TPosition] = {}
        cash_for_tg = acct.available_cash
        input_source = "oms_lifecycle"
        try:
            if self.ledger.store.get_fund(fund_id):
                state = self.ledger.get_state(fund_id)
                cash_for_tg = q2(D(state["cash"]) - acct.reserved_cash)
                if cash_for_tg < 0:
                    cash_for_tg = Decimal("0")
                for p in state.get("positions") or []:
                    if D(p.get("quantity") or 0) == 0:
                        continue
                    # reserved qty still OMS-side for sell capacity
                    oms_pos = self.store.get_position(acct.org_id, acct.id, p["symbol"])
                    qty = D(p["quantity"])
                    if oms_pos and oms_pos.reserved_quantity:
                        # expose free qty to TG as quantity (TG uses position.quantity)
                        qty = qty  # full open; broker validate still uses OMS available
                    tpos[p["symbol"]] = TPosition(
                        symbol=p["symbol"],
                        quantity=qty,
                        avg_price=D(p.get("avg_cost") or 0),
                        realized_pnl=D(p.get("realized_pnl") or 0),
                    )
                input_source = "canonical_fund_ledger"
        except Exception:
            positions = self.store.list_positions(acct.org_id, acct.id)
            tpos = {p.symbol: TPosition(symbol=p.symbol, quantity=p.quantity, avg_price=p.avg_cost,
                                        realized_pnl=p.realized_pnl) for p in positions if p.quantity != 0}
            cash_for_tg = acct.available_cash
            input_source = "oms_lifecycle_fallback"

        if not tpos and input_source != "canonical_fund_ledger":
            positions = self.store.list_positions(acct.org_id, acct.id)
            tpos = {p.symbol: TPosition(symbol=p.symbol, quantity=p.quantity, avg_price=p.avg_cost,
                                        realized_pnl=p.realized_pnl) for p in positions if p.quantity != 0}

        taccount = TAccount(account_id=acct.id, environment=Environment.PAPER, cash=cash_for_tg,
                            currency=acct.base_currency, positions=tpos)
        ref_price = D(event.ask) if intent.side == OrderSide.BUY else D(event.bid)
        guardian = TradingGuardian(limits=self._guardian_limits)
        decision = guardian.evaluate(intent, account=taccount, ref_price=ref_price,
                                     price_quality=event.quality, market_state=event.market_state,
                                     marks={intent.symbol: D(event.last)})
        pub = decision.to_public()
        pub["environment"] = "PAPER"
        pub["is_trade_approval"] = False
        pub["portfolio_input_source"] = input_source
        return pub

    # ── INTERNAL: submit (reached only via ExecutionGateway tool) ───────────
    def submit_order(self, ctx, *, intent_id: str, event: MarketEvent, approval_id: str = "",
                     _via_gateway: bool = False) -> dict:
        """Authorize + reserve + create a durable broker order. Guardian veto and
        approval consumption happen server-side, atomically with the order write."""
        ctx.require_permission(PlatformPermission.PAPER_ORDER_SUBMIT)
        rec = self.store.get_intent(ctx.org_id, intent_id)
        if not rec:
            raise PlatformContextError("NOT_FOUND", "intent not found for tenant")
        payload = rec["payload"]
        idem_key = rec["idempotency_key"]

        # idempotency: same key → return original order (restart/retry safe)
        existing = self.store.get_order_by_idempotency(ctx.org_id, idem_key)
        if existing:
            return {"order": existing.to_public(), "idempotent_replay": True}

        acct = self._account_or_404(ctx, rec["account_id"])
        if acct.environment != Environment.PAPER:
            raise PlatformContextError("VALIDATION_FAILED", "account not PAPER")
        if acct.status != AccountStatus.ACTIVE:
            raise PlatformContextError("VALIDATION_FAILED", f"account not ACTIVE ({acct.status.value})")

        intent = OrderIntent(
            intent_id=intent_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, account_id=acct.id,
            environment=Environment.PAPER, symbol=payload["symbol"], side=OrderSide(payload["side"]),
            order_type=OrderType(payload["order_type"]), quantity=D(payload["quantity"]),
            limit_price=D(payload["limit_price"]) if payload.get("limit_price") else None,
            time_in_force=TimeInForce(payload["time_in_force"]), idempotency_key=idem_key,
            approval_id=approval_id or "n/a", state=OrderState.APPROVAL_REQUIRED,
            audit_correlation_id=rec["correlation_id"])

        # 1) Guardian veto (independent, fail-closed) — persisted, immutable for this version
        guardian = self._guardian_review(acct, intent, event)
        if not guardian.get("allowed"):
            self.store.update_intent(ctx.org_id, intent_id, state=OrderState.REJECTED.value, guardian=guardian,
                                     reason="guardian veto: " + "; ".join(guardian.get("reasons", [])[:3]))
            self._audit(ctx, "paper.guardian.veto", intent_id=intent_id, reasons=guardian.get("reasons"))
            raise PlatformContextError("VALIDATION_FAILED", "guardian veto: " + "; ".join(guardian.get("reasons", [])[:3]))

        # 1b) M62.7 safety breaker posture (independent, fail-closed). Any active
        # blocking breaker relevant to this account/instrument/source vetoes submission.
        if self._safety is not None:
            try:
                posture = self._safety.breaker_posture(
                    ctx, account_id=acct.id, symbol=intent.symbol, source=event.ref,
                    workspace_id=ctx.workspace_id)
            except Exception:
                posture = {"blocked": True, "breakers": [{"breaker_type": "posture_unavailable"}]}  # fail closed
            if posture.get("blocked"):
                brk = posture.get("breakers", [])
                reason = "safety breaker veto: " + "; ".join(
                    f"{b.get('breaker_type', '?')}@{b.get('scope', '?')}:{b.get('scope_ref', '')}" for b in brk[:3])
                self.store.update_intent(ctx.org_id, intent_id, state=OrderState.REJECTED.value,
                                         guardian=guardian, reason=reason[:200])
                self._audit(ctx, "paper.safety.veto", intent_id=intent_id, breakers=brk)
                raise PlatformContextError("VALIDATION_FAILED", reason)

        # 2) reservation + broker validation
        ref_price = D(event.ask) if intent.side == OrderSide.BUY else D(event.bid)
        position = self.store.get_position(ctx.org_id, acct.id, intent.symbol)
        reserve_cost = Decimal("0")
        if intent.side == OrderSide.BUY:
            reserve_cost = self.broker.reserve_for_buy(quantity=intent.quantity, ref_price=ref_price,
                                                       limit_price=intent.limit_price, order_type=intent.order_type)
        val = self.broker.validate_new_order(account=acct, side=intent.side, order_type=intent.order_type,
                                             quantity=intent.quantity, limit_price=intent.limit_price,
                                             position=position, reserve_cost=reserve_cost, ref_price=ref_price)
        if not val.ok:
            self.store.update_intent(ctx.org_id, intent_id, state=OrderState.REJECTED.value, guardian=guardian,
                                     reason=val.reason)
            self._audit(ctx, "paper.order.rejected", intent_id=intent_id, reason=val.reason)
            raise PlatformContextError("VALIDATION_FAILED", val.reason)

        # 3) approval requirement (server-owned). Consumed atomically with the write.
        est_notional = q2(intent.quantity * ref_price)
        needs_approval = _via_gateway or est_notional >= APPROVAL_NOTIONAL_THRESHOLD
        consume_cb = None
        if needs_approval:
            self._verify_approval(ctx, approval_id, account_id=acct.id, est_notional=est_notional)
            consume_cb = self._make_consume_cb(ctx, approval_id)

        # 4) build durable order + apply reservation in memory
        now = _time.time()
        order = PaperOrder(
            id=new_id("pord_"), order_intent_id=intent_id, paper_account_id=acct.id, org_id=ctx.org_id,
            symbol=intent.symbol, side=intent.side, order_type=intent.order_type,
            original_quantity=intent.quantity, limit_price=intent.limit_price, time_in_force=intent.time_in_force,
            broker_state=BrokerOrderState.OPEN, idempotency_key=idem_key, market_data_ref=event.ref,
            correlation_id=rec["correlation_id"], submitted_at=now, accepted_at=now)
        ledger = None
        if intent.side == OrderSide.BUY:
            acct.reserved_cash = q2(acct.reserved_cash + reserve_cost)
            order.reserved_cash = reserve_cost
            ledger = ("reserve_cash", reserve_cost)
        else:
            position = position or PaperPosition(account_id=acct.id, symbol=intent.symbol)
            position.reserved_quantity = position.reserved_quantity + intent.quantity
            order.reserved_quantity = intent.quantity
        acct.version += 1

        idem_result = {"order": order.to_public(), "guardian": guardian}
        try:
            self.store.persist_submit(
                account=acct, position=(position if intent.side == OrderSide.SELL else None), order=order,
                intent_state=OrderState.SUBMITTED.value, guardian=guardian,
                transition=(BrokerOrderState.PENDING_VALIDATION.value, BrokerOrderState.OPEN.value, "accepted"),
                ledger=ledger, idem_scope="submit", idem_key=idem_key, idem_payload_hash=str(intent.quantity),
                idem_result=idem_result, consume_approval=consume_cb)
        except sqlite3.IntegrityError:
            existing = self.store.get_order_by_idempotency(ctx.org_id, idem_key)
            if existing:
                return {"order": existing.to_public(), "idempotent_replay": True}
            raise
        self._audit(ctx, "paper.order.submitted", order_id=order.id, intent_id=intent_id, symbol=order.symbol,
                    quantity=str(order.original_quantity), approval_id=approval_id)
        return {"order": order.to_public(), "guardian": guardian}

    # ── INTERNAL: process a market event (system) → deterministic fill ──────
    def process_market_event(self, ctx, *, order_id: str, event: MarketEvent) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_ORDER_SUBMIT)
        order = self.store.get_order(ctx.org_id, order_id)
        if not order:
            raise PlatformContextError("NOT_FOUND", "order not found for tenant")
        if order.is_terminal or order.broker_state == BrokerOrderState.CANCEL_PENDING:
            return {"filled": False, "reason": f"order {order.broker_state.value}", "order": order.to_public()}
        acct = self._account_or_404(ctx, order.paper_account_id)
        if acct.status != AccountStatus.ACTIVE:
            return {"filled": False, "reason": f"account {acct.status.value}", "order": order.to_public()}

        plan = self.broker.compute_fill(order=order, account=acct, event=event)
        if not plan.eligible:
            return {"filled": False, "reason": plan.reason, "order": order.to_public()}

        position = self.store.get_position(ctx.org_id, acct.id, order.symbol) or \
            PaperPosition(account_id=acct.id, symbol=order.symbol)
        f = plan.quantity
        prev_state = order.broker_state
        ledger_entries: list[tuple[str, Decimal, str]] = []

        if order.side == OrderSide.BUY:
            actual_out = q2(plan.gross_amount + plan.fee)
            acct.current_cash = q2(acct.current_cash - actual_out)
            release = q2(order.reserved_cash * (f / order.original_quantity)) if order.original_quantity > 0 else order.reserved_cash
            release = min(release, order.reserved_cash)
            order.reserved_cash = q2(order.reserved_cash - release)
            acct.reserved_cash = q2(acct.reserved_cash - release)
            new_qty = position.quantity + f
            position.avg_cost = q6((position.avg_cost * position.quantity + plan.gross_amount) / new_qty) if new_qty > 0 else Decimal("0")
            position.quantity = new_qty
            ledger_entries = [("buy", q2(-plan.gross_amount), "fill"), ("fee", q2(-plan.fee), "fill")]
        else:  # SELL (long reduction only)
            realized = q2((plan.price - position.avg_cost) * f)
            position.realized_pnl = q2(position.realized_pnl + realized)
            acct.realized_pnl = q2(acct.realized_pnl + realized)
            position.quantity = position.quantity - f
            position.reserved_quantity = position.reserved_quantity - f
            if position.quantity == 0:
                position.avg_cost = Decimal("0")
            net_in = q2(plan.gross_amount - plan.fee)
            acct.current_cash = q2(acct.current_cash + net_in)
            order.reserved_quantity = q2(order.reserved_quantity - f)
            ledger_entries = [("sell", q2(plan.gross_amount), "fill"), ("fee", q2(-plan.fee), "fill")]

        order.filled_quantity = order.filled_quantity + f
        fully = order.remaining_quantity <= 0
        order.broker_state = BrokerOrderState.FILLED if fully else BrokerOrderState.PARTIALLY_FILLED
        if fully:
            order.completed_at = _time.time()
            # release any residual reservation (rounding / slippage reserve)
            if order.side == OrderSide.BUY and order.reserved_cash > 0:
                acct.reserved_cash = q2(acct.reserved_cash - order.reserved_cash)
                order.reserved_cash = Decimal("0")
        order.version += 1
        acct.version += 1

        fill = PaperFill(id=new_id("pfill_"), paper_order_id=order.id, org_id=ctx.org_id, event_ts=event.ts,
                         quantity=f, price=plan.price, gross_amount=plan.gross_amount, fee=plan.fee,
                         slippage=plan.slippage_per_unit, side=order.side, liquidity_ref=event.ref,
                         market_data_ref=event.ref, fee_model_version=self.fee_model.version,
                         slippage_model_version=self.slippage_model.version, result_hash=plan.result_hash)

        applied = self.store.persist_fill(
            account=acct, position=position, order=order, fill=fill,
            transition=(prev_state.value, order.broker_state.value, "fill"),
            ledger_entries=ledger_entries, event_hash=event.event_hash())
        if not applied:
            # duplicate market event — OMS fill not re-inserted; retry any pending ledger posts
            cur = self.store.get_order(ctx.org_id, order_id)
            retried = []
            if self.auto_post_ledger:
                retried = retry_pending_posts(self.ledger, self.fill_posts, limit=20)
            return {
                "filled": False,
                "reason": "duplicate event (idempotent)",
                "order": cur.to_public(),
                "ledger_retry": retried,
            }
        if fully:
            self.store.update_intent(ctx.org_id, order.order_intent_id, state=OrderState.FILLED.value)
        else:
            self.store.update_intent(ctx.org_id, order.order_intent_id, state=OrderState.PARTIALLY_FILLED.value)

        # T-NEXT-1.1: automatic canonical ledger post after OMS fill commit
        ledger_post = None
        if self.auto_post_ledger:
            ledger_post = self._post_fill_to_canonical_ledger(acct, order, fill)
            # Optional mark at fill price for unrealized path
            try:
                fund_id = self.fill_posts.fund_for_account(acct.id) or fund_id_for_account(acct.id)
                if ledger_post and ledger_post.get("status") in (POST_POSTED, POST_DUPLICATE):
                    self.ledger.record_mark(
                        fund_id,
                        security_id=f"sec_{order.symbol.upper()}_PAPER",
                        price=plan.price,
                        symbol=order.symbol,
                        source="paper_fill_mark",
                        idempotency_key=f"mark:fill:{fill.id}",
                    )
            except Exception:
                pass

        self._audit(
            ctx,
            "paper.order.filled",
            order_id=order.id,
            quantity=str(f),
            price=str(plan.price),
            result_hash=plan.result_hash,
            fully=fully,
            fill_id=fill.id,
            ledger_event_id=(ledger_post or {}).get("ledger_event_id"),
            ledger_post_status=(ledger_post or {}).get("status"),
        )
        recon = self.portfolio_reconciliation_status(ctx, acct.id)
        return {
            "filled": True,
            "fill": fill.to_public(),
            "order": order.to_public(),
            "ledger_post": ledger_post,
            "portfolio_status": recon.get("portfolio_status"),
            "reconciliation": recon,
            "books_authority": "canonical_fund_ledger",
        }

    # ── INTERNAL: cancel (reached only via ExecutionGateway tool) ───────────
    def cancel_order(self, ctx, *, order_id: str, idempotency_key: str = "") -> dict:
        ctx.require_permission(PlatformPermission.PAPER_ORDER_CANCEL)
        order = self.store.get_order(ctx.org_id, order_id)
        if not order:
            raise PlatformContextError("NOT_FOUND", "order not found for tenant")
        if order.broker_state == BrokerOrderState.CANCELLED:
            return {"cancelled": True, "idempotent_replay": True, "order": order.to_public()}
        if order.is_terminal:
            raise PlatformContextError("VALIDATION_FAILED", f"cannot cancel {order.broker_state.value} order")
        acct = self._account_or_404(ctx, order.paper_account_id)
        position = self.store.get_position(ctx.org_id, acct.id, order.symbol)
        ledger = None
        if order.side == OrderSide.BUY and order.reserved_cash > 0:
            acct.reserved_cash = q2(acct.reserved_cash - order.reserved_cash)
            ledger = ("release_cash", order.reserved_cash)
            order.reserved_cash = Decimal("0")
        elif order.side == OrderSide.SELL and position is not None and order.reserved_quantity > 0:
            position.reserved_quantity = position.reserved_quantity - order.reserved_quantity
            order.reserved_quantity = Decimal("0")
        prev = order.broker_state
        order.broker_state = BrokerOrderState.CANCELLED
        order.cancelled_at = _time.time()
        order.version += 1
        acct.version += 1
        idem_result = {"cancelled": True, "order": order.to_public()}
        self.store.persist_cancel(
            account=acct, position=(position if order.side == OrderSide.SELL else None), order=order,
            transition=(prev.value, BrokerOrderState.CANCELLED.value, "cancel"), ledger=ledger,
            idem_scope="cancel", idem_key=idempotency_key, idem_payload_hash=order_id, idem_result=idem_result)
        # intent reflects partial-fill retention vs full cancel
        istate = OrderState.CANCELLED.value if order.filled_quantity == 0 else OrderState.PARTIALLY_FILLED.value
        self.store.update_intent(ctx.org_id, order.order_intent_id, state=istate)
        self._audit(ctx, "paper.order.cancelled", order_id=order.id, filled=str(order.filled_quantity))
        return idem_result

    # ── approval verification / consumption (server-owned) ──────────────────
    def _verify_approval(self, ctx, approval_id: str, *, account_id: str, est_notional: Decimal) -> None:
        if not approval_id:
            raise PlatformContextError("VALIDATION_FAILED", "approval required for this order")
        if not self._platform_store:
            raise PlatformContextError("VALIDATION_FAILED", "approval store unavailable (fail closed)")
        ap = self._platform_store.get_approval(approval_id)
        if not ap:
            raise PlatformContextError("NOT_FOUND", "approval not found")
        if ap.org_id != ctx.org_id:
            raise PlatformContextError("PERMISSION_DENIED", "cross-tenant approval rejected")
        if ap.status != ApprovalStatus.APPROVED.value:
            raise PlatformContextError("VALIDATION_FAILED", f"approval not usable ({ap.status})")
        if ap.expires_at and ap.expires_at < _time.time():
            raise PlatformContextError("VALIDATION_FAILED", "approval expired")
        # agents cannot approve their own order
        if ap.decided_by and ap.decided_by == ctx.user_id and ap.requested_by == ctx.requested_by():
            raise PlatformContextError("PERMISSION_DENIED", "self-approval prohibited")

    def _make_consume_cb(self, ctx, approval_id: str):
        org_id = ctx.org_id

        def _consume(cur: sqlite3.Cursor) -> bool:
            try:
                r = cur.execute(
                    "UPDATE approvals SET status=?, consumed_at=? WHERE approval_id=? AND status=? AND org_id=?",
                    (ApprovalStatus.CONSUMED.value, _time.time(), approval_id, ApprovalStatus.APPROVED.value, org_id))
                return r.rowcount == 1
            except sqlite3.OperationalError:
                return False
        return _consume

    # ── read: orders / fills / positions / ledger / summary ─────────────────
    def get_order(self, ctx, order_id: str) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_ORDER_READ)
        order = self.store.get_order(ctx.org_id, order_id)
        if not order:
            raise PlatformContextError("NOT_FOUND", "order not found for tenant")
        return {**order.to_public(), "transitions": self.store.list_transitions(ctx.org_id, order_id)}

    def list_orders(self, ctx, *, account_id=None, limit=200, offset=0) -> list[dict]:
        ctx.require_permission(PlatformPermission.PAPER_ORDER_READ)
        return [o.to_public() for o in self.store.list_orders(ctx.org_id, account_id=account_id,
                                                              limit=min(int(limit), 500), offset=int(offset))]

    def list_fills(self, ctx, order_id: str, *, limit=1000, offset=0) -> list[dict]:
        ctx.require_permission(PlatformPermission.PAPER_ORDER_READ)
        if not self.store.get_order(ctx.org_id, order_id):
            raise PlatformContextError("NOT_FOUND", "order not found for tenant")
        return self.store.list_fills(ctx.org_id, order_id, limit=min(int(limit), 1000), offset=int(offset))

    def list_positions(self, ctx, account_id: str) -> list[dict]:
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        acct = self._account_or_404(ctx, account_id)
        fund_id = self.fill_posts.fund_for_account(account_id) or fund_id_for_account(account_id)
        try:
            if self.ledger.store.get_fund(fund_id):
                state = self.ledger.get_state(fund_id)
                oms_positions = self.store.list_positions(ctx.org_id, account_id)
                reserved = {p.symbol: p.reserved_quantity for p in oms_positions}
                view = LedgerPortfolioViewAdapter.from_ledger_state(
                    state, account_id=account_id, reserved_cash=acct.reserved_cash, reserved_by_symbol=reserved
                )
                return view["positions"]
        except Exception:
            pass
        # OMS lifecycle fallback (not books authority)
        return [
            {**p.to_public(mark=p.avg_cost), "source": "oms_lifecycle_fallback",
             "legacy_oms_state_not_books_authority": True}
            for p in self.store.list_positions(ctx.org_id, account_id)
        ]

    def ledger(self, ctx, account_id: str, *, limit=500, offset=0) -> list[dict]:
        """OMS cash journal (lifecycle). Canonical events: list_canonical_events."""
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        self._account_or_404(ctx, account_id)
        rows = self.store.list_ledger(ctx.org_id, account_id, limit=min(int(limit), 1000), offset=int(offset))
        return [{**r, "authority": "OMS_LIFECYCLE_ONLY", "legacy_oms_state_not_books_authority": True} for r in rows]

    def list_canonical_events(self, ctx, account_id: str) -> list[dict]:
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        self._account_or_404(ctx, account_id)
        fund_id = self.fill_posts.fund_for_account(account_id) or fund_id_for_account(account_id)
        if not self.ledger.store.get_fund(fund_id):
            return []
        return self.ledger.list_events(fund_id)

    def summary(self, ctx, account_id: str) -> dict:
        acct_pub = self.get_account(ctx, account_id)
        acct_pub["open_orders"] = sum(1 for o in self.store.list_orders(ctx.org_id, account_id=account_id, limit=500)
                                      if not o.is_terminal)
        return acct_pub

    def command_center_snapshot(self, ctx, account_id: str) -> dict:
        """Runtime Command Center payload from canonical ledger (no manual injection)."""
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        self._account_or_404(ctx, account_id)
        fund_id = self.fill_posts.fund_for_account(account_id) or fund_id_for_account(account_id)
        recon = self.portfolio_reconciliation_status(ctx, account_id)
        if not self.ledger.store.get_fund(fund_id):
            return {
                "mode": "PAPER",
                "live_execution": "UNAVAILABLE",
                "source": "canonical_fund_ledger",
                "portfolio_status": "RECONCILIATION_REQUIRED",
                "error": "fund not open",
            }
        state = self.ledger.get_state(fund_id)
        snap = LedgerPortfolioViewAdapter.command_summary(state, recon=recon)
        snap["account_id"] = account_id
        return snap


    def risk_engine(self):
        """Lazy PortfolioRiskEngine bound to this paper service ledger."""
        if getattr(self, "_risk_engine", None) is None:
            from saathi.platform.portfolio_risk_engine.engine import PortfolioRiskEngine
            from saathi.platform.portfolio_risk_engine.history import NavHistoryStore
            from saathi.platform.fund_ledger.cutover import fund_id_for_account
            hist_path = None
            paper_path = getattr(self.store, "db_path", None)
            if paper_path is not None:
                from pathlib import Path as _P
                pp = _P(str(paper_path))
                hist_path = pp.with_name(pp.stem + "_risk_nav.db")
            eng = PortfolioRiskEngine(history=NavHistoryStore(hist_path))

            def _state(key: str):
                fid = key
                if not self.ledger.store.get_fund(fid):
                    fid = self.fill_posts.fund_for_account(key) or fund_id_for_account(key)
                return self.ledger.get_state(fid)

            def _recon(key: str):
                # account-scoped recon preferred
                try:
                    return self.portfolio_reconciliation_status(ctx=None, account_id=key)  # type: ignore
                except Exception:
                    pending = self.fill_posts.pending_count()
                    return {"ok": pending == 0, "portfolio_status": "HEALTHY" if pending == 0 else "RECONCILIATION_REQUIRED"}

            # recon needs ctx — bind simpler pending check
            def _recon2(key: str):
                pending = self.fill_posts.pending_count(key) if key.startswith("pacc_") else self.fill_posts.pending_count()
                # also fund pending
                return {
                    "ok": pending == 0,
                    "portfolio_status": "HEALTHY" if pending == 0 else "RECONCILIATION_REQUIRED",
                    "pending_ledger_posts": pending,
                }

            eng.bind_ledger(_state, _recon2)
            self._risk_engine = eng
        return self._risk_engine

    def paper_risk_snapshot(self, ctx, account_id: str) -> dict:
        """Command/agent-facing PAPER risk contract from independent engine."""
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        self._account_or_404(ctx, account_id)
        from saathi.platform.fund_ledger.cutover import fund_id_for_account
        fund_id = self.fill_posts.fund_for_account(account_id) or fund_id_for_account(account_id)
        eng = self.risk_engine()
        # prefer recon with real ctx
        recon = self.portfolio_reconciliation_status(ctx, account_id)
        state = self.ledger.get_state(fund_id) if self.ledger.store.get_fund(fund_id) else None
        if state is None:
            return {
                "label": "PAPER RISK",
                "mode": "PAPER",
                "live_execution": "UNAVAILABLE",
                "risk_status": "DATA_INSUFFICIENT",
                "error": "fund missing",
            }
        return eng.command_risk_contract(fund_id, ledger_state=state, recon=recon)

    def list_portfolio_proposals(self, ctx, account_id: str, *, limit: int = 10) -> dict:
        """Read-only proposal list for Hybrid Command. Never constructs or executes."""
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        self._account_or_404(ctx, account_id)
        from saathi.platform.fund_ledger.cutover import fund_id_for_account
        fund_id = self.fill_posts.fund_for_account(account_id) or fund_id_for_account(account_id)
        try:
            from saathi.platform.portfolio_construction.store import ProposalStore
        except Exception as e:
            return {
                "mode": "PAPER",
                "live_execution": "UNAVAILABLE",
                "authorizes_execution": False,
                "fund_id": fund_id,
                "proposals": [],
                "active": None,
                "provenance": "UNAVAILABLE",
                "error": f"construction module unavailable: {e}",
            }
        # Colocate proposal DB with paper store when path-backed
        store_path = ":memory:"
        paper_path = getattr(self.store, "db_path", None)
        if paper_path is not None:
            from pathlib import Path as _P
            pp = _P(str(paper_path))
            store_path = str(pp.with_name(pp.stem + "_proposals.db"))
        store = ProposalStore(store_path)
        items = store.list_for_fund(fund_id, limit=limit)
        active_raw = items[0] if items else None
        active = None
        if active_raw:
            active = {
                "id": active_raw.get("id") or active_raw.get("proposal_id"),
                "status": active_raw.get("status"),
                "created_at": active_raw.get("created_at"),
                "expires_at": active_raw.get("expires_at"),
                "source": active_raw.get("source"),
                "method": active_raw.get("method"),
                "current": active_raw.get("current"),
                "proposed": active_raw.get("proposed"),
                "delta": active_raw.get("delta"),
                "trades": active_raw.get("trades"),
                "projected_risk": active_raw.get("projected_risk"),
                "warnings": active_raw.get("warnings") or [],
                "reason_codes": active_raw.get("reason_codes") or [],
                "evidence_refs": active_raw.get("evidence_refs") or {},
                "approval_status": None,
                "authorizes_execution": False,
                "mode": "PAPER",
                "target_allocations": active_raw.get("target_allocations"),
                "turnover": active_raw.get("turnover"),
                "cash_weight": active_raw.get("cash_weight"),
            }
        return {
            "mode": "PAPER",
            "live_execution": "UNAVAILABLE",
            "authorizes_execution": False,
            "fund_id": fund_id,
            "proposals": items,
            "active": active,
            "provenance": "LIVE" if items else "UNAVAILABLE",
            "source": "portfolio_construction",
        }

    def _post_fill_to_canonical_ledger(self, acct: PaperAccount, order: PaperOrder, fill: PaperFill) -> dict:
        # Ensure bind exists (accounts created pre-cutover in tests still work)
        fund_id = self.fill_posts.fund_for_account(acct.id)
        if not fund_id:
            fund_id = fund_id_for_account(acct.id)
            if not self.ledger.store.get_fund(fund_id):
                try:
                    self.ledger.create_fund(
                        fund_id=fund_id,
                        name=f"paper:{acct.id}",
                        base_currency=acct.base_currency,
                        opening_cash=acct.starting_cash,
                        actor="cutover_lazy_open",
                    )
                except Exception:
                    pass
            self.fill_posts.bind_account(acct.id, fund_id, org_id=acct.org_id)
        side = order.side.value if hasattr(order.side, "value") else str(order.side)
        return post_accepted_fill(
            self.ledger,
            self.fill_posts,
            account_id=acct.id,
            fill_id=fill.id,
            order_id=order.id,
            side=side,
            symbol=order.symbol,
            quantity=fill.quantity,
            price=fill.price,
            fee=fill.fee,
            actor="paper_oms",
        )

    def retry_ledger_posts(self, ctx, *, limit: int = 50) -> dict:
        """Idempotent retry of PENDING/FAILED ledger posts after crash/degrade."""
        ctx.require_permission(PlatformPermission.PAPER_ORDER_SUBMIT)
        results = retry_pending_posts(self.ledger, self.fill_posts, limit=limit)
        return {
            "retried": len(results),
            "results": results,
            "pending_remaining": self.fill_posts.pending_count(),
        }

    def portfolio_reconciliation_status(self, ctx, account_id: str) -> dict:
        """OMS vs ledger gate — no silent repair."""
        self._account_or_404(ctx, account_id)
        fund_id = self.fill_posts.fund_for_account(account_id) or fund_id_for_account(account_id)
        pending = self.fill_posts.pending_count(account_id)
        issues = []
        ok = True
        if pending > 0:
            ok = False
            issues.append({"code": "LEDGER_POST_PENDING", "detail": f"{pending} fill(s) pending/failed ledger post"})

        norm = []
        for o in self.store.list_orders(ctx.org_id, account_id=account_id, limit=500):
            for f in self.store.list_fills(ctx.org_id, o.id, limit=1000):
                fid = f.get("id") if isinstance(f, dict) else None
                if fid:
                    norm.append(
                        {
                            "fill_id": fid,
                            "quantity": f.get("quantity"),
                            "price": f.get("price"),
                        }
                    )

        ledger_report = {"ok": True, "issues": []}
        if self.ledger.store.get_fund(fund_id):
            # When OMS fills exist, require matching ledger fills; empty OMS is fine for cash-only funds
            ledger_report = self.ledger.reconcile(fund_id, oms_fills=norm if norm else [])
            if not ledger_report.get("ok"):
                ok = False
                issues.extend(ledger_report.get("issues") or [])
        else:
            ok = False
            issues.append({"code": "FUND_MISSING", "detail": fund_id})

        status = "HEALTHY" if ok else "RECONCILIATION_REQUIRED"
        return {
            "fund_id": fund_id,
            "ok": ok,
            "portfolio_status": status,
            "pending_ledger_posts": pending,
            "issues": issues,
            "ledger_report": ledger_report,
            "mode": "PAPER",
            "legacy_oms_state_not_books_authority": LEGACY_OMS_STATE_NOT_BOOKS_AUTHORITY,
        }

    # ── invariant check (used by tests + future reconciliation) ─────────────
    def check_account_invariants(self, ctx, account_id: str, *, tol: Decimal = Decimal("0.01")) -> list[str]:
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        acct = self._account_or_404(ctx, account_id)
        errors: list[str] = []
        if acct.available_cash < -tol:
            errors.append(f"available cash negative: {acct.available_cash}")
        if acct.reserved_cash < -tol:
            errors.append(f"reserved cash negative: {acct.reserved_cash}")
        for p in self.store.list_positions(ctx.org_id, account_id):
            if p.quantity < -tol:
                errors.append(f"{p.symbol} position negative: {p.quantity}")
            if p.reserved_quantity < -tol:
                errors.append(f"{p.symbol} reserved position negative: {p.reserved_quantity}")
            # position reconciles to fills
            signed = Decimal("0")
            for o in self.store.list_orders(ctx.org_id, account_id=account_id, limit=500):
                if o.symbol != p.symbol:
                    continue
                for fl in self.store.list_fills(ctx.org_id, o.id):
                    signed += D(fl["quantity"]) if fl["side"] == "BUY" else -D(fl["quantity"])
            if abs(p.quantity - signed) > tol:
                errors.append(f"{p.symbol} qty {p.quantity} != fills {signed}")
        return errors
